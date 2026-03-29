from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, selectinload

import models
import schemas
from database import get_db
from utils.text import normalize_vn

app = FastAPI(title="Lyric360 API Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Trong thực tế sẽ đổi thành tên miền Next.js của bạn, hiện tại cho phép tất cả để test
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Lyric360 Backend is running smoothly!"}

# API: Lấy tất cả buổi diễn (dùng cho trang nhạc công, bao gồm cả đã kết thúc)
@app.get("/api/sessions", response_model=list[schemas.SessionResponse])
def get_all_sessions(db: Session = Depends(get_db)):
    return (
        db.query(models.LiveSession)
        .order_by(
            (models.LiveSession.status != "live"),
            models.LiveSession.session_date.desc(),
        )
        .all()
    )


# API: Lấy danh sách buổi diễn available (live trước, sau đó planned theo ngày)
@app.get("/api/sessions/available", response_model=list[schemas.SessionResponse])
def get_available_sessions(db: Session = Depends(get_db)):
    return (
        db.query(models.LiveSession)
        .filter(
            models.LiveSession.status.in_(["live", "planned"]),
            models.LiveSession.session_date >= date.today(),
        )
        .order_by(
            # live sessions first, then by date ascending
            (models.LiveSession.status != "live"),
            models.LiveSession.session_date.asc(),
        )
        .all()
    )


# API: Quản lý bài hát — danh sách kèm số lượng lyric/sheet và số chưa verify
# verify_status: UNVERIFIED_ALL | UNVERIFIED_LYRIC | UNVERIFIED_SHEET | VERIFIED
@app.get("/api/songs/manage", response_model=list[schemas.SongManageItem])
def get_songs_manage(q: str | None = None, verify_status: str | None = None, offset: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    query = db.query(models.Song)
    if q and q.strip():
        query = query.filter(
            models.Song.title_normalized.ilike(f"%{normalize_vn(q.strip())}%")
        )
    if verify_status == "UNVERIFIED_LYRIC":
        query = query.filter(models.Song.lyrics.any(models.SongLyrics.verified_at.is_(None)))
    elif verify_status == "UNVERIFIED_SHEET":
        query = query.filter(models.Song.sheets.any(models.SongSheet.verified_at.is_(None)))
    elif verify_status == "UNVERIFIED_ALL":
        query = query.filter(
            models.Song.lyrics.any(models.SongLyrics.verified_at.is_(None)) |
            models.Song.sheets.any(models.SongSheet.verified_at.is_(None))
        )
    elif verify_status == "VERIFIED":
        query = query.filter(
            ~models.Song.lyrics.any(models.SongLyrics.verified_at.is_(None)),
            ~models.Song.sheets.any(models.SongSheet.verified_at.is_(None)),
        )
    songs = (
        query
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .order_by(models.Song.title)
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = []
    for song in songs:
        unverified = sum(1 for s in song.sheets if s.verified_at is None) + \
                     sum(1 for l in song.lyrics if l.verified_at is None)
        result.append(schemas.SongManageItem(
            id=song.id,
            title=song.title,
            author=song.author,
            lyric_count=len(song.lyrics),
            sheet_count=len(song.sheets),
            unverified_count=unverified,
        ))
    return result


# API: Đếm tổng số bài có lyric/sheet chưa được verify
@app.get("/api/songs/unverified-count", response_model=schemas.UnverifiedCountResponse)
def get_unverified_count(db: Session = Depends(get_db)):
    from sqlalchemy import func
    unverified_lyrics = db.query(models.SongLyrics.song_id).filter(models.SongLyrics.verified_at.is_(None), models.SongLyrics.deleted_at.is_(None)).distinct()
    unverified_sheets = db.query(models.SongSheet.song_id).filter(models.SongSheet.verified_at.is_(None)).distinct()
    song_ids = unverified_lyrics.union(unverified_sheets).subquery()
    count = db.query(func.count()).select_from(song_ids).scalar()
    return {"count": count or 0}


# API: Chi tiết một bài hát (full lyrics + sheets)
@app.get("/api/songs/{song_id}", response_model=schemas.SongResponse)
def get_song(song_id: UUID, db: Session = Depends(get_db)):
    from sqlalchemy.orm import with_loader_criteria
    song = (
        db.query(models.Song)
        .options(
            selectinload(models.Song.sheets),
            selectinload(models.Song.lyrics),
            with_loader_criteria(models.SongLyrics, models.SongLyrics.deleted_at.is_(None)),
            with_loader_criteria(models.SongSheet, models.SongSheet.deleted_at.is_(None)),
        )
        .filter(models.Song.id == song_id)
        .first()
    )
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    return song


# API: Verify một lyric
@app.post("/api/songs/{song_id}/lyrics/{lyric_id}/verify", response_model=schemas.SongLyricsResponse)
def verify_lyric(song_id: UUID, lyric_id: UUID, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id,
        models.SongLyrics.song_id == song_id,
        models.SongLyrics.deleted_at.is_(None),
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Không tìm thấy lyric")
    lyric.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lyric)
    return lyric


# API: Xóa mềm một lyric
@app.delete("/api/songs/{song_id}/lyrics/{lyric_id}", response_model=schemas.SongLyricsResponse)
def delete_lyric(song_id: UUID, lyric_id: UUID, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id,
        models.SongLyrics.song_id == song_id,
        models.SongLyrics.deleted_at.is_(None),
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Không tìm thấy lyric")
    lyric.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lyric)
    return lyric


# API: Verify một sheet
@app.post("/api/songs/{song_id}/sheets/{sheet_id}/verify", response_model=schemas.SongSheetResponse)
def verify_sheet(song_id: UUID, sheet_id: UUID, db: Session = Depends(get_db)):
    sheet = db.query(models.SongSheet).filter(
        models.SongSheet.id == sheet_id,
        models.SongSheet.song_id == song_id,
        models.SongSheet.deleted_at.is_(None),
    ).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Không tìm thấy sheet")
    sheet.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sheet)
    return sheet


# API: Xóa mềm một sheet
@app.delete("/api/songs/{song_id}/sheets/{sheet_id}", response_model=schemas.SongSheetResponse)
def delete_sheet(song_id: UUID, sheet_id: UUID, db: Session = Depends(get_db)):
    sheet = db.query(models.SongSheet).filter(
        models.SongSheet.id == sheet_id,
        models.SongSheet.song_id == song_id,
        models.SongSheet.deleted_at.is_(None),
    ).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Không tìm thấy sheet")
    sheet.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sheet)
    return sheet


# API 1: Hỗ trợ Paging và Load mặc định
@app.get("/api/songs/search", response_model=list[schemas.SongResponse])
def search_songs(q: str | None = None, offset: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    query = db.query(models.Song)
    
    # Nếu có gõ tìm kiếm thì filter
    if q and len(q.strip()) > 0:
        query = query.filter(
            models.Song.title_normalized.ilike(f"%{normalize_vn(q.strip())}%")
        )
        
    # Phân trang (Paging) và sắp xếp theo tên ABC
    songs = (
        query
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .order_by(models.Song.title)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return songs

# API 2: Đăng ký bài hát mới vào hàng đợi
@app.post("/api/queue/register", response_model=schemas.QueueResponse)
def register_queue(queue_data: schemas.QueueCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra session_id (Đêm diễn) có tồn tại và đang live không
    session_exists = db.query(models.LiveSession).filter(models.LiveSession.id == queue_data.session_id).first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn này")
    if session_exists.status != "live":
        raise HTTPException(status_code=400, detail="Đêm diễn chưa bắt đầu hoặc đã kết thúc")

    # 2. Kiểm tra bài hát có trong kho không
    song_exists = db.query(models.Song).filter(models.Song.id == queue_data.song_id).first()
    if not song_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát này")

    # 3. Kiểm tra bài hát đã được đăng ký trong đêm diễn chưa
    duplicate = db.query(models.QueueRegistration).filter(
        models.QueueRegistration.session_id == queue_data.session_id,
        models.QueueRegistration.song_id == queue_data.song_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Bài hát này đã được đăng ký trong đêm diễn")

    # 4. Tạo record
    new_registration = models.QueueRegistration(
        session_id=queue_data.session_id,
        song_id=queue_data.song_id,
        singer_name=queue_data.singer_name,
        booker_phone=queue_data.booker_phone,
        table_position=queue_data.table_position,
        status="waiting"
    )
    
    db.add(new_registration)
    db.commit()
    db.refresh(new_registration)
    
    # Ở đây sau này sẽ trigger background task để gửi tin nhắn Zalo
    
    return new_registration

