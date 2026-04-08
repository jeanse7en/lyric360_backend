from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime, date

# Child responses
class SongSheetResponse(BaseModel):
    id: UUID
    sheet_drive_url: str
    tone_male: Optional[str] = None
    tone_female: Optional[str] = None
    verified_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SongLyricsUpdate(BaseModel):
    lyrics: Optional[str] = None


class SongLyricsResponse(BaseModel):
    id: UUID
    lyrics: str
    slide_drive_url: Optional[str] = None
    source_lyric: str = "MANUAL"
    composed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SongManageItem(BaseModel):
    id: UUID
    title: str
    author: Optional[str] = None
    lyric_count: int
    sheet_count: int
    unverified_count: int

    class Config:
        from_attributes = True


class UnverifiedCountResponse(BaseModel):
    count: int


# Response khi tìm kiếm bài hát
class SongResponse(BaseModel):
    id: UUID
    title: str
    author: Optional[str] = None
    sheets: list[SongSheetResponse] = []
    lyrics: list[SongLyricsResponse] = []

    class Config:
        from_attributes = True

class SessionResponse(BaseModel):
    id: UUID
    name: Optional[str] = None
    session_date: date
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    order_count: int = 0
    unverified_song_count: int = 0

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    name: Optional[str] = None
    session_date: date


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    session_date: Optional[date] = None


class SongCreate(BaseModel):
    title: str
    author: Optional[str] = None


class SongUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None


class SongSheetCreate(BaseModel):
    sheet_drive_url: str
    tone_male: Optional[str] = None
    tone_female: Optional[str] = None


class SongLyricsCreate(BaseModel):
    lyrics: str
    source_lyric: str = "MANUAL"
    composed_at: Optional[datetime] = None


# ── Sheet sync ──────────────────────────────────────────────────────────────

class SyncPreviewItem(BaseModel):
    row_number: int
    song_title: str
    author: Optional[str]
    year: Optional[str]
    lyrics_preview: Optional[str]   # first 200 chars
    sheet_url: Optional[str]
    lyric_slide_url: Optional[str]
    song_id: Optional[UUID] = None  # None → new song
    action: str                     # CREATE | UPDATE | SKIP
    changes: list[str]              # human-readable change descriptions

    class Config:
        from_attributes = True


class SyncPreviewResponse(BaseModel):
    items: list[SyncPreviewItem]
    total: int
    to_create: int
    to_update: int


class SyncRunResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


# User schemas
class UserResponse(BaseModel):
    id: UUID
    name: str
    phone_zalo: Optional[str] = None

    class Config:
        from_attributes = True


# Request khi khách gửi form đăng ký
class QueueCreate(BaseModel):
    session_id: UUID
    song_id: Optional[UUID] = None
    free_text_song_name: Optional[str] = None
    singer_name: str
    booker_phone: str
    table_position: Optional[str] = None
    user_id: Optional[UUID] = None

# Response trả về sau khi đăng ký thành công
class QueueResponse(BaseModel):
    id: UUID
    singer_name: str
    status: str
    created_at: datetime
    order_number: int = 0
    user_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class UserQueueItem(BaseModel):
    registration_id: UUID
    song_id: Optional[UUID] = None
    song_title: str
    song_author: Optional[str] = None
    slide_drive_url: Optional[str] = None
    status: str
    session_date: str

    class Config:
        from_attributes = True


class UserExistingRegistration(BaseModel):
    registration_id: UUID
    song_id: Optional[UUID] = None
    song_title: str


class SessionBookingInfo(BaseModel):
    booked_song_ids: list[UUID]
    user_registration: Optional[UserExistingRegistration] = None