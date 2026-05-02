from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime, date

# Child responses
class SongSheetResponse(BaseModel):
    id: UUID
    sheet_drive_url: str
    tone_male: Optional[str] = None
    tone_female: Optional[str] = None
    verified_at: Optional[datetime] = None
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
    is_private: bool = False
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    order_count: int = 0
    unverified_song_count: int = 0
    free_text_song_count: int = 0
    is_private: bool = False

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    name: Optional[str] = None
    session_date: date
    is_private: bool = False


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    session_date: Optional[date] = None
    is_private: Optional[bool] = None


class SessionQueueSong(BaseModel):
    id: UUID
    title: str
    author: Optional[str] = None

    class Config:
        from_attributes = True


class SessionQueueItem(BaseModel):
    id: UUID
    singer_name: str
    booker_phone: Optional[str] = None
    status: str
    created_at: datetime
    free_text_song_name: Optional[str] = None
    songs: Optional[SessionQueueSong] = None
    preorder_number: Optional[int] = None

    class Config:
        from_attributes = True


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


class UserListItem(BaseModel):
    id: UUID
    name: str
    phone_zalo: Optional[str] = None
    facebook_link: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone_zalo: Optional[str] = None
    facebook_link: Optional[str] = None


# Request khi khách gửi form đăng ký
class QueueCreate(BaseModel):
    session_id: UUID
    song_id: Optional[UUID] = None
    free_text_song_name: Optional[str] = None
    singer_name: str
    booker_phone: str
    table_position: Optional[str] = None
    drinks: Optional[List[str]] = []
    user_id: Optional[UUID] = None
    allow_duplicate: bool = False
    preorder_number: Optional[int] = None

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
    lyric_id: Optional[UUID] = None
    lyrics_text: Optional[str] = None
    status: str
    session_date: str
    session_id: UUID
    drinks: List[str] = []
    video_url: Optional[str] = None
    want_facebook_post: bool = False
    order_number: Optional[int] = None

    class Config:
        from_attributes = True


class QueueUpdate(BaseModel):
    session_id: Optional[UUID] = None
    song_id: Optional[UUID] = None
    free_text_song_name: Optional[str] = None
    drinks: Optional[List[str]] = None


class UserExistingRegistration(BaseModel):
    registration_id: UUID
    song_id: Optional[UUID] = None
    song_title: str


class SessionBookingInfo(BaseModel):
    booked_song_ids: list[UUID]
    user_registration: Optional[UserExistingRegistration] = None
    taken_preorder_numbers: list[int] = []


# ── Video cutting ────────────────────────────────────────────────────────────

class VideoSegmentResponse(BaseModel):
    registration_id: UUID
    song_title: str
    singer_name: str
    booker_phone: Optional[str] = None
    actual_start_iso: str
    actual_end_iso: str
    video_url: Optional[str] = None

    class Config:
        from_attributes = True


class SessionVideoResponse(BaseModel):
    session_id: UUID
    camera_start: Optional[datetime] = None
    video_folder_id: Optional[str] = None
    video_folder_name: str
    parent_folder_id: str
    segments: list[VideoSegmentResponse]


class VideoUrlUpdate(BaseModel):
    video_url: str


# ── Cài đặt venue ────────────────────────────────────────────────────────────

class SettingResponse(BaseModel):
    key: str
    value: str

    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    value: str