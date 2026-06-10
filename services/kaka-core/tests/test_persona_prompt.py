from pathlib import Path

from kaka_core.config.settings import PersonaSettings
from kaka_core.context.builder import build_system_prompt
from kaka_core.persona.prompt import load_persona_prompt


def test_load_persona_prompt_from_file(tmp_path) -> None:
    prompt_path = tmp_path / "kaka_persona.md"
    prompt_path.write_text("你是测试版卡咔。\n", encoding="utf-8")

    prompt = load_persona_prompt(PersonaSettings(prompt_path=prompt_path))

    assert prompt.content == "你是测试版卡咔。"
    assert prompt.source == "file"
    assert prompt.path == str(prompt_path)
    assert prompt.fallback_used is False
    assert prompt.error is None


def test_load_persona_prompt_falls_back_when_file_missing(tmp_path) -> None:
    prompt_path = tmp_path / "missing.md"

    prompt = load_persona_prompt(PersonaSettings(prompt_path=prompt_path))

    assert "你是卡咔" in prompt.content
    assert prompt.source == "default"
    assert prompt.path == str(prompt_path)
    assert prompt.fallback_used is True
    assert prompt.error


def test_build_system_prompt_uses_loaded_persona_text(tmp_path) -> None:
    prompt_path = tmp_path / "persona.md"
    prompt_path.write_text("你是文件里的人设。", encoding="utf-8")
    prompt = load_persona_prompt(PersonaSettings(prompt_path=prompt_path))

    system_prompt = build_system_prompt(
        prompt,
        memory_results=[],
        speaker_name="测试用户",
        relationship=None,
    )

    assert system_prompt.startswith("你是文件里的人设。")


def test_repository_persona_prompt_is_persona_only() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    prompt = load_persona_prompt(PersonaSettings(prompt_path=repo_root / "prompts" / "kaka_persona.md"))

    assert "你是卡咔" in prompt.content
    assert "从数据海里跑出来的电子猫娘" in prompt.content
    assert "好奇的观察者" in prompt.content
    assert "回复规则" not in prompt.content
    assert "关系规则" not in prompt.content
    assert "记忆和上下文" not in prompt.content
    assert "输出规范" not in prompt.content
