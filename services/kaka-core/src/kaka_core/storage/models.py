from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRecord(Base):
    """外部平台用户。

    QQ 号等稳定 ID 存在 platform_user_id，昵称只作为当前显示名。
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_users_platform_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    platform_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    inputs: Mapped[list["InputRecord"]] = relationship(back_populates="user")
    memories: Mapped[list["MemoryRecord"]] = relationship(back_populates="user")


class SceneRecord(Base):
    """消息发生的场景，例如 QQ 私聊或群聊。"""

    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("platform", "scene_type", "scene_id", name="uq_scenes_platform_scene"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scene_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scene_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    inputs: Mapped[list["InputRecord"]] = relationship(back_populates="scene")
    memories: Mapped[list["MemoryRecord"]] = relationship(back_populates="scene")


class InputRecord(Base):
    """卡咔接收到或观察到的输入。

    inputs 表记录完整输入流，不代表卡咔一定回复过。
    是否做过情绪、记忆、用户画像等后续分析由 analysis_status 标记。
    """

    __tablename__ = "inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_event: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    analysis_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_analyzed",
        server_default="not_analyzed",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[UserRecord] = relationship(back_populates="inputs")
    scene: Mapped[SceneRecord] = relationship(back_populates="inputs")
    output: Mapped["OutputRecord | None"] = relationship(back_populates="input")
    memory_candidates: Mapped[list["MemoryCandidateRecord"]] = relationship(
        back_populates="source_input"
    )


class MemoryCandidateRecord(Base):
    """大模型整理出的长期记忆候选。

    这里的候选不等于正式长期记忆，需要后续人工审核、合并或拒绝。
    """

    __tablename__ = "memory_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_input_id: Mapped[int] = mapped_column(
        ForeignKey("inputs.id"),
        nullable=False,
        index=True,
    )
    source_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source_scene_id: Mapped[int] = mapped_column(
        ForeignKey("scenes.id"),
        nullable=False,
        index=True,
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_memory: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_model: Mapped[str] = mapped_column(String(128), nullable=False)
    analysis_prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    source_input: Mapped[InputRecord] = relationship(back_populates="memory_candidates")
    source_user: Mapped[UserRecord] = relationship()
    source_scene: Mapped[SceneRecord] = relationship()
    memory: Mapped["MemoryRecord | None"] = relationship(back_populates="source_candidate")


class MemoryRecord(Base):
    """正式长期记忆。

    memories 表只保存已经从候选区合并出的长期记忆。后续回复检索只应读取
    status=active 的正式记忆，而不是直接读取 memory_candidates。
    """

    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("source_candidate_id", name="uq_memories_source_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("memory_candidates.id"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True, index=True)
    memory_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="candidate",
        server_default="candidate",
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )
    merge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    source_candidate: Mapped[MemoryCandidateRecord | None] = relationship(
        back_populates="memory"
    )
    user: Mapped[UserRecord] = relationship(back_populates="memories")
    scene: Mapped[SceneRecord | None] = relationship(back_populates="memories")


class OutputRecord(Base):
    """卡咔针对某条输入形成的输出结果或响应决策。"""

    __tablename__ = "outputs"
    __table_args__ = (
        UniqueConstraint("input_id", name="uq_outputs_input"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    output_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    input_id: Mapped[int | None] = mapped_column(ForeignKey("inputs.id"), nullable=True, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    output_origin: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="passive",
        server_default="passive",
        index=True,
    )
    output_reason: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    should_reply: Mapped[bool] = mapped_column(nullable=False, default=True)
    no_reply_reason: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    input: Mapped[InputRecord | None] = relationship(back_populates="output")
    scene: Mapped[SceneRecord] = relationship()
    user: Mapped[UserRecord | None] = relationship()


class EventProcessingLockRecord(Base):
    """跨进程事件处理锁。"""

    __tablename__ = "event_processing_locks"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    leased_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class AutoJobRunRecord(Base):
    """自动后台任务的一次运行记录。"""

    __tablename__ = "auto_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    checked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DesktopOperationRecord(Base):
    """卡咔的桌面操作任务。

    卡咔可以在主人电脑上执行操作（创建文件、截图、播放音效等）。
    这些能力是卡咔本身的能力，不暴露"助手"概念。
    """

    __tablename__ = "desktop_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 操作基本信息
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # 请求来源
    requester_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requester_scene_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requester_scene_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="private",
        server_default="private",
    )
    requester_platform: Mapped[str] = mapped_column(String(32), nullable=False)

    # 卡咔的决策信息
    approved: Mapped[bool] = mapped_column(nullable=False, default=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    kaka_mood: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 执行状态
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 审计
    permission_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
