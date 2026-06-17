import sys
from pathlib import Path

import pytest

LOCAL_SRC = Path(__file__).resolve().parents[1] / "src"
if str(LOCAL_SRC) not in sys.path:
    sys.path.insert(0, str(LOCAL_SRC))

from executor import KakaLocalExecutor


class DummyConfig:
    core_url = "http://core.test"
    poll_interval = 1


@pytest.mark.asyncio
async def test_execute_operation_reports_function_failure_as_failed(monkeypatch) -> None:
    executor = KakaLocalExecutor(DummyConfig())
    reported: dict[str, object] = {}

    async def fake_mark_executing(operation_id: int) -> None:
        reported["started"] = operation_id

    async def fake_report_result(operation_id: int, success: bool, result: dict) -> None:
        reported["operation_id"] = operation_id
        reported["success"] = success
        reported["result"] = result

    async def fake_play_sound(params: dict) -> dict:
        return {
            "success": False,
            "error": "not_implemented",
            "message": f"not implemented: {params['sound_name']}",
        }

    monkeypatch.setattr(executor, "mark_executing", fake_mark_executing)
    monkeypatch.setattr(executor, "report_result", fake_report_result)
    monkeypatch.setattr("executor.play_sound", fake_play_sound)

    try:
        await executor.execute_operation(
            {
                "id": 7,
                "operation_type": "play_sound",
                "params": {"sound_name": "ding.mp3"},
            }
        )
    finally:
        await executor.client.aclose()

    assert reported["started"] == 7
    assert reported["operation_id"] == 7
    assert reported["success"] is False
    assert reported["result"] == {
        "success": False,
        "error": "not_implemented",
        "message": "not implemented: ding.mp3",
    }
