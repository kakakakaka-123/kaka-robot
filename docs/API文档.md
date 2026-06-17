# 卡咔 API 文档

## 概述

卡咔核心服务（kaka-core）提供 RESTful API，支持：
- 消息处理（聊天、观察）
- 长期记忆管理
- 桌面操作任务
- 通知推送
- 管理后台

**基础地址**: `http://127.0.0.1:8001`

**API 文档**: `http://127.0.0.1:8001/docs` (Swagger UI)

---

## 认证

### 本地开发模式

本地环境下，大部分 API 无需认证。

### 生产模式

部分敏感 API 需要 Bearer Token：

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://127.0.0.1:8001/v1/admin/memories
```

配置 Token：在 `.env` 文件设置 `ADMIN_API_TOKEN`

---

## 核心 API

### 1. 消息处理

#### POST /v1/chat

处理用户消息并返回回复。

**请求体**:
```json
{
  "event_id": "msg_123",
  "platform": "qq",
  "scene_type": "group",
  "scene_id": "group_456",
  "user_id": "user_789",
  "content": {
    "type": "text",
    "text": "你好"
  },
  "display_name": "小明",
  "timestamp": "2026-06-16T12:00:00Z"
}
```

**响应**:
```json
{
  "reply_text": "你好呀~",
  "should_reply": true,
  "metadata": {}
}
```

**cURL 示例**:
```bash
curl -X POST http://127.0.0.1:8001/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "qq",
    "scene_type": "private",
    "scene_id": "user_123",
    "user_id": "user_123",
    "content": {"type": "text", "text": "你好"},
    "display_name": "测试用户"
  }'
```

#### POST /v1/observe

只记录消息，不生成回复（用于观察群聊）。

**请求体**: 同 `/v1/chat`

**响应**:
```json
{
  "observed": true,
  "input_id": 123
}
```

---

### 2. 桌面操作

#### GET /v1/desktop/operations/pending

获取待执行的桌面操作任务（本地组件轮询）。

**查询参数**:
- `limit`: 返回数量（默认 10）

**响应**:
```json
{
  "operations": [
    {
      "id": 1,
      "operation_type": "create_file",
      "params": {
        "filename": "test.txt",
        "content": "Hello"
      },
      "status": "pending",
      "created_at": "2026-06-16T12:00:00Z"
    }
  ]
}
```

**cURL 示例**:
```bash
curl http://127.0.0.1:8001/v1/desktop/operations/pending?limit=5
```

#### POST /v1/desktop/operations/{id}/start

标记任务为执行中。

**cURL 示例**:
```bash
curl -X POST http://127.0.0.1:8001/v1/desktop/operations/1/start
```

#### POST /v1/desktop/operations/{id}/complete

上传任务执行结果。

**请求体**:
```json
{
  "success": true,
  "result": {
    "message": "已创建 test.txt",
    "file_path": "/path/to/test.txt"
  }
}
```

**cURL 示例**:
```bash
curl -X POST http://127.0.0.1:8001/v1/desktop/operations/1/complete \
  -H "Content-Type: application/json" \
  -d '{
    "success": true,
    "result": {
      "message": "已创建 test.txt",
      "file_path": "/home/user/Desktop/卡咔的小角落/test.txt"
    }
  }'
```

---

### 3. 通知推送

#### POST /v1/notifications/deliver

推送通知到指定平台。

**请求体**:
```json
{
  "target": {
    "platform": "qq",
    "scene_type": "group",
    "scene_id": "group_123"
  },
  "content": {
    "type": "text",
    "text": "任务完成！"
  },
  "idempotency_key": "unique_key_123"
}
```

**响应**:
```json
{
  "accepted": true,
  "delivered": true,
  "target": {
    "platform": "qq",
    "scene_type": "group",
    "scene_id": "group_123"
  }
}
```

---

### 4. 记忆管理

#### GET /v1/admin/memories

查询正式记忆列表。

**查询参数**:
- `limit`: 返回数量（默认 50）
- `offset`: 偏移量
- `status`: 状态筛选（active/archived）

**cURL 示例**:
```bash
curl http://127.0.0.1:8001/v1/admin/memories?limit=10&status=active
```

#### POST /v1/admin/memories

创建新记忆。

**请求体**:
```json
{
  "type": "fact",
  "content": "主人喜欢喝咖啡",
  "source_platform": "qq",
  "source_user_id": "user_123",
  "status": "active"
}
```

#### PUT /v1/admin/memories/{id}

更新记忆。

#### DELETE /v1/admin/memories/{id}

删除记忆（需确认）。

---

## 错误码

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 502 | 上游服务错误（如 QQ 适配器） |
| 503 | 服务不可用 |

**错误响应格式**:
```json
{
  "detail": "错误描述"
}
```

---

## 速率限制

本地开发环境无速率限制。

生产环境建议：
- `/v1/chat`: 60 请求/分钟/用户
- `/v1/desktop/operations/pending`: 20 请求/分钟
- `/v1/admin/*`: 100 请求/分钟

---

## WebSocket (未来)

计划支持 WebSocket 实时通信：
- `/ws/chat`: 实时聊天
- `/ws/notifications`: 通知推送

---

## SDK 示例

### Python

```python
import httpx

async def chat_with_kaka(text: str) -> str:
    """与卡咔对话。"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://127.0.0.1:8001/v1/chat",
            json={
                "platform": "desktop",
                "scene_type": "private",
                "scene_id": "my_app",
                "user_id": "user_123",
                "content": {"type": "text", "text": text},
                "display_name": "开发者",
            },
        )
        data = response.json()
        return data.get("reply_text", "")

# 使用
reply = await chat_with_kaka("你好")
print(reply)
```

### JavaScript

```javascript
async function chatWithKaka(text) {
  const response = await fetch('http://127.0.0.1:8001/v1/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      platform: 'web',
      scene_type: 'private',
      scene_id: 'web_chat',
      user_id: 'user_456',
      content: {type: 'text', text: text},
      display_name: 'Web用户'
    })
  });
  const data = await response.json();
  return data.reply_text;
}

// 使用
const reply = await chatWithKaka('你好');
console.log(reply);
```

---

## 健康检查

### GET /health

检查服务健康状态。

**响应**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 12345
}
```

---

## 更多信息

- **完整 API 文档**: http://127.0.0.1:8001/docs
- **ReDoc 文档**: http://127.0.0.1:8001/redoc
- **OpenAPI Schema**: http://127.0.0.1:8001/openapi.json
