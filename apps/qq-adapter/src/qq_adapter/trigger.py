def should_handle_group_plaintext(text: str) -> bool:
    """判断群聊纯文本是否显式叫到卡咔。"""

    return "卡咔" in text
