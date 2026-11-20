"""
Local Data Loss Prevention (DLP) & Secret/PII Redaction Service (Issue #77).

Zero external dependencies — uses Python stdlib ``re`` + Luhn checksum validation
to detect and redact API keys, private keys, tokens, emails, phone numbers, SSNs,
Luhn-valid credit cards, and user-defined custom regex rules before prompts leave
the machine to non-loopback cloud providers.

Policy JSON is persisted at ``VESPER_DLP_POLICY_PATH`` (default
``~/.contextuai-solo/data/dlp_policy.json``), with environment overrides
``VESPER_DLP_ENABLED`` (default ``true``) and ``VESPER_DLP_REDACT_LOGS``
(default ``false``).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

logger = logging.getLogger(__name__)

BUILTIN_CATEGORIES: Tuple[str, ...] = (
    "api_keys",
    "emails",
    "phones",
    "ssns",
    "credit_cards",
    "custom",
)

DEFAULT_CATEGORIES: Dict[str, bool] = {cat: True for cat in BUILTIN_CATEGORIES}

_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}

_IGNORED_SECRET_VALUES = {
    "none",
    "null",
    "true",
    "false",
    "undefined",
    "changeme",
    "placeholder",
    "your_api_key",
    "your-api-key",
    "your_secret",
    "your-secret",
    "example",
    "redacted",
}

_policy_lock = threading.RLock()
# Cache tuple: (policy_path_str, mtime_ns_or_None, stored_policy_dict)
_policy_cache: Optional[Tuple[str, Optional[int], Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DlpResult:
    """Result of scanning and redacting a text string.

    Never stores raw matched secrets or PII values — only counts and categories.
    """

    redacted_text: str
    total_redactions: int = 0
    categories: List[str] = field(default_factory=list)
    counts_by_category: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "redacted_text": self.redacted_text,
            "total_redactions": self.total_redactions,
            "categories": list(self.categories),
            "counts_by_category": dict(self.counts_by_category),
        }

    def to_summary(self) -> Dict[str, Any]:
        return {
            "total_redactions": self.total_redactions,
            "total": self.total_redactions,
            "categories": list(self.categories),
            "counts_by_category": dict(self.counts_by_category),
        }

    def __getitem__(self, key: str) -> Any:
        if key == "redacted_text":
            return self.redacted_text
        if key == "total_redactions":
            return self.total_redactions
        if key == "categories":
            return self.categories
        if key == "counts_by_category":
            return self.counts_by_category
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


# ---------------------------------------------------------------------------
# Policy persistence & environment overrides
# ---------------------------------------------------------------------------

def _parse_env_bool(env_name: str) -> Optional[bool]:
    raw = os.environ.get(env_name)
    if raw is None:
        return None
    val = raw.strip().lower()
    if not val:
        return None
    if val in _TRUE_ENV_VALUES:
        return True
    if val in _FALSE_ENV_VALUES:
        return False
    return None


def _get_policy_path() -> Path:
    override = (os.environ.get("VESPER_DLP_POLICY_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".contextuai-solo" / "data" / "dlp_policy.json"


def _default_stored_policy() -> Dict[str, Any]:
    return {
        "enabled": True,
        "redact_logs": False,
        "categories": dict(DEFAULT_CATEGORIES),
        "custom_rules": [],
    }


def _validate_and_normalize_rules(raw_rules: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_rules, list):
        raise ValueError("custom_rules must be a list")

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            raise ValueError(f"Custom rule at index {idx} must be an object")

        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError(f"Custom rule at index {idx} requires a non-empty name")

        pattern = item.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"Custom rule '{name}' requires a non-empty regex pattern")

        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern for rule '{name}': {exc}") from exc

        rule_id = str(item.get("id") or "").strip() or f"rule-{uuid.uuid4().hex[:8]}"
        placeholder = str(item.get("placeholder") or "").strip() or "[REDACTED:CUSTOM]"
        enabled = bool(item.get("enabled", True))

        normalized.append(
            {
                "id": rule_id,
                "name": name,
                "pattern": pattern,
                "placeholder": placeholder,
                "enabled": enabled,
            }
        )
    return normalized


def _normalize_policy_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = _default_stored_policy()
    if "enabled" in raw and raw["enabled"] is not None:
        base["enabled"] = bool(raw["enabled"])
    if "redact_logs" in raw and raw["redact_logs"] is not None:
        base["redact_logs"] = bool(raw["redact_logs"])

    raw_cats = raw.get("categories")
    if isinstance(raw_cats, dict):
        for cat in BUILTIN_CATEGORIES:
            if cat in raw_cats and raw_cats[cat] is not None:
                base["categories"][cat] = bool(raw_cats[cat])

    raw_rules = raw.get("custom_rules")
    if raw_rules is None and isinstance(raw.get("custom"), list):
        raw_rules = raw.get("custom")
    if raw_rules is not None:
        base["custom_rules"] = _validate_and_normalize_rules(raw_rules)

    return base


def _load_stored_policy() -> Dict[str, Any]:
    global _policy_cache
    path = _get_policy_path()
    path_str = str(path)

    with _policy_lock:
        try:
            mtime_ns: Optional[int] = path.stat().st_mtime_ns
        except FileNotFoundError:
            mtime_ns = None
        except OSError:
            mtime_ns = None

        if _policy_cache is not None:
            cached_path, cached_mtime, cached_data = _policy_cache
            if cached_path == path_str and cached_mtime == mtime_ns:
                return copy.deepcopy(cached_data)

        stored = _default_stored_policy()
        if mtime_ns is not None:
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    stored = _normalize_policy_dict(loaded)
            except ValueError as exc:
                logger.warning("Ignoring invalid custom rule in %s: %s", path_str, exc)
            except Exception as exc:
                logger.warning("Failed to read DLP policy from %s: %s", path_str, exc)

        _policy_cache = (path_str, mtime_ns, copy.deepcopy(stored))
        return stored


def get_dlp_settings() -> Dict[str, Any]:
    """Return effective DLP settings (persisted policy + env overrides)."""
    stored = _load_stored_policy()

    env_enabled = _parse_env_bool("VESPER_DLP_ENABLED")
    if env_enabled is not None:
        stored["enabled"] = env_enabled

    env_redact_logs = _parse_env_bool("VESPER_DLP_REDACT_LOGS")
    if env_redact_logs is not None:
        stored["redact_logs"] = env_redact_logs

    stored["policy_path"] = str(_get_policy_path())
    return stored


def update_dlp_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Validate, merge, and persist DLP policy settings to disk."""
    global _policy_cache
    if not isinstance(patch, dict):
        raise ValueError("DLP settings patch must be a JSON object")

    path = _get_policy_path()

    with _policy_lock:
        current = _load_stored_policy()

        if "enabled" in patch and patch["enabled"] is not None:
            current["enabled"] = bool(patch["enabled"])
        if "redact_logs" in patch and patch["redact_logs"] is not None:
            current["redact_logs"] = bool(patch["redact_logs"])

        if "categories" in patch and patch["categories"] is not None:
            if not isinstance(patch["categories"], dict):
                raise ValueError("categories must be an object")
            for cat, val in patch["categories"].items():
                if cat in DEFAULT_CATEGORIES and val is not None:
                    current["categories"][cat] = bool(val)

        if "custom_rules" in patch and patch["custom_rules"] is not None:
            current["custom_rules"] = _validate_and_normalize_rules(patch["custom_rules"])
        elif "custom" in patch and isinstance(patch["custom"], list):
            current["custom_rules"] = _validate_and_normalize_rules(patch["custom"])

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        _policy_cache = None

    return get_dlp_settings()


# ---------------------------------------------------------------------------
# Built-in regex patterns & validators
# ---------------------------------------------------------------------------

_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_ANTHROPIC_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])sk-ant-[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])"
)
_OPENAI_PREFIXED_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])sk-(?:proj|svcacct|live|test)-[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])"
)
_OPENAI_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])"
)
_AWS_ACCESS_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])"
)
_GITHUB_CLASSIC_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{16,}(?![A-Za-z0-9_])"
)
_GITHUB_PAT_RE = re.compile(
    r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{16,}(?![A-Za-z0-9_])"
)
_SLACK_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9-])"
)
_GOOGLE_API_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])"
)

_AUTH_BEARER_RE = re.compile(
    r"(?i)Authorization\s*:\s*Bearer\s+([A-Za-z0-9._~+/=-]{8,})"
)
_BEARER_SYMBOLIC_RE = re.compile(
    r"(?<![A-Za-z0-9_-])Bearer\s+(?=[A-Za-z0-9._~+/=-]*[0-9._~+/=-])([A-Za-z0-9._~+/=-]{10,})(?![A-Za-z0-9._~+/=-])"
)
_BEARER_LONG_RE = re.compile(
    r"(?<![A-Za-z0-9_-])Bearer\s+([A-Za-z0-9._~+/=-]{20,})(?![A-Za-z0-9._~+/=-])"
)

_SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?i)\b(?:api_?key|access_?token|auth_?token|bearer_?token|secret_?key|client_?secret|private_?key|aws_secret_access_key|secret|token|password|passwd)\b\s*[:=]\s*(?:(["'])([^\s"']{8,})\1|([A-Za-z0-9._~+/!@#$%^&*=-]{7,}[A-Za-z0-9_~+/!@#$%^&*=-])(?!\s*\())"""
)

_JWT_VALUE_RE = re.compile(
    r"^eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*$"
)

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

_SSN_RE = re.compile(
    r"(?<![A-Za-z0-9-])\d{3}-\d{2}-\d{4}(?![A-Za-z0-9-])"
)

_CREDIT_CARD_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:\d[ -]?){12,18}\d(?![A-Za-z0-9-])"
)

_PHONE_INTL_RE = re.compile(
    r"(?<![A-Za-z0-9+])\+[1-9]\d{0,2}[\s.-]?(?:\(?\d{1,4}\)?[\s.-]?){1,5}\d{1,5}(?![A-Za-z0-9-])"
)
_PHONE_NANP_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:1[\s.-])?(?:\(\d{3}\)[\s.-]?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![A-Za-z0-9-])"
)


def _luhn_valid(digits: str) -> bool:
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        val = ord(ch) - 48
        if idx % 2 == 1:
            val *= 2
            if val > 9:
                val -= 9
        total += val
    return total % 10 == 0


def _is_valid_credit_card(raw: str) -> bool:
    seps = {ch for ch in raw if ch in (" ", "-")}
    # Avoid matching unrelated numbers joined by mixed separators
    if len(seps) > 1:
        return False
    digits = raw.replace(" ", "").replace("-", "")
    if not (13 <= len(digits) <= 19):
        return False
    if set(digits) == {"0"}:
        return False
    return _luhn_valid(digits)


def _is_valid_phone(raw: str) -> bool:
    if ("(" in raw) != (")" in raw):
        return False
    if raw.count("(") > 1 or raw.count(")") > 1:
        return False
    digits = [ch for ch in raw if ch.isdigit()]
    if raw.startswith("+"):
        return 7 <= len(digits) <= 15
    if len(digits) == 10:
        return True
    if len(digits) == 11 and digits[0] == "1":
        return True
    return False


def _is_valid_secret_value(val: str) -> bool:
    if not val or val.startswith(("[REDACTED", "<", "${", "***")):
        return False
    low = val.lower()
    if low in _IGNORED_SECRET_VALUES:
        return False
    # Ignore attribute references like self.config.api_key when lacking digits and not a JWT
    if "." in val and not any(ch.isdigit() for ch in val) and not _JWT_VALUE_RE.match(val):
        return False
    return True


def _collect_regex_spans(
    text: str,
    pattern: Pattern[str],
    category: str,
    placeholder: str,
    accepted: List[Tuple[int, int, str, str]],
    *,
    group: int = 0,
    validator: Optional[Callable[[str], bool]] = None,
) -> None:
    for match in pattern.finditer(text):
        start, end = match.span(group)
        if start < 0 or end <= start:
            continue
        matched_val = match.group(group)
        if validator is not None and not validator(matched_val):
            continue
        if any(not (end <= s or start >= e) for s, e, _, _ in accepted):
            continue
        accepted.append((start, end, category, placeholder))


# ---------------------------------------------------------------------------
# Public scanning & message redaction API
# ---------------------------------------------------------------------------

def scan_and_redact(
    text: str,
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> DlpResult:
    """Scan ``text`` for enabled DLP categories and return a ``DlpResult``."""
    if not text:
        return DlpResult(redacted_text=text or "", total_redactions=0, categories=[], counts_by_category={})

    effective = _normalize_policy_dict(policy) if policy is not None else get_dlp_settings()
    if not effective.get("enabled", True):
        return DlpResult(redacted_text=text, total_redactions=0, categories=[], counts_by_category={})

    categories_cfg = effective.get("categories") or DEFAULT_CATEGORIES
    custom_rules = effective.get("custom_rules") or []

    accepted: List[Tuple[int, int, str, str]] = []

    # 1. API keys & secrets (most specific first to avoid partial/double matches)
    if categories_cfg.get("api_keys", True):
        _collect_regex_spans(text, _PEM_PRIVATE_KEY_RE, "api_keys", "[REDACTED:PRIVATE_KEY]", accepted)
        _collect_regex_spans(text, _ANTHROPIC_KEY_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _OPENAI_PREFIXED_KEY_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _OPENAI_KEY_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _AWS_ACCESS_KEY_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _GITHUB_PAT_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _GITHUB_CLASSIC_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _SLACK_TOKEN_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(text, _GOOGLE_API_KEY_RE, "api_keys", "[REDACTED:API_KEY]", accepted)
        _collect_regex_spans(
            text, _AUTH_BEARER_RE, "api_keys", "[REDACTED:API_KEY]", accepted,
            group=1, validator=_is_valid_secret_value,
        )
        _collect_regex_spans(
            text, _BEARER_SYMBOLIC_RE, "api_keys", "[REDACTED:API_KEY]", accepted,
            group=1, validator=_is_valid_secret_value,
        )
        _collect_regex_spans(
            text, _BEARER_LONG_RE, "api_keys", "[REDACTED:API_KEY]", accepted,
            group=1, validator=_is_valid_secret_value,
        )
        for match in _SECRET_ASSIGNMENT_RE.finditer(text):
            grp = 2 if match.group(2) is not None else 3
            start, end = match.span(grp)
            if start < 0 or end <= start:
                continue
            val = match.group(grp)
            if not _is_valid_secret_value(val):
                continue
            if any(not (end <= s or start >= e) for s, e, _, _ in accepted):
                continue
            accepted.append((start, end, "api_keys", "[REDACTED:API_KEY]"))

    # 2. Credit cards (before phones so 16-digit cards are never misclassified as phones)
    if categories_cfg.get("credit_cards", True):
        _collect_regex_spans(
            text, _CREDIT_CARD_RE, "credit_cards", "[REDACTED:CREDIT_CARD]", accepted,
            validator=_is_valid_credit_card,
        )

    # 3. SSNs (before phones)
    if categories_cfg.get("ssns", True):
        _collect_regex_spans(text, _SSN_RE, "ssns", "[REDACTED:SSN]", accepted)

    # 4. Emails
    if categories_cfg.get("emails", True):
        _collect_regex_spans(text, _EMAIL_RE, "emails", "[REDACTED:EMAIL]", accepted)

    # 5. Phones
    if categories_cfg.get("phones", True):
        _collect_regex_spans(
            text, _PHONE_INTL_RE, "phones", "[REDACTED:PHONE]", accepted,
            validator=_is_valid_phone,
        )
        _collect_regex_spans(
            text, _PHONE_NANP_RE, "phones", "[REDACTED:PHONE]", accepted,
            validator=_is_valid_phone,
        )

    # 6. Custom regex rules
    if categories_cfg.get("custom", True) and custom_rules:
        for rule in custom_rules:
            if not rule.get("enabled", True):
                continue
            compiled = re.compile(rule["pattern"])
            placeholder = rule.get("placeholder") or "[REDACTED:CUSTOM]"
            _collect_regex_spans(text, compiled, "custom", placeholder, accepted)

    if not accepted:
        return DlpResult(redacted_text=text, total_redactions=0, categories=[], counts_by_category={})

    accepted.sort(key=lambda item: (item[0], item[1]))
    parts: List[str] = []
    cursor = 0
    counts: Dict[str, int] = {}

    for start, end, category, placeholder in accepted:
        if start < cursor:
            continue
        parts.append(text[cursor:start])
        parts.append(placeholder)
        cursor = end
        counts[category] = counts.get(category, 0) + 1

    parts.append(text[cursor:])
    redacted_text = "".join(parts)
    total = sum(counts.values())
    categories = sorted(counts.keys())

    return DlpResult(
        redacted_text=redacted_text,
        total_redactions=total,
        categories=categories,
        counts_by_category=counts,
    )


def redact_messages(
    messages: List[Dict[str, Any]],
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Redact sensitive data across a list of chat messages without mutating input.

    Supports both plain string ``content`` and multimodal list-of-parts ``content``.
    Returns ``(redacted_messages, summary)`` where ``summary`` contains only
    ``total_redactions``, ``total``, ``categories``, and ``counts_by_category``.
    """
    effective = _normalize_policy_dict(policy) if policy is not None else get_dlp_settings()
    cloned: List[Dict[str, Any]] = copy.deepcopy(messages)

    if not effective.get("enabled", True):
        return cloned, {
            "total_redactions": 0,
            "total": 0,
            "categories": [],
            "counts_by_category": {},
        }

    counts_by_category: Dict[str, int] = {}

    def _merge(res: DlpResult) -> None:
        for cat, cnt in res.counts_by_category.items():
            counts_by_category[cat] = counts_by_category.get(cat, 0) + cnt

    for msg in cloned:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            res = scan_and_redact(content, policy=effective)
            if res.total_redactions > 0:
                msg["content"] = res.redacted_text
                _merge(res)
        elif isinstance(content, list):
            new_parts: List[Any] = []
            for part in content:
                if isinstance(part, str):
                    res = scan_and_redact(part, policy=effective)
                    if res.total_redactions > 0:
                        _merge(res)
                    new_parts.append(res.redacted_text)
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    res = scan_and_redact(part["text"], policy=effective)
                    if res.total_redactions > 0:
                        part = {**part, "text": res.redacted_text}
                        _merge(res)
                    new_parts.append(part)
                else:
                    new_parts.append(part)
            msg["content"] = new_parts

    total = sum(counts_by_category.values())
    summary = {
        "total_redactions": total,
        "total": total,
        "categories": sorted(counts_by_category.keys()),
        "counts_by_category": counts_by_category,
    }
    return cloned, summary


# ---------------------------------------------------------------------------
# Logging filter
# ---------------------------------------------------------------------------

class DlpLogFilter(logging.Filter):
    """Python ``logging.Filter`` that scrubs secrets/PII from log records when enabled."""

    def __init__(self, name: str = "", *, force: Optional[bool] = None) -> None:
        super().__init__(name)
        self._force = force

    def _should_redact(self) -> Optional[Dict[str, Any]]:
        settings = get_dlp_settings()
        if self._force is True:
            # Force-enabled filter still respects configured categories/custom rules
            return {**settings, "enabled": True}
        if self._force is False:
            return None
        if settings.get("enabled", True) and settings.get("redact_logs", False):
            return settings
        return None

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            policy = self._should_redact()
            if policy is None:
                return True

            try:
                formatted = record.getMessage()
                res = scan_and_redact(formatted, policy=policy)
                if res.total_redactions > 0:
                    record.msg = res.redacted_text
                    record.args = None
            except Exception:
                if isinstance(record.msg, str):
                    res = scan_and_redact(record.msg, policy=policy)
                    if res.total_redactions > 0:
                        record.msg = res.redacted_text

            if isinstance(record.exc_text, str) and record.exc_text:
                exc_res = scan_and_redact(record.exc_text, policy=policy)
                if exc_res.total_redactions > 0:
                    record.exc_text = exc_res.redacted_text
        except Exception:
            # Never break application logging on filter failure
            pass
        return True
