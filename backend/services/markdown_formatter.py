"""
Format crew/automation output for each distribution channel.

Crews emit CommonMark by default. Most outbound platforms do not render
CommonMark — they need either plain text, HTML, or a platform-native
flavour (Slack mrkdwn, Telegram MarkdownV2). This module converts once,
at the dispatch boundary, so adapters can stay format-agnostic.
"""

import re
from typing import Optional

import markdown2


def to_plain(content: str) -> str:
    """Strip Markdown to plain text. Lossy but the only option for
    Twitter, LinkedIn, Facebook, Instagram — none render formatting."""
    if not content:
        return content
    text = content

    # Fenced code blocks: keep the body, drop the fences.
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    text = text.replace("```", "")
    # Inline code: keep the body.
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Headers: strip leading hashes.
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold + italic markers (** __ * _) without removing the words.
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)
    # Strikethrough.
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    # Links: [text](url) -> "text (url)". Bare URLs stay.
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    # Images: ![alt](src) -> "alt".
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Block quotes.
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # List bullets / numbers.
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Horizontal rules.
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Collapse 3+ blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def to_html(content: str) -> str:
    """Convert Markdown to HTML for email, blog, and Telegram parse_mode=HTML."""
    if not content:
        return content
    extras = ["fenced-code-blocks", "tables", "strike", "cuddled-lists"]
    return markdown2.markdown(content, extras=extras).strip()


# Tags Telegram's HTML parser accepts. Anything else must be stripped or
# the API rejects the message with a 400.
_TELEGRAM_HTML_ALLOWED = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "blockquote", "br",
}


def to_telegram_html(content: str) -> str:
    """Telegram supports a restricted HTML subset. Convert via markdown2
    then drop any tag Telegram's API would reject."""
    if not content:
        return content
    html = to_html(content)
    # Drop unsupported tags while keeping their inner text.
    def _strip(match: re.Match[str]) -> str:
        tag = match.group(1).lower()
        return "" if tag not in _TELEGRAM_HTML_ALLOWED else match.group(0)

    html = re.sub(r"</?([a-zA-Z0-9]+)[^>]*>", _strip, html)
    return html


def to_slack_mrkdwn(content: str) -> str:
    """Slack mrkdwn is similar to but not Markdown. Most notable diffs:
    bold is *single asterisks*, italic is _underscores_, headers don't
    exist (so we render them as bold). Lists keep their bullets."""
    if not content:
        return content
    text = content

    # Fenced code blocks pass through as ```code```.
    # Inline code stays as `code`.
    # Headers -> bold line.
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    # **bold** -> *bold* (must run BEFORE single-asterisk rules, otherwise
    # the pair gets matched as two separate italics).
    text = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", text)
    # __bold__ -> *bold*
    text = re.sub(r"__([^_]+)__", r"*\1*", text)
    # Links [text](url) -> <url|text>.
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    # Images -> alt text (Slack does not inline images via webhook).
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Strikethrough ~~x~~ -> ~x~
    text = re.sub(r"~~([^~]+)~~", r"~\1~", text)

    return text.strip()


def format_for_channel(content: str, channel_type: str) -> str:
    """Top-level dispatch: pick the right format for the target channel.

    Returns plain content unchanged for channel types we don't know about
    so a new adapter doesn't silently lose data."""
    if not content:
        return content
    ct = (channel_type or "").lower()
    if ct in ("twitter", "linkedin", "facebook", "instagram"):
        return to_plain(content)
    if ct == "slack":
        return to_slack_mrkdwn(content)
    if ct == "telegram":
        return to_telegram_html(content)
    if ct in ("email", "blog"):
        return to_html(content)
    if ct == "discord":
        # Discord natively renders CommonMark subset.
        return content
    return content


def telegram_send_kwargs(content: str) -> dict:
    """Build the JSON body for Telegram's sendMessage. Returns text +
    parse_mode together so the caller doesn't have to know about the
    HTML conversion."""
    formatted = to_telegram_html(content)
    return {"text": formatted, "parse_mode": "HTML"}


__all__ = [
    "format_for_channel",
    "telegram_send_kwargs",
    "to_plain",
    "to_html",
    "to_telegram_html",
    "to_slack_mrkdwn",
]
