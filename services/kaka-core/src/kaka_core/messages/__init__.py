"""消息处理模块。"""

from kaka_core.messages.rich_content import (
    ImageAttachment,
    RichMessageBuilder,
    VoiceAttachment,
    FileAttachment,
    create_image_message,
    create_screenshot_message,
)

__all__ = [
    "ImageAttachment",
    "RichMessageBuilder",
    "VoiceAttachment",
    "FileAttachment",
    "create_image_message",
    "create_screenshot_message",
]
