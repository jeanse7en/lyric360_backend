from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

# Response khi tìm kiếm bài hát
class SongResponse(BaseModel):
    id: UUID
    title: str
    author: Optional[str] = None
    tone_male: Optional[str] = None
    tone_female: Optional[str] = None
    
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