from pathlib import Path

from kaka_core.config import settings as settings_module


def test_load_env_files_uses_utf8_sig(monkeypatch) -> None:
    calls: list[tuple[Path, bool | None, str | None]] = []

    def fake_load_dotenv(path: Path, *, override: bool | None = None, encoding: str | None = None) -> None:
        calls.append((path, override, encoding))

    monkeypatch.setattr(settings_module, "load_dotenv", fake_load_dotenv)

    settings_module._load_env_files()

    assert calls
    assert all(call[2] == "utf-8-sig" for call in calls)
