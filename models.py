import uuid
from sqlalchemy import Column, String, Boolean, Text, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Venue(Base):
    __tablename__ = "venues"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    address = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE"))
    phone_zalo = Column(String)
    name = Column(String, nullable=False)
    role = Column(String, default="customer")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Song(Base):
    __tablename__ = "songs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    title_normalized = Column(String, nullable=True)
    author = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sheets = relationship("SongSheet", back_populates="song", cascade="all, delete-orphan")
    lyrics = relationship("SongLyrics", back_populates="song", cascade="all, delete-orphan")


class SongSheet(Base):
    __tablename__ = "song_sheets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    song_id = Column(UUID(as_uuid=True), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    sheet_drive_url = Column(String, nullable=False)
    tone_male = Column(String)
    tone_female = Column(String)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    song = relationship("Song", back_populates="sheets")


class SongLyrics(Base):
    __tablename__ = "song_lyrics"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    song_id = Column(UUID(as_uuid=True), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    lyrics = Column(Text, nullable=False)
    slide_drive_url = Column(String)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    song = relationship("Song", back_populates="lyrics")

class LiveSession(Base):
    __tablename__ = "live_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=True)
    session_date = Column(Date, nullable=False)
    status = Column(String, default="planned")
    camera_start = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    registrations = relationship("QueueRegistration", back_populates="session", cascade="all, delete-orphan")

class QueueRegistration(Base):
    __tablename__ = "queue_registrations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False)
    song_id = Column(UUID(as_uuid=True), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    singer_name = Column(String, nullable=False)
    booker_phone = Column(String)
    table_position = Column(String)
    status = Column(String, default="waiting")
    actual_start = Column(DateTime(timezone=True))
    actual_end = Column(DateTime(timezone=True))
    video_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("LiveSession", back_populates="registrations")
    song = relationship("Song")