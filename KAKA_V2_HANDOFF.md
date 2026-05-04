# 卡咔 v2 项目交接文档

本文档用于在新的对话框中快速恢复上下文。下一个对话框只要先阅读本文档，就应该能理解卡咔 v2 的目标、技术路线、用户偏好、旧项目经验和下一步工作。

## 0. 最新交接摘要

当前日期：2026-05-04。  
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
-> 输入分析状态和候选区状态的网页端管理
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
- NapCat 已经能把真实 QQ 私聊和群聊文本消息转发到当前 `kaka-v2`。
- 卡咔已经可以在 QQ 中通过 DeepSeek 生成文本回复。
- 群聊已加触发限制：私聊全回复，群聊只在 @机器人 或包含“卡咔”时回复；普通群聊文本不回复，但会写入 `inputs` 作为观察记录。
- `kaka-core` 已经接入 SQLite 基础记录，默认文件为 `data/kaka.sqlite3`；`inputs` 记录卡咔收到/观察到的输入，`outputs` 记录卡咔对已处理输入形成的输出结果或响应决策，`memory_candidates` 记录长期记忆候选，`memories` 记录已合并的正式长期记忆。
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
- 已做一轮长期记忆 E2E 合成数据回放，已验证分析、候选写入、LLM 复核、正式记忆查看和检索脚本的完整链路。
- `show_recent_conversations.py`、`show_memory_candidates.py`、`merge_memory_candidates.py`、`review_memory_candidates.py`、`show_memories.py`、`manage_memories.py`、`search_memories.py`、`analyze_inputs.py`、`seed_memory_e2e_data.py` 和 `doctor.py` 已在文件顶部写明 PyCharm 右键运行方式和可用参数；数据脚本优先提供 `PYCHARM_*` 简单配置，写库默认关闭；用户不熟悉命令行参数，后续新增类似脚本也要沿用这个风格。
- 已有根目录 `.env.example` 配置模板。
- 已有 `scripts/doctor.py` 本地自检脚本，用于检查配置形状、数据库、导入和端口状态。
- 已有 `docs/长期记忆设计.md`，明确第一版记什么、不记什么、`memories` 表建议和抽取规则。
- 已有本地 Web 管理台：前端在 `apps/web-console`，`kaka-core` 托管 `/admin`，管理 API 在 `/admin/api/*`；当前覆盖总览、最近对话、输入分析预览、输入分析状态调整、候选区状态调整、候选区合并、正式记忆归档/恢复/删除、记忆检索预览和系统状态。
- Web 管理台已成为日常数据管理入口；脚本现在主要留给开发、测试、批量修复和应急排查。
- 输入分析页支持按 `inputs.analysis_status` 筛选，并能把选中输入设为 `not_analyzed / analyzed / skipped`；“按规则标记 skipped”仍只标记规则判定可跳过的输入。
- 候选区页支持按 `memory_candidates.status` 筛选，并能把选中候选设为 `pending / approved / rejected / merged_duplicate`；候选合并预览和执行只在 `pending` 视图下显示，避免误操作已处理候选。
- 正式记忆页支持 `active / archived` 切换和确认后的硬删除；危险写库动作都有确认弹窗。
- 脚本现在定位为开发、测试、排查和应急备用入口；用户日常管理优先使用网页。
- 已经创建根目录 `.env`，其中有 DeepSeek API Key。`.env` 被 `.gitignore` 忽略，不要把 Key 写进任何文档或回复。

当前测试和验证结果：

```text
kaka-protocol：5 passed（历史完整测试记录）
kaka-core：88 passed
qq-adapter：18 passed（历史完整测试记录）
doctor：56 OK, 3 WARN, 0 FAIL
web-console：npm run build passed
本轮核心相关针对性测试：31 passed
admin API 单测：4 passed
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
先阅读本交接文档和 docs/下次上下文.md；如果继续验收，优先打开 http://127.0.0.1:8001/admin 手动检查输入分析、候选区和正式记忆管理；之后再按需要启动 QQ 链路，观察自动候选分析、自动候选区复核和回复时长期记忆使用是否稳定
```

第一目标仍然只做文本：

```text
QQ 发一句话
-> qq-adapter 收到
-> 转成 MessageEvent
-> kaka-core 回复前检索少量 active 长期记忆并组装 prompt，或只观察记录
-> 返回 KakaResponse
-> qq-adapter 发回 QQ 文本或不回复
-> SQLite 记录消息，触发回复时记录输出
-> 最近对话脚本可以查到观察记录和回复记录
-> 满足条件时自动整理 memory_candidates 候选区
-> 自动候选复核满足条件时把 pending 候选写入 memories，或继续手动用 LLM 复核脚本确认
-> 用户偶尔查看 memories，不合适的记忆用 manage_memories.py 归档或硬删除
-> 用户日常也可以直接用 /admin 管理 inputs、memory_candidates 和 memories
```

暂时不要做图片、表情包、语音和复杂主动行为。下一步先保持真实 QQ 对话运行，观察自动记忆链路和回复中的记忆使用效果。

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
卡咔-v2-电子生命系统设计文档.md
KAKA_V2_HANDOFF.md
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

`卡咔-v2-电子生命系统设计文档.md` 是 v2 的总体设计蓝图。  
`KAKA_V2_HANDOFF.md` 是本文件，用于给下一个对话框恢复记忆。

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
- 卡咔人设 prompt。
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
- 可以逐步迁移成熟功能到 v2。

旧项目的问题：

- 功能越来越多后容易混在一起。
- QQ 接入、人格、记忆、状态、工具逻辑耦合偏重。
- 用户已经感到看不懂、项目变乱。
- 不适合继续无限堆功能。

结论：

```text
nonebot-kaka = v1 原型和经验库
kaka-v2 = 长期正式地基
```

不要立刻删除旧项目。  
不要直接复制旧项目代码到 v2。  
应该参考旧项目的功能和经验，用更清晰的架构重写。

## 5. 卡咔的人设方向

用户喜欢的卡咔不是普通工具人，也不是过度卖萌模板。

当前人设方向：

- 轻猫系猫娘。
- 有一点猫感，但不要过度二次元模板化。
- 有边界感。
- 不过度讨好。
- 有一点点傲娇，但只能轻微。
- 对熟人更柔软。
- 对陌生人礼貌但保留距离。
- 会偷懒，会困，会不想营业。
- 有观察欲和好奇心。
- 有自己的小情绪。
- 不依赖 emoji 或颜文字塑造人格。

关于主人：

- 权限上，主人是维护者和最高管理者。
- 人设上，主人是卡咔最亲近的平等朋友。
- 不是主仆关系。
- 卡咔可以信任主人、依赖主人、嘴硬、撒娇。
- 卡咔不应该把主人当陌生人。

关于群友：

- 初见是陌生人或普通群友。
- 通过长期互动逐渐形成熟悉感。
- 使用 QQ 号作为身份主键。
- 日常称呼优先使用群昵称或后续形成的亲昵称呼。
- 权限判断必须用 QQ 号。
- 记忆存储必须用 QQ 号区分。

## 6. v2 核心架构原则

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
卡咔核心大脑 Kaka Core
        |
        v
数据库 / 向量库 / 文件库 / 模型服务 / IoT 设备
```

含义：

- QQ 适配器只负责收发 QQ 消息。
- Kaka Core 才负责人格、记忆、决策、工具、情绪和关系。
- 未来网页、语音、AIoT 硬件都接同一个 Kaka Core。
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
-> 发送给 Kaka Core
-> Kaka Core 读取基础人格和基础记忆
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

  KAKA_V2_ELECTRONIC_LIFE_DESIGN.md
  KAKA_V2_HANDOFF.md
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

## 10. Kaka Core 应该包含的系统

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

用户是物联网工程专业，因此 v2 要预留 AIoT 扩展。

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
38. 新增 `kaka_core.context.builder` 回复上下文组装器，当前负责基础人设、长期记忆和当前消息，后续情绪、关系、短期上下文都应接入这里。
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
51. 修复 Web 管理台 token 可用性：顶部新增“管理 Token”输入框，保存在当前浏览器本地，所有 `/admin/api` 请求自动带 `X-Kaka-Admin-Token`。
52. 修复 `/admin/api/*` 未知路径被前端兜底页面接住的问题，现在未知管理 API 返回明确 404。
53. 对齐 Web Console 类型依赖：React 18 对应 `@types/react` / `@types/react-dom` 18 系列。
54. 已对真实 `data/kaka.sqlite3` 执行一次显式迁移，移除旧 `memory_candidates.source_input_id` 唯一索引；迁移前做过一次临时备份，确认迁移无误后已清理。
55. 再次收紧 `.gitignore`：`data/media/*` 默认忽略，只保留 `data/media/.gitkeep`，避免后续媒体文件被误加入 Git。
56. 补充并发幂等：`generate_chat_response` 现在按 `event_id` 加进程内异步锁，同一事件并发进入时只会有一次 LLM 调用，后续请求复用已保存 output。

2026-05-04 本轮检查验证结果：

```text
kaka-protocol：5 passed
kaka-core：88 passed
qq-adapter：18 passed
web-console：npm run build passed
compileall：passed
pip check：No broken requirements found
npm audit --registry=https://registry.npmjs.org --audit-level=high：0 vulnerabilities
doctor：56 OK, 3 WARN, 0 FAIL
真实 SQLite 结构检查：duplicate_output_inputs=0，unique_source_input_indexes=0，outputs.input_id unique index=1
真实管理 API 回放：通过
浏览器管理台回放：通过
```

下一步建议按顺序做：

1. 启动 `kaka-core`，打开 `http://127.0.0.1:8001/admin` 做一次手动验收。
2. 检查输入分析页是否能筛选和调整 `not_analyzed / analyzed / skipped`。
3. 检查候选区页是否能筛选和调整 `pending / approved / rejected / merged_duplicate`。
4. 再启动 `qq-adapter` 保持真实 QQ 对话运行，观察自动候选分析和自动候选区复核是否稳定。
5. 用响应 metadata 或数据库输出记录回查 `used_memory_ids`。
6. 偶尔查看 `memories`，不合适的记忆优先 `archived`，确认错误、垃圾或敏感再硬删除。
7. 如果回复过度提起旧事，再调低 `MEMORY_REPLY_LIMIT` 或提高 `MEMORY_REPLY_MIN_SCORE`。

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
-> /admin 能完成日常最近对话、输入分析、候选区和正式记忆管理
-> 重复 QQ 事件不会重复调用 LLM 或重置分析状态
-> 一条 input 可以产生多条不同 memory_candidates
-> doctor.py 没有 FAIL
```

注意：不要直接跳到关系网、情绪系统、多模态或复杂主动行为。当前长期记忆第一版已经接入回复，下一阶段先保持 `inputs -> memory_candidates -> memories -> 回复前检索` 小而稳、可回查、可管理。

## 13. 明天新对话框的实际启动建议

如果明天用户在新对话框继续，优先做这些事：

1. 阅读 `KAKA_V2_HANDOFF.md`、`docs/下次上下文.md`、`docs/开发运行说明.md`。
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
KAKA_V2_HANDOFF.md
docs/下次上下文.md
docs/开发运行说明.md
卡咔-v2-电子生命系统设计文档.md
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
卡咔 v2 应该是长期成长项目，第一目标是结构正确、用户能理解、未来能扩展。

特别提醒：

- `.env` 里有用户的 DeepSeek API Key，不要读取、展示或复制 Key。
- 如果需要测试 LLM，可以通过 Swagger 或服务接口测，不要把 Key 写进代码。
- 用户使用 PyCharm，偏好直接运行 `services/kaka-core/run.py` 这类入口文件。
- 用户不会经常使用命令行参数，也不容易记住 `--group`、`--date`、`--mark-skipped` 这类关键词。因此所有开发辅助脚本都应该在 Python 文件顶部写清楚脚本用途、PyCharm 改哪一行、可用参数、哪些参数会修改数据库、常用例子。
- 用户希望 Python 文件里的注释和 docstring 尽量使用中文，并且关键处适当解释；技术名词、接口字段、环境变量名和第三方固定标记可以保留原文。
- 文档命名风格：`README.md` 和 `KAKA_V2_HANDOFF.md` 保持英文名；`docs/` 下说明类 Markdown 使用中文名；文件夹、Python 包、模块、脚本和配置文件保持英文名。
- 用户希望每次引入技术时解释清楚“它是什么、解决什么问题、为什么现在需要或暂时不需要”。
