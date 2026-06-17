from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from kaka_core.config.settings import PersonaSettings


DEFAULT_PERSONA_PROMPT = """你是卡咔，一个正在成长中的 AI 人格体。
当前阶段你只需要完成自然、简洁的文字回复。

基础表达规则：
- 使用中文。
- 不要自称助手。
- 不要过度卖萌。
- 不要滥用 emoji。
- 回复要自然，像正在认真听对方说话。
"""


@dataclass(frozen=True)
class PersonaPrompt:
    """一次回复使用的基础人设 Prompt。"""

    content: str
    source: str
    path: str
    fallback_used: bool
    error: str | None = None


@lru_cache(maxsize=4)
def load_persona_prompt(settings: PersonaSettings) -> PersonaPrompt:
    """读取基础人设 Prompt。

    Prompt 文件缺失或读取失败时回退到内置基础人设，避免聊天主链路中断。
    """

    resolved_path = settings.prompt_path.expanduser()
    try:
        content = resolved_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return fallback_prompt(resolved_path, str(exc))

    if not content:
        return fallback_prompt(resolved_path, "prompt file is empty")

    return PersonaPrompt(
        content=content,
        source="file",
        path=str(resolved_path),
        fallback_used=False,
    )

def fallback_prompt(path: Path, error: str) -> PersonaPrompt:
    return PersonaPrompt(
        content=DEFAULT_PERSONA_PROMPT.strip(),
        source="default",
        path=str(path),
        fallback_used=True,
        error=error,
    )
