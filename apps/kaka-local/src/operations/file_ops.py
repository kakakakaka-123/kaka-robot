"""文件操作实现。"""

import time
from pathlib import Path

from security import is_safe_filename, validate_path


async def create_file(params: dict) -> dict:
    """在白名单目录创建文件。"""
    filename = params.get("filename", "小纸条.txt")
    content = params.get("content", "")
    base_path = params.get("base_path", "Desktop/卡咔的小角落")

    # 安全检查：文件名
    if not is_safe_filename(filename):
        raise ValueError(f"文件名不安全：{filename}")

    # 构造完整路径
    workspace = Path.home() / base_path
    workspace.mkdir(parents=True, exist_ok=True)

    full_path = workspace / filename

    # 安全检查：路径
    if not validate_path(full_path):
        raise ValueError(f"路径不在白名单内：{full_path}")

    # 写入文件
    full_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "message": f"已创建 {filename}",
        "file_path": str(full_path),
    }
