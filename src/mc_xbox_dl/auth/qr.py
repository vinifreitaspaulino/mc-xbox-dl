"""Terminal QR Code rendering for the Microsoft/Xbox Device Code login flow."""

import shutil
import sys

import segno
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mc_xbox_dl.i18n import t

MIN_TERMINAL_WIDTH = 70


def build_qr_renderable(url: str) -> Text:
    """Generates a compact QR Code in half-blocks with symmetrical borders."""
    qr = segno.make(url, error="L")
    matrix = [list(row) for row in qr.matrix_iter(border=2)]
    width = len(matrix[0]) if matrix else 0

    text = Text()
    pair_limit = len(matrix) - (len(matrix) % 2)
    for y in range(0, pair_limit, 2):
        top_row = matrix[y]
        bot_row = matrix[y + 1]
        chars: list[str] = []
        for top, bot in zip(top_row, bot_row, strict=True):
            if top and bot:
                chars.append("█")
            elif top and not bot:
                chars.append("▀")
            elif not top and bot:
                chars.append("▄")
            else:
                chars.append(" ")
        line = "".join(chars)
        is_last = y + 2 >= len(matrix)
        text.append(line if is_last else f"{line}\n", style="black on white")

    # Odd matrix height leaves one final border row; render only its upper half-block
    # in white so the bottom quiet zone matches the top quiet zone (2 modules).
    if len(matrix) % 2 == 1:
        text.append("▀" * width, style="white")

    return text


def display_login_prompt(url: str, code: str, fallback_text: str) -> None:
    """Displays a QR Code and Device Code panel, with an automatic plain-text fallback."""
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    width = shutil.get_terminal_size(fallback=(80, 24)).columns

    if not sys.stdout.isatty() or width < MIN_TERMINAL_WIDTH or "utf" not in encoding:
        print(fallback_text, flush=True)
        return

    try:
        qr_text = build_qr_renderable(url)

        info = Text()
        info.append(f"{t('qr_login_step1')}\n", style="bold")
        info.append(f"   {t('qr_login_or_browser')}\n")
        info.append(f"   {url}\n\n", style=f"bold cyan link {url}")
        info.append(f"{t('qr_login_step2')}\n", style="bold")
        info.append(f"   {code}", style="bold green")

        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="left", vertical="middle")
        grid.add_column(justify="left", vertical="middle")
        grid.add_row(qr_text, info)

        Console().print(Panel(grid, title=t("qr_login_title"), expand=False))
    except Exception:
        print(fallback_text, flush=True)