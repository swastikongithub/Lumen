"""Postgres tables (SPEC §7.1).

Enum columns are stored as VARCHAR + CHECK constraint (not native Postgres ENUM types),
so adding a value later is a plain migration that edits the constraint.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.enums import Client, DocumentCategory, DocumentStatus, FeedbackReason, Role

# Predictable constraint names, so Alembic migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Every `Mapped[datetime]` column is TIMESTAMP WITH TIME ZONE.
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


def enum_column(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR(32) + CHECK constraint holding the enum's lowercase values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class Document(Base):
    """One version of one source document. A changed file gets a new row (version + 1)."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_id", "version"),
        # At most one active version per source document.
        Index(
            "uq_documents_one_active_per_source",
            "source_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The stable `id` from data/sources.yaml, e.g. "exam-policy".
    source_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    category: Mapped[DocumentCategory] = mapped_column(enum_column(DocumentCategory, "category"))
    academic_year: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex of the raw file
    version: Mapped[int]
    status: Mapped[DocumentStatus] = mapped_column(enum_column(DocumentStatus, "status"))
    page_count: Mapped[int]
    chunk_count: Mapped[int]
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CorpusVersion(Base):
    """One row per ingestion run that changed the index. The current version is the highest.

    Qdrant payloads and the answer cache carry `corpus_version`, so a new row here
    invalidates cached answers.
    """

    __tablename__ = "corpus_versions"

    version: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Anonymous ID from the X-Session-Id header. Not authentication (SPEC §10).
    session_id: Mapped[str] = mapped_column(Text, index=True)
    client: Mapped[Client] = mapped_column(enum_column(Client, "client"))
    app_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[Role] = mapped_column(enum_column(Role, "role"))
    content: Mapped[str] = mapped_column(Text)
    # Standalone question used for retrieval (assistant turns after a rewrite).
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    # [{n, chunk_id, document_id, page_start, page_end}]
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    abstained: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    cache_hit: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # The fields below are only filled for assistant messages.
    model: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    latency_ms: Mapped[int | None]
    ttft_ms: Mapped[int | None]
    trace_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Feedback(Base):
    """One rating per message; a second rating replaces the first (upsert on message_id)."""

    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating IN (-1, 1)", name="rating"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True
    )
    rating: Mapped[int] = mapped_column(SmallInteger)
    # Thumbs-down reason; empty for thumbs-up.
    reason: Mapped[FeedbackReason | None] = mapped_column(enum_column(FeedbackReason, "reason"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
