# GitHub 项目雷达外部插件说明

这个功能由 n8n 查询 GitHub、生成榜单并格式化周报，卡咔负责命令触发和主动推送。它已经从"上周高星新项目"升级为"GitHub 项目雷达周报"：不限定语言和方向，重点筛出已经经过一定时间验证、最近仍然活跃的项目。

工作流支持两条入口：

- 命令 Webhook：收到卡咔的 `/github项目雷达` 命令后，直接以 JSON 结果返回给当前对话。
- 定时任务：每周一 09:00 主动生成一条项目雷达周报，再调用 kaka-core 的通知接口推送到指定 QQ 场景。

## 命令触发

启用插件系统后，在 QQ 或桌宠里发送：

```text
/github项目雷达
```

旧命令格式仍然兼容：

```text
插件：n8n github_weekly_stars
```

两种方式都会触发同一个 n8n 工作流，调用的 webhook 路径均为：

```text
http://127.0.0.1:5678/webhook/kaka/github_weekly_stars
```

导入的工作流名称已经改为 `Kaka GitHub Project Radar`。n8n 的 `Command Webhook` 节点路径是 `kaka/github_weekly_stars`，并使用 `responseMode: responseNode`。工作流返回的对象包含：

```json
{
  "text": "中文 GitHub 项目雷达周报",
  "data": {
    "growthSnapshotMode": "synthetic_first_run"
  },
  "metadata": {
    "source": "github_project_radar"
  }
}
```

卡咔会读取 `text` 并回复到触发命令的当前对话。

## /help 帮助面板

发送：

```text
/help
```

会列出所有可用的命令快捷方式和已注册插件。

## 周报内容

每次只发送一条消息，消息里包含三段榜单，每段默认 5 个项目：

```text
本周 GitHub 项目雷达

一、成熟活跃项目 Top 5
二、潜力项目 Top 5
三、增长最快项目 Top 5
```

三段榜单的含义：

- 成熟活跃项目：总 stars 较高，并且最近仍有更新，代表已经有较强验证和维护活跃度。
- 潜力项目：stars 位于中腰部，最近仍有更新，避免榜单长期被超级大项目占满。
- 增长最快项目：对比本次和上次快照的 stars 差值，按增长量排序。

增长榜需要历史快照。第一次运行时没有上次快照，工作流会生成可预测的测试增长数据，并在消息里标注：

```text
三、增长最快项目 Top 5（测试数据，真实增长榜将在下次周报生成）
```

定时分支每次运行后会把增长候选池写入 n8n workflow static data。下一次运行时，增长榜会用真实快照差值计算。

## 定时主动推送

n8n 的 `Weekly Schedule` 节点设置为每周一 09:00 执行。工作流调用 GitHub Search API：

```text
https://api.github.com/search/repositories
```

当前三组查询默认类似：

```text
成熟活跃项目：stars:>10000 fork:false archived:false pushed:>最近30天 sort=stars
潜力项目：stars:500..10000 fork:false archived:false pushed:>最近30天 sort=stars
增长候选池：stars:>500 fork:false archived:false pushed:>最近30天 sort=updated
```

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
    "text": "中文 GitHub 项目雷达周报"
  },
  "source": "n8n:github_project_radar",
  "idempotency_key": "github-project-radar:2026-06-15:group:QQ群号"
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
KAKA_CORE_BASE_URL=http://127.0.0.1:8001

PLUGIN_NOTIFICATION_TOKEN=<本地随机密钥>
PLUGIN_NOTIFICATION_ADAPTER_TIMEOUT=30

QQ_ADAPTER_SEND_BASE_URL=http://127.0.0.1:8081/proactive
QQ_ADAPTER_SEND_TOKEN=<本地随机密钥>

GITHUB_TOKEN=
GITHUB_RADAR_SECTION_LIMIT=5
GITHUB_RADAR_ACTIVE_DAYS=30
GITHUB_RADAR_MATURE_MIN_STARS=10000
GITHUB_RADAR_POTENTIAL_MIN_STARS=500
GITHUB_RADAR_POTENTIAL_MAX_STARS=10000
GITHUB_RADAR_GROWTH_MIN_STARS=500
GITHUB_RADAR_GROWTH_CANDIDATE_LIMIT=50
GITHUB_RADAR_FAKE_GROWTH_ON_FIRST_RUN=true
GITHUB_RADAR_TARGET_SCENE_TYPE=group
GITHUB_RADAR_TARGET_SCENE_ID=QQ群号
```

`GITHUB_TOKEN` 可为空。为空时工作流走匿名 GitHub Search 请求，不会发送空的 `Authorization: Bearer ` 请求头；配置后会发送 `Authorization: Bearer <GITHUB_TOKEN>`，搜索限额更稳定。

`KAKA_CORE_BASE_URL` 用于定时推送分支调用 kaka-core。未配置时，工作流默认使用 `http://127.0.0.1:8001`，适合 n8n 和 kaka-core 都在本机运行的开发环境。如果 n8n 运行在 Docker、另一台机器或服务器上，需要把它改成 n8n 能访问到的 kaka-core 地址。

## Docker 版 n8n 注意事项

如果 n8n 是用 Docker 跑的，n8n 工作流里的 `$env` 读取的是容器环境变量，不会自动读取卡咔项目根目录的 `.env`。需要把 GitHub 项目雷达相关配置也传给 n8n 容器。

Windows Docker Desktop 下，容器访问宿主机 kaka-core 推荐写：

```env
KAKA_CORE_BASE_URL=http://host.docker.internal:8001
```

如果写成 `http://127.0.0.1:8001`，n8n 容器会访问容器自己，定时主动推送会连不上宿主机上的 kaka-core。

n8n Code 节点需要读取 `$env.GITHUB_TOKEN`、`$env.GITHUB_RADAR_*`、`$env.PLUGIN_NOTIFICATION_TOKEN` 等变量。容器环境里必须允许 Code 节点访问环境变量：

```env
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

当前本机 n8n 推荐启动环境至少包含：

```env
KAKA_CORE_BASE_URL=http://host.docker.internal:8001
PLUGIN_NOTIFICATION_TOKEN=<和卡咔 .env 一致>
GITHUB_TOKEN=<可为空，建议填写 GitHub fine-grained token>
GITHUB_RADAR_SECTION_LIMIT=5
GITHUB_RADAR_ACTIVE_DAYS=30
GITHUB_RADAR_MATURE_MIN_STARS=10000
GITHUB_RADAR_POTENTIAL_MIN_STARS=500
GITHUB_RADAR_POTENTIAL_MAX_STARS=10000
GITHUB_RADAR_GROWTH_MIN_STARS=500
GITHUB_RADAR_GROWTH_CANDIDATE_LIMIT=50
GITHUB_RADAR_FAKE_GROWTH_ON_FIRST_RUN=true
GITHUB_RADAR_TARGET_SCENE_TYPE=group
GITHUB_RADAR_TARGET_SCENE_ID=<QQ群号>
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

修改 n8n 容器环境变量后，需要重建或重启容器。只在 n8n 网页里重新发布工作流，不会改变容器环境变量。

## 配置项说明

```env
GITHUB_RADAR_SECTION_LIMIT=5
```

每段榜单展示几个项目。当前推荐 5 个，避免一条 QQ 消息过长。

```env
GITHUB_RADAR_ACTIVE_DAYS=30
```

只选择最近多少天内更新过的项目。

```env
GITHUB_RADAR_MATURE_MIN_STARS=10000
```

成熟活跃项目榜的最低 stars。

```env
GITHUB_RADAR_POTENTIAL_MIN_STARS=500
GITHUB_RADAR_POTENTIAL_MAX_STARS=10000
```

潜力项目榜的 stars 区间。

```env
GITHUB_RADAR_GROWTH_MIN_STARS=500
GITHUB_RADAR_GROWTH_CANDIDATE_LIMIT=50
```

增长榜候选池的最低 stars 和候选数量。候选池越大，增长榜越有机会筛出真实热点，但 GitHub API 请求结果也更长。

```env
GITHUB_RADAR_FAKE_GROWTH_ON_FIRST_RUN=true
```

第一次没有历史快照时，是否生成测试增长数据。生成时会明确标注"测试数据"，不会伪装成真实增长。

```env
GITHUB_RADAR_TARGET_SCENE_TYPE=group
GITHUB_RADAR_TARGET_SCENE_ID=QQ群号
```

定时周报推送目标。`group` 表示 QQ 群，`private` 表示 QQ 私聊。

## n8n 导入

在 n8n 中选择导入工作流 JSON：

```text
docs/n8n/github_weekly_stars.workflow.json
```

导入后需要在 n8n 里启用或激活这个工作流。未激活时，生产 webhook 不会接收卡咔的 POST 请求，定时 Schedule 也不会运行。

导入后检查：

- workflow 名称是 `Kaka GitHub Project Radar`。
- `Command Webhook` 的 method 是 `POST`，path 是 `kaka/github_weekly_stars`。
- `Weekly Schedule` 是每周一 09:00。
- `Command Has GitHub Token?` 和 `Schedule Has GitHub Token?` 会把 GitHub 请求分为带 token 和匿名两种路径。
- `Route Command Digest` 只连接 `Respond to Command`。
- `Route Schedule Digest` 只连接 `Post Scheduled Digest to Kaka`。

## 测试建议

先测命令触发：

```text
/github项目雷达
```

或旧格式：

```text
插件：n8n github_weekly_stars
```

再在 n8n 里手动执行定时分支，确认链路：

```text
n8n -> kaka-core /v1/notifications -> QQ adapter /proactive/v1/send -> QQ 群
```

第一次定时分支运行后，增长榜会显示测试数据并写入快照。下一次定时分支运行后，增长榜会用真实快照差值。

## Token 安全

- 不要把 `.env`、`GITHUB_TOKEN`、`PLUGIN_NOTIFICATION_TOKEN`、`QQ_ADAPTER_SEND_TOKEN` 提交到 Git。
- `PLUGIN_NOTIFICATION_TOKEN` 只用于 n8n 调 kaka-core 的 `/v1/notifications`。
- `QQ_ADAPTER_SEND_TOKEN` 只用于 kaka-core 调 QQ adapter 的 proactive send API。
- GitHub token 建议使用最小权限 token；这个工作流只需要读取公开搜索结果。
- 如果 n8n 部署在非本机环境，请确保 kaka-core 和 QQ adapter 的主动通知接口不要暴露到公网，或放在可信内网和反向代理鉴权之后。
