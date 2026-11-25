"""Tests for terminal QR Code rendering and localized Device Code prompt (auth/qr.py)."""

import io
import os
from unittest.mock import MagicMock

import pytest

from mc_xbox_dl.auth import qr
from mc_xbox_dl.i18n import set_language


class _FakeStdout(io.StringIO):
    """Minimal stdout stub with configurable TTY status and encoding."""

    def __init__(self, *, tty: bool = True, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        return self._encoding

    def isatty(self) -> bool:
        return self._tty


def test_build_qr_renderable_structure() -> None:
    text = qr.build_qr_renderable("https://www.microsoft.com/link")
    styles = {span.style for span in text.spans}
    assert "black on white" in styles
    assert "white" in styles
    lines = text.plain.splitlines()
    assert len(lines) > 5
    # All lines must share the same width and use only half-block characters or spaces
    widths = {len(line) for line in lines}
    assert len(widths) == 1
    assert set(text.plain) <= {"█", "▀", "▄", " ", "\n"}
    # Top quiet zone is blank; bottom row uses upper half-blocks to balance 2-module border
    assert lines[0].strip() == ""
    assert set(lines[-1]) == {"▀"}


def test_display_login_prompt_fallback_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_out = _FakeStdout(tty=False, encoding="utf-8")
    monkeypatch.setattr("sys.stdout", fake_out)
    qr.display_login_prompt(
        url="https://www.microsoft.com/link",
        code="ABCD-1234",
        fallback_text="FALLBACK_TEXT",
    )
    output = fake_out.getvalue()
    assert "FALLBACK_TEXT" in output
    assert "█" not in output


def test_display_login_prompt_fallback_narrow_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_out = _FakeStdout(tty=True, encoding="utf-8")
    monkeypatch.setattr("sys.stdout", fake_out)
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: os.terminal_size((60, 24)))
    qr.display_login_prompt(
        url="https://www.microsoft.com/link",
        code="ABCD-1234",
        fallback_text="FALLBACK_NARROW",
    )
    output = fake_out.getvalue()
    assert "FALLBACK_NARROW" in output
    assert "█" not in output


def test_display_login_prompt_fallback_non_utf_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_out = _FakeStdout(tty=True, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", fake_out)
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: os.terminal_size((100, 30)))
    qr.display_login_prompt(
        url="https://www.microsoft.com/link",
        code="ABCD-1234",
        fallback_text="FALLBACK_ENCODING",
    )
    output = fake_out.getvalue()
    assert "FALLBACK_ENCODING" in output
    assert "█" not in output


def test_display_login_prompt_fallback_on_render_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_out = _FakeStdout(tty=True, encoding="utf-8")
    monkeypatch.setattr("sys.stdout", fake_out)
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: os.terminal_size((100, 30)))
    monkeypatch.setattr(
        qr, "build_qr_renderable", MagicMock(side_effect=RuntimeError("render boom"))
    )
    qr.display_login_prompt(
        url="https://www.microsoft.com/link",
        code="ABCD-1234",
        fallback_text="FALLBACK_ERROR",
    )
    output = fake_out.getvalue()
    assert "FALLBACK_ERROR" in output


@pytest.mark.parametrize(
    ("lang", "expected_title", "expected_step1", "expected_browser", "expected_step2"),
    [
        (
            "en",
            "Xbox Live Device Login",
            "1. Scan the QR Code",
            "or open in your browser:",
            "2. Enter the code:",
        ),
        (
            "pt",
            "Login de Dispositivo Xbox Live",
            "1. Escaneie o QR Code",
            "ou acesse no seu navegador:",
            "2. Digite o código:",
        ),
    ],
)
def test_display_login_prompt_localized_panel(
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    expected_title: str,
    expected_step1: str,
    expected_browser: str,
    expected_step2: str,
) -> None:
    set_language(lang)
    fake_out = _FakeStdout(tty=True, encoding="utf-8")
    monkeypatch.setattr("sys.stdout", fake_out)
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: os.terminal_size((100, 30)))

    qr.display_login_prompt(
        url="https://www.microsoft.com/link",
        code="TEST-9876",
        fallback_text="FALLBACK_UNUSED",
    )

    output = fake_out.getvalue()
    assert expected_title in output
    assert expected_step1 in output
    assert expected_browser in output
    assert expected_step2 in output
    assert "https://www.microsoft.com/link" in output
    assert "TEST-9876" in output
    assert "█" in output
    assert "FALLBACK_UNUSED" not in output
