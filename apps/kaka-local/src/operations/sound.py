"""音效播放功能实现。"""


async def play_sound(params: dict) -> dict:
    """播放音效。"""
    sound_name = params.get("sound_name", "ding.mp3")

    return {
        "success": False,
        "error": "not_implemented",
        "message": f"音效播放功能尚未实现（{sound_name}）",
    }
