import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _load_env_files() -> None:
    """加载本地环境变量文件。

    优先从项目根目录读取 `.env`，这样所有服务可以共用同一份本地配置。
    如果以后某个服务需要独立配置，也可以在服务目录放自己的 `.env`。
    """

    current_file = Path(__file__).resolve()
    repo_root = current_file.parents[5]
    service_root = current_file.parents[3]

    load_dotenv(repo_root / ".env")
    load_dotenv(service_root / ".env", override=False)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _get_csv_set(name: str) -> frozenset[str]:
    value = os.getenv(name)
    if value is None:
        return frozenset()
    items = [item.strip() for item in value.split(",")]
    return frozenset(item for item in items if item)


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


@dataclass(frozen=True)
class DatabaseSettings:
    """数据库配置。

    第一阶段默认使用 SQLite 文件，后续可以通过 DATABASE_URL 切到 PostgreSQL。
    """

    url: str


@dataclass(frozen=True)
class LLMSettings:
    """大模型相关配置。

    第一版只有 chat_model 会实际使用，其余模型角色先保留，方便后续扩展模型路由。
    """

    enabled: bool
    api_key: str
    base_url: str
    chat_model: str
    reasoning_model: str
    memory_model: str
    tool_model: str
    temperature: float
    max_tokens: int

    @property
    def can_call_remote(self) -> bool:
        """是否具备调用远程模型的最低条件。"""

        return self.enabled and bool(self.api_key)


@dataclass(frozen=True)
class MemoryAnalysisSettings:
    """自动记忆候选分析配置。"""

    enabled: bool
    trigger_count: int
    batch_limit: int
    max_runs_per_check: int
    interval_seconds: int


@dataclass(frozen=True)
class MemoryReviewSettings:
    """自动候选区复核配置。"""

    enabled: bool
    trigger_count: int
    batch_size: int
    max_runs_per_check: int


@dataclass(frozen=True)
class MemoryReplySettings:
    """回复时长期记忆注入配置。"""

    enabled: bool
    limit: int
    min_score: float
    pool_size: int


@dataclass(frozen=True)
class ShortContextSettings:
    """回复时短期上下文注入配置。"""

    enabled: bool
    limit: int
    max_chars: int
    window_minutes: int


@dataclass(frozen=True)
class RelationshipSettings:
    """回复时关系上下文配置。"""

    owner_user_ids: frozenset[str]
    familiar_input_count: int
    familiar_recent_input_count: int
    familiar_active_memory_count: int
    regular_input_count: int
    regular_recent_input_count: int
    regular_active_memory_count: int
    recent_days: int


@dataclass(frozen=True)
class PersonaSettings:
    """回复时基础人设 Prompt 配置。"""

    prompt_path: Path


@dataclass(frozen=True)
class AdminSettings:
    """本地管理台访问保护配置。"""

    local_only: bool
    api_token: str


@dataclass(frozen=True)
class Settings:
    """卡咔核心服务总配置。"""

    database: DatabaseSettings
    llm: LLMSettings
    memory_analysis: MemoryAnalysisSettings
    memory_review: MemoryReviewSettings
    memory_reply: MemoryReplySettings
    short_context: ShortContextSettings
    relationship: RelationshipSettings
    persona: PersonaSettings
    admin: AdminSettings


@lru_cache
def get_settings() -> Settings:
    """读取并缓存配置。

    配置读取集中在这里，业务代码不直接读环境变量。
    """

    _load_env_files()
    current_file = Path(__file__).resolve()
    repo_root = current_file.parents[5]
    default_database_url = f"sqlite:///{repo_root / 'data' / 'kaka.sqlite3'}"
    default_persona_prompt_path = repo_root / "prompts" / "kaka_persona.md"
    persona_prompt_path = _resolve_path(
        os.getenv("KAKA_PERSONA_PROMPT_PATH", str(default_persona_prompt_path)),
        base_dir=repo_root,
    )

    return Settings(
        database=DatabaseSettings(
            url=os.getenv("DATABASE_URL", default_database_url),
        ),
        llm=LLMSettings(
            enabled=_get_bool("LLM_ENABLED", False),
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            chat_model=os.getenv("LLM_CHAT_MODEL", "deepseek-v4-flash"),
            reasoning_model=os.getenv("LLM_REASONING_MODEL", "deepseek-v4-pro"),
            memory_model=os.getenv("LLM_MEMORY_MODEL", "deepseek-v4-flash"),
            tool_model=os.getenv("LLM_TOOL_MODEL", "deepseek-v4-flash"),
            temperature=_get_float("LLM_TEMPERATURE", 0.7),
            max_tokens=_get_int("LLM_MAX_TOKENS", 800),
        ),
        memory_analysis=MemoryAnalysisSettings(
            enabled=_get_bool("MEMORY_AUTO_ANALYSIS_ENABLED", False),
            trigger_count=_get_int("MEMORY_AUTO_ANALYSIS_TRIGGER_COUNT", 50),
            batch_limit=_get_int("MEMORY_AUTO_ANALYSIS_BATCH_LIMIT", 50),
            max_runs_per_check=_get_int("MEMORY_AUTO_ANALYSIS_MAX_RUNS_PER_CHECK", 2),
            interval_seconds=_get_int("MEMORY_AUTO_ANALYSIS_INTERVAL_SECONDS", 0),
        ),
        memory_review=MemoryReviewSettings(
            enabled=_get_bool("MEMORY_AUTO_REVIEW_ENABLED", False),
            trigger_count=_get_int("MEMORY_AUTO_REVIEW_TRIGGER_COUNT", 20),
            batch_size=_get_int("MEMORY_AUTO_REVIEW_BATCH_SIZE", 10),
            max_runs_per_check=_get_int("MEMORY_AUTO_REVIEW_MAX_RUNS_PER_CHECK", 1),
        ),
        memory_reply=MemoryReplySettings(
            enabled=_get_bool("MEMORY_REPLY_INJECTION_ENABLED", True),
            limit=_get_int("MEMORY_REPLY_LIMIT", 5),
            min_score=_get_float("MEMORY_REPLY_MIN_SCORE", 1.0),
            pool_size=_get_int("MEMORY_REPLY_POOL_SIZE", 300),
        ),
        short_context=ShortContextSettings(
            enabled=_get_bool("SHORT_CONTEXT_ENABLED", True),
            limit=_get_int("SHORT_CONTEXT_LIMIT", 20),
            max_chars=_get_int("SHORT_CONTEXT_MAX_CHARS", 1200),
            window_minutes=_get_int("SHORT_CONTEXT_WINDOW_MINUTES", 30),
        ),
        relationship=RelationshipSettings(
            owner_user_ids=_get_csv_set("KAKA_OWNER_USER_IDS"),
            familiar_input_count=_get_int("RELATIONSHIP_FAMILIAR_INPUT_COUNT", 100),
            familiar_recent_input_count=_get_int("RELATIONSHIP_FAMILIAR_RECENT_INPUT_COUNT", 30),
            familiar_active_memory_count=_get_int("RELATIONSHIP_FAMILIAR_ACTIVE_MEMORY_COUNT", 8),
            regular_input_count=_get_int("RELATIONSHIP_REGULAR_INPUT_COUNT", 30),
            regular_recent_input_count=_get_int("RELATIONSHIP_REGULAR_RECENT_INPUT_COUNT", 10),
            regular_active_memory_count=_get_int("RELATIONSHIP_REGULAR_ACTIVE_MEMORY_COUNT", 3),
            recent_days=_get_int("RELATIONSHIP_RECENT_DAYS", 7),
        ),
        persona=PersonaSettings(
            prompt_path=persona_prompt_path,
        ),
        admin=AdminSettings(
            local_only=_get_bool("ADMIN_LOCAL_ONLY", True),
            api_token=os.getenv("ADMIN_API_TOKEN", "").strip(),
        ),
    )
