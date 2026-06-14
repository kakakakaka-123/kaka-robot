# GitHub Weekly Stars External Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable external-plugin path for a weekly GitHub high-star new-project digest, supporting both command-triggered replies and scheduled proactive QQ delivery.

**Architecture:** Keep GitHub fetching and digest formatting in n8n. `kaka-core` remains platform-agnostic: it invokes n8n through the existing plugin bridge for command-triggered use, and exposes a protected notification API for external workflows. `qq-adapter` owns QQ delivery by exposing a local protected send endpoint that `kaka-core` can call with normalized notification targets.

**Tech Stack:** Python 3.12, FastAPI, Pydantic protocol models, httpx, NoneBot OneBot V11, n8n workflow JSON, pytest.

---

### File Structure

- Create `packages/kaka-protocol/src/kaka_protocol/notifications.py`: shared notification request/response models used by core and adapters.
- Modify `packages/kaka-protocol/src/kaka_protocol/__init__.py`: export notification models.
- Modify `packages/kaka-protocol/tests/test_protocol_models.py`: cover notification serialization and validation.
- Modify `services/kaka-core/src/kaka_core/config/settings.py`: add external notification settings.
- Create `services/kaka-core/src/kaka_core/notifications/__init__.py`: notification package exports.
- Create `services/kaka-core/src/kaka_core/notifications/service.py`: validate notification targets and forward them to platform adapters.
- Modify `services/kaka-core/src/kaka_core/api/routes.py`: add protected `/v1/notifications` endpoint for n8n.
- Modify `services/kaka-core/tests/test_api.py`: test notification auth, validation, and adapter forwarding.
- Modify `apps/qq-adapter/src/qq_adapter/config.py`: add local send API settings.
- Create `apps/qq-adapter/src/qq_adapter/api.py`: FastAPI routes for protected proactive QQ sending.
- Modify `apps/qq-adapter/bot.py`: mount proactive send API into the NoneBot FastAPI driver app.
- Modify `apps/qq-adapter/src/qq_adapter/nonebot_plugins/kaka_chat.py`: reuse direct send helper for proactive sending.
- Create `apps/qq-adapter/tests/test_proactive_send_api.py`: test QQ send endpoint using a fake bot.
- Modify `.env.example`: document GitHub/n8n notification variables.
- Create `docs/n8n/github_weekly_stars.workflow.json`: importable n8n workflow for command and scheduled triggers.
- Create `docs/GitHub周报外部插件说明.md`: setup and usage notes.

---

### Task 1: Shared Notification Protocol Models

**Files:**
- Create: `packages/kaka-protocol/src/kaka_protocol/notifications.py`
- Modify: `packages/kaka-protocol/src/kaka_protocol/__init__.py`
- Test: `packages/kaka-protocol/tests/test_protocol_models.py`

- [ ] **Step 1: Write failing protocol tests**

Append these tests to `packages/kaka-protocol/tests/test_protocol_models.py`:

```python
from kaka_protocol import (
    NotificationRequest,
    NotificationResult,
    NotificationTarget,
)


def test_notification_request_can_be_serialized() -> None:
    request = NotificationRequest(
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="20002",
        ),
        content=MessageContent.text_message("GitHub 周报"),
        source="n8n:github_weekly_stars",
        idempotency_key="github-weekly-stars:2026-06-08:qq:group:20002",
    )

    data = request.model_dump(mode="json")

    assert data["target"]["platform"] == "qq"
    assert data["target"]["scene_type"] == "group"
    assert data["target"]["scene_id"] == "20002"
    assert data["content"]["type"] == "text"
    assert data["content"]["text"] == "GitHub 周报"
    assert data["source"] == "n8n:github_weekly_stars"
    assert data["idempotency_key"] == "github-weekly-stars:2026-06-08:qq:group:20002"


def test_notification_result_can_be_serialized() -> None:
    result = NotificationResult(
        accepted=True,
        delivered=True,
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="20002",
        ),
        metadata={"adapter": "qq"},
    )

    data = result.model_dump(mode="json")

    assert data["accepted"] is True
    assert data["delivered"] is True
    assert data["target"]["platform"] == "qq"
    assert data["metadata"]["adapter"] == "qq"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest packages\kaka-protocol\tests\test_protocol_models.py -q
```

Expected: FAIL with import errors for `NotificationRequest`, `NotificationResult`, and `NotificationTarget`.

- [ ] **Step 3: Add notification models**

Create `packages/kaka-protocol/src/kaka_protocol/notifications.py`:

```python
from typing import Any

from pydantic import BaseModel, Field

from kaka_protocol.enums import Platform, SceneType
from kaka_protocol.messages import MessageContent


class NotificationTarget(BaseModel):
    """A platform-neutral target for proactive outbound messages."""

    platform: Platform
    scene_type: SceneType
    scene_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationRequest(BaseModel):
    """A proactive notification request from an external workflow or core service."""

    target: NotificationTarget
    content: MessageContent
    source: str = "external"
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationResult(BaseModel):
    """Delivery result for a proactive notification."""

    accepted: bool
    delivered: bool = False
    target: NotificationTarget
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Modify `packages/kaka-protocol/src/kaka_protocol/__init__.py`:

```python
"""卡咔 的统一协议模型。

这个包会被两类模块共同使用：
- adapter：QQ、网页、语音、IoT 等外部入口。
- kaka-core：卡咔的核心大脑。

协议层只负责定义数据格式，不负责连接平台、调用模型或保存数据库。
"""

from kaka_protocol.enums import ActionType, ContentType, Platform, SceneType
from kaka_protocol.messages import MessageContent, MessageEvent
from kaka_protocol.notifications import (
    NotificationRequest,
    NotificationResult,
    NotificationTarget,
)
from kaka_protocol.responses import KakaResponse, ResponseAction

__all__ = [
    "ActionType",
    "ContentType",
    "KakaResponse",
    "MessageContent",
    "MessageEvent",
    "NotificationRequest",
    "NotificationResult",
    "NotificationTarget",
    "Platform",
    "ResponseAction",
    "SceneType",
]
```

- [ ] **Step 4: Run protocol tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest packages\kaka-protocol\tests\test_protocol_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add packages/kaka-protocol/src/kaka_protocol/notifications.py packages/kaka-protocol/src/kaka_protocol/__init__.py packages/kaka-protocol/tests/test_protocol_models.py
git commit -m "feat: add notification protocol models"
```

---

### Task 2: Core Notification Forwarding Service

**Files:**
- Modify: `services/kaka-core/src/kaka_core/config/settings.py`
- Create: `services/kaka-core/src/kaka_core/notifications/__init__.py`
- Create: `services/kaka-core/src/kaka_core/notifications/service.py`
- Modify: `services/kaka-core/src/kaka_core/api/routes.py`
- Test: `services/kaka-core/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Append these imports to `services/kaka-core/tests/test_api.py`:

```python
import httpx
```

Append these tests to `services/kaka-core/tests/test_api.py`:

```python
def test_notification_rejects_missing_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-auth.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "secret-token")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    get_settings.cache_clear()

    request = {
        "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
    }

    response = client.post("/v1/notifications", json=request)

    assert response.status_code == 401
    get_settings.cache_clear()


def test_notification_rejects_unsupported_platform(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-platform.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "secret-token")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    get_settings.cache_clear()

    request = {
        "target": {"platform": "desktop", "scene_type": "private", "scene_id": "desktop-local"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
    }

    response = client.post(
        "/v1/notifications",
        headers={"Authorization": "Bearer secret-token"},
        json=request,
    )

    assert response.status_code == 400
    assert "unsupported notification platform" in response.json()["detail"]
    get_settings.cache_clear()


def test_notification_forwards_to_qq_adapter(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-forward.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "secret-token")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def fake_post(self: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "delivered": True,
                "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
                "metadata": {"adapter": "qq"},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    request = {
        "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
        "idempotency_key": "github-weekly-stars:2026-06-08:qq:group:20002",
    }

    response = client.post(
        "/v1/notifications",
        headers={"Authorization": "Bearer secret-token"},
        json=request,
    )

    assert response.status_code == 200
    assert response.json()["delivered"] is True
    assert captured["url"] == "http://qq-adapter.local/v1/send"
    assert captured["headers"] == {"Authorization": "Bearer qq-send-token"}
    assert captured["json"] == request
    get_settings.cache_clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_api.py -q
```

Expected: FAIL because `/v1/notifications` does not exist.

- [ ] **Step 3: Add notification settings**

Modify `services/kaka-core/src/kaka_core/config/settings.py`.

Add this dataclass after `PluginSettings`:

```python
@dataclass(frozen=True)
class NotificationSettings:
    """External proactive notification configuration."""

    token: str
    qq_adapter_send_base_url: str
    qq_adapter_send_token: str
    adapter_timeout_seconds: float
```

Add a field to `Settings`:

```python
    notifications: NotificationSettings
```

Add this block inside `get_settings()` when constructing `Settings`:

```python
        notifications=NotificationSettings(
            token=os.getenv("PLUGIN_NOTIFICATION_TOKEN", "").strip(),
            qq_adapter_send_base_url=os.getenv("QQ_ADAPTER_SEND_BASE_URL", "").rstrip("/"),
            qq_adapter_send_token=os.getenv("QQ_ADAPTER_SEND_TOKEN", "").strip(),
            adapter_timeout_seconds=_get_float("PLUGIN_NOTIFICATION_ADAPTER_TIMEOUT", 30.0),
        ),
```

- [ ] **Step 4: Add forwarding service**

Create `services/kaka-core/src/kaka_core/notifications/__init__.py`:

```python
from kaka_core.notifications.service import NotificationDeliveryError, deliver_notification

__all__ = ["NotificationDeliveryError", "deliver_notification"]
```

Create `services/kaka-core/src/kaka_core/notifications/service.py`:

```python
import httpx

from kaka_core.config.settings import NotificationSettings
from kaka_protocol import NotificationRequest, NotificationResult, Platform


class NotificationDeliveryError(RuntimeError):
    """Raised when a notification cannot be forwarded to its platform adapter."""


def deliver_notification(
    request: NotificationRequest,
    settings: NotificationSettings,
) -> NotificationResult:
    """Forward a normalized proactive notification to the target platform adapter."""

    if request.target.platform != Platform.QQ:
        raise NotificationDeliveryError(
            f"unsupported notification platform: {request.target.platform}"
        )
    if not settings.qq_adapter_send_base_url:
        raise NotificationDeliveryError("QQ adapter send base URL is not configured")

    url = f"{settings.qq_adapter_send_base_url}/v1/send"
    headers = {}
    if settings.qq_adapter_send_token:
        headers["Authorization"] = f"Bearer {settings.qq_adapter_send_token}"

    try:
        with httpx.Client(timeout=settings.adapter_timeout_seconds) as client:
            response = client.post(
                url,
                headers=headers,
                json=request.model_dump(mode="json"),
            )
    except httpx.HTTPError as exc:
        raise NotificationDeliveryError(f"QQ adapter request failed: {exc}") from exc

    if response.status_code >= 400:
        raise NotificationDeliveryError(
            f"QQ adapter rejected notification: HTTP {response.status_code} {response.text}"
        )

    return NotificationResult.model_validate(response.json())
```

- [ ] **Step 5: Add protected core endpoint**

Modify `services/kaka-core/src/kaka_core/api/routes.py`:

```python
from fastapi import APIRouter, Header, HTTPException, status

from kaka_core.chat.service import generate_chat_response, observe_message
from kaka_core.config.settings import get_settings
from kaka_core.notifications import NotificationDeliveryError, deliver_notification
from kaka_protocol import KakaResponse, MessageEvent, NotificationRequest, NotificationResult
```

Append this helper and route:

```python
def _require_notification_token(authorization: str | None) -> None:
    settings = get_settings()
    token = settings.notifications.token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="notification token is not configured",
        )
    if authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid notification token",
        )


@router.post("/v1/notifications", response_model=NotificationResult)
def notify(
    request: NotificationRequest,
    authorization: str | None = Header(default=None),
) -> NotificationResult:
    """Receive a proactive external notification and forward it to the adapter."""

    _require_notification_token(authorization)
    settings = get_settings()
    try:
        return deliver_notification(request, settings.notifications)
    except NotificationDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

- [ ] **Step 6: Run core API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests\test_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add services/kaka-core/src/kaka_core/config/settings.py services/kaka-core/src/kaka_core/notifications services/kaka-core/src/kaka_core/api/routes.py services/kaka-core/tests/test_api.py
git commit -m "feat: add external notification forwarding"
```

---

### Task 3: QQ Adapter Proactive Send API

**Files:**
- Modify: `apps/qq-adapter/src/qq_adapter/config.py`
- Create: `apps/qq-adapter/src/qq_adapter/api.py`
- Modify: `apps/qq-adapter/bot.py`
- Modify: `apps/qq-adapter/src/qq_adapter/nonebot_plugins/kaka_chat.py`
- Test: `apps/qq-adapter/tests/test_proactive_send_api.py`

- [ ] **Step 1: Write failing proactive send API tests**

Create `apps/qq-adapter/tests/test_proactive_send_api.py`:

```python
from fastapi.testclient import TestClient

from kaka_protocol import MessageContent, NotificationRequest, NotificationTarget, Platform, SceneType
from qq_adapter.api import create_send_api
from qq_adapter.config import get_settings


class FakeBot:
    def __init__(self) -> None:
        self.group_messages: list[tuple[int, str]] = []
        self.private_messages: list[tuple[int, str]] = []

    async def send_group_msg(self, *, group_id: int, message: str) -> None:
        self.group_messages.append((group_id, message))

    async def send_private_msg(self, *, user_id: int, message: str) -> None:
        self.private_messages.append((user_id, message))


def test_send_api_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))
    request = NotificationRequest(
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="20002",
        ),
        content=MessageContent.text_message("GitHub 周报"),
        source="n8n:github_weekly_stars",
    )

    response = client.post("/v1/send", json=request.model_dump(mode="json"))

    assert response.status_code == 401
    assert fake_bot.group_messages == []
    get_settings.cache_clear()


def test_send_api_sends_group_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))
    request = NotificationRequest(
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="20002",
        ),
        content=MessageContent.text_message("GitHub 周报"),
        source="n8n:github_weekly_stars",
    )

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["delivered"] is True
    assert fake_bot.group_messages == [(20002, "GitHub 周报")]
    get_settings.cache_clear()


def test_send_api_sends_private_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))
    request = NotificationRequest(
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.PRIVATE,
            scene_id="10001",
        ),
        content=MessageContent.text_message("GitHub 周报"),
        source="n8n:github_weekly_stars",
    )

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["delivered"] is True
    assert fake_bot.private_messages == [(10001, "GitHub 周报")]
    get_settings.cache_clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps\qq-adapter\tests\test_proactive_send_api.py -q
```

Expected: FAIL because `qq_adapter.api` does not exist.

- [ ] **Step 3: Add QQ adapter send settings**

Modify `apps/qq-adapter/src/qq_adapter/config.py`.

Update `QQAdapterSettings`:

```python
@dataclass(frozen=True)
class QQAdapterSettings:
    """QQ adapter configuration."""

    core_base_url: str
    request_timeout_seconds: float
    send_token: str
```

Update `get_settings()`:

```python
    return QQAdapterSettings(
        core_base_url=os.getenv("KAKA_CORE_BASE_URL", "http://127.0.0.1:8001").rstrip("/"),
        request_timeout_seconds=float(os.getenv("QQ_ADAPTER_REQUEST_TIMEOUT", "60")),
        send_token=os.getenv("QQ_ADAPTER_SEND_TOKEN", "").strip(),
    )
```

- [ ] **Step 4: Add direct send helpers**

Modify `apps/qq-adapter/src/qq_adapter/nonebot_plugins/kaka_chat.py`.

Add imports:

```python
from kaka_protocol import NotificationRequest, SceneType
```

Add this function near `_send_text_action()`:

```python
async def send_notification_request(bot: Bot, request: NotificationRequest) -> None:
    """Send a proactive notification without relying on an inbound QQ event."""

    if not request.content.text:
        raise ValueError("only non-empty text notifications are supported")

    if request.target.scene_type == SceneType.GROUP:
        await bot.send_group_msg(group_id=int(request.target.scene_id), message=request.content.text)
        return

    if request.target.scene_type == SceneType.PRIVATE:
        await bot.send_private_msg(user_id=int(request.target.scene_id), message=request.content.text)
        return

    raise ValueError(f"unsupported QQ notification scene type: {request.target.scene_type}")
```

- [ ] **Step 5: Add FastAPI send app**

Create `apps/qq-adapter/src/qq_adapter/api.py`:

```python
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status

from kaka_protocol import NotificationRequest, NotificationResult, Platform
from qq_adapter.config import get_settings
from qq_adapter.nonebot_plugins.kaka_chat import send_notification_request


def _require_send_token(authorization: str | None) -> None:
    token = get_settings().send_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QQ adapter send token is not configured",
        )
    if authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid QQ adapter send token",
        )


def create_send_api(get_bot: Callable[[], Any]) -> FastAPI:
    """Create a small FastAPI app for proactive QQ delivery."""

    app = FastAPI(title="kaka QQ adapter send API")

    @app.post("/v1/send", response_model=NotificationResult)
    async def send(
        request: NotificationRequest,
        authorization: str | None = Header(default=None),
    ) -> NotificationResult:
        _require_send_token(authorization)
        if request.target.platform != Platform.QQ:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported platform: {request.target.platform}",
            )
        try:
            await send_notification_request(get_bot(), request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return NotificationResult(
            accepted=True,
            delivered=True,
            target=request.target,
            metadata={"adapter": "qq", "source": request.source},
        )

    return app
```

- [ ] **Step 6: Mount send API in the NoneBot app**

Modify `apps/qq-adapter/bot.py`:

```python
"""QQ adapter NoneBot2 entrypoint."""

import nonebot
from nonebot import get_bots, get_driver
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from qq_adapter.api import create_send_api

nonebot.init(host="127.0.0.1", port=8081)

driver = get_driver()
driver.register_adapter(OneBotV11Adapter)


def _get_primary_bot():
    bots = get_bots()
    if not bots:
        raise RuntimeError("no OneBot connection is available")
    return next(iter(bots.values()))


driver.server_app.mount("/proactive", create_send_api(_get_primary_bot))

nonebot.load_plugin("qq_adapter.nonebot_plugins.kaka_chat")


if __name__ == "__main__":
    nonebot.run()
```

The proactive endpoint becomes:

```text
POST http://127.0.0.1:8081/proactive/v1/send
```

- [ ] **Step 7: Run QQ adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps\qq-adapter\tests -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add apps/qq-adapter/src/qq_adapter/config.py apps/qq-adapter/src/qq_adapter/api.py apps/qq-adapter/src/qq_adapter/nonebot_plugins/kaka_chat.py apps/qq-adapter/bot.py apps/qq-adapter/tests/test_proactive_send_api.py
git commit -m "feat: add proactive QQ send API"
```

---

### Task 4: n8n GitHub Weekly Stars Workflow

**Files:**
- Create: `docs/n8n/github_weekly_stars.workflow.json`
- Modify: `.env.example`
- Create: `docs/GitHub周报外部插件说明.md`

- [ ] **Step 1: Create the n8n workflow export**

Create `docs/n8n/github_weekly_stars.workflow.json` with this importable workflow skeleton:

```json
{
  "name": "kaka-github-weekly-stars",
  "nodes": [
    {
      "parameters": {
        "path": "kaka/github_weekly_stars",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "WebhookTrigger",
      "name": "Command Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 0],
      "webhookId": "kaka-github-weekly-stars-command"
    },
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "weeks",
              "triggerAtDay": [1],
              "triggerAtHour": 9,
              "triggerAtMinute": 0
            }
          ]
        }
      },
      "id": "ScheduleTrigger",
      "name": "Weekly Schedule",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 260]
    },
    {
      "parameters": {
        "jsCode": "const now = new Date();\nconst day = now.getDay();\nconst daysSinceMonday = (day + 6) % 7;\nconst thisMonday = new Date(now);\nthisMonday.setDate(now.getDate() - daysSinceMonday);\nthisMonday.setHours(0, 0, 0, 0);\nconst lastMonday = new Date(thisMonday);\nlastMonday.setDate(thisMonday.getDate() - 7);\nconst lastSunday = new Date(thisMonday);\nlastSunday.setDate(thisMonday.getDate() - 1);\nconst fmt = (d) => d.toISOString().slice(0, 10);\nconst minStars = Number($env.GITHUB_WEEKLY_MIN_STARS || 50);\nconst limit = Number($env.GITHUB_WEEKLY_LIMIT || 10);\nconst language = ($env.GITHUB_WEEKLY_LANGUAGE || '').trim();\nconst languageQuery = language ? ` language:${language}` : '';\nconst q = `created:${fmt(lastMonday)}..${fmt(lastSunday)} fork:false archived:false stars:>${minStars}${languageQuery}`;\nreturn [{ json: { startDate: fmt(lastMonday), endDate: fmt(lastSunday), minStars, limit, q, trigger: $json.workflow ? 'command' : 'schedule', input: $json.input || '' } }];"
      },
      "id": "BuildQuery",
      "name": "Build GitHub Query",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [260, 130]
    },
    {
      "parameters": {
        "url": "https://api.github.com/search/repositories",
        "sendQuery": true,
        "queryParameters": {
          "parameters": [
            { "name": "q", "value": "={{$json.q}}" },
            { "name": "sort", "value": "stars" },
            { "name": "order", "value": "desc" },
            { "name": "per_page", "value": "={{$json.limit}}" }
          ]
        },
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            { "name": "Accept", "value": "application/vnd.github+json" },
            { "name": "X-GitHub-Api-Version", "value": "2022-11-28" },
            { "name": "Authorization", "value": "={{$env.GITHUB_TOKEN ? `Bearer ${$env.GITHUB_TOKEN}` : ''}}" }
          ]
        },
        "options": {}
      },
      "id": "GitHubSearch",
      "name": "Search Repositories",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [520, 130]
    },
    {
      "parameters": {
        "jsCode": "const startDate = $('Build GitHub Query').first().json.startDate;\nconst endDate = $('Build GitHub Query').first().json.endDate;\nconst repos = $json.items || [];\nconst lines = [`上周 GitHub 高星新项目 Top ${repos.length}（${startDate} 至 ${endDate}）`];\nif (!repos.length) {\n  lines.push('没有找到符合条件的新项目，可以降低 GITHUB_WEEKLY_MIN_STARS。');\n} else {\n  repos.forEach((repo, index) => {\n    const stars = repo.stargazers_count?.toLocaleString('en-US') || '0';\n    const lang = repo.language || 'Unknown';\n    const desc = repo.description || '暂无描述';\n    lines.push(`${index + 1}. ${repo.full_name}  ⭐ ${stars}`);\n    lines.push(`   ${desc}`);\n    lines.push(`   语言：${lang}`);\n    lines.push(`   ${repo.html_url}`);\n  });\n}\nreturn [{ json: { text: lines.join('\\n'), data: { startDate, endDate, count: repos.length, repos }, metadata: { source: 'github_weekly_stars' } } }];"
      },
      "id": "FormatDigest",
      "name": "Format Digest",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [780, 130]
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "={{$json}}",
        "options": {}
      },
      "id": "RespondToKaka",
      "name": "Respond to Command",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1.1,
      "position": [1040, 0]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{$env.KAKA_CORE_BASE_URL || 'http://127.0.0.1:8001'}}/v1/notifications",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            { "name": "Authorization", "value": "=Bearer {{$env.PLUGIN_NOTIFICATION_TOKEN}}" }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={{ { target: { platform: 'qq', scene_type: $env.GITHUB_WEEKLY_TARGET_SCENE_TYPE || 'group', scene_id: $env.GITHUB_WEEKLY_TARGET_SCENE_ID }, content: { type: 'text', text: $json.text }, source: 'n8n:github_weekly_stars', idempotency_key: `github-weekly-stars:${$json.data.startDate}:${$env.GITHUB_WEEKLY_TARGET_SCENE_ID}` } }}",
        "options": {}
      },
      "id": "PostToKaka",
      "name": "Post Scheduled Digest to Kaka",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [1040, 260]
    }
  ],
  "connections": {
    "Command Webhook": {
      "main": [[{ "node": "Build GitHub Query", "type": "main", "index": 0 }]]
    },
    "Weekly Schedule": {
      "main": [[{ "node": "Build GitHub Query", "type": "main", "index": 0 }]]
    },
    "Build GitHub Query": {
      "main": [[{ "node": "Search Repositories", "type": "main", "index": 0 }]]
    },
    "Search Repositories": {
      "main": [[{ "node": "Format Digest", "type": "main", "index": 0 }]]
    },
    "Format Digest": {
      "main": [
        [{ "node": "Respond to Command", "type": "main", "index": 0 }],
        [{ "node": "Post Scheduled Digest to Kaka", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": { "executionOrder": "v1" }
}
```

- [ ] **Step 2: Add environment examples**

Append to `.env.example`:

```env

# External proactive notifications from n8n or other workflows.
# Use a local random value and send it as Authorization: Bearer <token>.
PLUGIN_NOTIFICATION_TOKEN=replace-with-local-notification-token
PLUGIN_NOTIFICATION_ADAPTER_TIMEOUT=30

# kaka-core -> QQ adapter proactive send API.
QQ_ADAPTER_SEND_BASE_URL=http://127.0.0.1:8081/proactive
QQ_ADAPTER_SEND_TOKEN=replace-with-local-qq-send-token

# n8n GitHub weekly stars workflow.
# GITHUB_TOKEN is optional but recommended for stable GitHub Search API limits.
GITHUB_TOKEN=
GITHUB_WEEKLY_MIN_STARS=50
GITHUB_WEEKLY_LIMIT=10
GITHUB_WEEKLY_LANGUAGE=
GITHUB_WEEKLY_TARGET_SCENE_TYPE=group
GITHUB_WEEKLY_TARGET_SCENE_ID=replace-with-your-qq-group-id
```

- [ ] **Step 3: Add setup documentation**

Create `docs/GitHub周报外部插件说明.md`:

```markdown
# GitHub 周报外部插件说明

这个功能由 n8n 负责查询 GitHub 和格式化榜单，卡咔负责命令触发和主动推送。

## 命令触发

启用插件系统后，在 QQ 或桌宠里发送：

```text
插件：n8n github_weekly_stars
```

卡咔会请求：

```text
http://127.0.0.1:5678/webhook/kaka/github_weekly_stars
```

n8n 返回 `{ "text": "..." }` 后，卡咔把榜单发回当前对话。

## 定时主动推送

n8n 每周一 09:00 运行一次，查询上周一到上周日创建的公开仓库：

```text
created:上周一..上周日 fork:false archived:false stars:>50
```

然后 POST 到：

```text
http://127.0.0.1:8001/v1/notifications
```

kaka-core 校验 `PLUGIN_NOTIFICATION_TOKEN` 后，把消息转发给 QQ adapter：

```text
http://127.0.0.1:8081/proactive/v1/send
```

## 本地配置

`.env` 里至少需要：

```env
PLUGIN_SYSTEM_ENABLED=true
PLUGIN_N8N_WEBHOOK_BASE_URL=http://127.0.0.1:5678/webhook/kaka
PLUGIN_NOTIFICATION_TOKEN=本地随机密钥
QQ_ADAPTER_SEND_BASE_URL=http://127.0.0.1:8081/proactive
QQ_ADAPTER_SEND_TOKEN=本地随机密钥
GITHUB_WEEKLY_TARGET_SCENE_TYPE=group
GITHUB_WEEKLY_TARGET_SCENE_ID=QQ群号
```

`GITHUB_TOKEN` 可选，但建议配置。它只用于提高 GitHub Search API 的稳定性，不需要写入代码。

## n8n 导入

导入：

```text
docs/n8n/github_weekly_stars.workflow.json
```

导入后检查 HTTP Request 节点的环境变量和 Schedule Trigger 时间。
```

- [ ] **Step 4: Validate workflow JSON**

Run:

```powershell
node -e "JSON.parse(require('fs').readFileSync('docs/n8n/github_weekly_stars.workflow.json','utf8')); console.log('workflow json ok')"
```

Expected: `workflow json ok`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/n8n/github_weekly_stars.workflow.json docs/GitHub周报外部插件说明.md .env.example
git commit -m "docs: add github weekly stars n8n workflow"
```

---

### Task 5: End-to-End Verification

**Files:**
- All files changed above.

- [ ] **Step 1: Run protocol tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest packages\kaka-protocol\tests -q
```

Expected: all protocol tests pass.

- [ ] **Step 2: Run core tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest services\kaka-core\tests -q
```

Expected: all core tests pass.

- [ ] **Step 3: Run QQ adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps\qq-adapter\tests -q
```

Expected: all QQ adapter tests pass.

- [ ] **Step 4: Run full Python regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest packages\kaka-protocol\tests services\kaka-core\tests apps\qq-adapter\tests
```

Expected: all tests pass.

- [ ] **Step 5: Check for whitespace and secret leaks**

Run:

```powershell
git diff --check
rg -n "github_pat_|ghp_|GITHUB_TOKEN=github|PLUGIN_NOTIFICATION_TOKEN=[A-Za-z0-9_-]{12,}|QQ_ADAPTER_SEND_TOKEN=[A-Za-z0-9_-]{12,}" .
```

Expected: `git diff --check` exits 0. The `rg` command must not find real tokens; placeholders in `.env.example` are acceptable only if they are not real secrets.

- [ ] **Step 6: Manual command-trigger check**

Start n8n and kaka-core, then run:

```powershell
$body = @{
  event_id = "manual-github-weekly-stars"
  platform = "qq"
  scene_type = "group"
  scene_id = "20002"
  user_id = "10001"
  display_name = "tester"
  content = @{ type = "text"; text = "插件：n8n github_weekly_stars" }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/v1/chat -Body $body -ContentType "application/json"
```

Expected: response has one `send_text` action containing `GitHub 高星新项目`.

- [ ] **Step 7: Manual proactive notification check**

With QQ adapter connected to NapCat, run:

```powershell
$body = @{
  target = @{ platform = "qq"; scene_type = "group"; scene_id = $env:GITHUB_WEEKLY_TARGET_SCENE_ID }
  content = @{ type = "text"; text = "GitHub 周报主动推送测试" }
  source = "manual-test"
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8001/v1/notifications `
  -Headers @{ Authorization = "Bearer $env:PLUGIN_NOTIFICATION_TOKEN" } `
  -Body $body `
  -ContentType "application/json"
```

Expected: target QQ group receives `GitHub 周报主动推送测试`.

- [ ] **Step 8: Final commit if manual fixes were needed**

If verification required fixes, commit them:

```powershell
git add .
git commit -m "fix: stabilize github weekly stars notification flow"
```

Expected: no uncommitted source changes remain except local `.env` or runtime data ignored by git.

---

### Self-Review Notes

- Command-triggered use is covered by the existing n8n plugin bridge; no new GitHub-specific internal plugin is added.
- Scheduled proactive use is platform-neutral at the core boundary and QQ-specific only inside `qq-adapter`.
- Tokens are read from environment variables and documented as local-only values.
- The plan intentionally does not store notification idempotency keys yet. The workflow sends one notification per scheduled run; persistent dedupe can be added later if duplicate scheduled executions become a real problem.
