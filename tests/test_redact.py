"""Tests for the secret redaction and masking module (redact.py)."""

from mc_xbox_dl.redact import redact_data, redact_string


def test_redact_sensitive_dict_keys() -> None:
    data = {
        "access_token": "secret_access_token_12345",
        "refresh_token": "secret_refresh_token_67890",
        "xsts_token": "secret_xsts_token_abcde",
        "Token": "secret_raw_token",
        "Authorization": "XBL3.0 x=12345;secret_token",
        "RpsTicket": "t=secret_rps_ticket",
        "user_code": "ABCDEF12",
        "device_code": "secret_device_code",
        "public_field": "safe_value",
        "count": 42,
    }

    redacted = redact_data(data)

    assert redacted["access_token"] == "***"
    assert redacted["refresh_token"] == "***"
    assert redacted["xsts_token"] == "***"
    assert redacted["Token"] == "***"
    assert redacted["Authorization"] == "***"
    assert redacted["RpsTicket"] == "***"
    assert redacted["user_code"] == "***"
    assert redacted["device_code"] == "***"
    assert redacted["public_field"] == "safe_value"
    assert redacted["count"] == 42

    # Verify that the original dictionary was not mutated
    assert data["access_token"] == "secret_access_token_12345"


def test_redact_nested_structures() -> None:
    data = {
        "user": {
            "name": "Alex",
            "tokens": [
                {"access_token": "secret_nested_1"},
                {"refresh_token": "secret_nested_2"},
            ],
        },
        "meta": {"status": "ok"},
    }

    redacted = redact_data(data)

    assert redacted["user"]["name"] == "Alex"
    assert redacted["user"]["tokens"][0]["access_token"] == "***"
    assert redacted["user"]["tokens"][1]["refresh_token"] == "***"
    assert redacted["meta"]["status"] == "ok"


def test_redact_bearer_and_xbl_headers() -> None:
    text = "Authorization: Bearer secret_bearer_token_here and extra info"
    assert redact_string(text) == "Authorization: Bearer *** and extra info"

    xbl_text = "Header: XBL3.0 x=userhash;xsts_secret_token_123"
    assert redact_string(xbl_text) == "Header: XBL3.0 x=***;***"

    rps_key_text = "Properties: RpsTicket=t=secret_token_xyz"
    assert redact_string(rps_key_text) == "Properties: RpsTicket=***"

    rps_standalone = "Ticket param: t=secret_token_xyz"
    assert redact_string(rps_standalone) == "Ticket param: t=***"


def test_redact_jwt_pattern() -> None:
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG4ZupWpmD"
    result = redact_string(f"Token: {jwt}")
    assert jwt not in result
    assert "***JWT***" in result
