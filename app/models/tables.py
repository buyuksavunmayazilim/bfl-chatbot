import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, Float, Integer, DateTime,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.db.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── 1. conversations ──────────────────────────────────────────────────────────
class Conversation(Base):
    """
    Her kullanıcı oturumu bir conversation'dır.
    session_id → Redis'teki anahtarla eşleşir.
    """
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # İlişki
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


# ── 2. messages ───────────────────────────────────────────────────────────────
class Message(Base):
    """
    Konuşmadaki her mesaj (kullanıcı veya bot) bir satırdır.
    source: hangi katmandan geldi (k1_keyword, k2_similarity, k3_llama, fallback, static)
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(
        SAEnum("user", "bot", name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(
        SAEnum(
            "k1_keyword", "k2_similarity", "k3_llama",
            "fallback", "static",
            name="message_source"
        ),
        nullable=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # İlişki
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")


# ── 3. qa_embeddings ──────────────────────────────────────────────────────────
class QAEmbedding(Base):
    """
    Q&A veri tabanı. pgvector ile cosine similarity araması yapılır.
    embedding → 384 boyut (MiniLM)
    """
    __tablename__ = "qa_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    intent_category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_augmented: Mapped[bool] = mapped_column(default=False)   # parafraz mı, orijinal mi?
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# ── 4. fallback_contacts ──────────────────────────────────────────────────────
class FallbackContact(Base):
    """
    Fallback akışında kullanıcıdan alınan iletişim bilgileri.
    status: new → contacted → closed
    """
    __tablename__ = "fallback_contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    contact_type: Mapped[str] = mapped_column(
        SAEnum("phone", "email", name="contact_type"), nullable=False
    )
    contact_value: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum("new", "contacted", "closed", name="contact_status"),
        default="new",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# ── 5. analytics_events ───────────────────────────────────────────────────────
class AnalyticsEvent(Base):
    """
    Her chatbot isteği için performans ve katman bilgisi.
    layer_hit: hangi katmanda yanıt üretildi.
    """
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    layer_hit: Mapped[str | None] = mapped_column(
        SAEnum(
            "k1_keyword", "k2_similarity", "k3_llama",
            "fallback", "static",
            name="layer_hit_type"
        ),
        nullable=True,
    )
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)