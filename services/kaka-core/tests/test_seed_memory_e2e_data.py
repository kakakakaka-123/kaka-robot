from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_memory_e2e_data.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("seed_memory_e2e_data", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pycharm_simple_config_previews_by_default(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_LIMIT_PREVIEW", 5)
    monkeypatch.setattr(module, "PYCHARM_APPLY", False)
    monkeypatch.setattr(module, "PYCHARM_CONFIRM_SEED", False)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())

    assert args.limit_preview == 5
    assert args.apply is False


def test_pycharm_apply_requires_seed_confirmation(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_APPLY", True)
    monkeypatch.setattr(module, "PYCHARM_CONFIRM_SEED", False)

    try:
        module.build_pycharm_simple_args()
    except SystemExit as exc:
        assert "PYCHARM_CONFIRM_SEED" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_pycharm_apply_with_confirmation_builds_apply_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_LIMIT_PREVIEW", 5)
    monkeypatch.setattr(module, "PYCHARM_APPLY", True)
    monkeypatch.setattr(module, "PYCHARM_CONFIRM_SEED", True)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())

    assert args.limit_preview == 5
    assert args.apply is True
