import sys
from pathlib import Path

import pytest

LOCAL_SRC = Path(__file__).resolve().parents[1] / "src"
if str(LOCAL_SRC) not in sys.path:
    sys.path.insert(0, str(LOCAL_SRC))

from operations.sound import play_sound


@pytest.mark.asyncio
async def test_play_sound_reports_not_implemented_failure() -> None:
    result = await play_sound({"sound_name": "ding.mp3"})

    assert result["success"] is False
    assert result["error"] == "not_implemented"
    assert "ding.mp3" in result["message"]
