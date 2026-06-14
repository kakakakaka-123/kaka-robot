# GitHub 周报外部插件说明

这个功能由 n8n 查询 GitHub 和格式化榜单，卡咔负责命令触发和主动推送。工作流支持两条入口：

- 命令 Webhook：收到卡咔的 `n8n` 插件请求后，直接把 JSON 结果返回给当前对话。
- 定时任务：每周一 09:00 主动查询上周榜单，再调用 kaka-core 的通知接口推送到指定 QQ 场景。

## 命令触发

启用插件系统后，在 QQ 或桌宠里发送：

```text
插件：n8n github_weekly_stars
```

卡咔会请求 n8n：

```text
http://127.0.0.1:5678/webhook/kaka/github_weekly_stars
```

n8n 的 `Command Webhook` 节点路径是 `kaka/github_weekly_stars`，并使用 `responseMode: responseNode`。工作流返回的对象包含：

```json
{
  "text": "中文 GitHub 周报摘要",
  "data": {},
  "metadata": {}
}
```

卡咔会读取 `text` 并回复到触发命令的当前对话。

## 定时主动推送

n8n 的 `Weekly Schedule` 节点设置为每周一 09:00 执行。工作流会计算上周一到上周日的日期范围，并调用 GitHub Search API：

```text
https://api.github.com/search/repositories
```

查询条件形如：

```text
created:2026-06-01..2026-06-07 fork:false archived:false stars:>50
```

如果配置了 `GITHUB_WEEKLY_LANGUAGE`，会追加 `language:<语言>`。请求参数包含 `sort=stars`、`order=desc`、`per_page=<GITHUB_WEEKLY_LIMIT>`。

定时分支格式化完成后，会 POST 到：

```text
http://127.0.0.1:8001/v1/notifications
```

通知请求体形如：

```json
{
  "target": {
    "platform": "qq",
    "scene_type": "group",
    "scene_id": "QQ群号"
  },
  "content": {
    "type": "text",
    "text": "中文 GitHub 周报摘要"
  },
  "source": "n8n:github_weekly_stars",
  "idempotency_key": "github-weekly-stars:2026-06-01:group:QQ群号"
}
```

kaka-core 校验 `PLUGIN_NOTIFICATION_TOKEN` 后，会把通知转发给 QQ adapter：

```text
http://127.0.0.1:8081/proactive/v1/send
```

## 本地配置

复制 `.env.example` 到 `.env` 后，至少配置：

```env
PLUGIN_SYSTEM_ENABLED=true
PLUGIN_N8N_WEBHOOK_BASE_URL=http://127.0.0.1:5678/webhook/kaka
PLUGIN_NOTIFICATION_TOKEN=本地随机密钥
PLUGIN_NOTIFICATION_ADAPTER_TIMEOUT=30
QQ_ADAPTER_SEND_BASE_URL=http://127.0.0.1:8081/proactive
QQ_ADAPTER_SEND_TOKEN=本地随机密钥
GITHUB_TOKEN=
GITHUB_WEEKLY_MIN_STARS=50
GITHUB_WEEKLY_LIMIT=10
GITHUB_WEEKLY_LANGUAGE=
GITHUB_WEEKLY_TARGET_SCENE_TYPE=group
GITHUB_WEEKLY_TARGET_SCENE_ID=QQ群号
```

`GITHUB_TOKEN` 可为空。为空时工作流走匿名 GitHub Search 请求，不会发送空的 `Authorization: Bearer ` 请求头；配置后会发送 `Authorization: Bearer <GITHUB_TOKEN>`，搜索限额更稳定。

## n8n 导入

在 n8n 中选择导入工作流 JSON：

```text
docs/n8n/github_weekly_stars.workflow.json
```

导入后检查：

- `Command Webhook` 的 path 是 `kaka/github_weekly_stars`。
- `Weekly Schedule` 是每周一 09:00。
- `Command Has GitHub Token?` 和 `Schedule Has GitHub Token?` 会把 GitHub 请求分为带 token 和匿名两种路径。
- `Route Command Digest` 只连接 `Respond to Command`。
- `Route Schedule Digest` 只连接 `Post Scheduled Digest to Kaka`。

## Token 安全

- 不要把 `.env`、`GITHUB_TOKEN`、`PLUGIN_NOTIFICATION_TOKEN`、`QQ_ADAPTER_SEND_TOKEN` 提交到 Git。
- `PLUGIN_NOTIFICATION_TOKEN` 只用于 n8n 调 kaka-core 的 `/v1/notifications`。
- `QQ_ADAPTER_SEND_TOKEN` 只用于 kaka-core 调 QQ adapter 的 proactive send API。
- GitHub token 建议使用最小权限 token；这个工作流只需要读取公开搜索结果。
- 如果 n8n 部署在非本机环境，请确保 kaka-core 和 QQ adapter 的主动通知接口不要暴露到公网，或放在可信内网和反向代理鉴权之后。
