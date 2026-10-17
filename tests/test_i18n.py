"""Tests for the internationalization (i18n) module and CLI language switching."""

from pathlib import Path

import pytest

from mc_xbox_dl.cli import extract_lang_arg, main
from mc_xbox_dl.i18n import (
    DEFAULT_LANGUAGE,
    detect_system_language,
    get_language,
    get_saved_language,
    load_settings,
    normalize_language_code,
    save_language_preference,
    set_language,
    t,
)


def test_normalize_language_code() -> None:
    assert normalize_language_code("pt") == "pt"
    assert normalize_language_code("pt-BR") == "pt"
    assert normalize_language_code("pt_BR") == "pt"
    assert normalize_language_code("PT-pt") == "pt"
    assert normalize_language_code("en") == "en"
    assert normalize_language_code("en-US") == "en"
    assert normalize_language_code("en_GB") == "en"
    assert normalize_language_code("fr") == "en"
    assert normalize_language_code(None) == DEFAULT_LANGUAGE
    assert normalize_language_code("") == DEFAULT_LANGUAGE


def test_detect_system_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "pt_BR.UTF-8")
    assert detect_system_language() == "pt"

    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert detect_system_language() == "en"

    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.setattr("locale.getlocale", lambda: ("pt_BR", "UTF-8"))
    assert detect_system_language() == "pt"

    monkeypatch.setattr("locale.getlocale", lambda: ("de_DE", "UTF-8"))
    assert detect_system_language() == "en"


def test_set_and_get_language() -> None:
    assert set_language("pt-BR") == "pt"
    assert get_language() == "pt"

    assert set_language("en-US") == "en"
    assert get_language() == "en"

    # Reset to default
    set_language("en")


def test_translation_formatting_and_fallback() -> None:
    set_language("pt")
    assert t("login_start") == "Iniciando autenticação via Device Code..."
    assert (
        t("whoami", gamertag="PlayerOne", xuid="12345") == "Conectado como: PlayerOne (XUID: 12345)"
    )

    set_language("en")
    assert t("login_start") == "Starting authentication via Device Code..."
    assert (
        t("whoami", gamertag="PlayerOne", xuid="12345") == "Logged in as: PlayerOne (XUID: 12345)"
    )

    # Non-existent key returns key name
    assert t("non_existent_key") == "non_existent_key"


def test_extract_lang_arg() -> None:
    lang, cleaned = extract_lang_arg(["--lang", "pt", "list"])
    assert lang == "pt"
    assert cleaned == ["list"]

    lang, cleaned = extract_lang_arg(["list", "--lang", "en"])
    assert lang == "en"
    assert cleaned == ["list"]

    lang, cleaned = extract_lang_arg(["download", "1", "--lang=pt-BR", "--install"])
    assert lang == "pt-BR"
    assert cleaned == ["download", "1", "--install"]

    lang, cleaned = extract_lang_arg(["whoami"])
    assert lang is None
    assert cleaned == ["whoami"]


def test_cli_help_in_different_languages(capsys: pytest.CaptureFixture[str]) -> None:
    # Portuguese help
    with pytest.raises(SystemExit):
        main(["--lang", "pt", "--help"])
    captured_pt = capsys.readouterr()
    assert "CLI para listar e baixar mundos" in captured_pt.out
    assert "Comandos disponíveis:" in captured_pt.out

    # English help
    with pytest.raises(SystemExit):
        main(["--lang", "en", "--help"])
    captured_en = capsys.readouterr()
    assert "CLI tool to list and download" in captured_en.out
    assert "Available commands:" in captured_en.out


def test_cli_whoami_unauthenticated_localized(capsys: pytest.CaptureFixture[str]) -> None:
    # In Portuguese
    code_pt = main(["--lang", "pt", "whoami"])
    assert code_pt == 3
    captured_pt = capsys.readouterr()
    assert "Você não está autenticado" in captured_pt.err

    # In English
    code_en = main(["--lang", "en", "whoami"])
    assert code_en == 3
    captured_en = capsys.readouterr()
    assert "You are not authenticated" in captured_en.err

    # With flag after subcommand
    code_after = main(["whoami", "--lang", "en"])
    assert code_after == 3
    captured_after = capsys.readouterr()
    assert "You are not authenticated" in captured_after.err


def test_settings_persistence(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    assert load_settings(settings_file) == {}
    assert get_saved_language(settings_file) is None

    # Save Portuguese preference
    save_language_preference("pt", settings_file)
    assert get_saved_language(settings_file) == "pt"

    # Load via set_language(None)
    lang = set_language(None, settings_file=settings_file)
    assert lang == "pt"
    assert get_language() == "pt"

    # Save English preference
    save_language_preference("en", settings_file)
    assert get_saved_language(settings_file) == "en"

    lang = set_language(None, settings_file=settings_file)
    assert lang == "en"
    assert get_language() == "en"


def test_cli_persists_language_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setenv("MC_XBOX_DL_SETTINGS_FILE", str(settings_file))

    # 1. First run with --lang pt saves preference
    code = main(["--lang", "pt", "whoami"])
    assert code == 3
    captured = capsys.readouterr()
    assert "Você não está autenticado" in captured.err
    assert get_saved_language(settings_file) == "pt"

    # 2. Subsequent run WITHOUT --lang uses saved Portuguese
    code = main(["whoami"])
    assert code == 3
    captured = capsys.readouterr()
    assert "Você não está autenticado" in captured.err

    # 3. Switching with --lang en updates saved preference
    code = main(["whoami", "--lang", "en"])
    assert code == 3
    captured = capsys.readouterr()
    assert "You are not authenticated" in captured.err
    assert get_saved_language(settings_file) == "en"

    # 4. Subsequent run WITHOUT --lang uses saved English
    code = main(["whoami"])
    assert code == 3
    captured = capsys.readouterr()
    assert "You are not authenticated" in captured.err


def test_corrupted_settings_fallback(tmp_path: Path) -> None:
    settings_file = tmp_path / "bad_settings.json"
    settings_file.write_text("{ not valid json :", encoding="utf-8")

    assert load_settings(settings_file) == {}
    assert get_saved_language(settings_file) is None
