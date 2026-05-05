# 卡咔

卡咔是一个长期演进的 AI 人格体项目。它不是单纯的 QQ 机器人，而是以 `kaka-core` 为核心大脑，未来可以接入 QQ、网页、语音、桌宠、AIoT 硬件和其他终端的电子生命系统。

当前阶段的重点不是堆功能，而是先搭好清晰、可学习、可扩展的地基。

## 项目目标

长期目标是让卡咔具备这些能力：

- 有稳定但会成长的人格。
- 有长期记忆，而不是每次对话都像第一次见面。
- 能识别不同的人，并根据关系调整表达方式。
- 能理解文字、图片、语音、视频、网页和现实传感器信息。
- 能使用工具，比如 B 站解析、网页总结、群聊总结、日记、记忆查询等。
- 未来能接入 AIoT 硬件，拥有更接近现实世界的感知和表达方式。

工程边界也要明确：卡咔不会真正拥有人类意识。这个项目要做的是通过记忆、人格、状态、关系、主动行为和多端感知，让她在工程表现上更有连续性、个性和生命感。

## 核心原则

最重要的架构原则是：

```text
卡咔不是 QQ 机器人，QQ 只是卡咔的一个身体。
```

正确结构应该是：

```text
QQ / Web / Voice / IoT / Desktop
        |
        v
Adapter 适配器层
        |
        v
kaka-core 核心大脑
        |
        v
数据库 / 向量库 / 文件库 / 模型服务 / IoT 设备
```

含义是：

- `qq-adapter` 只负责 QQ 消息收发。
- `kaka-core` 才负责人格、记忆、关系、情绪、决策、工具和表达。
- 未来换成网页、语音、硬件或桌宠时，核心大脑不需要推倒重写。

## 当前阶段

当前项目还处在第一阶段地基。

第一阶段目标是完成一个最小可运行闭环：

```text
QQ 收到消息
-> qq-adapter 转成统一消息格式
-> 发给 kaka-core
-> kaka-core 使用基础人格 prompt
-> 调用 LLM 生成回复
-> 返回给 qq-adapter
-> QQ 发出回复
-> 数据库记录消息和回复
```

第一阶段暂时不做：

- 复杂主动生活系统
- AIoT 硬件接入
- 语音系统
- 图片理解
- 对外部署的多用户复杂管理后台
- 本地模型训练
- 复杂 Agent 编排

本地 Web 管理台已经作为数据管理入口实现；这里暂时不做的是带公网部署、登录权限、多人协作和复杂配置系统的完整后台。

## 当前已完成

截至 2026-05-04，已经完成：

- `packages/kaka-protocol`：统一消息协议。
- `services/kaka-core`：核心大脑 FastAPI 服务。
- DeepSeek LLM 接入：`/v1/chat` 可以调用大模型生成回复。
- 观察接口：`/v1/observe` 可以只记录消息，不调用模型、不回复。
- `apps/qq-adapter`：QQ 文本适配器，已经接入 NoneBot2。
- NapCat + OneBot V11 真实 QQ 文本闭环。
- SQLite 基础记录：`inputs` 记录卡咔收到/观察到的输入，`outputs` 记录卡咔对已处理输入形成的输出结果或响应决策，`memory_candidates` 记录待审核长期记忆候选，`memories` 记录已经合并的正式长期记忆，`auto_job_runs` 记录自动后台任务运行结果，默认写入 `data/kaka.sqlite3`。
- 最近对话查看脚本：支持按数量、群、用户、日期、场景、是否输出和输出原因筛选，并显示北京时间。
- 最小输入分析脚本：扫描 `inputs.analysis_status=not_analyzed`，支持规则初筛、批量 LLM 判断、只读预览、候选区写入和 skipped/analyzed 状态更新。
- 记忆候选查看脚本：`show_memory_candidates.py` 可按候选 ID、状态、类型、群、用户、日期查看 `memory_candidates`。
- 候选区合并脚本：`merge_memory_candidates.py` 默认只读预览，加 `--apply` 后把 pending 候选合并到正式 `memories` 表，并做基础去重；PyCharm 可直接填 `PYCHARM_CANDIDATE_IDS`。
- 候选区合并核心逻辑：`kaka_core.memory.merge` 已抽出可复用的加载、去重、合并和统计函数；脚本和 `/admin` 都直接复用它。
- 候选区 LLM 复核脚本：`review_memory_candidates.py` 可在测试阶段临时代替人工审核 pending/rejected 候选；默认只读预览，加 `--apply` 后按 approve/reject/duplicate 写入或更新；PyCharm 可直接填 `PYCHARM_CANDIDATE_IDS`。
- 正式记忆查看脚本：`show_memories.py` 可按记忆 ID、状态、类型、来源、群、用户、日期查看 `memories`。
- 正式记忆管理脚本：`manage_memories.py` 可把记忆切到 `active` / `archived`，或在确认错误、垃圾、敏感时硬删除。
- 正式记忆检索预览脚本：`search_memories.py` 可按当前用户和当前消息，只读预览会命中的少量正式记忆。
- 本地 Web 管理台：启动 `kaka-core` 后打开 `http://127.0.0.1:8001/admin`；当前 Web 界面保留总览、正式记忆、回复检索预览、运行状态和预留扩展入口。正式记忆页支持按 ID 稳定排序、每页 50 条分页、新增、编辑、归档、恢复和确认后硬删除；运行状态页会显示最近自动候选分析/复核记录；最近对话、输入分析、候选区等后台能力仍保留在 API、脚本和数据库中，但不再作为日常 Web 页面暴露。
- 管理 API：`/admin/api/*`，默认只允许本机访问；如果设置 `ADMIN_LOCAL_ONLY=false`，必须配置 `ADMIN_API_TOKEN` 并在请求头传 `X-Kaka-Admin-Token`。Web 管理台顶部的“管理 Token”输入框会把 token 暂存在当前浏览器会话里并自动带到 API 请求里。核心代码在 `services/kaka-core/src/kaka_core/api/admin_routes.py` 和 `services/kaka-core/src/kaka_core/admin/service.py`；总览里展示的数据库连接串会自动脱敏。后续面向用户的数据管理功能优先扩展这里。
- 基础人设 Prompt 文件：`prompts/kaka_persona.md` 会作为回复时 System Prompt 的基础层；关系上下文和长期记忆会在它之后动态追加。路径可用 `KAKA_PERSONA_PROMPT_PATH` 调整，文件缺失时会回退到内置基础人设。
- 回复前关系上下文：`kaka-core` 会用 `KAKA_OWNER_USER_IDS`、历史输入数、最近 7 天输入数和 active 正式记忆数，把当前说话者粗分为 `owner / familiar / regular / stranger`。这不是好感度系统，只用于让卡咔不把主人当陌生人，也不对新人装熟。
- 长期记忆 E2E 测试造数脚本：`seed_memory_e2e_data.py` 只用于本地测试，默认预览，加 `--apply` 才写入测试输入。
- 程序内置自动候选分析：可选开启后，`kaka-core` 在下一个整点及之后每个整点检查一次；`not_analyzed >= 50` 时最多处理两轮，每轮 50 条；每次检查会写入 `auto_job_runs`。
- 程序内置自动候选区复核：可选开启后，`kaka-core` 在下一个整点及之后每个整点检查一次；`pending >= 20` 时最多处理一批，每批 10 条；每次检查会写入 `auto_job_runs`。
- 根目录 `.env.example` 配置模板。
- `scripts/doctor.py` 本地自检脚本。
- 项目专用虚拟环境 `.venv`。
- 根目录 `.env` 本地配置文件。
- 基础文档和开发日志。

当前已经跑通：

```text
QQ 文本消息
-> NapCat
-> OneBot V11 反向 WebSocket
-> NoneBot2
-> qq-adapter
-> kaka-core /v1/chat 或 /v1/observe
-> DeepSeek 或只观察记录
-> KakaResponse
-> QQ 文本回复或不回复
-> SQLite 消息和回复记录
```

当前群聊触发规则：

```text
私聊：全部回复
群聊：只有 @机器人 或 文本包含“卡咔”才回复
群聊普通文本：不回复，但会写入 inputs 作为观察记录
```

当前仍然只做文本，不处理图片、语音、表情包和复杂主动行为。

当前数据库语义：

```text
users：外部平台用户
scenes：消息发生场景
inputs：卡咔收到/观察到的输入，包含后续分析状态
outputs：卡咔对已处理输入形成的输出结果或响应决策，包含输出来源和输出原因
memory_candidates：大模型或规则整理出的长期记忆候选，状态默认为 pending，后续可合并到正式记忆
memories：已经从候选区合并出的正式长期记忆，后续回复检索只应读取 active 记忆
auto_job_runs：自动候选分析和自动候选复核的运行记录
```

当前状态语义：

```text
inputs.analysis_status：
  not_analyzed：还没有进入长期记忆分析流程
  analyzed：已经处理过，或已经产生候选/被人工标记为已处理
  skipped：确认没有长期记忆价值，后续不再分析

memory_candidates.status：
  pending：等待审核或合并
  approved：已经合并进正式 memories
  rejected：确认不进入正式记忆
  merged_duplicate：和已有正式记忆重复，没有新增 memories

memories.status：
  active：参与回复前检索
  archived：保留记录，但不参与回复
```

## 目录结构

```text
kaka-v2/
  apps/
    qq-adapter/          # QQ 接入层，已接入 NoneBot2 + OneBot V11
    web-console/         # 本地 Web 管理台，已由 kaka-core 托管到 /admin
    iot-adapter/         # 后期硬件接入
    voice-gateway/       # 后期语音入口

  services/
    kaka-core/           # 卡咔核心大脑
      api/               # FastAPI 接口
      personality/       # 人格系统
      memory/            # 记忆系统
      emotion/           # 情绪状态
      relationship/      # 用户关系
      perception/        # 感知系统
      decision/          # 行为决策
      expression/        # 表达系统
      tools/             # 工具调用
      reflection/        # 反思与日记

  packages/
    kaka-protocol/       # 多端统一消息协议
    kaka-shared/         # 公共工具和类型

  data/
    media/               # 图片、语音、视频、表情包等资源
    kaka.sqlite3         # 本地 SQLite 对话记录，已被 .gitignore 忽略

  deploy/                # 部署配置
  docs/                  # 技术文档和学习文档
```

## 推荐阅读顺序

如果是第一次看这个项目，建议按这个顺序读：

1. `README.md`
2. `KAKA_HANDOFF.md`
3. `docs/下次上下文.md`
4. `docs/开发运行说明.md`
5. `docs/路线图.md`
6. `docs/长期记忆设计.md`
7. `docs/技术栈说明.md`
8. `卡咔电子生命系统设计文档.md`

命名约定：

- 关键入口文档保留英文名：`README.md`、`KAKA_HANDOFF.md`。
- `docs/` 下的说明类文档使用中文名。
- 文件夹、Python 包、模块、脚本和配置文件继续保持英文名。

## 下一步

当前第一阶段地基已经通过真实 QQ 测试，并已经进入正式长期记忆用于回复的阶段：

```text
真实 QQ 文本闭环
-> 群聊触发限制
-> SQLite 观察消息和回复记录
-> 最近对话筛选查看
-> 输入分析和候选区写入
-> 自动整点候选分析
-> 正式 memories 表和候选合并脚本
-> 候选区 LLM 复核脚本
-> 自动整点候选区复核
-> 正式 memories 查看脚本
-> 正式 memories 管理脚本
-> 正式 memories 只读检索预览脚本
-> 回复前少量 active 记忆注入
-> 本地 Web 管理台 /admin
-> 正式记忆分页、新增和编辑
-> 回复上下文预览
-> 基础人设 prompt 文件化
-> 配置模板和本地自检
```

2026-05-01 用户实测确认：

```text
普通群聊观察记录正常
私聊 / @ / “卡咔”关键词触发回复正常
inputs / outputs 记录正常
最近对话筛选查看正常
```

当前已经完成“回复时读取正式长期记忆”的第一版接入：`search_memories.py` 的检索逻辑已经抽成正式模块，`kaka-core` 回复前会按当前用户、场景和消息检索少量 `active` 记忆，并把命中的记忆作为可参考背景放进模型 prompt。当前也已接入第一版短期上下文，默认读取同场景最近 30 分钟内最多 20 条输入记录，总字符上限 1200，排除当前消息。回复前还会注入第一版关系上下文，按主人、熟人、普通熟悉群友和陌生人粗分表达边界。基础人设已经从代码拆到 `prompts/kaka_persona.md`，后续正式写人设时优先改这个文件。回复上下文内部已经分为 `persona / relationship / memory / recent_context / current_message` 层，方便后续继续接入用户画像和情绪状态。长期记忆、短期上下文、关系阈值和人设路径都可通过 `.env` 调整。程序里也已经内置自动候选分析和自动候选区复核，两者都在整点触发。

当前也已经完成本地 Web 管理台第一版接入。用户日常查看总览、管理正式记忆、预览回复检索和检查运行状态，优先使用 `/admin`；正式记忆可以在页面内新增、编辑、归档、恢复和删除。最近对话、输入分析、候选区等后台能力仍保留在 API、脚本和数据库中，Python 脚本主要留给开发、测试、批量修复和应急排查。

当前回复记忆接入规则：

1. 默认最多取 5 条高分 `active` 记忆。
2. 默认最多取最近 30 分钟内 20 条同场景短期上下文。
3. 基础人设来自 `prompts/kaka_persona.md`，动态关系和记忆会追加在后面。
4. 记忆和短期上下文只是背景，不强迫模型主动提起或机械复述。
5. 响应 metadata 会记录 `context_layer_names`、`persona_prompt_source`、`used_memory_ids`、`memory_count`、`memory_injection_enabled`、`short_context_input_ids`、`short_context_count`、`relationship_level`、`relationship_is_owner` 和关系计数。
6. 后续情绪、用户画像和更细关系维度应继续接入 `kaka_core.context.builder`，不要散落在聊天服务里。

当前暂时不要做图片、表情包、语音和复杂主动行为。先保证文本闭环、原始记录和开发工具长期稳定。
