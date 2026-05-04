from enum import StrEnum


class Platform(StrEnum):
    """消息或事件来自哪个平台。

    适配器收到外部输入后，需要先标记来源平台，再交给卡咔核心服务。
    """

    QQ = "qq"
    WEB = "web"
    VOICE = "voice"
    IOT = "iot"
    DESKTOP = "desktop"
    SYSTEM = "system"


class SceneType(StrEnum):
    """消息发生在哪种场景里。

    同一个用户在私聊、群聊、房间或设备事件里的处理方式可能不同。
    """

    PRIVATE = "private"
    GROUP = "group"
    ROOM = "room"
    DEVICE = "device"
    SYSTEM = "system"


class ContentType(StrEnum):
    """统一后的内容类型。

    第一阶段主要使用文本；图片、语音、视频和传感器数据为后续阶段预留。
    """

    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    EMOJI = "emoji"
    SENSOR = "sensor"
    EVENT = "event"
    MIXED = "mixed"


class ActionType(StrEnum):
    """卡咔核心服务希望适配器执行的动作类型。

    适配器只执行动作，不决定卡咔该怎么想、怎么记、怎么表达。
    """

    SEND_TEXT = "send_text"
    SEND_IMAGE = "send_image"
    SEND_VOICE = "send_voice"
    SEND_VIDEO = "send_video"
    SEND_EMOJI = "send_emoji"
    CALL_TOOL = "call_tool"
    NOOP = "noop"
