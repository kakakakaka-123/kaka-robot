"""安全检查：路径白名单、文件名验证。"""

from pathlib import Path


# 白名单路径
ALLOWED_BASE_PATHS = [
    Path.home() / "Desktop" / "卡咔的小角落",
    Path.home() / "Documents" / "卡咔",
]


def validate_path(target_path: Path) -> bool:
    """检查路径是否在白名单内。"""
    try:
        target_resolved = target_path.resolve()
    except (OSError, RuntimeError):
        return False

    for allowed in ALLOWED_BASE_PATHS:
        try:
            allowed_resolved = allowed.resolve()
            target_resolved.relative_to(allowed_resolved)
            return True
        except ValueError:
            continue

    return False


def is_safe_filename(filename: str) -> bool:
    """检查文件名是否安全。"""
    # 不能包含路径分隔符
    if "/" in filename or "\\" in filename:
        return False

    # 不能是特殊名称
    if filename in [".", "..", ""]:
        return False

    # 不能包含危险字符
    dangerous_chars = ["<", ">", ":", '"', "|", "?", "*"]
    if any(char in filename for char in dangerous_chars):
        return False

    # 只允许特定扩展名
    allowed_extensions = {".txt", ".md", ".json", ".log", ""}
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_extensions:
        return False

    return True
