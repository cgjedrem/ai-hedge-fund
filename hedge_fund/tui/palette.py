"""The app's colours, in one place.

Rich styles cannot read CSS variables, so the six brand colours are mirrored
here from app.tcss, and every screen and renderer imports them from this
module. ANSI_THEME maps the plain colour names that reused renderables speak
("green", "red", "cyan") onto the same palette, so one green exists app-wide.
"""

from rich.terminal_theme import TerminalTheme

from hedge_fund.reporting.palette import BRIGHT, CYAN, GREEN, MUTED, RED, TEXT  # noqa: F401

# Reused rich renderables (the equity curve, the roster) speak in ANSI color
# names — "green", "red", "cyan". This theme lands those on the brand palette
# instead of Textual's defaults, so one green exists app-wide.
ANSI_THEME = TerminalTheme(
    (11, 16, 14),  # background
    (217, 230, 224),  # foreground
    [
        (11, 16, 14),  # black
        (248, 113, 113),  # red — losses
        (43, 217, 124),  # green — the accent
        (251, 191, 36),  # yellow — in-flight work
        (56, 189, 248),  # blue
        (192, 132, 252),  # magenta
        (34, 211, 238),  # cyan — data
        (217, 230, 224),  # white
    ],
    [
        (95, 114, 104),  # bright black
        (248, 113, 113),
        (43, 217, 124),
        (251, 191, 36),
        (56, 189, 248),
        (192, 132, 252),
        (34, 211, 238),
        (242, 247, 244),
    ],
)
