"""Phase 3 feature flags.

Phase 3 ships behind `UNIFIED_CREWS` so existing inbound/outbound paths keep
working until PR 4 flips the default to true.

  UNIFIED_CREWS=1   → inbound_router + scheduled_runner + connection_bindings
                       outbound publishing all active.
  UNIFIED_CREWS=0   → legacy trigger_service + channel_bindings outbound path
                       (today's behaviour).
"""

from __future__ import annotations

import os


def _env_truthy(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def unified_crews_enabled() -> bool:
    """Read at call time so tests can monkeypatch the env var per-case.

    Phase 3 PR 4 flipped the default to True — the unified inbound_router +
    scheduled_runner + direction-aware outbound publishing is now the primary
    code path. Set UNIFIED_CREWS=0 to fall back to the legacy paths.
    """
    return _env_truthy("UNIFIED_CREWS", default=True)
