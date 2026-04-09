import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
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

# API: Lấy tất cả buổi diễn — hỗ trợ filter theo tên và khoảng ngày
@app.get("/api/sessions", response_model=list[schemas.SessionDetailResponse])
def get_all_sessions(
    name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy import func as sqlfunc
    query = db.query(models.LiveSession).options(selectinload(models.LiveSession.registrations))
    if name and name.strip():
        query = query.filter(models.LiveSession.name.ilike(f"%{name.strip()}%"))
    if date_from:
        query = query.filter(models.LiveSession.session_date >= date_from)
    if date_to:
        query = query.filter(models.LiveSession.session_date <= date_to)
    sessions = query.order_by(
        (models.LiveSession.status != "live"),
        models.LiveSession.session_date.desc(),
    ).all()

    result = []
    for s in sessions:
        song_ids_with_unverified = (
            db.query(models.SongLyrics.song_id).filter(
                models.SongLyrics.verified_at.is_(None),
                models.SongLyrics.deleted_at.is_(None),
                models.SongLyrics.song_id.in_([r.song_id for r in s.registrations]),
            ).union(
                db.query(models.SongSheet.song_id).filter(
                    models.SongSheet.verified_at.is_(None),
                    models.SongSheet.deleted_at.is_(None),
                    models.SongSheet.song_id.in_([r.song_id for r in s.registrations]),
                )
            ).distinct().count()
        ) if s.registrations else 0
        result.append(schemas.SessionDetailResponse(
            id=s.id,
            name=s.name,
            session_date=s.session_date,
            status=s.status,
            started_at=s.started_at,
            ended_at=s.ended_at,
            order_count=len(s.registrations),
            unverified_song_count=song_ids_with_unverified,
        ))
    return result


# API: Tạo buổi diễn mới
@app.post("/api/sessions", response_model=schemas.SessionResponse)
def create_session(data: schemas.SessionCreate, db: Session = Depends(get_db)):
    # Dùng venue_id tạm — sau này lấy từ auth token
    from sqlalchemy import text
    venue_id = db.execute(text("SELECT id FROM venues LIMIT 1")).scalar()
    if not venue_id:
        raise HTTPException(status_code=400, detail="Không tìm thấy venue")
    session = models.LiveSession(
        venue_id=venue_id,
        name=data.name,
        session_date=data.session_date,
        status="planned",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


# API: Bắt đầu buổi diễn
@app.post("/api/sessions/{session_id}/start", response_model=schemas.SessionResponse)
def start_session(session_id: UUID, db: Session = Depends(get_db)):
    live_already = db.query(models.LiveSession).filter(models.LiveSession.status == "live").first()
    if live_already and live_already.id != session_id:
        raise HTTPException(status_code=409, detail=f"Buổi diễn '{live_already.name or live_already.session_date}' đang live. Hãy kết thúc trước.")
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    if session.status != "planned":
        raise HTTPException(status_code=400, detail="Chỉ có thể bắt đầu buổi diễn ở trạng thái planned")
    session.status = "live"
    session.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


# API: Kết thúc buổi diễn
@app.post("/api/sessions/{session_id}/stop", response_model=schemas.SessionResponse)
def stop_session(session_id: UUID, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    if session.status != "live":
        raise HTTPException(status_code=400, detail="Chỉ có thể kết thúc buổi diễn đang live")
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


# API: Cập nhật thông tin buổi diễn
@app.patch("/api/sessions/{session_id}", response_model=schemas.SessionResponse)
def update_session(session_id: UUID, data: schemas.SessionUpdate, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    if data.name is not None:
        session.name = data.name or None
    if data.session_date is not None:
        session.session_date = data.session_date
    db.commit()
    db.refresh(session)
    return session


# API: Xóa buổi diễn
@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: UUID, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    db.delete(session)
    db.commit()


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


# API: Tạo bài hát mới thủ công
@app.post("/api/songs", response_model=schemas.SongResponse)
def create_song(data: schemas.SongCreate, db: Session = Depends(get_db)):
    song = models.Song(
        title=data.title,
        title_normalized=normalize_vn(data.title),
        author=data.author,
    )
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


# API: Cập nhật thông tin bài hát
@app.patch("/api/songs/{song_id}", response_model=schemas.SongResponse)
def update_song(song_id: UUID, data: schemas.SongUpdate, db: Session = Depends(get_db)):
    song = db.query(models.Song).filter(models.Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    if data.title is not None:
        song.title = data.title
        song.title_normalized = normalize_vn(data.title)
    if data.author is not None:
        song.author = data.author or None
    db.commit()
    db.refresh(song)
    return song


# API: Thêm sheet nhạc vào bài hát
@app.post("/api/songs/{song_id}/sheets", response_model=schemas.SongSheetResponse)
def add_sheet(song_id: UUID, data: schemas.SongSheetCreate, db: Session = Depends(get_db)):
    song = db.query(models.Song).filter(models.Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    sheet = models.SongSheet(
        song_id=song_id,
        sheet_drive_url=data.sheet_drive_url,
        tone_male=data.tone_male,
        tone_female=data.tone_female,
        verified_at=datetime.now(timezone.utc),  # user-created = auto-verified
    )
    db.add(sheet)
    db.commit()
    db.refresh(sheet)
    return sheet


# API: Thêm lời bài hát thủ công
@app.post("/api/songs/{song_id}/lyrics", response_model=schemas.SongLyricsResponse)
def add_lyric(song_id: UUID, data: schemas.SongLyricsCreate, db: Session = Depends(get_db)):
    song = db.query(models.Song).filter(models.Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    lyric = models.SongLyrics(
        song_id=song_id,
        lyrics=data.lyrics,
        source_lyric=data.source_lyric,
        composed_at=data.composed_at,
        verified_at=datetime.now(timezone.utc),  # user-created = auto-verified
    )
    db.add(lyric)
    db.commit()
    db.refresh(lyric)
    return lyric


# API: Cập nhật lời bài hát
@app.patch("/api/songs/{song_id}/lyrics/{lyric_id}", response_model=schemas.SongLyricsResponse)
def update_lyric(song_id: UUID, lyric_id: UUID, data: schemas.SongLyricsUpdate, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id,
        models.SongLyrics.song_id == song_id,
        models.SongLyrics.deleted_at.is_(None),
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Lyric not found")
    if data.lyrics is not None:
        lyric.lyrics = data.lyrics
    db.commit()
    db.refresh(lyric)
    return lyric


# API: Lấy lời bài hát từ AI
@app.post("/api/songs/ai-fetch-lyrics")
def ai_fetch_lyrics(title: str, author: str | None = None):
    from utils.gemini import fetch_lyrics_from_gemini
    try:
        return fetch_lyrics_from_gemini(title, author)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))


# API: Generate a Google Slides presentation from saved lyrics
@app.post("/api/songs/{song_id}/lyrics/{lyric_id}/generate-slide", response_model=schemas.SongLyricsResponse)
def generate_lyric_slide(song_id: UUID, lyric_id: UUID, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id,
        models.SongLyrics.song_id == song_id,
        models.SongLyrics.deleted_at.is_(None),
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Lyric not found")

    song = db.query(models.Song).filter(models.Song.id == song_id).first()

    import logging, traceback
    from utils.slides import create_lyric_slide
    try:
        url = create_lyric_slide(song.title, song.author, lyric.lyrics)
    except Exception as e:
        logging.getLogger("slides").error("generate_lyric_slide error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"Slide generation failed: {e}")

    lyric.slide_drive_url = url
    db.commit()
    db.refresh(lyric)
    return lyric


# API: Xem trước thay đổi từ Google Sheet (phải đặt trước /{song_id})
@app.get("/api/songs/sync/preview", response_model=schemas.SyncPreviewResponse)
def sync_preview(
    sheet_name: str = "NewSheet",
    spreadsheet_id: str | None = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy.orm import with_loader_criteria
    from utils.sheets import read_sheet_rows

    try:
        rows = read_sheet_rows(sheet_name, spreadsheet_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không thể đọc sheet: {e}")

    items = []
    for row in rows:
        title_norm = normalize_vn(row["song_title"])
        song = (
            db.query(models.Song)
            .options(
                selectinload(models.Song.sheets),
                selectinload(models.Song.lyrics),
                with_loader_criteria(models.SongLyrics, models.SongLyrics.deleted_at.is_(None)),
                with_loader_criteria(models.SongSheet, models.SongSheet.deleted_at.is_(None)),
            )
            .filter(models.Song.title_normalized == title_norm)
            .first()
        )

        changes: list[str] = []
        action = "SKIP"
        song_id = None

        if song is None:
            action = "CREATE"
            changes.append("Tạo mới bài hát")
            if row["lyrics"]:
                changes.append("Thêm lời bài hát")
            if row["sheet_url"]:
                changes.append("Thêm sheet nhạc")
            if row["lyric_slide_url"]:
                changes.append("Thêm link slide lyric")
        else:
            song_id = song.id

            if row["author"] and row["author"] != song.author:
                changes.append("Cập nhật tác giả")

            if row["year"]:
                active_lyric = next((l for l in song.lyrics if l.deleted_at is None), None)
                existing_year = (
                    str(active_lyric.composed_at.year)
                    if active_lyric and active_lyric.composed_at
                    else None
                )
                if existing_year != row["year"]:
                    changes.append("Cập nhật năm sáng tác")

            if row["lyrics"]:
                changes.append("Cập nhật lời bài hát")

            if row["lyric_slide_url"]:
                changes.append("Cập nhật link slide lyric")

            if row["sheet_url"]:
                active_sheet = next((s for s in song.sheets if s.deleted_at is None), None)
                if not active_sheet or active_sheet.sheet_drive_url != row["sheet_url"]:
                    changes.append("Cập nhật sheet nhạc")

            action = "UPDATE" if changes else "SKIP"

        raw_lyrics = row["lyrics"] or ""
        items.append(
            schemas.SyncPreviewItem(
                row_number=row["row_number"],
                song_title=row["song_title"],
                author=row["author"],
                year=row["year"],
                lyrics_preview=(raw_lyrics[:200] + "…") if len(raw_lyrics) > 200 else raw_lyrics or None,
                sheet_url=row["sheet_url"],
                lyric_slide_url=row["lyric_slide_url"],
                song_id=song_id,
                action=action,
                changes=changes,
            )
        )

    return schemas.SyncPreviewResponse(
        items=items,
        total=len(items),
        to_create=sum(1 for i in items if i.action == "CREATE"),
        to_update=sum(1 for i in items if i.action == "UPDATE"),
    )


# API: Thực hiện đồng bộ từ Google Sheet (phải đặt trước /{song_id})
@app.post("/api/songs/sync/run", response_model=schemas.SyncRunResult)
def sync_run(
    sheet_name: str = "NewSheet",
    spreadsheet_id: str | None = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy.orm import with_loader_criteria
    from utils.sheets import read_sheet_rows

    try:
        rows = read_sheet_rows(sheet_name, spreadsheet_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không thể đọc sheet: {e}")

    created = updated = skipped = 0
    errors: list[str] = []

    for row in rows:
        try:
            title_norm = normalize_vn(row["song_title"])
            song = (
                db.query(models.Song)
                .options(
                    selectinload(models.Song.sheets),
                    selectinload(models.Song.lyrics),
                    with_loader_criteria(models.SongLyrics, models.SongLyrics.deleted_at.is_(None)),
                    with_loader_criteria(models.SongSheet, models.SongSheet.deleted_at.is_(None)),
                )
                .filter(models.Song.title_normalized == title_norm)
                .first()
            )

            def _parse_year(year_str: str | None) -> "datetime | None":
                if not year_str:
                    return None
                try:
                    return datetime(int(year_str), 1, 1, tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    return None

            if song is None:
                song = models.Song(
                    title=row["song_title"],
                    title_normalized=title_norm,
                    author=row["author"],
                )
                db.add(song)
                db.flush()

                if row["lyrics"]:
                    db.add(
                        models.SongLyrics(
                            song_id=song.id,
                            lyrics=row["lyrics"],
                            slide_drive_url=row["lyric_slide_url"],
                            source_lyric="SHEET_SYNC",
                            composed_at=_parse_year(row["year"]),
                            verified_at=None,
                        )
                    )

                if row["sheet_url"]:
                    db.add(
                        models.SongSheet(
                            song_id=song.id,
                            sheet_drive_url=row["sheet_url"],
                            verified_at=None,
                        )
                    )

                db.commit()
                created += 1

            else:
                changed = False

                if row["author"] and row["author"] != song.author:
                    song.author = row["author"]
                    changed = True

                if row["lyrics"]:
                    for lyr in song.lyrics:
                        if lyr.deleted_at is None:
                            lyr.deleted_at = datetime.now(timezone.utc)
                    db.add(
                        models.SongLyrics(
                            song_id=song.id,
                            lyrics=row["lyrics"],
                            slide_drive_url=row["lyric_slide_url"],
                            source_lyric="SHEET_SYNC",
                            composed_at=_parse_year(row["year"]),
                            verified_at=None,
                        )
                    )
                    changed = True

                if row["sheet_url"]:
                    for sht in song.sheets:
                        if sht.deleted_at is None:
                            sht.deleted_at = datetime.now(timezone.utc)
                    db.add(
                        models.SongSheet(
                            song_id=song.id,
                            sheet_drive_url=row["sheet_url"],
                            verified_at=None,
                        )
                    )
                    changed = True

                if changed:
                    db.commit()
                    updated += 1
                else:
                    skipped += 1

        except Exception as e:
            db.rollback()
            errors.append(f"Dòng {row['row_number']} ({row['song_title']}): {e}")

    return schemas.SyncRunResult(created=created, updated=updated, skipped=skipped, errors=errors)


# API: Tìm kiếm bài hát (phải đặt trước /{song_id} để tránh FastAPI bắt "search" như UUID)
@app.get("/api/songs/search", response_model=list[schemas.SongResponse])
def search_songs(q: str | None = None, offset: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    query = db.query(models.Song)
    if q and len(q.strip()) > 0:
        query = query.filter(
            models.Song.title_normalized.ilike(f"%{normalize_vn(q.strip())}%")
        )
    songs = (
        query
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .order_by(models.Song.title)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return songs


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

# Tìm kiếm người dùng theo tên — phải khai báo trước /{user_id}
@app.get("/api/users/search", response_model=list[schemas.UserResponse])
def search_users(q: str = "", db: Session = Depends(get_db)):
    if not q.strip():
        return []
    q_like = f"%{q.strip()}%"
    return (
        db.query(models.User)
        .filter(
            models.User.name.ilike(q_like) |
            models.User.phone_zalo.ilike(q_like)
        )
        .order_by(models.User.name)
        .limit(10)
        .all()
    )


# Lấy thông tin một user theo id
@app.get("/api/users/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


def _ingest_free_text_song(registration_id: UUID, title: str):
    """Background task: create Song, AI-fetch lyrics, generate slide, link back to registration."""
    import logging, traceback
    from database import SessionLocal
    from utils.gemini import fetch_lyrics_from_gemini
    from utils.slides import create_lyric_slide

    log = logging.getLogger("ingest_free_text")
    db = SessionLocal()
    try:
        # 1. Create Song
        song = models.Song(title=title, title_normalized=normalize_vn(title))
        db.add(song)
        db.flush()

        # 2. Fetch lyrics via AI
        try:
            result = fetch_lyrics_from_gemini(title, author=None)
            # fetch_lyrics_from_gemini returns a dict {title, author, year, lyrics}
            if isinstance(result, dict):
                lyrics_text = result.get("lyrics")
                if not song.author and result.get("author"):
                    song.author = result.get("author")
            else:
                lyrics_text = result
        except Exception:
            log.warning("AI lyrics fetch failed for '%s':\n%s", title, traceback.format_exc())
            lyrics_text = None

        slide_url = None
        if lyrics_text:
            # 3. Create SongLyrics
            lyric = models.SongLyrics(
                song_id=song.id,
                lyrics=lyrics_text,
                source_lyric="AI",
            )
            db.add(lyric)
            db.flush()

            # 4. Generate slide
            try:
                slide_url = create_lyric_slide(title, song.author, lyrics_text)
                lyric.slide_drive_url = slide_url
            except Exception:
                log.warning("Slide generation failed for '%s':\n%s", title, traceback.format_exc())

        # 5. Link registration back to new song
        reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == registration_id).first()
        if reg:
            reg.song_id = song.id

        db.commit()
        log.info("Free-text song ingested: '%s' → song_id=%s slide=%s", title, song.id, slide_url)
    except Exception:
        db.rollback()
        log.error("_ingest_free_text_song failed:\n%s", traceback.format_exc())
    finally:
        db.close()


# API 2: Đăng ký bài hát mới vào hàng đợi
@app.post("/api/queue/register", response_model=schemas.QueueResponse)
def register_queue(queue_data: schemas.QueueCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # 1. Kiểm tra session_id (Đêm diễn) có tồn tại và đang live không
    session_exists = db.query(models.LiveSession).filter(models.LiveSession.id == queue_data.session_id).first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn này")
    if session_exists.status == "ended":
        raise HTTPException(status_code=400, detail="Đêm diễn đã kết thúc")

    # 2. Validate: phải có song_id hoặc free_text_song_name
    if not queue_data.song_id and not queue_data.free_text_song_name:
        raise HTTPException(status_code=400, detail="Vui lòng chọn hoặc nhập tên bài hát")

    # 3. Kiểm tra bài hát có trong kho không (chỉ khi có song_id)
    if queue_data.song_id:
        song_exists = db.query(models.Song).filter(models.Song.id == queue_data.song_id).first()
        if not song_exists:
            raise HTTPException(status_code=404, detail="Không tìm thấy bài hát này")

        # Kiểm tra bài hát đã được đăng ký trong đêm diễn chưa
        duplicate = db.query(models.QueueRegistration).filter(
            models.QueueRegistration.session_id == queue_data.session_id,
            models.QueueRegistration.song_id == queue_data.song_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Bài hát này đã được đăng ký trong đêm diễn")

    # 4. Tìm hoặc tạo user
    user_id = queue_data.user_id
    if user_id:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user and queue_data.booker_phone and not user.phone_zalo:
            user.phone_zalo = queue_data.booker_phone
            db.flush()
    else:
        # Tìm theo tên + phone, hoặc chỉ tên nếu không có phone
        user = None
        if queue_data.booker_phone:
            user = db.query(models.User).filter(
                models.User.name == queue_data.singer_name,
                models.User.phone_zalo == queue_data.booker_phone,
            ).first()
        if not user:
            user = db.query(models.User).filter(
                models.User.name == queue_data.singer_name,
            ).first()
        if not user:
            user = models.User(
                name=queue_data.singer_name,
                phone_zalo=queue_data.booker_phone or None,
                role="customer",
            )
            db.add(user)
            db.flush()
        user_id = user.id

    # 5. Tạo record
    new_registration = models.QueueRegistration(
        session_id=queue_data.session_id,
        song_id=queue_data.song_id,
        free_text_song_name=queue_data.free_text_song_name,
        user_id=user_id,
        singer_name=queue_data.singer_name,
        booker_phone=queue_data.booker_phone,
        table_position=queue_data.table_position,
        status="waiting"
    )

    db.add(new_registration)
    db.commit()
    db.refresh(new_registration)

    # Tính order number (vị trí trong hàng đợi của session)
    order_number = db.query(models.QueueRegistration).filter(
        models.QueueRegistration.session_id == queue_data.session_id,
        models.QueueRegistration.created_at <= new_registration.created_at,
    ).count()

    # Background: ingest free-text song (create Song → AI lyrics → Slide)
    if queue_data.free_text_song_name and not queue_data.song_id:
        background_tasks.add_task(_ingest_free_text_song, new_registration.id, queue_data.free_text_song_name)

    # TODO: trigger Zalo notification

    result = schemas.QueueResponse(
        id=new_registration.id,
        singer_name=new_registration.singer_name,
        status=new_registration.status,
        created_at=new_registration.created_at,
        order_number=order_number,
        user_id=user_id,
    )
    return result


# Lấy danh sách bài hát đã đăng ký của một user
@app.get("/api/queue/user/{user_id}", response_model=list[schemas.UserQueueItem])
def get_user_queue(user_id: str, db: Session = Depends(get_db)):
    registrations = (
        db.query(models.QueueRegistration)
        .filter(models.QueueRegistration.user_id == user_id)
        .order_by(models.QueueRegistration.created_at.desc())
        .limit(50)
        .all()
    )
    result = []
    for reg in registrations:
        if reg.song:
            lyric = next(
                (l for l in reg.song.lyrics if l.deleted_at is None and l.slide_drive_url),
                None,
            )
            title = reg.song.title
            author = reg.song.author
            slide_url = lyric.slide_drive_url if lyric else None
        else:
            # free-text song not yet ingested by background task
            title = reg.free_text_song_name or ""
            author = None
            slide_url = None
        result.append(schemas.UserQueueItem(
            registration_id=reg.id,
            song_id=reg.song_id,
            song_title=title,
            song_author=author,
            slide_drive_url=slide_url,
            status=reg.status,
            session_date=str(reg.session.session_date),
        ))
    return result


# Lấy thông tin đặt chỗ trong một session: danh sách song_id đã đặt + đăng ký của user (nếu có)
@app.get("/api/sessions/{session_id}/booked-songs", response_model=schemas.SessionBookingInfo)
def get_session_booked_songs(session_id: str, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    registrations = (
        db.query(models.QueueRegistration)
        .filter(models.QueueRegistration.session_id == session_id)
        .all()
    )
    booked_song_ids = [reg.song_id for reg in registrations if reg.song_id is not None]
    user_registration = None
    if user_id:
        user_reg = next((r for r in registrations if str(r.user_id) == user_id), None)
        if user_reg:
            song_title = user_reg.song.title if user_reg.song else (user_reg.free_text_song_name or "")
            user_registration = schemas.UserExistingRegistration(
                registration_id=user_reg.id,
                song_id=user_reg.song_id,
                song_title=song_title,
            )
    return schemas.SessionBookingInfo(booked_song_ids=booked_song_ids, user_registration=user_registration)

