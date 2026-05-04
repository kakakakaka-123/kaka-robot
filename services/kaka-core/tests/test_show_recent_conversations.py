from datetime import date, datetime, timezone
from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "show_recent_conversations.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("show_recent_conversations", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_date_to_utc_range_uses_beijing_time():
    module = load_script_module()

    start, end = module.local_date_to_utc_range(date(2026, 5, 1))

    assert start == datetime(2026, 4, 30, 16, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, 16, 0, tzinfo=timezone.utc)


def test_build_filters():
    module = load_script_module()

    args = module.parse_args_from_list(
        [
            "--ids",
            "7,8",
            "--group",
            "1073224364",
            "--user",
            "1419825488",
            "--date",
            "2026-05-01",
            "--limit",
            "7",
        ]
    )
    filters = module.build_filters(args)

    assert filters.limit == 7
    assert filters.input_ids == (7, 8)
    assert filters.group_id == "1073224364"
    assert filters.user_id == "1419825488"
    assert filters.target_date == date(2026, 5, 1)
    assert filters.scene_type is None


def test_build_private_filter():
    module = load_script_module()

    args = module.parse_args_from_list(["--private"])
    filters = module.build_filters(args)

    assert filters.scene_type == "private"


def test_pycharm_simple_config_builds_input_id_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_INPUT_IDS", "9,10")
    monkeypatch.setattr(module, "PYCHARM_LIMIT", 30)
    monkeypatch.setattr(module, "PYCHARM_GROUP_ID", "20002")
    monkeypatch.setattr(module, "PYCHARM_USER_ID", "10001")
    monkeypatch.setattr(module, "PYCHARM_DATE", "2026-05-01")
    monkeypatch.setattr(module, "PYCHARM_PRIVATE", False)
    monkeypatch.setattr(module, "PYCHARM_GROUP_CHAT", True)
    monkeypatch.setattr(module, "PYCHARM_REPLIED_ONLY", True)
    monkeypatch.setattr(module, "PYCHARM_OBSERVED_ONLY", False)
    monkeypatch.setattr(module, "PYCHARM_OUTPUT_ORIGIN", "passive")
    monkeypatch.setattr(module, "PYCHARM_OUTPUT_REASON", "mention")

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.input_ids == (9, 10)
    assert filters.limit == 30
    assert filters.group_id == "20002"
    assert filters.user_id == "10001"
    assert filters.target_date == date(2026, 5, 1)
    assert filters.scene_type == "group"
    assert filters.replied_only is True
    assert filters.observed_only is False
    assert filters.output_origin == "passive"
    assert filters.output_reason == "mention"
