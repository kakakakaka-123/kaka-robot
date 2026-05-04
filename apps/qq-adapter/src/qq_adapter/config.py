import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _load_env_files() -> None:
    """加载项目根目录和适配器目录的环境变量。"""

    current_file = Path(__file__).resolve()
    repo_root = current_file.parents[4]
    adapter_root = current_file.parents[2]

    load_dotenv(repo_root / ".env")
    load_dotenv(adapter_root / ".env", override=False)


@dataclass(frozen=True)
class QQAdapterSettings:
    """QQ 适配器配置。"""

    core_base_url: str
    request_timeout_seconds: float


@lru_cache
def get_settings() -> QQAdapterSettings:
    """读取并缓存 QQ 适配器配置。"""

    _load_env_files()
    return QQAdapterSettings(
        core_base_url=os.getenv("KAKA_CORE_BASE_URL", "http://127.0.0.1:8001").rstrip("/"),
        request_timeout_seconds=float(os.getenv("QQ_ADAPTER_REQUEST_TIMEOUT", "60")),
    )
