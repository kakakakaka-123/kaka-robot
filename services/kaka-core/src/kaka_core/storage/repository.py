from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kaka_core.storage.models import (
    EventProcessingLockRecord,
    InputRecord,
    OutputRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)
from kaka_protocol import ActionType, KakaResponse, MessageEvent


def save_observed_input(
    session: Session,
    event: MessageEvent,
    *,
    analysis_status: str = "not_analyzed",
) -> InputRecord:
    """保存一条卡咔看见的输入。

    这一步只代表卡咔观察到了消息，不代表已经调用模型或发送回复。
    同一个 event_id 重复写入时，会更新基础信息，但不会把已经 analyzed/skipped
    的输入降级回 not_analyzed。
    """

    user = _get_or_create_user(session, event)
    scene = _get_or_create_scene(session, event)

    input_record = session.scalar(
        select(InputRecord).where(InputRecord.event_id == event.event_id)
    )
    if input_record is None:
        input_record = InputRecord(
            event_id=event.event_id,
            user=user,
            scene=scene,
            content_type=str(event.content.type),
            content_text=event.content.text,
            raw_event=event.raw_event,
            extra_metadata=event.metadata,
            analysis_status=analysis_status,
            created_at=event.timestamp,
        )
        session.add(input_record)
        session.flush()
        return input_record

    input_record.user = user
    input_record.scene = scene
    input_record.content_type = str(event.content.type)
    input_record.content_text = event.content.text
    input_record.raw_event = event.raw_event
    input_record.extra_metadata = event.metadata
    input_record.analysis_status = merge_analysis_status(
        input_record.analysis_status,
        analysis_status,
    )
    session.flush()
    return input_record


def save_conversation(
    session: Session,
    event: MessageEvent,
    response: KakaResponse,
    *,
    output_origin: str = "passive",
    output_reason: str = "unknown",
    no_reply_reason: str | None = None,
) -> None:
    """保存一次已经处理的输入和输出结果。

    这里保存的是原始输入和响应决策，不做记忆抽取和用户画像更新。
    """

    input_record = save_observed_input(
        session,
        event,
        analysis_status="not_analyzed",
    )

    existing_output = load_output_for_input(session, input_record)
    if existing_output is None:
        session.add(
            OutputRecord(
                output_id=response.response_id,
                input=input_record,
                scene=input_record.scene,
                user=input_record.user,
                output_origin=output_origin,
                output_reason=output_reason,
                should_reply=response.should_reply,
                no_reply_reason=no_reply_reason,
                content_text=_first_text_action(response),
                extra_metadata=response.metadata,
                created_at=response.created_at,
            )
        )

    session.commit()


def load_input_by_event_id(session: Session, event_id: str) -> InputRecord | None:
    """按统一事件 ID 读取已保存输入。"""

    return session.scalar(select(InputRecord).where(InputRecord.event_id == event_id))


def try_acquire_event_processing_lock(
    session: Session,
    event_id: str,
    *,
    lease_seconds: int = 300,
) -> str | None:
    """尝试获取事件处理锁。

    返回 owner_token 表示已获取锁；返回 None 表示当前有其他处理者在工作。
    """

    now = _as_utc_naive(utc_now())
    lease_until = now + timedelta(seconds=lease_seconds)
    owner_token = uuid4().hex

    existing = session.get(EventProcessingLockRecord, event_id)
    if existing is None:
        session.add(
            EventProcessingLockRecord(
                event_id=event_id,
                owner_token=owner_token,
                leased_until=lease_until,
                created_at=now,
                updated_at=now,
            )
        )
        try:
            session.commit()
            return owner_token
        except IntegrityError:
            session.rollback()
            existing = session.get(EventProcessingLockRecord, event_id)

    if existing is not None and _as_utc_naive(existing.leased_until) > now:
        session.rollback()
        return None

    updated = session.execute(
        update(EventProcessingLockRecord)
        .where(
            EventProcessingLockRecord.event_id == event_id,
            EventProcessingLockRecord.leased_until <= now,
        )
        .values(
            owner_token=owner_token,
            leased_until=lease_until,
            updated_at=now,
        )
    ).rowcount
    if updated:
        session.commit()
        return owner_token

    session.rollback()
    return None


def release_event_processing_lock(session: Session, event_id: str, owner_token: str) -> None:
    """释放事件处理锁。"""

    deleted = session.execute(
        delete(EventProcessingLockRecord).where(
            EventProcessingLockRecord.event_id == event_id,
            EventProcessingLockRecord.owner_token == owner_token,
        )
    ).rowcount
    if deleted:
        session.commit()


def load_output_for_input(session: Session, input_record: InputRecord) -> OutputRecord | None:
    """读取某条输入已经关联的输出决策。"""

    return session.scalar(
        select(OutputRecord)
        .where(OutputRecord.input_id == input_record.id)
        .order_by(OutputRecord.created_at.asc(), OutputRecord.id.asc())
    )


def output_record_to_response(output: OutputRecord, event_id: str | None = None) -> KakaResponse:
    """把已保存的输出记录还原成统一响应。

    这用于重复事件的幂等返回，避免同一条 QQ 消息被重放时再次调用模型。
    """

    if not output.should_reply:
        response = KakaResponse.no_reply(event_id=event_id, reason=output.no_reply_reason)
    else:
        response = KakaResponse.text_reply(output.content_text or "", event_id=event_id)
    response.response_id = output.output_id
    response.created_at = output.created_at
    response.metadata.update(output.extra_metadata or {})
    response.metadata["deduplicated"] = True
    return response


def merge_analysis_status(current: str | None, incoming: str) -> str:
    """合并输入分析状态，避免重复观察把已处理状态重置。"""

    current_text = str(current or "").strip() or "not_analyzed"
    incoming_text = str(incoming or "").strip() or "not_analyzed"
    if current_text != "not_analyzed" and incoming_text == "not_analyzed":
        return current_text
    return incoming_text


def _get_or_create_user(session: Session, event: MessageEvent) -> UserRecord:
    user = session.scalar(
        select(UserRecord).where(
            UserRecord.platform == str(event.platform),
            UserRecord.platform_user_id == event.user_id,
        )
    )
    if user is not None:
        user.display_name = event.display_name
        return user

    user = UserRecord(
        platform=str(event.platform),
        platform_user_id=event.user_id,
        display_name=event.display_name,
    )
    session.add(user)
    session.flush()
    return user


def _get_or_create_scene(session: Session, event: MessageEvent) -> SceneRecord:
    scene = session.scalar(
        select(SceneRecord).where(
            SceneRecord.platform == str(event.platform),
            SceneRecord.scene_type == str(event.scene_type),
            SceneRecord.scene_id == event.scene_id,
        )
    )
    if scene is not None:
        return scene

    scene = SceneRecord(
        platform=str(event.platform),
        scene_type=str(event.scene_type),
        scene_id=event.scene_id,
    )
    session.add(scene)
    session.flush()
    return scene


def _first_text_action(response: KakaResponse) -> str | None:
    for action in response.actions:
        if action.type != ActionType.SEND_TEXT:
            continue
        if action.content is None:
            continue
        if action.content.text:
            return action.content.text
    return None


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
