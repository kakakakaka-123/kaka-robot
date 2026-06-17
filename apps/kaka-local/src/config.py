"""配置管理。"""

import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    """本地组件配置。"""

    def __init__(self):
        # 尝试从多个位置加载 .env
        env_paths = [
            Path(__file__).parent.parent / ".env",
            Path.home() / ".kaka" / "local.env",
        ]

        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                break

        self.core_url = os.getenv("KAKA_CORE_URL", "http://127.0.0.1:8001")
        self.poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "3"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")


def load_config() -> Config:
    """加载配置。"""
    return Config()
