# Kaka Robot Framework

Kaka is a modular robot framework for experimenting with a core "brain" service, platform adapters, long-term memory, local admin tools, and external workflow plugins.

This public repository contains the framework code only. Private persona prompts, local runtime data, development logs, and project-specific creative material are intentionally not included.

## Architecture

```text
Platform adapters
  -> kaka-protocol MessageEvent
  -> kaka-core
  -> LLM / memory / plugins / notifications
  -> kaka-protocol KakaResponse
  -> platform adapters
```

Main parts:

- `packages/kaka-protocol`: shared message and response models.
- `services/kaka-core`: FastAPI core service, memory storage, LLM routing, plugin runtime, admin API.
- `apps/qq-adapter`: QQ/OneBot adapter using NoneBot2.
- `apps/web-console`: local admin console for memory and runtime inspection.
- `docs/n8n`: n8n workflow for a GitHub project radar weekly digest.

## Local Setup

Use Python 3.12+ and Node.js 22+.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .\packages\kaka-protocol
.\.venv\Scripts\python.exe -m pip install -e .\services\kaka-core
.\.venv\Scripts\python.exe -m pip install -e .\apps\qq-adapter
```

Create local config:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` locally. Do not commit real tokens or local database files.

Start core:

```powershell
.\.venv\Scripts\python.exe .\services\kaka-core\run.py
```

Start QQ adapter:

```powershell
.\.venv\Scripts\python.exe .\apps\qq-adapter\bot.py
```

Open local admin console:

```text
http://127.0.0.1:8001/admin
```

## n8n Plugin

The included n8n workflow can generate a weekly GitHub project radar digest:

```text
docs/n8n/github_weekly_stars.workflow.json
```

Command trigger through the internal plugin system:

```text
插件：n8n github_weekly_stars
```

If n8n runs in Docker on Windows, set container environment variables like:

```env
KAKA_CORE_BASE_URL=http://host.docker.internal:8001
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest packages\kaka-protocol\tests apps\qq-adapter\tests docs\tests -q
node -e "JSON.parse(require('fs').readFileSync('docs/n8n/github_weekly_stars.workflow.json','utf8')); console.log('workflow json ok')"
npm --prefix apps\web-console run build
```

## Public Scope

This repository is a public-safe framework snapshot. It excludes:

- `.env` and real tokens.
- Runtime data under `data/`.
- Private persona prompts.
- Development logs and handoff notes.
- Private project plans and creative character documents.
