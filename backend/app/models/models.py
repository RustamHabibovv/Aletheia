import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, func
from sqlmodel import Column, DateTime, Enum, Field, Relationship, SQLModel

# ── Enums ──────────────────────────────────────────────────────────


class UserTier(enum.StrEnum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class AnalysisType(enum.StrEnum):
    FACT_CHECK = "FACT_CHECK"
    SOURCE_VERIFY = "SOURCE_VERIFY"
    MISINFO_DETECT = "MISINFO_DETECT"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"


class Verdict(enum.StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    PARTIALLY_TRUE = "PARTIALLY_TRUE"
    UNVERIFIABLE = "UNVERIFIABLE"
    MISLEADING = "MISLEADING"


class SubscriptionStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"


# ── Models ─────────────────────────────────────────────────────────


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=320)
    name: str | None = Field(default=None, max_length=255)
    image: str | None = Field(default=None, max_length=1024)
    tier: UserTier = Field(
        default=UserTier.FREE,
        sa_column=Column(Enum(UserTier), nullable=False, server_default="FREE"),
    )
    stripe_customer_id: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    )

    conversations: list["Conversation"] = Relationship(back_populates="user")
    subscriptions: list["Subscription"] = Relationship(back_populates="user")


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    title: str = Field(default="New Conversation", max_length=500)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    )

    user: User = Relationship(back_populates="conversations")
    messages: list["Message"] = Relationship(back_populates="conversation")


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversations.id", index=True)
    role: MessageRole = Field(sa_column=Column(Enum(MessageRole), nullable=False))
    content: str = Field(default="")
    metadata_: dict | None = Field(default=None, sa_column=Column("metadata", JSON, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )

    conversation: Conversation = Relationship(back_populates="messages")
    analysis_result: Optional["AnalysisResult"] = Relationship(
        back_populates="message", sa_relationship_kwargs={"uselist": False}
    )


class AnalysisResult(SQLModel, table=True):
    __tablename__ = "analysis_results"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="messages.id", unique=True, index=True)
    analysis_type: AnalysisType = Field(sa_column=Column(Enum(AnalysisType), nullable=False))
    verdict: Verdict | None = Field(default=None, sa_column=Column(Enum(Verdict), nullable=True))
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str = Field(default="")
    detailed_breakdown: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    sources: list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )

    message: Message = Relationship(back_populates="analysis_result")


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    stripe_subscription_id: str = Field(max_length=255, unique=True)
    plan: UserTier = Field(sa_column=Column(Enum(UserTier), nullable=False))
    status: SubscriptionStatus = Field(
        sa_column=Column(Enum(SubscriptionStatus), nullable=False, server_default="ACTIVE")
    )
    current_period_start: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    current_period_end: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    )

    user: User = Relationship(back_populates="subscriptions")


class UsageRecord(SQLModel, table=True):
    __tablename__ = "usage_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    date: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    request_count: int = Field(default=0)
    tokens_used: int = Field(default=0)
