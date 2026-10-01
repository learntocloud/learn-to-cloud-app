"""Tests for the local submission reset command."""

from scripts import reset_local_submissions


def test_confirmation_accepts_explicit_yes(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    assert reset_local_submissions._confirm_deletion()


def test_confirmation_rejects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert not reset_local_submissions._confirm_deletion()


def test_confirmation_rejects_missing_stdin(monkeypatch, capsys) -> None:
    def raise_eof(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert not reset_local_submissions._confirm_deletion()
    assert "no changes applied" in capsys.readouterr().err
