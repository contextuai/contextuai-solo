"""
PPTX Slide Layout Configurations for ContextuAI AI Workspace.

Defines slide layouts, colors, and fonts used by DocumentGenerationService
when generating PowerPoint presentations via python-pptx.
"""

# ---------------------------------------------------------------------------
# Brand identity
# ---------------------------------------------------------------------------

BRAND_COLOR = "FF4700"  # ContextuAI orange
BRAND_COLOR_DARK = "CC3900"
BRAND_COLOR_LIGHT = "FF7A40"

TITLE_FONT = "Calibri"
BODY_FONT = "Calibri"
CODE_FONT = "Consolas"

# Neutral palette
WHITE = "FFFFFF"
LIGHT_GRAY = "F5F5F5"
MEDIUM_GRAY = "888888"
DARK_GRAY = "2D2D2D"
BLACK = "1A1A1A"

# Section slide background
SECTION_BG = "1A1A2E"

# Code block background
CODE_BG = "F0F0F0"
CODE_BORDER = "DDDDDD"

# Table colors
TABLE_HEADER_BG = "FF4700"
TABLE_HEADER_TEXT = "FFFFFF"
TABLE_ROW_ALT = "FFF5F0"

# Summary highlight background
SUMMARY_BG = "FFF0E6"
SUMMARY_ACCENT = "FF4700"

# ---------------------------------------------------------------------------
# Slide layout configurations
# ---------------------------------------------------------------------------

SLIDE_LAYOUTS = {
    "title": {
        "description": "Title slide with brand gradient background.",
        "layout_index": 0,
        "title_font": TITLE_FONT,
        "title_font_size": 40,
        "title_color": WHITE,
        "title_bold": True,
        "subtitle_font": BODY_FONT,
        "subtitle_font_size": 22,
        "subtitle_color": WHITE,
        "body_font": BODY_FONT,
        "background_color": BRAND_COLOR,
        "background_color_end": BRAND_COLOR_DARK,
        "accent_color": WHITE,
    },
    "section": {
        "description": "Section divider slide with dark background.",
        "layout_index": 5,  # Blank layout for custom rendering
        "title_font": TITLE_FONT,
        "title_font_size": 36,
        "title_color": WHITE,
        "title_bold": True,
        "body_font": BODY_FONT,
        "body_font_size": 18,
        "body_color": LIGHT_GRAY,
        "background_color": SECTION_BG,
        "accent_color": BRAND_COLOR,
    },
    "content": {
        "description": "Standard content slide with title bar and bullet points.",
        "layout_index": 1,
        "title_font": TITLE_FONT,
        "title_font_size": 28,
        "title_color": BRAND_COLOR,
        "title_bold": True,
        "body_font": BODY_FONT,
        "body_font_size": 18,
        "body_color": DARK_GRAY,
        "bullet_color": BRAND_COLOR,
        "line_spacing": 1.4,
        "background_color": WHITE,
        "title_bar_color": BRAND_COLOR,
        "title_bar_height_inches": 0.06,
    },
    "two_column": {
        "description": "Two-column layout for side-by-side comparisons.",
        "layout_index": 5,  # Blank layout for custom rendering
        "title_font": TITLE_FONT,
        "title_font_size": 28,
        "title_color": BRAND_COLOR,
        "title_bold": True,
        "body_font": BODY_FONT,
        "body_font_size": 16,
        "body_color": DARK_GRAY,
        "left_column_width_pct": 50,
        "right_column_width_pct": 50,
        "column_gap_inches": 0.5,
        "background_color": WHITE,
        "column_header_color": BRAND_COLOR,
        "column_header_font_size": 20,
    },
    "table": {
        "description": "Table slide with styled header row.",
        "layout_index": 5,  # Blank layout for custom rendering
        "title_font": TITLE_FONT,
        "title_font_size": 28,
        "title_color": BRAND_COLOR,
        "title_bold": True,
        "body_font": BODY_FONT,
        "body_font_size": 14,
        "body_color": DARK_GRAY,
        "background_color": WHITE,
        "header_bg_color": TABLE_HEADER_BG,
        "header_text_color": TABLE_HEADER_TEXT,
        "alt_row_color": TABLE_ROW_ALT,
    },
    "code": {
        "description": "Code slide with monospace font and gray background.",
        "layout_index": 5,  # Blank layout for custom rendering
        "title_font": TITLE_FONT,
        "title_font_size": 28,
        "title_color": BRAND_COLOR,
        "title_bold": True,
        "code_font": CODE_FONT,
        "code_font_size": 12,
        "code_color": DARK_GRAY,
        "code_bg_color": CODE_BG,
        "code_border_color": CODE_BORDER,
        "background_color": WHITE,
        "language_label_color": MEDIUM_GRAY,
        "language_label_font_size": 10,
    },
    "summary": {
        "description": "Summary / closing slide with highlight background.",
        "layout_index": 5,  # Blank layout for custom rendering
        "title_font": TITLE_FONT,
        "title_font_size": 32,
        "title_color": BRAND_COLOR,
        "title_bold": True,
        "body_font": BODY_FONT,
        "body_font_size": 18,
        "body_color": DARK_GRAY,
        "background_color": SUMMARY_BG,
        "accent_color": BRAND_COLOR,
        "number_color": BRAND_COLOR,
        "number_font_size": 22,
    },
}

# ---------------------------------------------------------------------------
# Footer / branding
# ---------------------------------------------------------------------------

FOOTER_TEXT = "Generated by ContextuAI AI Workspace"
FOOTER_FONT_SIZE = 8
FOOTER_COLOR = MEDIUM_GRAY
WATERMARK_TEXT = "ContextuAI"
WATERMARK_COLOR = "E8E8E8"
WATERMARK_FONT_SIZE = 10

# ---------------------------------------------------------------------------
# Default slide dimensions (16:9 widescreen)
# ---------------------------------------------------------------------------

SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5

# ---------------------------------------------------------------------------
# Spacing & margin defaults (inches)
# ---------------------------------------------------------------------------

MARGIN_LEFT = 0.75
MARGIN_RIGHT = 0.75
MARGIN_TOP = 1.0
MARGIN_BOTTOM = 0.75
CONTENT_TOP = 1.8  # Top offset for body content (below title)
