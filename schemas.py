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


class SongLyricsResponse(BaseModel):
    id: UUID
    lyrics: str
    slide_drive_url: Optional[str] = None
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
    session_date: date
    status: str

    class Config:
        from_attributes = True


# Request khi khách gửi form đăng ký
class QueueCreate(BaseModel):
    session_id: UUID
    song_id: UUID
    singer_name: str
    booker_phone: str
    table_position: Optional[str] = None

# Response trả về sau khi đăng ký thành công
class QueueResponse(BaseModel):
    id: UUID
    singer_name: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True