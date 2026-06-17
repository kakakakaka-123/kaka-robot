"""增强的消息内容类型 - 支持图片、语音、富文本等。

扩展 MessageContent 以支持更多媒体类型。
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from kaka_protocol import ContentType, MessageContent


class MediaType(str, Enum):
    """媒体类型枚举。"""

    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"


class ImageFormat(str, Enum):
    """图片格式。"""

    PNG = "png"
    JPEG = "jpeg"
    GIF = "gif"
    WEBP = "webp"


@dataclass
class ImageAttachment:
    """图片附件。"""

    url: str  # 图片 URL 或本地路径
    width: int | None = None
    height: int | None = None
    format: ImageFormat | None = None
    size_bytes: int | None = None
    thumbnail_url: str | None = None

    @classmethod
    def from_local_file(cls, path: Path) -> "ImageAttachment":
        """从本地文件创建。"""
        return cls(
            url=f"file://{path.absolute()}",
            size_bytes=path.stat().st_size if path.exists() else None,
        )


@dataclass
class VoiceAttachment:
    """语音附件。"""

    url: str
    duration_seconds: float | None = None
    format: str | None = None  # mp3, wav, opus
    size_bytes: int | None = None


@dataclass
class FileAttachment:
    """文件附件。"""

    url: str
    filename: str
    size_bytes: int | None = None
    mime_type: str | None = None


class RichMessageBuilder:
    """富文本消息构建器。

    用于构建包含多种媒体类型的消息。
    """

    def __init__(self, text: str | None = None):
        self.text = text or ""
        self.images: list[ImageAttachment] = []
        self.voices: list[VoiceAttachment] = []
        self.files: list[FileAttachment] = []
        self.metadata: dict[str, Any] = {}

    def add_text(self, text: str) -> "RichMessageBuilder":
        """添加文本。"""
        if self.text:
            self.text += "\n" + text
        else:
            self.text = text
        return self

    def add_image(
        self,
        url: str,
        width: int | None = None,
        height: int | None = None,
    ) -> "RichMessageBuilder":
        """添加图片。"""
        self.images.append(
            ImageAttachment(url=url, width=width, height=height)
        )
        return self

    def add_image_file(self, path: Path) -> "RichMessageBuilder":
        """添加本地图片文件。"""
        self.images.append(ImageAttachment.from_local_file(path))
        return self

    def add_voice(self, url: str, duration: float | None = None) -> "RichMessageBuilder":
        """添加语音。"""
        self.voices.append(VoiceAttachment(url=url, duration_seconds=duration))
        return self

    def add_file(self, url: str, filename: str) -> "RichMessageBuilder":
        """添加文件。"""
        self.files.append(FileAttachment(url=url, filename=filename))
        return self

    def set_metadata(self, key: str, value: Any) -> "RichMessageBuilder":
        """设置元数据。"""
        self.metadata[key] = value
        return self

    def build(self) -> MessageContent:
        """构建为 MessageContent。"""
        # 如果只有文本，返回纯文本消息
        if not self.images and not self.voices and not self.files:
            return MessageContent.text_message(self.text)

        # 否则构建富文本消息
        data: dict[str, Any] = {"text": self.text}

        if self.images:
            data["images"] = [
                {
                    "url": img.url,
                    "width": img.width,
                    "height": img.height,
                    "format": img.format.value if img.format else None,
                    "size_bytes": img.size_bytes,
                    "thumbnail_url": img.thumbnail_url,
                }
                for img in self.images
            ]

        if self.voices:
            data["voices"] = [
                {
                    "url": voice.url,
                    "duration_seconds": voice.duration_seconds,
                    "format": voice.format,
                    "size_bytes": voice.size_bytes,
                }
                for voice in self.voices
            ]

        if self.files:
            data["files"] = [
                {
                    "url": file.url,
                    "filename": file.filename,
                    "size_bytes": file.size_bytes,
                    "mime_type": file.mime_type,
                }
                for file in self.files
            ]

        if self.metadata:
            data["metadata"] = self.metadata

        return MessageContent(
            type=ContentType.TEXT,  # 暂时用 TEXT，未来可能需要 RICH_TEXT
            text=self.text,
            data=data,
        )


def create_image_message(
    text: str,
    image_url: str,
    width: int | None = None,
    height: int | None = None,
) -> MessageContent:
    """快捷方式：创建包含图片的消息。"""
    return (
        RichMessageBuilder(text)
        .add_image(image_url, width, height)
        .build()
    )


def create_screenshot_message(
    text: str,
    screenshot_path: Path,
    width: int | None = None,
    height: int | None = None,
) -> MessageContent:
    """快捷方式：创建包含截图的消息。"""
    return (
        RichMessageBuilder(text)
        .add_image_file(screenshot_path)
        .set_metadata("screenshot", True)
        .build()
    )
