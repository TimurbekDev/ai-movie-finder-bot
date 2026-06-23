from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="en")
    is_premium: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    searches: Mapped[list["SearchHistory"]] = relationship(back_populates="user")


class SearchHistory(Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_type: Mapped[str] = mapped_column(String(20))
    movie_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="searches")


class IdentificationCache(Base):
    """Perceptual-hash dedup cache: maps near-identical images to a prior result.

    Lookup is a hamming-distance scan (see cache_service), so the btree index on
    phash only speeds exact-duplicate (distance 0) hits, not the range query.
    """

    __tablename__ = "identification_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    phash: Mapped[int] = mapped_column(BigInteger, index=True)
    tmdb_id: Mapped[int | None] = mapped_column(nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    result_json: Mapped[str] = mapped_column(String)
    hits: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
