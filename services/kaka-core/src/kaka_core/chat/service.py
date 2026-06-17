import asyncio
import re
import time
from dataclasses import dataclass

from kaka_core.config.settings import PluginSettings, get_settings
from kaka_core.context.builder import build_reply_context, classify_scene
from kaka_core.llm.client import LLMClientError
from kaka_core.llm.router import LLMRouter
from kaka_core.plugins.result import PluginResult
from kaka_core.plugins.runtime import create_default_plugin_runtime
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.repository import (
    load_input_by_event_id,
    load_output_for_input,
    output_record_to_response,
    release_event_processing_lock,
    save_conversation,
    save_observed_input,
    try_acquire_event_processing_lock,
)
from kaka_protocol import KakaResponse, MessageEvent


@dataclass
class EventLockState:
    lock: asyncio.Lock
    users: int = 0


_event_lock_guard = asyncio.Lock()
_event_locks: dict[str, EventLockState] = {}
EVENT_PROCESSING_LOCK_LEASE_SECONDS = 300
EVENT_PROCESSING_LOCK_POLL_SECONDS = 0.25
# 跨进程轮询等待已有输出的最长时间，避免另一进程持锁卡死时请求无限期阻塞。
EVENT_PROCESSING_WAIT_TIMEOUT_SECONDS = 30.0


class EventDedupError(RuntimeError):
    """去重相关的数据库查询失败时抛出。

    去重查询出错时不能静默当作"没有已有输出/锁"继续往下走，否则重放的
    event_id 会再次调用 LLM 并重复发消息。这里显式抛错，让上层 fail-closed。
    """



def generate_fallback_response(event: MessageEvent, reason: str | None = None) -> KakaResponse:
    """生成本地占位回复。

    没有配置 API Key 或 LLM 调用失败时使用它，保证核心服务仍能测试。
    """

    text = event.content.text or ""
    display_name = event.display_name or event.user_id

    if text:
        reply = f"收到 {display_name} 的消息：{text}"
    else:
        reply = f"收到 {display_name} 发来的 {event.content.type} 内容。"

    response = KakaResponse.text_reply(reply, event_id=event.event_id)
    if reason:
        response.metadata["fallback_reason"] = reason
    return response


def record_observed_input_safely(
    event: MessageEvent,
    *,
    analysis_status: str = "not_analyzed",
) -> str | None:
    """安全保存一条观察输入。

    返回 None 表示保存成功；返回字符串表示保存失败原因。
    """

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            save_observed_input(
                session,
                event,
                analysis_status=analysis_status,
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return None


def record_conversation_safely(event: MessageEvent, response: KakaResponse) -> None:
    """保存对话记录。

    数据记录不能影响聊天主流程；即使数据库暂时不可用，也应该先把回复发出去。
    """

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            save_conversation(
                session,
                event,
                response,
                output_origin=normalize_output_field(
                    event.metadata.get("output_origin"),
                    default="passive",
                ),
                output_reason=normalize_output_field(
                    event.metadata.get("output_reason"),
                    default="unknown",
                ),
                no_reply_reason=normalize_optional_output_field(
                    event.metadata.get("no_reply_reason")
                ),
            )
    except Exception as exc:  # noqa: BLE001
        response.metadata["record_error"] = str(exc)


def observe_message(event: MessageEvent) -> KakaResponse:
    """只记录消息，不调用模型，也不产生回复。"""

    response = KakaResponse.no_reply(event_id=event.event_id, reason="observed")
    record_error = record_observed_input_safely(
        event,
        analysis_status="not_analyzed",
    )
    if record_error:
        response.metadata["record_error"] = record_error
    return response


def load_existing_response_safely(event: MessageEvent) -> KakaResponse | None:
    """读取重复事件已有响应。

    QQ 侧可能重放同一 message_id。这里在调用 LLM 之前先查库，避免重复消费
    模型额度和重复写 outputs。

    查不到已有输出时返回 None；数据库查询本身失败时抛 EventDedupError，
    让上层 fail-closed，而不是把"查询失败"误当成"没有已有输出"继续生成。
    """

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            input_record = load_input_by_event_id(session, event.event_id)
            if input_record is None:
                return None
            output = load_output_for_input(session, input_record)
            if output is None:
                return None
            return output_record_to_response(output, event_id=event.event_id)
    except Exception as exc:  # noqa: BLE001
        raise EventDedupError(f"failed to load existing response: {exc}") from exc


async def acquire_event_lock(event_id: str) -> EventLockState:
    """按 event_id 串行化同一事件的回复生成，避免并发重复调用 LLM。"""

    async with _event_lock_guard:
        state = _event_locks.get(event_id)
        if state is None:
            state = EventLockState(lock=asyncio.Lock())
            _event_locks[event_id] = state
        state.users += 1
        return state


async def release_event_lock(event_id: str, state: EventLockState) -> None:
    async with _event_lock_guard:
        state.users = max(0, state.users - 1)
        if state.users == 0 and not state.lock.locked() and _event_locks.get(event_id) is state:
            _event_locks.pop(event_id, None)


def normalize_output_field(value: object, *, default: str) -> str:
    """规范化输出来源和原因，避免外部传入空值或过长字符串。"""

    text = str(value or "").strip().lower()
    if not text:
        return default
    return text[:32]


def normalize_optional_output_field(value: object) -> str | None:
    """规范化可选输出字段。"""

    text = str(value or "").strip().lower()
    return text[:64] or None


async def generate_chat_response(
    event: MessageEvent,
    router: LLMRouter | None = None,
) -> KakaResponse:
    """生成聊天回复。

    第一版流程：
    1. 从 MessageEvent 取出文本。
    2. 拼接最小人格 prompt。
    3. 调用 LLMRouter 的普通聊天模型。
    4. 将模型文本包装成 KakaResponse。
    """

    lock_state = await acquire_event_lock(event.event_id)
    db_lock_owner: str | None = None
    try:
        async with lock_state.lock:
            try:
                existing_response, db_lock_owner = await reserve_event_processing_turn(event)
            except EventDedupError:
                # 去重状态不确定时 fail-closed：不再生成新回复、不发消息，
                # 避免重放的 event_id 触发重复 LLM 调用和重复发送。
                return KakaResponse.no_reply(
                    event_id=event.event_id,
                    reason="dedup_unavailable",
                )
            if existing_response is not None:
                return existing_response

            settings = get_settings()
            plugin_response = await generate_plugin_response_if_available(event, settings.plugins)
            if plugin_response is not None:
                record_conversation_safely(event, plugin_response)
                return plugin_response

            if not settings.llm.can_call_remote:
                response = generate_fallback_response(event, reason="llm_disabled_or_missing_key")
                record_conversation_safely(event, response)
                return response

            user_text = event.content.text
            if not user_text:
                response = generate_fallback_response(event, reason="non_text_content")
                record_conversation_safely(event, response)
                return response

            llm_router = router or LLMRouter(settings.llm)
            reply_context = build_reply_context(
                event,
                settings.memory_reply,
                settings.short_context,
                settings.relationship,
                settings.persona,
            )

            try:
                reply = await llm_router.chat(list(reply_context.messages))
            except LLMClientError as exc:
                response = generate_fallback_response(event, reason=str(exc))
                response.metadata.update(reply_context.metadata)
                record_conversation_safely(event, response)
                return response

            reply = sanitize_llm_reply(
                reply,
                scene=classify_scene(user_text),
                relationship_level=str(reply_context.metadata.get("relationship_level", "normal")),
            )
            response = KakaResponse.text_reply(reply, event_id=event.event_id)
            response.metadata["llm_model"] = settings.llm.chat_model
            response.metadata.update(reply_context.metadata)
            record_conversation_safely(event, response)
            return response
    finally:
        if db_lock_owner is not None:
            release_event_processing_lock_safely(event.event_id, db_lock_owner)
        await release_event_lock(event.event_id, lock_state)


async def reserve_event_processing_turn(event: MessageEvent) -> tuple[KakaResponse | None, str | None]:
    """等待轮到当前事件处理。

    先检查数据库里是否已经有输出。如果没有，则尝试获取跨进程事件锁。
    没抢到时持续轮询，直到已有输出可复用或成功拿到锁。

    去重查询或抢锁出现数据库错误时抛 EventDedupError，由上层 fail-closed，
    避免把"查询失败"误当成"可以放心生成"。
    轮询超过 EVENT_PROCESSING_WAIT_TIMEOUT_SECONDS 仍拿不到锁时也抛错，
    避免另一个进程持锁卡死时请求被无限期阻塞。
    """

    lease_seconds = EVENT_PROCESSING_LOCK_LEASE_SECONDS
    deadline = time.monotonic() + EVENT_PROCESSING_WAIT_TIMEOUT_SECONDS
    while True:
        existing_response = load_existing_response_safely(event)
        if existing_response is not None:
            return existing_response, None

        try:
            owner_token = acquire_event_processing_lock_safely(
                event.event_id,
                lease_seconds=lease_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise EventDedupError(f"failed to acquire processing lock: {exc}") from exc
        if owner_token is not None:
            return None, owner_token

        if time.monotonic() >= deadline:
            raise EventDedupError(
                "timed out waiting for another worker to finish processing this event"
            )

        await asyncio.sleep(EVENT_PROCESSING_LOCK_POLL_SECONDS)


def acquire_event_processing_lock_safely(event_id: str, *, lease_seconds: int) -> str | None:
    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        return try_acquire_event_processing_lock(
            session,
            event_id,
            lease_seconds=lease_seconds,
        )


def release_event_processing_lock_safely(event_id: str, owner_token: str) -> None:
    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            release_event_processing_lock(session, event_id, owner_token)
    except Exception:  # noqa: BLE001
        return


async def generate_plugin_response_if_available(
    event: MessageEvent,
    plugin_settings: PluginSettings,
) -> KakaResponse | None:
    runtime = create_default_plugin_runtime(
        enabled=plugin_settings.enabled,
        command_prefixes=plugin_settings.command_prefixes,
        n8n_webhook_base_url=plugin_settings.n8n_webhook_base_url,
        n8n_webhook_timeout_seconds=plugin_settings.n8n_webhook_timeout_seconds,
        s60_base_url=plugin_settings.s60_base_url,
        s60_timeout_seconds=plugin_settings.s60_timeout_seconds,
        github_api_base_url=plugin_settings.github_api_base_url,
        github_timeout_seconds=plugin_settings.github_timeout_seconds,
        github_token=plugin_settings.github_token,
    )
    result = await runtime.run_for_event(event)
    if result is None:
        return None
    return plugin_result_to_response(result, event_id=event.event_id)


def plugin_result_to_response(result: PluginResult, *, event_id: str) -> KakaResponse:
    if result.should_reply:
        response = KakaResponse.text_reply(result.text, event_id=event_id)
    else:
        response = KakaResponse.no_reply(event_id=event_id, reason="plugin_no_reply")

    response.metadata.update(result.metadata)
    if result.data:
        response.metadata["plugin_data"] = result.data
    response.metadata["plugin_handled"] = True
    response.metadata["plugin_id"] = result.plugin_id
    return response


def sanitize_llm_reply(reply: str, *, scene: str, relationship_level: str) -> str:
    """轻量清洗模型回复，兜住高频风格偏航。

    这里不做完整二次改写，只处理确定性问题：换行、动作前缀、禁用自称、主仆称呼、
    客服式尾问，以及低落场景的明显玩梗偏航。
    """

    text = re.sub(r"\s*\n+\s*", " ", reply).strip()
    text = strip_leading_stage_directions(text)
    text = strip_leading_bare_action_phrases(text)
    text = strip_forbidden_identity_prefix(text)
    # 替换称呼时避免误伤后接 CJK 字符形成的复合词（如"主人公"、"大人物"）。
    # 只要后面紧跟 CJK 字符就不替换；前面有 CJK 字符（如"好主人，"）仍正常替换。
    _NO_CJK_AHEAD = r"(?![一-鿿])"
    if relationship_level == "special":
        text = re.sub(rf"主人{_NO_CJK_AHEAD}", "创造者大人", text)
    else:
        text = re.sub(rf"主人{_NO_CJK_AHEAD}", "群友", text)
        text = re.sub(rf"大人{_NO_CJK_AHEAD}", "群友", text)
    text = strip_generic_service_tail(text)
    text = re.sub(r"\s+", " ", text).strip()

    if scene == "low_mood" and is_low_mood_reply_drift(text):
        return "这句话先别盖章，卡咔不批准。破事先排队，一个一个来。"

    return text


def strip_leading_stage_directions(text: str) -> str:
    """删除模型偶发的开头动作描写。"""

    cleaned = text.strip()
    while True:
        next_text = re.sub(r"^[（(][^（）()\n]{1,80}[）)]\s*", "", cleaned).strip()
        if next_text == cleaned:
            return cleaned
        cleaned = next_text


def strip_leading_bare_action_phrases(text: str) -> str:
    """删除没有括号但明显是舞台动作的开头短语。"""

    return re.sub(
        r"^(?:探头看看|探头|歪头|眨眨眼|眨眼|抬头看看|凑过来看看)[，,。.\s]*",
        "",
        text.strip(),
    ).strip()


def strip_forbidden_identity_prefix(text: str) -> str:
    """删除“作为AI/作为卡咔”式客服开头。"""

    return re.sub(
        r"^(作为\s*(?:ai|人工智能|卡咔|电子猫娘)[，,：:\s]*)+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def strip_generic_service_tail(text: str) -> str:
    """删除没有信息量的客服式尾问。"""

    patterns = (
        r"\s*(?:有什么事|找我什么事|你找我什么事|需要我做什么|我能帮你什么)[吗呀呢嘛]*[？?。!！]*$",
        r"\s*(?:什么事|有事吗)[吗呀呢嘛]*[？?。!！]*$",
        r"\s*(?:需要帮忙的话可以告诉我|如果需要可以继续问我)[。!！]*$",
    )
    cleaned = text.strip()
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned).strip()
    return cleaned


def is_low_mood_reply_drift(text: str) -> bool:
    drift_markers = (
        "乱码",
        "问号",
        "卡键盘",
        "压缩包密码",
        "猫薄荷",
        "查无此词",
        "不存在",
        "明天继续跑",
        "继续跑起来",
        "缓一缓就好了",
    )
    return any(marker in text for marker in drift_markers)
