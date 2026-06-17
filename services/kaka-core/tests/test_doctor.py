from pathlib import Path

import importlib.util
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR_SCRIPT = REPO_ROOT / "scripts" / "doctor.py"


def load_doctor_module():
    spec = importlib.util.spec_from_file_location("kaka_doctor_for_test", DOCTOR_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_doctor_no_longer_checks_removed_relationship_thresholds() -> None:
    source = DOCTOR_SCRIPT.read_text(encoding="utf-8")

    assert "RELATIONSHIP_RECENT_DAYS" not in source
    assert "RELATIONSHIP_FAMILIAR_INPUT_COUNT" not in source
    assert "RELATIONSHIP_FAMILIAR_RECENT_INPUT_COUNT" not in source
    assert "RELATIONSHIP_FAMILIAR_ACTIVE_MEMORY_COUNT" not in source
    assert "RELATIONSHIP_REGULAR_INPUT_COUNT" not in source
    assert "RELATIONSHIP_REGULAR_RECENT_INPUT_COUNT" not in source
    assert "RELATIONSHIP_REGULAR_ACTIVE_MEMORY_COUNT" not in source


def test_doctor_parse_env_file_accepts_utf8_bom(tmp_path: Path) -> None:
    doctor = load_doctor_module()
    env_path = tmp_path / ".env"
    env_path.write_text("\ufeffLLM_ENABLED=true\nLLM_API_KEY=hidden\n", encoding="utf-8")

    values = doctor.parse_env_file(env_path)

    assert values["LLM_ENABLED"] == "true"
    assert values["LLM_API_KEY"] == "hidden"


def test_doctor_allows_public_repo_without_private_persona_prompt() -> None:
    doctor = load_doctor_module()
    results = []

    doctor.check_project_layout(results)

    persona_results = [
        item
        for item in results
        if "prompts" in item.title and "kaka_persona.md" in item.title
    ]
    assert persona_results
    assert all(item.level != "FAIL" for item in persona_results)


def test_doctor_warns_when_env_file_missing() -> None:
    doctor = load_doctor_module()
    results = []

    values = doctor.check_env_file(results)

    assert values == {}
    assert any(item.title == ".env" and item.level == "WARN" for item in results)
    assert not any(item.title == ".env" and item.level == "FAIL" for item in results)


def test_doctor_empty_persona_prompt_path_uses_builtin_fallback() -> None:
    doctor = load_doctor_module()
    results = []

    doctor.check_persona_prompt_path(results, "")

    assert any(
        item.title == "KAKA_PERSONA_PROMPT_PATH" and item.level == "WARN"
        for item in results
    )
    assert not any(item.level == "FAIL" for item in results)
