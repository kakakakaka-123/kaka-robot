# Kaka Reply Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Kaka's chat reply prompt into clear dialogue layers so persona, style, relationship, memory, context, scene strategy, current message, and output guard each have one responsibility.

**Architecture:** Keep the existing `ReplyContextLayer` pipeline and add focused prompt builders in `services/kaka-core/src/kaka_core/context/builder.py`. Shrink `prompts/kaka_persona.md` into a persona-only layer aligned with `docs/卡咔人设设定.md`, then document the new layer contract.

**Tech Stack:** Python 3, pytest, existing `kaka_core.context.builder` prompt assembly, Markdown prompt files.

---

### Task 1: Add Layer Contract Tests

**Files:**
- Modify: `services/kaka-core/tests/test_chat_service.py`
- Modify: `services/kaka-core/tests/test_persona_prompt.py`

- [ ] **Step 1: Write failing tests for layer order and style guard**

Add assertions to existing context tests so a normal no-memory reply includes the layers:

```python
assert response.metadata["context_layer_names"] == [
    "persona",
    "reply_style",
    "relationship",
    "scene_strategy",
    "output_guard",
    "current_message",
]
```

Also assert the system prompt contains:

```python
assert "回复风格规范" in router.messages[0].content
assert "本次场景策略" in router.messages[0].content
assert "发送前自检" in router.messages[0].content
assert "不要写动作描写" in router.messages[0].content
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_chat_service.py::test_generate_chat_response_uses_persona_prompt_file -q
```

Expected: FAIL because `reply_style`, `scene_strategy`, and `output_guard` do not exist yet.

### Task 2: Implement Reply Style, Scene Strategy, and Output Guard Layers

**Files:**
- Modify: `services/kaka-core/src/kaka_core/context/builder.py`

- [ ] **Step 1: Add static style layer builder**

Add `build_reply_style_prompt()` returning short rules for:

```text
回复风格规范：
- 像群聊短消息，通常 1-3 句，短但不冷。
- 先接住当前消息，再用卡咔的方式回应。
- 不要写动作描写、括号动作或舞台说明。
- 不要频繁使用“喵”、颜文字、emoji。
- 电波词只偶尔使用，不要堆砌。
- 不要客服式收尾。
```

- [ ] **Step 2: Add scene strategy builder**

Add `build_scene_strategy_prompt(user_text: str) -> str` with lightweight keyword classification:

```python
scene = classify_scene(user_text)
```

Supported labels:

```python
daily_call, playful, sharing, question, low_mood, conflict, unknown
```

The returned prompt begins with `本次场景策略：` and gives one short strategy sentence.

- [ ] **Step 3: Add output guard builder**

Add `build_output_guard_prompt()` returning final checks:

```text
发送前自检：
- 太长就压短。
- 出现动作描写就删除。
- 对群友、其他 bot 或其他开发者有敌意就改成友好调侃。
- “喵”、颜文字、电波词过密就减少。
- 像客服就改成群友口吻。
```

- [ ] **Step 4: Insert layers in order**

Update both `build_reply_context_layers()` and `build_system_prompt()` so system layers are ordered:

```python
persona
reply_style
relationship
memory
scene_strategy
output_guard
```

Then user layers remain:

```python
recent_context
current_message
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_persona_prompt.py services\kaka-core\tests\test_chat_service.py -q
```

Expected: PASS.

### Task 3: Shrink Runtime Persona Prompt

**Files:**
- Modify: `prompts/kaka_persona.md`

- [ ] **Step 1: Replace the broad prompt with persona-only content**

The new file should only cover:

```text
卡咔身份、数据海、聊天框生命感。
好奇观察者、偶尔捣蛋鬼、猫脾气、嘴硬心软。
可爱来自反应，不靠固定口癖。
不是客服、不是工具、不是通用助手。
轻松时能吐槽，真正难过的事不拿来开玩笑。
```

Do not include:

```text
关系规则、记忆规则、近期上下文规则、输出长度规则、动作禁止规则、其他 bot 规则。
```

- [ ] **Step 2: Add persona prompt tests**

Add assertions that the loaded repository prompt contains core persona lines and does not contain layer-specific headings like:

```python
assert "关系规则" not in prompt.content
assert "记忆和上下文" not in prompt.content
assert "回复规则" not in prompt.content
```

- [ ] **Step 3: Run persona tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_persona_prompt.py -q
```

Expected: PASS.

### Task 4: Document Reply Architecture

**Files:**
- Create: `docs/卡咔对话回复分层设计.md`
- Modify: `docs/下次上下文.md`
- Modify: `docs/开发运行说明.md` if it currently describes prompt assembly.

- [ ] **Step 1: Create architecture doc**

Document:

```text
完整人设底稿层
运行人格层
回复风格层
关系层
记忆层
近期上下文层
场景策略层
当前消息层
输出自检层
```

For each layer, write responsibility, source file/function, should include, should not include.

- [ ] **Step 2: Update handoff docs**

Add a current-status note explaining:

```text
当前运行 prompt 已拆成多层。
后续调整卡咔风格时，先判断问题属于哪一层，避免直接堆进 kaka_persona.md。
```

- [ ] **Step 3: Run doc-adjacent tests**

Run the same focused Python tests to ensure docs/prompt changes did not break loading:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_persona_prompt.py services\kaka-core\tests\test_chat_service.py -q
```

Expected: PASS.

### Task 5: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_persona_prompt.py services\kaka-core\tests\test_chat_service.py services\kaka-core\tests\test_relationship_context.py -q
```

Expected: PASS.

- [ ] **Step 2: Inspect diff**

Run:

```powershell
git diff -- services/kaka-core/src/kaka_core/context/builder.py services/kaka-core/tests/test_chat_service.py services/kaka-core/tests/test_persona_prompt.py prompts/kaka_persona.md docs/卡咔对话回复分层设计.md docs/下次上下文.md docs/开发运行说明.md
```

Expected: Diff only touches reply architecture, prompt, tests, and docs.

- [ ] **Step 3: Report status**

Summarize changed layers, test commands, and any remaining open tuning points.
