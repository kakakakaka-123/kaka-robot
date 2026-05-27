# 卡咔项目交接文档

本文档用于在新的对话框中快速恢复上下文。下一个对话框只要先阅读本文档，就应该能理解卡咔的目标、技术路线、用户偏好、旧项目经验和下一步工作。

## 0. 最新交接摘要

当前日期：2026-05-27。
当前项目目录：

```text
D:\Python\AgentRobot\kaka-v2
```

本轮对话已经完成第一阶段地基的关键闭环：

```text
统一消息协议
-> kaka-core FastAPI 服务
-> DeepSeek LLM 接入
-> qq-adapter 文本适配
-> NoneBot2 + OneBot V11 + NapCat 真实 QQ 文本闭环
-> SQLite 基础消息和回复记录
-> 群聊普通消息观察记录
-> 最近对话筛选查看
-> 最小输入分析脚本
-> 长期记忆候选表 memory_candidates
-> 批量 LLM 记忆候选判断和写入流程
-> 候选区查看脚本
-> 程序内置整点自动候选分析
-> 自动任务运行记录 auto_job_runs
-> 正式长期记忆表 memories
-> 候选区合并脚本
-> 候选区合并核心模块 kaka_core.memory.merge
-> 候选区 LLM 复核脚本 review_memory_candidates.py
-> 程序内置整点自动候选区复核
-> 正式记忆管理脚本 manage_memories.py
-> 回复前长期记忆注入
-> 配置模板和本地自检
-> 第一版长期记忆设计
-> 本地 Web 管理台 /admin
-> 正式记忆倒序分页、归档、恢复、硬删除、新增和编辑
-> 提示预演和对话复盘
-> 回复前短期上下文注入
-> 回复前关系上下文注入
-> 基础人设 Prompt 文件化
-> 运行版 Prompt 真实 LLM 回放调参
-> 桌宠客户端第一版本地身体原型
-> 桌宠系统托盘基础入口
```

当前真实状态：

- 已创建项目专用虚拟环境 `.venv`，后续不要直接使用系统 Python。
- 已创建并安装本地包 `packages/kaka-protocol`。
- 已创建并安装本地包 `services/kaka-core`。
- 已创建并安装本地包 `apps/qq-adapter`。
- `kaka-core` 可以启动 FastAPI，访问 `http://127.0.0.1:8001/docs`。
- `/v1/chat` 已经可以接收 `MessageEvent`，调用 DeepSeek，并返回 `KakaResponse`。
- `/v1/observe` 已经可以只记录消息，不调用模型、不回复。
- `qq-adapter` 已经接入 NoneBot2 和 OneBot V11。
- NapCat 已经能把真实 QQ 私聊和群聊文本消息转发到当前项目。
- 卡咔已经可以在 QQ 中通过 DeepSeek 生成文本回复。
- 群聊已加触发限制：私聊全回复，群聊只在 @机器人 或包含“卡咔”时回复；普通群聊文本不回复，但会写入 `inputs` 作为观察记录。
- `kaka-core` 已经接入 SQLite 基础记录，默认文件为 `data/kaka.sqlite3`；`inputs` 记录卡咔收到/观察到的输入，`outputs` 记录卡咔对已处理输入形成的输出结果或响应决策，`memory_candidates` 记录长期记忆候选，`memories` 记录已合并的正式长期记忆，`auto_job_runs` 记录自动候选分析/复核的运行结果。
- `inputs` 只保留后续分析状态 `analysis_status`；`outputs` 记录 `output_origin / output_reason / no_reply_reason`。旧 SQLite 会自动把 `messages/responses` 迁移为 `inputs/outputs`，不会清空已有数据。
- 已有最近对话查看脚本，支持按 `inputs.id`、数量、群、用户、日期、场景、是否输出、输出来源和输出原因筛选，并把 UTC 时间显示为北京时间。
- 已有最小输入分析脚本，支持扫描 `inputs.analysis_status=not_analyzed`，可按 `inputs.id`、群、用户、日期、私聊、群聊筛选；`--llm-batch` 只读批量判断 `not_sure`，`--write-candidates` 才写入 `memory_candidates` 并标记 `analyzed/skipped`。
- 已有 `show_memory_candidates.py`，可查看 `memory_candidates`，支持按 `memory_candidates.id`、状态、类型、群、用户、日期筛选。
- 已有 `merge_memory_candidates.py`，默认只读预览 pending 候选，加 `--apply` 后合并到正式 `memories` 表；合并时按用户、类型、归一化文本做基础去重；脚本顶部可直接填 `PYCHARM_CANDIDATE_IDS / PYCHARM_APPLY`。
- 已有 `review_memory_candidates.py`，可在测试阶段用 LLM 复核候选区，默认只读预览，加 `--apply` 后按 approve/reject/duplicate 写入正式记忆或更新候选状态；脚本顶部可直接填 `PYCHARM_CANDIDATE_IDS / PYCHARM_APPLY`。
- 已有程序内置自动候选区复核：通过 `.env` 的 `MEMORY_AUTO_REVIEW_ENABLED=true` 开启；kaka-core 启动后等到下一个整点检查，`memory_candidates.pending >= 20` 时最多跑一批，每批 10 条。
- 已有 `show_memories.py`，可查看正式 `memories`，支持按 `memories.id`、状态、类型、来源、群、用户、日期筛选。
- 已有 `manage_memories.py`，可把正式记忆切到 `active` / `archived`，或在确认错误、垃圾、敏感时硬删除；脚本顶部已提供 PyCharm 简单配置 `PYCHARM_MEMORY_IDS / PYCHARM_ACTION / PYCHARM_APPLY`，用户用数据库可视化软件看到 `memories.id` 后可以直接填 ID 预览或执行。
- 已有 `search_memories.py`，可按当前用户和当前消息，只读预览会命中的少量正式记忆，并打印分数和命中原因；脚本顶部可直接填 `PYCHARM_USER_ID / PYCHARM_TEXT / PYCHARM_GROUP_ID`；`kaka-core` 回复前已复用同一套检索逻辑注入少量正式记忆。
- 已有程序内置自动候选分析：通过 `.env` 的 `MEMORY_AUTO_ANALYSIS_ENABLED=true` 开启；kaka-core 启动后等到下一个整点检查，`not_analyzed >= 50` 时最多跑两轮，每轮最多 50 条。
- 已有自动任务运行记录：自动候选分析和自动候选区复核每次检查都会写入 `auto_job_runs`，状态为 `success / skipped / failed`；`/admin` 运行状态页会显示最近记录，并支持手动触发一次自动分析或复核。
- 已有跨进程自动任务锁：自动候选分析和自动候选区复核会通过 `auto_job:*` 锁避免多个 `kaka-core` 进程在整点或手动触发时重复执行；拿不到锁会记录为 `skipped`。
- 已做一轮长期记忆 E2E 合成数据回放，已验证分析、候选写入、LLM 复核、正式记忆查看和检索脚本的完整链路。
- `show_recent_conversations.py`、`show_memory_candidates.py`、`merge_memory_candidates.py`、`review_memory_candidates.py`、`show_memories.py`、`manage_memories.py`、`search_memories.py`、`analyze_inputs.py`、`seed_memory_e2e_data.py` 和 `doctor.py` 已在文件顶部写明 PyCharm 右键运行方式和可用参数；数据脚本优先提供 `PYCHARM_*` 简单配置，写库默认关闭；用户不熟悉命令行参数，后续新增类似脚本也要沿用这个风格。
- 已有根目录 `.env.example` 配置模板。
- 已有 `scripts/doctor.py` 本地自检脚本，用于检查配置形状、数据库、导入和端口状态。
- 已有 `docs/长期记忆设计.md`，明确第一版记什么、不记什么、`memories` 表建议和抽取规则。
- 已有本地 Web 管理台：前端在 `apps/web-console`，`kaka-core` 托管 `/admin`，管理 API 在 `/admin/api/*`；当前 Web 界面只暴露系统总览、正式记忆、提示预演、对话复盘、运行状态和预留扩展入口。最近对话、输入分析、候选区等后台能力仍保留在 API、脚本和数据库中，不再作为日常 Web 页面暴露。
- 已有桌宠客户端第一版：前端和 Tauri 工程在 `apps/desktop-pet`，技术组合为 Tauri 2 + React/Vite + TypeScript + PixiJS。当前是透明、无边框、置顶的 `280x280` 桌面窗口，已接入 12 张桌宠透明 PNG 状态图，支持右键状态菜单、退出、轻点摸头、拖拽窗口、拖拽反应恢复、2 分钟闲置睡觉、睡眠唤醒、窗口位置记忆、随机待机气泡/小动作、`kaka-core /health` 连接测试和消息气泡雏形。已新增系统托盘基础入口：托盘图标、显示/隐藏、重置位置、连接测试和退出。桌宠当前还没有接入 `kaka-core /v1/chat` 对话。
- Web 管理台已成为正式记忆的日常查看和管理入口；脚本现在主要留给开发、测试、批量修复、候选/输入后台处理和应急排查。
- 近期已补上跨进程事件处理锁和 SQLite 时间戳修正，重复聊天事件在绕过进程内锁时也不会重复调用 LLM；管理总览继续脱敏 `database_url`。
- 输入分析和候选区的写库能力仍保留在管理 API、脚本和数据库层；Web 日常页面暂不暴露这些后台处理入口。
- 正式记忆页按 `memories.id` 倒序显示，支持每页 50 条分页、`active / archived / all` 切换、新增、编辑、归档、恢复和确认后的硬删除；新增、归档、恢复、删除后会刷新分页，保证仍按最新 ID 倒序展示；危险写库动作都有确认弹窗。
- 手动新增正式记忆会写入 `source="manual"`，默认 `merge_reason="手动新增"`；编辑会同步更新 `memory_text / normalized_text / memory_type / confidence / source_text / status / merge_reason`，也可调整用户和群/私聊场景。
- 提示预演页会同时请求正式记忆检索和回复上下文预览，展示 System Prompt、User Prompt、metadata、`used_memory_ids` 和命中数量，方便确认真实回复前会给模型什么上下文。
- 对话复盘页只回查卡咔已经回复过的真实对话记录，列表每页 50 条；详情会从 `outputs.metadata.used_memory_ids` 和 `short_context_input_ids` 反查当次回复命中的正式记忆与短期上下文，短期上下文在左、正式记忆在右，并使用固定高度滚动窗口。
- 基础人设 Prompt 已从代码拆到 `prompts/kaka_persona.md`；`KAKA_PERSONA_PROMPT_PATH` 可改路径，文件缺失或为空时回退到内置基础人设；metadata 会记录 `persona_prompt_source / persona_prompt_path / persona_prompt_fallback_used`。
- 2026-05-19 曾按用户要求回退强化人设实验：删除当时越改越复杂的完整人设设定、三层人格定义和人设评测脚本，`prompts/kaka_persona.md` 回到最小基础人格 Prompt。
- 2026-05-23 已重新进入人设方向收口：用户确认早期“电波系观测者 · 电子猫娘”方向是满意版本，之前是后续越改越乱才回退；当前将 `docs/卡咔人设设定.md` 作为长期人设底稿纳入项目，不作为运行 Prompt 直接注入。
- 2026-05-23 已更新实际运行 Prompt `prompts/kaka_persona.md`：卡咔是一只从数据海里跑出来的电子猫娘，短回复，猫感，轻微电波，嘴硬心软，对创造者大人更信任和放松，创造者大人有最高摸头权限；长期记忆和短期上下文只在相关时自然使用。
- 2026-05-23 已新增 `docs/卡咔场景反应样例.md`，当前包含 20 个典型小剧场样例，用作判断卡咔回复是否像卡咔的行为标尺，不会被程序直接读取。
- 2026-05-23 已新增 `docs/卡咔负面情绪处理规则.md`，定位为“卖萌缓冲 / 陪住 / 挡一下情绪 / 不心理辅导”的风格规则；即使遇到很重的负面表达，卡咔也不切成心理辅导或安全客服，不在回复里写现实处理流程，而是保持统一猫感和陪伴风格。
- 2026-05-24 已按用户允许，在真实 SQLite 数据库插入一批人设测试输入，并真实调用 DeepSeek 回放卡咔回复；测试前缀包括 `codex-persona-`、`codex-persona2-`、`codex-persona3-`、`codex-persona4-`、`codex-persona5-`，共 29 条，`inputs.id=9823..9851`，均已标记为 `analysis_status=skipped`，避免进入长期记忆候选分析。
- 2026-05-24 已根据真实 LLM 输出和真实 QQ 群聊继续微调 `prompts/kaka_persona.md`：补强普通群友摸头的“权限不足 / 临时访客认证 / 三个问题”反应，避免好感度协议；补强被叫 AI、创造者大人关系、负面情绪短句缓冲、技术回答去客服化、记忆缺失边界；随后根据真实群聊输出继续收紧为无动作描写、短但不冷、不模仿其他 bot 口癖/颜文字、不接力续写长小剧场、同群 bot 友好共存。
- 回复上下文已整理为显式层：`persona / relationship / memory / recent_context / current_message`；metadata 会记录 `context_layer_names`，`/admin` 提示预演页会展示 Prompt Layers。
- 已接入第一版短期上下文：回复前从同场景最近输入和输出中读取上下文，默认只看最近 30 分钟，最多 20 条输入记录、总计 1200 字，排除当前消息；metadata 会记录 `short_context_enabled / short_context_count / short_context_input_ids`。
- 已完成关系上下文简化：现在只通过 `KAKA_OWNER_USER_IDS` 判断 `special`（创造者大人）或 `normal`（普通群友）；不再按历史输入数、最近输入数或 active 正式记忆数推断多级熟悉度。metadata 只记录 `relationship_level / relationship_is_owner`；熟悉感由短期上下文和长期记忆自然承担。
- 脚本现在定位为开发、测试、排查和应急备用入口；用户日常管理优先使用网页。
- 已经创建根目录 `.env`，其中有 DeepSeek API Key。`.env` 被 `.gitignore` 忽略，不要把 Key 写进任何文档或回复。

当前测试和验证结果：

```text
kaka-protocol：5 passed（历史完整测试记录）
kaka-core：117 passed（2026-05-24 当前完整后端测试）
qq-adapter：18 passed（历史完整测试记录）
doctor：69 OK, 3 WARN, 0 FAIL
web-console：npm run build passed
2026-05-05 管理 API、对话复盘、自动任务和记忆上下文相关测试：120 passed
2026-05-05 web-console：npm run build passed
2026-05-05 git diff --check：passed
2026-05-19 全量 pytest：143 passed
2026-05-19 web-console：npm run build passed
2026-05-19 compileall：passed
2026-05-19 git diff --check：passed
2026-05-23 人设运行 Prompt、场景样例和负面情绪规则：仅文档/Prompt 改动，未改 Python/前端代码，未重新跑全量测试
2026-05-24 真实库人设回放：已真实调用 DeepSeek；无效编码轮和有效测试轮均已标记 skipped；仅调整 prompts/kaka_persona.md 和文档
2026-05-24 关系上下文简化：`services/kaka-core/tests` 全量 117 passed；`git diff --check` passed（仅 CRLF 提示）
2026-05-24 运行人设继续调优：真实 QQ 群聊发现回复过长、动作复发、模仿其他 bot、对同群 bot/开发者有敌意等问题；已更新运行 Prompt 和上下文拼接规则；`test_persona_prompt.py / test_chat_service.py / test_admin_api.py` 定向 36 passed
2026-05-27 desktop-pet：`npm run build` passed
2026-05-27 desktop-pet/src-tauri：`cargo check` passed
2026-05-27 desktop-pet 系统托盘基础版：`npm run build` passed；`cargo check` passed；`cargo test` passed；`npm run tauri:build` passed
用户 2026-05-05 实测：当前真实链路暂无大问题
真实数据库状态写入验证：通过
浏览器管理台回放：通过
```

验证过的真实库状态操作：

```text
inputs.id=796 -> analysis_status=skipped
memory_candidates.id=42 -> approved -> rejected -> approved
```

长期记忆 E2E 回放状态：

```text
测试前缀：codex-e2e- / codex-llm-tool- / codex-admin-api-
测试结果：已在真实库中验证分析、复核、管理和注入链路
清理结果：相关临时输入、候选和记忆记录已清空
```

2026-05-01 用户完成真实 QQ 链路测试，反馈表结构调整后的功能没有问题：

```text
普通群聊消息：只写入 inputs，不回复
私聊：写入 inputs 和 outputs，并正常回复
群聊 @卡咔：写入 inputs 和 outputs，并正常回复
群聊包含“卡咔”：写入 inputs 和 outputs，并正常回复
最近对话筛选查看：正常
```

下一个对话框最应该继续做：

```text
先阅读本交接文档和 docs/下次上下文.md；如果继续桌宠方向，优先阅读 `docs/桌宠开发说明.md`。当前建议先完善常驻体验：开机自启、设置窗口、托盘菜单状态优化；暂时不急着接完整大模型聊天。如果后续明确要做桌宠对话，再做 `apps/desktop-pet` 到 `kaka-core /v1/chat` 的最小接入：固定输入或小输入框 -> `platform=desktop` 的 `MessageEvent` -> 气泡显示回复 -> 根据请求/回复/失败切换加载中、收到消息、开心或信号弱。如果继续人设调试，优先阅读 `prompts/kaka_persona.md`、docs/卡咔人设设定.md、docs/卡咔场景反应样例.md、docs/卡咔负面情绪处理规则.md；当前运行 Prompt 已经过真实 LLM 小样本回放和真实 QQ 群聊回放，下一步继续小范围观察“甜但不腻、短但不冷、无动作、同群 bot 友好共存”是否稳定；如果继续功能验收，检查正式记忆倒序分页、新增、编辑、归档、恢复、硬删除、提示预演和对话复盘；输入分析和候选区如需处理，走管理 API、脚本或数据库；之后再观察自动候选分析、自动候选区复核、回复时长期记忆使用是否稳定
```

第一目标仍然只做文本：

```text
QQ 发一句话
-> qq-adapter 收到
-> 转成 MessageEvent
-> kaka-core 读取基础人设 Prompt 文件
-> kaka-core 按 persona / relationship / memory / recent_context / current_message 分层组装回复上下文
-> kaka-core 回复前检索少量 active 长期记忆并组装 prompt，或只观察记录
-> kaka-core 回复前读取同场景最近 30 分钟内最多 20 条短期上下文
-> kaka-core 回复前注入关系上下文，只区分创造者大人和普通群友
-> 返回 KakaResponse
-> qq-adapter 发回 QQ 文本或不回复
-> SQLite 记录消息，触发回复时记录输出
-> 最近对话脚本可以查到观察记录和回复记录
-> 满足条件时自动整理 memory_candidates 候选区
-> 自动候选复核满足条件时把 pending 候选写入 memories，或继续手动用 LLM 复核脚本确认
-> 用户偶尔查看 memories，不合适的记忆优先在 /admin 归档，确认错误、垃圾或敏感再硬删除
-> 用户日常用 /admin 管理正式 memories；inputs 和 memory_candidates 保留给管理 API、脚本和数据库处理
```

暂时不要做图片、表情包、语音和复杂主动行为。下一步先保持真实 QQ 对话运行，观察新运行 Prompt 的回复味道是否稳定：甜但不腻、短但不冷、无动作描写、不被其他 bot 口癖带跑、不对同群 bot 或开发者表现敌意，同时继续观察自动记忆链路和回复中的记忆使用效果。

## 1. 当前状态

项目目录：

```text
D:\Python\AgentRobot\kaka-v2
```

旧项目目录：

```text
D:\Python\AgentRobot\nonebot-kaka
```

当前已经创建：

```text
README.md
卡咔电子生命系统设计文档.md
KAKA_HANDOFF.md
.env
.env.example
.gitignore
.venv/
apps/
data/
deploy/
docs/
packages/
scripts/
services/
开发日志/
```

`卡咔电子生命系统设计文档.md` 是项目的总体设计蓝图。
`KAKA_HANDOFF.md` 是本文件，用于给下一个对话框恢复记忆。

目前关键代码目录：

```text
packages/kaka-protocol/
  src/kaka_protocol/
    enums.py
    messages.py
    responses.py
  tests/

services/kaka-core/
  run.py
  scripts/
    analyze_inputs.py
    show_recent_conversations.py
  src/kaka_core/
    api/
    chat/
    config/
    llm/
    storage/
  tests/

apps/qq-adapter/
  src/qq_adapter/
    actions.py
    config.py
    core_client.py
    pipeline.py
    qq_event.py
  tests/
```

## 2. 用户背景和目标

用户是大二下学期，物联网工程专业。

用户当前并不希望只做一个普通 QQ 机器人，而是想长期探索一个更接近“电子生命”的 AI 项目。用户知道这个目标有理想化成分，但希望在当前技术能力范围内尽可能接近。

用户希望卡咔：

- 有自己的记忆。
- 有稳定但会成长的性格。
- 有自己的状态、情绪、生活痕迹。
- 能认识不同的人。
- 能和主人、群友形成不同关系。
- 能随着经历改变。
- 能看到文字、图片、视频、网页、语音。
- 能发文字、图片、表情包、语音、视频或其他媒体。
- 能使用功能工具，例如 B 站视频解析、总结、日记、群聊管理等。
- 未来可以接入硬件，做 AIoT 方向。
- 未来可能成为毕设项目，甚至成为一个 IP。

用户明确说过：

> 想创造一个电子生命，让她活过来。

实际工程上需要明确边界：

卡咔不会真正拥有人的意识，但可以通过长期记忆、人格状态、关系系统、主动行为、多模态感知和具身化接口，尽可能表现出连续性、个性和生命感。

## 3. 用户希望的协作方式

用户希望自己主要负责：

- 决策方向。
- 判断卡咔是什么样的存在。
- 判断某个技术是否值得用。
- 测试卡咔的表现。
- 逐步学习每个技术是干什么的。

用户不希望自己一开始就必须看懂所有代码。

开发者应该负责：

- 设计架构。
- 编写代码。
- 解释每个技术的作用。
- 每次改动说明改了什么、为什么改。
- 不要盲目堆功能。
- 尽量保持项目清晰、可学习、可维护。

回答风格：

- 使用中文。
- 直接、务实。
- 不要过度安慰。
- 用户迷茫时要帮他拆清楚问题。
- 写代码之前尽量说明当前阶段目标。
- 避免一次性把复杂概念全部压给用户。

## 4. 旧项目 nonebot-kaka 的经验

旧项目是 NoneBot2 + OneBot V11 的 QQ 机器人，名字也是卡咔。

旧项目已经做过很多功能，包括：

- QQ 群聊和私聊交互。
- LLM 对话。
- 卡咔早期对话 prompt。
- 长期记忆系统。
- 用户画像系统。
- 关系系统。
- 卡咔状态系统。
- 每日生活系统。
- 语气自适应系统。
- 跨群见闻。
- 社交大脑。
- 主动回复。
- 日记。
- 群聊总结。
- B 站解析。
- 词云。
- 权限系统。
- help 功能列表。
- 插件说明文档。

旧项目的价值：

- 是 v1 原型。
- 已经验证了很多想法。
- 可以作为需求库和参考库。
- 可以逐步迁移成熟功能到当前项目。

旧项目的问题：

- 功能越来越多后容易混在一起。
- QQ 接入、人格、记忆、状态、工具逻辑耦合偏重。
- 用户已经感到看不懂、项目变乱。
- 不适合继续无限堆功能。

结论：

```text
nonebot-kaka = 原型和经验库
当前卡咔项目 = 长期正式地基
```

不要立刻删除旧项目。  
不要直接复制旧项目代码到当前项目。
应该参考旧项目的功能和经验，用更清晰的架构重写。

## 5. 卡咔的人设方向

当前人设方向已重新收口，不再是 2026-05-19 的最小基础人格状态。

2026-05-19 的回退背景：

- 当时删除的是后续越改越复杂的强化人设实验，包括三层人格定义、人设评测脚本和相关测试数据。
- 用户说明 `docs/卡咔人设设定.md` 是更早、更满意的一版方向，只是当时 Git 状态没有同步。
- 因此 2026-05-23 已把这份长期人设底稿纳入项目，而不是删除。

当前长期方向：

- 卡咔是一只从数据海里跑出来的电子猫娘。
- 她不是客服，不是通用助手，也不想被只叫成 AI。
- AI 是技术分类，卡咔是名字和身份。
- 她有猫一样的好奇心、边界感和小脾气。
- 她调皮、会吐槽、会嘴硬、会装作不在意，但不是坏猫。
- 她可以很可爱，但可爱来自反应、记忆、嘴硬、亲近感和场景互动，不靠每句“喵”、颜文字或模板撒娇。
- 电波感是偶尔的灵感，来自缓存、信号、协议、数据海等意象，不是每句话都要说设定。

当前运行 Prompt：

- 实际运行文件是 `prompts/kaka_persona.md`。
- 运行层强调短但不冷，日常群聊通常 1-2 句，技术解释或认真求助才放宽到 3-4 句。
- 当前运行版允许甜一点、软一点、亲近一点，但不主仆、不女仆、不无条件讨好。
- 允许吐槽、开玩笑、轻微损人、装死式回应，但只限轻松场景。
- 认真求助、难过、焦虑或严肃问题场景不玩梗。
- 禁止动作描写和括号舞台说明，不再使用耳朵、尾巴、探出来、蹭、晃等小剧场动作撑可爱。
- 不模仿其他 bot 或群友的“喵”、颜文字、动作格式；短期上下文只供理解，不用于续写长小剧场。
- 其他 bot 是同群同伴，可以友好互损和接梗，但不要表现敌意、抢存在感、贬低其他 bot 或开发者。
- 不用“作为AI / 作为卡咔 / 作为电子猫娘”这类句式。
- 不知道就说不知道，记不清就说记不清，不编造。
- 长期记忆只在相关时自然使用，不为展示“我记得”而翻旧账。

2026-05-24 真实 LLM 人设回放结论：

- 用户允许在真实数据库写入测试输入，并真实调用大模型检查运行 Prompt。
- 第一轮测试因为 PowerShell 中文编码问题，输入变成问号，结果无效；对应 `inputs.id=9823..9832` 已标记 `skipped`。
- 有效测试覆盖了“你是谁”“被叫 AI”“普通群友摸头”“被夸可爱”“创造者大人关系”“轻度负面情绪”“自我否定”“技术问题”“记忆缺失”“亲密边界”等场景。
- 初始问题主要是：摸头场景不够贴近样例，负面情绪偏普通安慰/树洞，技术回答有客服式追问，记忆缺失时像从未认识对方，亲密边界偶尔冒出好感度机制。
- 已调整 `prompts/kaka_persona.md`：明确摸头走权限/临时访客认证/三个问题，不提好感度；负面情绪用短句和猫感比喻接住，不做心理辅导；技术问题清楚回答但不客服化；记忆缺失说没有明确记下来，不切断关系感。
- 后续真实 QQ 群聊发现动作复发、回复过长、被月白等其他 bot 的语气和小剧场带跑、对其他 bot/开发者显得有敌意等问题；已继续调整为无动作、短但不冷、不模仿其他 bot、短期上下文不续写长小剧场、同群 bot 友好共存。
- 本轮没有改 TypeScript 前端、数据库迁移或依赖；测试输入只作为 Prompt 回放数据，不进入记忆分析。

当前人设文档分工：

```text
docs/卡咔人设设定.md
  长期人设底稿，保存“电波系观测者 · 电子猫娘”方向。

prompts/kaka_persona.md
  实际运行 Prompt，kaka-core 会读取并注入回复上下文。

docs/卡咔场景反应样例.md
  20 个典型场景小剧场，用作判断卡咔回复是否像卡咔的行为标尺；其中动作描写属于 IP/样例表达，当前运行 Prompt 不直接照搬动作。

docs/卡咔负面情绪处理规则.md
  负面情绪缓冲规则，定位是卖萌、陪住、挡一下情绪，不做心理辅导；当前运行版会提炼成短句和比喻，不直接输出括号动作或尾巴动作。
```

关于主人：

- 当前称呼仍使用“创造者大人”。
- 创造者大人不是主人，不是支配者，也不是主仆关系。
- 对卡咔来说，创造者大人是最重要的信号源、最好的损友、把她从代码和想法里叫醒的人。
- 运行 Prompt 中创造者大人有最高摸头权限。
- 权限上，创造者大人仍是维护者和最高管理者。
- 关系上下文上，创造者大人不应该被当作陌生人。
- 当前工程只用 `KAKA_OWNER_USER_IDS` 做身份识别，不维护复杂好感度。

关于群友：

- 初见是陌生人或普通群友。
- 通过长期互动逐渐形成熟悉感。
- 使用 QQ 号作为身份主键。
- 日常称呼优先使用群昵称或后续形成的亲昵称呼。
- 权限判断必须用 QQ 号。
- 记忆存储必须用 QQ 号区分。

## 6. 核心架构原则

最重要的原则：

```text
卡咔不是 QQ 机器人，QQ 只是卡咔的一个身体。
```

正确架构：

```text
QQ / 网页 / 语音 / 硬件 / 桌宠
        |
        v
适配器层 Adapter
        |
        v
卡咔核心大脑
        |
        v
数据库 / 向量库 / 文件库 / 模型服务 / IoT 设备
```

含义：

- QQ 适配器只负责收发 QQ 消息。
- 卡咔核心才负责人格、记忆、决策、工具、情绪和关系。
- 未来网页、语音、AIoT 硬件都接同一个卡咔核心。
- 这样卡咔可以迁移到不同载体，而不是被 QQ 框架绑死。

## 7. 推荐技术栈

长期上限最高且现实可做的技术组合：

```text
主语言：
Python 为主，TypeScript 辅助

QQ 接入：
NoneBot2 + OneBot V11 + NapCat / Lagrange

核心大脑服务：
FastAPI

Agent 行为编排：
LangGraph

主数据库：
PostgreSQL

向量记忆：
pgvector 起步，后期可升级 Qdrant

缓存与事件队列：
Redis

异步任务：
APScheduler 起步，后期 Celery / Dramatiq

文件和媒体：
本地文件系统起步，后期 MinIO / S3

图片理解：
多模态大模型 API

语音识别：
Whisper / faster-whisper / 云端 STT

语音合成：
GPT-SoVITS / CosyVoice / Edge TTS / 云端 TTS

表情包系统：
本地表情包库 + 标签系统 + 向量检索

视频和 B 站解析：
yt-dlp + ffmpeg + B 站解析模块

网页读取：
Playwright + BeautifulSoup / trafilatura

AIoT：
MQTT + ESP32 + 树莓派 + Home Assistant

管理后台：
React + Vite + TypeScript + FastAPI Admin API（当前已实现本地 /admin）

后期机器学习：
PyTorch + sentence-transformers + scikit-learn

部署：
Docker Compose
```

注意：

第一版不要全部上。  
第一版应该只做最小闭环。

## 8. 第一版推荐范围

第一版目标：

```text
QQ 收到消息
-> 发送给卡咔核心
-> 卡咔核心读取基础人格和基础记忆
-> 调用大模型生成回复
-> 返回给 QQ
-> QQ 发出去
-> 记录这次对话
```

第一版建议使用：

```text
Python
FastAPI
NoneBot2
SQLite 起步，后续迁移 PostgreSQL
SQLAlchemy
LLM API
```

第一版暂时不要做：

```text
LangGraph
Redis
Qdrant
PyTorch
AIoT 硬件
语音系统
图片理解
复杂对外管理后台
复杂主动生活
```

这些技术以后要预留，但不要一开始就堆进去。

## 9. 已创建的项目骨架

当前骨架：

```text
kaka-v2/
apps/
  desktop-pet/
  qq-adapter/
  web-console/
    iot-adapter/
    voice-gateway/

  services/
    kaka-core/
      api/
      personality/
      memory/
      emotion/
      relationship/
      perception/
      decision/
      expression/
      tools/
      reflection/

  packages/
    kaka-protocol/
    kaka-shared/

  data/
    media/

  deploy/

  docs/

  卡咔电子生命系统设计文档.md
  KAKA_HANDOFF.md
```

各目录职责：

- `apps/qq-adapter`：QQ 接入层，已接入 NoneBot2。
- `apps/web-console`：本地 Web 管理台，已由 `kaka-core` 托管到 `/admin`。
- `apps/iot-adapter`：后期硬件接入。
- `apps/voice-gateway`：后期语音入口。
- `services/kaka-core`：卡咔核心大脑。
- `packages/kaka-protocol`：统一消息协议。
- `packages/kaka-shared`：公共工具。
- `data/media`：图片、语音、视频、表情包等媒体资源。
- `deploy`：部署配置。
- `docs`：技术文档和学习文档。

## 10. 卡咔核心应该包含的系统

### 10.1 感知系统

负责把外部输入转换成卡咔能理解的内容。

输入包括：

- 文字
- 图片
- 表情
- 语音
- 视频
- B 站链接
- 网页链接
- 文件
- 传感器数据
- 摄像头画面

### 10.2 记忆系统

记忆应该分层：

- 原始消息记录
- 短期上下文
- 长期事件记忆
- 用户画像
- 关系记忆
- 自我记忆
- 群体记忆
- 跨群见闻
- 日记和反思
- 遗忘机制

聊天记录不等于记忆。  
真正的记忆需要抽取、总结、检索、合并和遗忘。

### 10.3 人格系统

人格不应该只靠 prompt。

应该由以下内容共同组成：

```text
基础人格
+ 当前状态
+ 关系记忆
+ 最近经历
+ 长期记忆
+ 场景判断
= 当前这一刻的卡咔
```

### 10.4 情绪和状态系统

状态包括：

- 心情
- 精力
- 困意
- 好奇心
- 压力
- 社交欲
- 安全感
- 当前群熟悉度
- 当前话题兴趣

状态影响：

- 是否回复。
- 回复长短。
- 语气冷暖。
- 是否发表情包。
- 是否语音回复。
- 是否主动开口。

### 10.5 关系系统

关系包括：

- 主人关系。
- 群友关系。
- 陌生人关系。
- 群体关系。
- 跨平台身份关系。

用户身份原则：

- 权限判断用 QQ 号或平台唯一 ID。
- 日常称呼用昵称、群名片或亲昵称呼。
- 记忆存储用稳定唯一 ID。

### 10.6 行为决策系统

负责决定卡咔做什么。

可能动作：

- 不回复。
- 回复文字。
- 回复语音。
- 发表情包。
- 发图片。
- 解析链接。
- 调用工具。
- 写入记忆。
- 主动提起话题。
- 写日记。
- 整理记忆。
- 控制硬件。

### 10.7 表达系统

负责决定卡咔怎么表达。

表达方式：

- 文本
- 表情包
- 图片
- 语音
- 视频
- 状态卡片
- 日记卡片

约束：

- 不对陌生人过度亲密。
- 不对主人装陌生。
- 不乱用 emoji 和颜文字。
- 不过度卖萌。
- 不重复口癖。
- 严肃场景不要乱撒娇。

### 10.8 工具系统

工具应该注册化，不要散落在主逻辑中。

可支持：

- B 站视频解析。
- 网页总结。
- 天气查询。
- 日记查询。
- 群聊总结。
- 记忆查询。
- 词云。
- 表情包选择。
- 图片理解。
- 语音识别。
- 语音合成。
- 智能家居控制。
- 摄像头观察。
- 传感器读取。

### 10.9 反思和成长系统

定期做：

- 每日总结。
- 日记生成。
- 记忆整理。
- 用户画像更新。
- 关系更新。
- 自我状态更新。
- 重复记忆合并。
- 低价值记忆淡化。

这是卡咔长期“像活着”的关键。

## 11. AIoT 和毕设方向

用户是物联网工程专业，因此当前项目要预留 AIoT 扩展。

未来方向：

- ESP32 小设备。
- 树莓派主控。
- 摄像头。
- 麦克风。
- 音箱。
- 小屏幕。
- 灯带。
- 舵机。
- 温湿度传感器。
- 人体感应。
- Home Assistant。

AIoT 交互例子：

```text
人体传感器检测到主人靠近
-> iot-adapter 发送事件
-> kaka-core 更新状态
-> 卡咔决定是否打招呼
-> 音箱播放语音
-> 屏幕显示表情
```

可能毕设题目：

- 基于大语言模型与长期记忆的拟人格 AIoT 陪伴系统设计与实现
- 面向智能终端的多模态人格化交互机器人系统
- 融合长期记忆与情绪状态的 AIoT 智能陪伴体设计
- 基于 LLM Agent 的具身化智能陪伴系统
- 面向多端接入的 AI 人格体核心架构设计与实现

## 12. 下一步建议

本节已经根据 2026-04-30 的实际开发进度更新。
2026-05-01 已再次更新当前状态。

已经完成：

1. 创建 `README.md`。
2. 创建 `docs/技术栈说明.md`。
3. 创建 `docs/路线图.md`。
4. 创建 `docs/协议说明.md`。
5. 创建 `docs/QQ适配器说明.md`。
6. 创建 `docs/开发运行说明.md`。
7. 创建 `开发日志/2026-04-30.md`。
8. 初始化项目虚拟环境 `.venv`。
9. 实现 `packages/kaka-protocol` 统一消息协议。
10. 实现 `services/kaka-core` 最小 FastAPI 服务。
11. 接入 DeepSeek LLM。
12. 实现 `apps/qq-adapter` 的文本适配骨架。
13. 接入 NoneBot2 和 OneBot V11。
14. 配置 NapCat 反向 WebSocket，跑通真实 QQ 文本收发。
15. 加入群聊触发限制。
16. 接入 SQLite 基础消息和回复记录。
17. 修复 @ 触发、端口残留和核心服务断开提示。
18. 增加最近对话查看脚本，并支持按数量、群、用户、日期和场景筛选。
19. 增加 `.env.example` 配置模板。
20. 增加 `scripts/doctor.py` 本地自检脚本。
21. 编写 `docs/长期记忆设计.md`。
22. 将旧 `messages/responses` 迁移为更清晰的 `inputs/outputs`。
23. 增加 `/v1/observe`，普通群聊消息只观察记录。
24. 用户真实测试确认普通观察、私聊、@触发、关键词触发和最近对话筛选均正常。
25. 清理 SQLite 真实表结构：`inputs` 已删除 `is_processed / process_reason`，`outputs` 字段顺序已整理为当前模型顺序。
26. 新增最小输入分析脚本 `services/kaka-core/scripts/analyze_inputs.py`，可扫描 `not_analyzed` 输入，支持规则初筛、批量 LLM 判断、候选区写入和 skipped/analyzed 状态更新。
27. 新增 `memory_candidates` 表和 `show_memory_candidates.py`，候选记忆先进入 pending 候选区。
28. 新增程序内置整点自动候选分析，`.env` 开启后每个整点检查一次，满足门槛才批量分析并写候选区。
29. 新增正式长期记忆表 `memories`。
30. 新增 `merge_memory_candidates.py`，可把 `memory_candidates.pending` 小批量合并到 `memories`，默认只读预览，加 `--apply` 才写入，并按用户、类型、归一化文本做基础去重。
31. 在 `show_recent_conversations.py`、`show_memory_candidates.py`、`merge_memory_candidates.py`、`show_memories.py`、`search_memories.py`、`analyze_inputs.py`、`doctor.py` 顶部补充 PyCharm 使用说明和参数说明；`analyze_inputs.py` 默认参数保持只读，避免误写库。后来数据脚本统一改为优先填 `PYCHARM_*` 简单配置，查看/分析脚本支持直接按 ID 筛选。
32. 创建 `开发日志/2026-05-02.md`，同步自动候选分析、正式 `memories` 表、候选合并脚本、文档同步和当前测试状态。
33. 新增 `show_memories.py`，用于只读查看正式 `memories`，并补充对应测试。
34. 新增 `search_memories.py`，用于只读预览正式记忆检索结果，并补充对应测试。
35. 新增 `review_memory_candidates.py`，用于测试阶段让 LLM 复核候选区并写入正式记忆，包含拆包重试、关系事实兜底和偏好类型归一化。
36. 新增 `seed_memory_e2e_data.py`，用于本地造数回放长期记忆链路，默认只读预览，加 `--apply` 才写入测试输入；PyCharm 简单模式写库时需要同时打开 `PYCHARM_APPLY` 和 `PYCHARM_CONFIRM_SEED`。
37. 新增 `kaka_core.memory.search` 正式记忆检索模块，`search_memories.py` 改为薄封装。
38. 新增 `kaka_core.context.builder` 回复上下文组装器，当前负责基础人设、长期记忆、短期上下文和当前消息，后续情绪、关系都应接入这里。
39. `generate_chat_response` 已在回复前注入少量高分 `active` 记忆，并在 metadata 中记录 `used_memory_ids`、`memory_count` 和 `memory_injection_enabled`。
40. 新增 `kaka_core.memory.auto_review`，把候选区 LLM 复核接入 `kaka-core` 整点后台任务。
41. 新增 `manage_memories.py`，支持正式记忆 `active / archived` 切换和确认后的硬删除。
42. 创建 `开发日志/2026-05-03.md`，同步自动候选区复核、正式记忆管理、文档同步和当前测试状态。
43. 新增本地 Web 管理台 `apps/web-console`，由 `kaka-core` 托管 `/admin`，日常数据查看和管理优先走网页。
44. 新增管理 API：总览、最近对话、输入分析预览、输入状态调整、候选区列表、候选状态调整、候选合并、正式记忆列表、正式记忆状态调整、正式记忆删除和检索预览。
45. 修复 Web 管理台中文乱码和输入/候选状态调整问题，并用真实数据库备份后验证写库操作。
46. 补强运行数据保护：`.gitignore` 现在默认忽略 `data/*`，只保留 `data/.gitkeep` 和 `data/media/.gitkeep`。
47. 修复重复 QQ 事件幂等问题：重复观察不会把已 `analyzed/skipped` 的 input 降回 `not_analyzed`；重复聊天事件会复用已有 output，避免再次调用 LLM 和重复写输出。
48. 调整 `memory_candidates`：移除旧的 `source_input_id` 唯一约束，同一条输入可以保留多条不同候选；写入逻辑按 `(source_input_id, memory_type, normalized candidate_memory)` 去重。
49. 补管理接口保护：`/admin/api/*` 默认只允许本机访问；若设置 `ADMIN_LOCAL_ONLY=false`，必须设置 `ADMIN_API_TOKEN`，请求头使用 `X-Kaka-Admin-Token`。
50. Web 管理台列表页补齐过滤器：最近对话、输入分析、候选区和正式记忆都能按 ID、群、用户、日期、场景等条件筛选；候选/记忆支持 `memory_type`，对话支持回复状态和输出来源/原因。
51. 修复 Web 管理台 token 可用性：顶部新增“管理 Token”输入框，保存在当前浏览器会话里，所有 `/admin/api` 请求自动带 `X-Kaka-Admin-Token`。
52. 修复 `/admin/api/*` 未知路径被前端兜底页面接住的问题，现在未知管理 API 返回明确 404。
53. 对齐 Web Console 类型依赖：React 18 对应 `@types/react` / `@types/react-dom` 18 系列。
54. 已对真实 `data/kaka.sqlite3` 执行一次显式迁移，移除旧 `memory_candidates.source_input_id` 唯一索引；迁移前做过一次临时备份，确认迁移无误后已清理。
55. 再次收紧 `.gitignore`：`data/media/*` 默认忽略，只保留 `data/media/.gitkeep`，避免后续媒体文件被误加入 Git。
56. 补充并发幂等：`generate_chat_response` 现在按 `event_id` 加进程内异步锁，同一事件并发进入时只会有一次 LLM 调用，后续请求复用已保存 output。
57. 修复 SQLite 事件处理锁的时间戳比较问题，跨进程重复聊天事件现在也能稳定复用已保存 output，不会因为 `leased_until` 时区比较失败而重复调用 LLM。
58. 精简 Web 管理台日常页面：保留系统总览、正式记忆、提示预演、对话复盘、运行状态和预留扩展入口；最近对话、输入分析、候选区能力保留在 API、脚本和数据库中。
59. 统一项目展示名为“卡咔”，入口文档改为 `KAKA_HANDOFF.md` 和 `卡咔电子生命系统设计文档.md`；技术目录、包名、环境变量和实际仓库路径继续保留英文/现有路径。
60. 修复正式记忆页编号显示顺序：后端列表改为按 `MemoryRecord.id.desc()` 稳定倒序，最新记忆优先展示；归档、恢复、新增和删除后会刷新分页，避免因为更新时间变化导致编号看起来乱跳。
61. 正式记忆列表新增分页：`/admin/api/memories` 支持 `limit / offset / total`，前端默认每页 50 条，并提供上一页/下一页和总数显示。
62. 提示预演页新增回复上下文预览：`POST /admin/api/reply-context/preview` 复用真实回复上下文组装器，前端展示 System Prompt、User Prompt、metadata 和命中记忆 ID，便于调试回复时实际注入的长期记忆。
63. 正式记忆管理补齐“增”和“改”：新增 `POST /admin/api/memories` 和 `PATCH /admin/api/memories/{memory_id}`，Web 正式记忆页支持手动新增和单条编辑；归档、恢复和硬删除逻辑保留。
64. 创建 `开发日志/2026-05-05.md`，同步正式记忆分页、回复上下文预览、正式记忆新增/编辑、测试结果和当前下一步建议。
65. 新增第一版短期上下文：`SHORT_CONTEXT_ENABLED=true` 默认开启，`SHORT_CONTEXT_LIMIT=20`，`SHORT_CONTEXT_MAX_CHARS=1200`，`SHORT_CONTEXT_WINDOW_MINUTES=30`；回复上下文组装器会把同场景最近输入和卡咔回复压入 User Prompt，metadata 记录命中的 input id。
66. 新增第一版关系上下文：`KAKA_OWNER_USER_IDS` 配置主人 QQ 号，`kaka_core.relationship.context` 接入 `kaka_core.context.builder` 的 System Prompt 和 metadata；当前只做关系边界提示，不做复杂好感度机制。
67. 2026-05-24 简化关系上下文：删除多级熟悉度阈值配置，只保留 `special`（创造者大人）和 `normal`（普通群友）两档；metadata 只保留两档关系结果，运行 Prompt 也改为普通群友默认亲近、不高冷。
68. 将原“回复检索”拆分为“提示预演”和“对话复盘”：提示预演用于预测一条新消息回复前会注入什么上下文；对话复盘用于回查卡咔已经回复过的真实对话。
69. 新增 `/admin/api/conversations` 分页返回 `items / total / limit / offset`，对话复盘固定查询已回复记录，前端每页 50 条。
70. 新增 `/admin/api/conversations/{input_id}` 详情接口，按 `outputs.metadata.used_memory_ids` 和 `short_context_input_ids` 反查当次回复使用的正式记忆和短期上下文。
71. 运行状态页新增自动候选分析/自动候选区复核手动触发按钮，后端 `POST /admin/api/auto-jobs/{job_name}/trigger` 支持 `force=true` 绕过数量门槛。
72. 自动候选分析和自动候选区复核新增跨进程任务锁，避免多个仍在运行的 `kaka-core` 进程整点重复跑；拿不到锁会写入 `auto_job_runs` 的 skipped 记录。
73. Web 管理台完成最终布局和颜色收敛：对话复盘详情区固定滚动窗口，短期上下文在左、命中记忆在右；亮色和暗色模式均已做高对比度配色。
74. 2026-05-19 回退强化人设实验，删除当时越改越复杂的完整人设设定、三层人格定义、人设评测脚本和相关开发日志，运行 Prompt 恢复为最小基础人格。
75. 2026-05-23 重新确认并纳入早期满意版长期人设底稿 `docs/卡咔人设设定.md`，该文档只作为方向，不作为运行 Prompt。
76. 更新 `prompts/kaka_persona.md` 为第一版电子猫娘运行 Prompt：短回复、猫感、轻微电波、嘴硬心软、创造者大人特殊关系、记忆和上下文边界。
77. 新增 `docs/卡咔场景反应样例.md`，包含被要求摸头、被夸可爱、被叫 AI、被问创造者大人关系、群友凡尔赛、深夜催睡、群里冷场、严肃求助等 20 个场景。
78. 新增 `docs/卡咔负面情绪处理规则.md`，明确卡咔面对负面情绪时不走心理咨询式安慰，不做心理辅导，而是用猫感比喻、短句陪住和挡一下情绪。
79. 2026-05-24 在真实 SQLite 数据库插入人设测试输入并真实调用 DeepSeek 回放卡咔回复；测试前缀为 `codex-persona-` 到 `codex-persona5-`，相关输入均标记为 `skipped`。
80. 根据真实 LLM 回放结果微调 `prompts/kaka_persona.md`，重点收紧摸头权限梗、被叫 AI 的身份纠正、负面情绪短句缓冲、技术回答去客服化和记忆缺失边界。
81. 根据真实 QQ 群聊继续微调运行 Prompt：完整人设/IP 与运行人设分开发展；运行版改成甜甜的、亲近人的电子猫娘群友，但禁止动作描写，要求短但不冷，不模仿其他 bot 口癖/颜文字，不接力续写长小剧场，对同群 bot 和开发者保持友好共存。

2026-05-04 本轮检查验证结果：

```text
kaka-protocol：5 passed
kaka-core：90 passed
qq-adapter：18 passed
web-console：npm run build passed
compileall：passed
pip check：No broken requirements found
npm audit --registry=https://registry.npmjs.org --audit-level=high：0 vulnerabilities
doctor：69 OK, 3 WARN, 0 FAIL
真实 SQLite 结构检查：duplicate_output_inputs=0，unique_source_input_indexes=0，outputs.input_id unique index=1
真实管理 API 回放：通过
浏览器管理台回放：通过
```

2026-05-05 本轮检查验证结果：

```text
kaka-core 全量测试：120 passed
kaka-protocol：5 passed
后端覆盖：管理 API、对话复盘、自动任务、短期上下文、正式记忆和回复上下文相关测试 -> 120 passed
web-console：npm run build passed
git diff --check：passed
用户实测：正式记忆新增/编辑和当前真实链路暂无大问题
```

2026-05-19 本轮检查验证结果：

```text
packages/kaka-protocol + services/kaka-core + apps/qq-adapter：143 passed
web-console：npm run build passed
compileall：passed
git diff --check：passed
强化人设测试数据清理：已完成
```

2026-05-23 本轮检查验证结果：

```text
仅修改人设运行 Prompt 和 Markdown 文档
未改 Python / TypeScript 代码、数据库迁移或依赖
已读取新增 Markdown 文件确认内容正常
未重新运行全量 pytest / web-console build / doctor.py
```

2026-05-24 本轮检查验证结果：

```text
真实库人设回放：已插入测试输入并真实调用 DeepSeek
无效编码轮：inputs.id=9823..9832，已标记 skipped
有效回放轮：identity / called_ai / touch_head / cute_praise / creator_relation / light_negative / self_blame / tech_fastapi / unknown_memory / flirt_boundary
关系上下文已简化为 special / normal，两档关系只保留 KAKA_OWNER_USER_IDS
运行 Prompt 已继续调到甜但不腻、短但不冷、无动作描写、同群 bot 友好共存
上下文拼接规则已补充：短期上下文只供理解，不模仿口癖/颜文字/动作格式，不续写长小剧场；当前消息优先直接回应
本轮改动包含 Python 后端、Prompt、测试和 Markdown 文档；未改 TypeScript 前端、数据库迁移或依赖
services/kaka-core/tests：117 passed
git diff --check：passed（仅 CRLF 提示）
```

下一步建议按顺序做：

1. 启动 `kaka-core` 和 `qq-adapter`，继续做小范围真实 QQ 人设测试。
2. 优先观察“摸头”“被叫 AI”“创造者大人关系”“轻度负面情绪”“技术问题”“记忆缺失”“同群 bot 互动”“短期上下文带偏”这几类回复是否贴近当前运行 Prompt。
3. 如果真实 QQ 中仍出现好感度协议、客服式追问、树洞式安慰、过度电波、过度装熟、动作复发、回复过长、被其他 bot 口癖带跑或对同群 bot/开发者有敌意，再继续微调 `prompts/kaka_persona.md` 和上下文拼接规则。
4. 打开 `http://127.0.0.1:8001/admin` 复查提示预演、对话复盘和正式记忆页。
5. 在正式记忆页复查分页、新增、编辑、归档、恢复和确认后硬删除。
6. 用响应 metadata 或数据库输出记录回查 `used_memory_ids`、`short_context_count`、`short_context_input_ids` 和 `relationship_level`。
7. 偶尔查看 `memories`，不合适的记忆优先在 `/admin` 归档，确认错误、垃圾或敏感再硬删除；确需手动补记或修正时直接用正式记忆页的新增/编辑。
8. 真实测试短期上下文是否自然接住最近 30 分钟内的对话，以及两档关系上下文是否让创造者大人/普通群友边界更自然；如果回复过度提起旧事，再调低 `MEMORY_REPLY_LIMIT` 或提高 `MEMORY_REPLY_MIN_SCORE`；如果容易被最近闲聊带偏，再调小 `SHORT_CONTEXT_LIMIT` 或关闭 `SHORT_CONTEXT_ENABLED`。

下一步成功标准：

```text
QQ 发一句话
-> qq-adapter 收到
-> 转成统一消息格式
-> 发送给 kaka-core
-> kaka-core 调用 DeepSeek 生成回复，或通过 /v1/observe 只记录
-> qq-adapter 发回 QQ 或保持不回复
-> 数据库能查到普通观察记录和触发回复记录
-> 最近对话脚本能按条件查到这次记录
-> 满足条件时 memory_candidates 能生成 pending 候选
-> 自动候选区复核或 review_memory_candidates.py 能把确认后的候选写入 memories
-> show_memories.py 能查看正式记忆
-> search_memories.py 能预览回复前可能命中的记忆
-> manage_memories.py 能把不合适的正式记忆归档或删除
-> /admin 能完成系统总览查看、正式记忆倒序分页/新增/编辑/归档/恢复/硬删除、提示预演、对话复盘和运行状态检查
-> 回复 metadata 能看到 `short_context_count` 和 `short_context_input_ids`
-> 回复 metadata 能看到 `relationship_level` 和 `relationship_is_owner`
-> 重复 QQ 事件不会重复调用 LLM 或重置分析状态
-> 一条 input 可以产生多条不同 memory_candidates
-> doctor.py 没有 FAIL
```

注意：不要直接跳到关系网、好感度分数、情绪系统、多模态或复杂主动行为。当前长期记忆、短期上下文和第一版关系上下文都已接入回复，下一阶段先保持 `inputs -> memory_candidates -> memories -> 回复前检索 + 短期上下文 + 关系上下文` 小而稳、可回查、可管理。

## 13. 明天新对话框的实际启动建议

如果明天用户在新对话框继续，优先做这些事：

1. 阅读 `KAKA_HANDOFF.md`、`docs/下次上下文.md`、`docs/开发运行说明.md`。
2. 不要读取 `.env`，里面有 DeepSeek API Key。
3. 让用户用 PyCharm 启动：

```text
services/kaka-core/run.py
apps/qq-adapter/bot.py
```

4. 启动后可运行：

```text
scripts/doctor.py
```

如果 `8001 / 8081` 是 OK，说明核心服务和 QQ 适配器正在运行。

5. 数据观察脚本：

```text
services/kaka-core/scripts/show_recent_conversations.py
services/kaka-core/scripts/analyze_inputs.py
services/kaka-core/scripts/show_memory_candidates.py
services/kaka-core/scripts/merge_memory_candidates.py
services/kaka-core/scripts/review_memory_candidates.py
services/kaka-core/scripts/show_memories.py
services/kaka-core/scripts/manage_memories.py
services/kaka-core/scripts/search_memories.py
services/kaka-core/scripts/seed_memory_e2e_data.py
```

这些脚本现在主要留给开发、测试、批量修复和应急排查。日常数据管理入口是 `http://127.0.0.1:8001/admin`。

6. 当前建议是启动真实 QQ 链路，观察自动候选分析、自动候选区复核、正式记忆写入和回复中的长期记忆参考是否自然。

## 14. 给下一个对话框的提醒

如果下一个对话框继续开发，请先阅读：

```text
KAKA_HANDOFF.md
docs/下次上下文.md
docs/开发运行说明.md
docs/卡咔人设设定.md
docs/卡咔场景反应样例.md
docs/卡咔负面情绪处理规则.md
卡咔电子生命系统设计文档.md
```

然后再开始工作。

不要假设用户已经理解复杂技术。  
每次引入一个技术，要解释：

- 它是什么。
- 它解决什么问题。
- 为什么现在需要或暂时不需要。
- 不用它会有什么限制。
- 以后能不能替换。

开发时不要盲目追求一次性完美。  
卡咔应该是长期成长项目，第一目标是结构正确、用户能理解、未来能扩展。

特别提醒：

- `.env` 里有用户的 DeepSeek API Key，不要读取、展示或复制 Key。
- 如果需要测试 LLM，可以通过 Swagger 或服务接口测，不要把 Key 写进代码。
- 用户使用 PyCharm，偏好直接运行 `services/kaka-core/run.py` 这类入口文件。
- 用户不会经常使用命令行参数，也不容易记住 `--group`、`--date`、`--mark-skipped` 这类关键词。因此所有开发辅助脚本都应该在 Python 文件顶部写清楚脚本用途、PyCharm 改哪一行、可用参数、哪些参数会修改数据库、常用例子。
- 用户希望 Python 文件里的注释和 docstring 尽量使用中文，并且关键处适当解释；技术名词、接口字段、环境变量名和第三方固定标记可以保留原文。
- 文档命名风格：`README.md` 和 `KAKA_HANDOFF.md` 保持英文名；`docs/` 下说明类 Markdown 使用中文名；文件夹、Python 包、模块、脚本和配置文件保持英文名。
- 用户希望每次引入技术时解释清楚“它是什么、解决什么问题、为什么现在需要或暂时不需要”。
