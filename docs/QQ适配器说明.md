# QQ 适配器说明

`apps/qq-adapter` 是卡咔 v2 的 QQ 接入层。

它只负责 QQ 消息收发和协议转换，不负责人格、记忆、关系和 LLM 调用决策。

当前已经跑通真实 QQ 文本链路：

```text
QQ 文本消息
-> NapCat
-> OneBot V11 反向 WebSocket
-> NoneBot2
-> qq_adapter.nonebot_plugins.kaka_chat
-> MessageEvent
-> kaka-core /v1/chat 或 /v1/observe
-> KakaResponse
-> QQSendTextAction 或空动作
-> QQ 文本回复或不回复
```

## 当前启动方式

启动入口：

```text
apps/qq-adapter/bot.py
```

运行：

```powershell
cd D:\Python\AgentRobot\kaka-v2
.\.venv\Scripts\python.exe .\apps\qq-adapter\bot.py
```

当前监听地址：

```text
http://127.0.0.1:8081
```

NapCat OneBot V11 反向 WebSocket 地址：

```text
ws://127.0.0.1:8081/onebot/v11/ws
```

当前测试成功的 NapCat 配置文件：

```text
D:\Python\AgentRobot\NapCat.Shell.Windows.OneKey\NapCat.44498.Shell\versions\9.9.26-44498\resources\app\napcat\config\onebot11_1537786366.json
```

## 当前已完成

### NoneBot2 入口

文件：

```text
apps/qq-adapter/bot.py
```

作用：

- 初始化 NoneBot2。
- 注册 OneBot V11 适配器。
- 加载 `qq_adapter.nonebot_plugins.kaka_chat` 插件。

### NoneBot 插件

文件：

```text
apps/qq-adapter/src/qq_adapter/nonebot_plugins/kaka_chat.py
```

作用：

- 接收 NoneBot 的 QQ 消息事件。
- 先判断应该回复、只观察，还是忽略。
- 把事件整理成 OneBot 风格字典。
- 调用现有 `handle_onebot_text_event` 流水线。
- 把 `QQSendTextAction` 发回 QQ。

当前触发规则：

```text
私聊：全部回复
群聊：只有 @机器人 或 文本包含“卡咔”才回复
群聊普通文本：不回复，但发送到 /v1/observe 写入 inputs
```

### QQ 事件转换

文件：

```text
apps/qq-adapter/src/qq_adapter/qq_event.py
```

作用：

- 接收 OneBot 风格的 QQ 原始事件字典。
- 支持私聊文本消息。
- 支持群聊文本消息。
- 把 QQ 消息转换成 `kaka-protocol` 的 `MessageEvent`。
- 使用 QQ 场景和 `message_id` 构造稳定 `event_id`，避免同一条消息重复入库。

示例：

```text
group_id -> scene_id
user_id -> user_id
sender.card / sender.nickname -> display_name
message text -> content.text
```

### kaka-core 客户端

文件：

```text
apps/qq-adapter/src/qq_adapter/core_client.py
```

作用：

- 用 HTTP 请求 `kaka-core`。
- 发送 `MessageEvent`。
- 接收并解析 `KakaResponse`。

默认请求地址：

```text
http://127.0.0.1:8001/v1/chat
http://127.0.0.1:8001/v1/observe
```

可以通过 `.env` 修改：

```env
KAKA_CORE_BASE_URL=http://127.0.0.1:8001
QQ_ADAPTER_REQUEST_TIMEOUT=60
```

### 响应动作解析

文件：

```text
apps/qq-adapter/src/qq_adapter/actions.py
```

作用：

- 把 `KakaResponse` 里的 `send_text` 动作转换成 QQ 侧待发送文本。
- 第一版只处理文本发送。

### 处理流水线

文件：

```text
apps/qq-adapter/src/qq_adapter/pipeline.py
```

作用：

```text
OneBot 原始事件
-> MessageEvent
-> 按 should_reply 请求 kaka-core /v1/chat 或 /v1/observe
-> KakaResponse
-> QQSendTextAction
```

## 当前未完成

当前还没有做：

- 图片、语音、表情、文件消息处理。
- 群聊复杂主动回复策略。
- 权限和管理员命令。
- QQ 侧错误重试。

这些会在后续阶段逐步接入。

## 测试结果

当前测试覆盖：

- QQ 群聊文本事件转换。
- QQ 私聊文本事件转换。
- 非文本消息拒绝。
- KakaResponse 到 QQ 文本动作转换。
- qq-adapter 调用 kaka-core 客户端。
- 完整适配器流水线。
- 群聊文本触发规则，包括“卡咔”关键词、@机器人和普通观察记录。

运行方式：

```powershell
..\..\.venv\Scripts\python.exe -m pytest
```

工作目录：

```text
D:\Python\AgentRobot\kaka-v2\apps\qq-adapter
```

当前通过：

```text
qq-adapter：18 passed
```

这是最近一次完整适配器测试记录；本轮 Web 管理台和管理 API 修复没有改动 QQ 适配器核心链路。
