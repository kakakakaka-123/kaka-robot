"""截图功能实现。"""

import time
from pathlib import Path

import pyautogui
from PIL import Image, ImageDraw, ImageFilter


async def take_screenshot(params: dict) -> dict:
    """截取桌面当前画面。

    参数：
    - blur_sensitive: bool - 是否模糊敏感信息（默认 False）
    - region: dict - 截取区域 {"x": int, "y": int, "width": int, "height": int}
    - quality: int - 保存质量 1-100（默认 85）

    返回：
    - success: bool
    - message: str
    - screenshot: str - 截图文件路径
    """
    blur_sensitive = params.get("blur_sensitive", False)
    region = params.get("region")
    quality = params.get("quality", 85)

    try:
        # 1. 截图
        if region:
            screenshot = pyautogui.screenshot(
                region=(region["x"], region["y"], region["width"], region["height"])
            )
        else:
            screenshot = pyautogui.screenshot()

        # 2. 可选：模糊敏感区域（窗口标题栏、任务栏等）
        if blur_sensitive:
            screenshot = _blur_sensitive_areas(screenshot)

        # 3. 保存到临时目录
        screenshots_dir = Path.home() / ".kaka" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        screenshot_path = screenshots_dir / f"screenshot_{timestamp}.png"

        screenshot.save(screenshot_path, quality=quality, optimize=True)

        # 4. 获取文件大小
        file_size_kb = screenshot_path.stat().st_size / 1024

        return {
            "success": True,
            "message": f"截图已保存 ({file_size_kb:.1f} KB)",
            "screenshot": str(screenshot_path),
            "width": screenshot.width,
            "height": screenshot.height,
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"截图失败：{str(e)}",
            "screenshot": None,
        }


def _blur_sensitive_areas(image: Image.Image) -> Image.Image:
    """模糊敏感区域（窗口标题栏、任务栏）。

    Windows 系统的敏感区域：
    - 顶部 40 像素（窗口标题栏）
    - 底部 50 像素（任务栏）
    """
    width, height = image.size

    # 创建副本
    blurred = image.copy()

    # 模糊顶部区域（标题栏）
    top_region = image.crop((0, 0, width, 40))
    top_blurred = top_region.filter(ImageFilter.GaussianBlur(radius=15))
    blurred.paste(top_blurred, (0, 0))

    # 模糊底部区域（任务栏）
    bottom_y = max(0, height - 50)
    bottom_region = image.crop((0, bottom_y, width, height))
    bottom_blurred = bottom_region.filter(ImageFilter.GaussianBlur(radius=15))
    blurred.paste(bottom_blurred, (0, bottom_y))

    return blurred
