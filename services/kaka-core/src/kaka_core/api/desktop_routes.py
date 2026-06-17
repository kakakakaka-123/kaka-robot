"""桌面操作 API 路由。

卡咔可以在主人电脑上执行操作（创建文件、截图等）。
这些能力是卡咔本身的能力，对外不暴露"助手"概念。
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from kaka_core.config.settings import get_settings
from kaka_core.messages import create_screenshot_message
from kaka_core.notifications import deliver_notification
from kaka_core.storage.database import get_session
from kaka_core.storage.desktop_repository import (
    complete_operation,
    create_desktop_operation,
    get_operation_by_id,
    get_pending_operations,
    mark_operation_executing,
)
from kaka_protocol import MessageContent, NotificationRequest, NotificationTarget, Platform, SceneType

router = APIRouter(prefix="/v1/desktop", tags=["desktop"])
SessionDep = Annotated[Session, Depends(get_session)]


# ==================== 数据模型 ====================


class CreateOperationRequest(BaseModel):
    """创建桌面操作请求（由插件内部调用）。"""

    operation_type: str
    params: dict
    requester_user_id: str
    requester_scene_id: str
    requester_scene_type: str = "private"
    requester_platform: str
    approved: bool = True
    decision_reason: str | None = None
    kaka_mood: str | None = None
    permission_level: int = 1


class CompleteOperationRequest(BaseModel):
    """完成操作请求（由本地组件上传结果）。"""

    success: bool
    result: dict


class OperationResponse(BaseModel):
    """操作详情响应。"""

    id: int
    operation_type: str
    params: dict
    status: str
    result: dict | None = None
    created_at: str


class PendingOperationsResponse(BaseModel):
    """待执行操作列表响应。"""

    operations: list[OperationResponse]


# ==================== 给本地组件用的 API ====================


@router.get("/operations/pending")
async def get_pending_operations_endpoint(
    session: SessionDep,
    limit: int = 10,
) -> PendingOperationsResponse:
    """本地组件轮询待执行的操作。"""
    records = get_pending_operations(session, limit=limit)

    operations = [
        OperationResponse(
            id=record.id,
            operation_type=record.operation_type,
            params=record.params,
            status=record.status,
            result=record.result,
            created_at=record.created_at.isoformat(),
        )
        for record in records
    ]

    return PendingOperationsResponse(operations=operations)


@router.post("/operations/{operation_id}/start")
async def start_operation(
    operation_id: int,
    session: SessionDep,
) -> dict:
    """本地组件标记操作开始执行。"""
    mark_operation_executing(session, operation_id)
    session.commit()
    return {"success": True}


@router.post("/operations/{operation_id}/complete")
async def complete_operation_endpoint(
    operation_id: int,
    request: CompleteOperationRequest,
    session: SessionDep,
) -> dict:
    """本地组件上传执行结果，并推送通知到原场景。"""
    # 1. 更新数据库
    operation = complete_operation(
        session, operation_id, success=request.success, result=request.result
    )

    if not operation:
        return {"success": False, "error": "Operation not found"}

    session.commit()

    # 2. 构造回复消息
    reply_text = _build_completion_message(operation, request)

    # 3. 推送回原场景
    await _send_completion_notification(operation, reply_text, request)

    return {"success": True}


# ==================== 内部调用的 API ====================


@router.post("/operations")
async def create_operation_endpoint(
    request: CreateOperationRequest,
    session: SessionDep,
) -> dict:
    """创建桌面操作任务（由插件调用）。"""
    operation_id = create_desktop_operation(
        session,
        operation_type=request.operation_type,
        params=request.params,
        requester_user_id=request.requester_user_id,
        requester_scene_id=request.requester_scene_id,
        requester_platform=request.requester_platform,
        requester_scene_type=request.requester_scene_type,
        approved=request.approved,
        decision_reason=request.decision_reason,
        kaka_mood=request.kaka_mood,
        permission_level=request.permission_level,
    )
    session.commit()

    return {"operation_id": operation_id, "status": "pending"}


@router.get("/operations/{operation_id}")
async def get_operation_endpoint(
    operation_id: int,
    session: SessionDep,
) -> OperationResponse | dict:
    """查询操作详情。"""
    record = get_operation_by_id(session, operation_id)

    if not record:
        return {"error": "Operation not found"}

    return OperationResponse(
        id=record.id,
        operation_type=record.operation_type,
        params=record.params,
        status=record.status,
        result=record.result,
        created_at=record.created_at.isoformat(),
    )


# ==================== 辅助函数 ====================


def _build_completion_message(operation, request: CompleteOperationRequest) -> str:
    """构造完成后的回复消息。"""
    if request.success:
        # 成功：强调"我做的"
        base_messages = {
            "create_file": "写好了~",
            "screenshot": "截好了~",
            "play_sound": "放完了~",
        }

        reply = base_messages.get(operation.operation_type, "搞定~")

        # 附加详细信息
        if request.result.get("message"):
            reply += f" {request.result['message']}"

        return reply
    else:
        # 失败：不甩锅，说"我遇到问题"
        error = request.result.get("error", "未知错误")
        return f"唔...遇到点问题：{error}"


async def _send_completion_notification(operation, text: str, request: CompleteOperationRequest):
    """推送完成通知到原场景。"""
    try:
        scene_type = SceneType(operation.requester_scene_type)
    except (TypeError, ValueError):
        scene_type = SceneType.PRIVATE

    # 判断平台
    if operation.requester_platform == "qq":
        platform = Platform.QQ
    else:
        # 未知平台，跳过推送
        return

    # 构造消息内容
    # 如果是截图操作且成功，附带截图
    if (
        request.success
        and operation.operation_type == "screenshot"
        and request.result.get("screenshot")
    ):
        screenshot_path = Path(request.result["screenshot"])
        if screenshot_path.exists():
            # 创建包含截图的富文本消息
            content = create_screenshot_message(
                text=text,
                screenshot_path=screenshot_path,
                width=request.result.get("width"),
                height=request.result.get("height"),
            )
        else:
            # 截图文件不存在，回退到纯文本
            content = MessageContent.text_message(text)
    else:
        # 其他操作或失败，使用纯文本
        content = MessageContent.text_message(text)

    # 推送通知
    notification = NotificationRequest(
        target=NotificationTarget(
            platform=platform,
            scene_type=scene_type,
            scene_id=operation.requester_scene_id,
        ),
        content=content,
        source="desktop_operation_complete",
        metadata={
            "operation_id": operation.id,
            "operation_type": operation.operation_type,
        },
    )

    settings = get_settings()
    await deliver_notification(notification, settings.notifications)
