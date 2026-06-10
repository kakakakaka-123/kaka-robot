# Kaka Plugin System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal, platform-agnostic plugin runtime to `kaka-core` so side capabilities can evolve without coupling to QQ, desktop, or future adapters.

**Architecture:** Plugins live in `kaka_core.plugins` and consume a normalized `PluginContext` built from `MessageEvent`. The runtime is disabled by default, supports command-style invocation first, and returns `PluginResult` objects that `kaka-core` converts to normal `KakaResponse` replies.

**Tech Stack:** Python 3.12, FastAPI service code, Pydantic protocol models, SQLAlchemy repository helpers, pytest.

---

### Task 1: Plugin Types and Registry

**Files:**
- Create: `services/kaka-core/src/kaka_core/plugins/__init__.py`
- Create: `services/kaka-core/src/kaka_core/plugins/base.py`
- Create: `services/kaka-core/src/kaka_core/plugins/context.py`
- Create: `services/kaka-core/src/kaka_core/plugins/result.py`
- Create: `services/kaka-core/src/kaka_core/plugins/registry.py`
- Test: `services/kaka-core/tests/test_plugins.py`

- [ ] **Step 1: Write failing tests for plugin context, result, and registry**

Create `services/kaka-core/tests/test_plugins.py` with tests that construct a `MessageEvent`, build a `PluginContext`, register a fake plugin, and resolve it by ID.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: import failure for `kaka_core.plugins`.

- [ ] **Step 3: Implement minimal plugin types**

Define `PluginContext`, `PluginResult`, `KakaPlugin`, and `PluginRegistry`. Keep them platform-agnostic: no QQ, NoneBot, desktop, or adapter imports.

- [ ] **Step 4: Run plugin tests**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: new plugin tests pass.

### Task 2: Plugin Settings and Runtime

**Files:**
- Modify: `services/kaka-core/src/kaka_core/config/settings.py`
- Create: `services/kaka-core/src/kaka_core/plugins/runtime.py`
- Test: `services/kaka-core/tests/test_plugins.py`

- [ ] **Step 1: Write failing tests for disabled runtime and command invocation**

Add tests proving that disabled runtime returns `None`, and enabled runtime only handles explicit plugin commands such as `插件：echo hello`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: missing `PluginRuntime` or settings field failure.

- [ ] **Step 3: Add plugin settings and runtime**

Add `PluginSettings(enabled: bool, command_prefixes: tuple[str, ...])` and load `PLUGIN_SYSTEM_ENABLED=false` by default. Implement command parsing and safe plugin execution with exception-to-result handling.

- [ ] **Step 4: Run plugin tests**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: runtime tests pass.

### Task 3: Memory Search Plugin

**Files:**
- Create: `services/kaka-core/src/kaka_core/plugins/builtin/__init__.py`
- Create: `services/kaka-core/src/kaka_core/plugins/builtin/memory_search.py`
- Test: `services/kaka-core/tests/test_plugins.py`

- [ ] **Step 1: Write failing memory plugin test**

Add a test that creates active memories for a user, invokes `memory_search`, and verifies the result text contains matching memory text without referencing QQ.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: import failure for `MemorySearchPlugin`.

- [ ] **Step 3: Implement memory search plugin**

Use existing `search_user_memories()` and `MemorySearchFilters`. Return a concise `PluginResult.text` when memories are found, and a clear empty-result text when none are found.

- [ ] **Step 4: Run plugin tests**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: memory plugin tests pass.

### Task 4: Chat Service Integration

**Files:**
- Modify: `services/kaka-core/src/kaka_core/chat/service.py`
- Test: `services/kaka-core/tests/test_chat_service.py`
- Test: `services/kaka-core/tests/test_plugins.py`

- [ ] **Step 1: Write failing chat integration tests**

Add tests proving normal chat behavior is unchanged when plugins are disabled, and explicit plugin command returns a plugin-backed `KakaResponse` when enabled.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_chat_service.py services\kaka-core\tests\test_plugins.py -q`

Expected: enabled plugin command is not handled yet.

- [ ] **Step 3: Integrate runtime before LLM generation**

In `generate_chat_response()`, after duplicate-event reservation and before normal LLM flow, call the plugin runtime. If it returns a result, convert it to `KakaResponse.text_reply`, attach plugin metadata, record the conversation, and return.

- [ ] **Step 4: Run integration tests**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_chat_service.py services\kaka-core\tests\test_plugins.py -q`

Expected: tests pass.

### Task 5: n8n Webhook External Plugin

**Files:**
- Create: `services/kaka-core/src/kaka_core/plugins/builtin/n8n_webhook.py`
- Modify: `services/kaka-core/src/kaka_core/plugins/runtime.py`
- Modify: `services/kaka-core/src/kaka_core/plugins/__init__.py`
- Modify: `services/kaka-core/src/kaka_core/plugins/builtin/__init__.py`
- Modify: `services/kaka-core/src/kaka_core/config/settings.py`
- Modify: `.env.example`
- Test: `services/kaka-core/tests/test_plugins.py`
- Test: `services/kaka-core/tests/test_chat_service.py`

- [ ] **Step 1: Write failing tests for n8n webhook behavior**

Add tests proving `插件：n8n github_trending ai agent` posts a platform-agnostic payload to `<base-url>/github_trending`, converts `{ "text": "...", "data": {}, "metadata": {} }` into `PluginResult`, and reports a clear configuration error when the base URL is missing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py -q`

Expected: import failure for `N8nWebhookPlugin`.

- [ ] **Step 3: Implement n8n webhook plugin**

Create `N8nWebhookPlugin` with ID `n8n`. It parses the first command token as the workflow name, posts normalized context to the workflow webhook, supports plain text or JSON responses, and returns `PluginResult`.

- [ ] **Step 4: Register n8n plugin by default**

Add `PLUGIN_N8N_WEBHOOK_BASE_URL` and `PLUGIN_N8N_WEBHOOK_TIMEOUT` to settings, pass them into `create_default_plugin_runtime()`, and include the plugin in the default registry. Keep `PLUGIN_SYSTEM_ENABLED=false` by default.

- [ ] **Step 5: Run n8n plugin tests**

Run: `.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_plugins.py services\kaka-core\tests\test_chat_service.py -q`

Expected: tests pass.

### Task 6: Verification and Commit

**Files:**
- All files changed above.

- [ ] **Step 1: Run Python regression**

Run: `.\.venv\Scripts\python.exe -m pytest packages\kaka-protocol\tests services\kaka-core\tests apps\qq-adapter\tests`

Expected: all tests pass.

- [ ] **Step 2: Run diff check**

Run: `git diff --check`

Expected: exit 0.

- [ ] **Step 3: Commit plugin system**

Run:

```powershell
git add services/kaka-core/src/kaka_core/plugins services/kaka-core/src/kaka_core/config/settings.py services/kaka-core/src/kaka_core/chat/service.py services/kaka-core/tests/test_plugins.py services/kaka-core/tests/test_chat_service.py docs/superpowers/plans/2026-06-10-kaka-plugin-system.md
git commit -m "feat: add kaka plugin runtime"
```
