from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR_SCRIPT = REPO_ROOT / "scripts" / "doctor.py"


def test_doctor_no_longer_checks_removed_relationship_thresholds() -> None:
    source = DOCTOR_SCRIPT.read_text(encoding="utf-8")

    assert "RELATIONSHIP_RECENT_DAYS" not in source
    assert "RELATIONSHIP_FAMILIAR_INPUT_COUNT" not in source
    assert "RELATIONSHIP_FAMILIAR_RECENT_INPUT_COUNT" not in source
    assert "RELATIONSHIP_FAMILIAR_ACTIVE_MEMORY_COUNT" not in source
    assert "RELATIONSHIP_REGULAR_INPUT_COUNT" not in source
    assert "RELATIONSHIP_REGULAR_RECENT_INPUT_COUNT" not in source
    assert "RELATIONSHIP_REGULAR_ACTIVE_MEMORY_COUNT" not in source
