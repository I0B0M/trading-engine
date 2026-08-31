"""The .env loader: parsing, quote handling, and precedence."""

import os

from trading_engine.live.env import load_env_file


def test_loads_keys_and_ignores_comments_and_blanks(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "ALPACA_API_KEY=abc123\n"
        'ALPACA_SECRET_KEY="quoted-secret"\n'
        "MALFORMED_LINE_NO_EQUALS\n"
    )
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    load_env_file(env)

    assert os.environ["ALPACA_API_KEY"] == "abc123"
    assert os.environ["ALPACA_SECRET_KEY"] == "quoted-secret"


def test_existing_environment_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ALPACA_API_KEY=from-file\n")
    monkeypatch.setenv("ALPACA_API_KEY", "from-shell")

    load_env_file(env)

    assert os.environ["ALPACA_API_KEY"] == "from-shell"


def test_missing_file_is_not_an_error(tmp_path):
    load_env_file(tmp_path / "does-not-exist")
