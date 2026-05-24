import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

import models
import schemas
from database import get_db
from utils.text import normalize_vn

router = APIRouter(prefix="/api/songs", tags=["songs"])


# ── Static paths — must be declared before /{song_id} ──────────────────────

@router.get("/manage", response_model=list[schemas.SongManageItem])
def get_songs_manage(
    q: str | None = None,
    verify_status: str | None = None,
    min_lyric_count: int | None = None,
    max_lyric_count: int | None = None,
    min_sheet_count: int | None = None,
    max_sheet_count: int | None = None,
    min_lyric_chars: int | None = None,
    max_lyric_chars: int | None = None,
    search_lyric: bool = False,
    sort_by: str = "last_viewed_at",
    offset: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(models.Song).filter(models.Song.deleted_at.is_(None))
    if q and q.strip():
        q_norm = normalize_vn(q.strip())
        title_match = models.Song.title_normalized.ilike(f"%{q_norm}%")
        if search_lyric:
            lyric_match = models.Song.lyrics.any(models.SongLyrics.lyrics.ilike(f"%{q.strip()}%"))
            query = query.filter(title_match | lyric_match)
        else:
            query = query.filter(title_match)

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

    if min_lyric_count is not None or max_lyric_count is not None:
        lyric_cnt_sq = (
            select(func.count(models.SongLyrics.id))
            .where(models.SongLyrics.song_id == models.Song.id)
            .correlate(models.Song).scalar_subquery()
        )
        if min_lyric_count is not None:
            query = query.filter(lyric_cnt_sq >= min_lyric_count)
        if max_lyric_count is not None:
            query = query.filter(lyric_cnt_sq <= max_lyric_count)

    if min_sheet_count is not None or max_sheet_count is not None:
        sheet_cnt_sq = (
            select(func.count(models.SongSheet.id))
            .where(models.SongSheet.song_id == models.Song.id)
            .correlate(models.Song).scalar_subquery()
        )
        if min_sheet_count is not None:
            query = query.filter(sheet_cnt_sq >= min_sheet_count)
        if max_sheet_count is not None:
            query = query.filter(sheet_cnt_sq <= max_sheet_count)

    if min_lyric_chars is not None or max_lyric_chars is not None:
        max_chars_sq = (
            select(func.max(func.char_length(models.SongLyrics.lyrics)))
            .where(models.SongLyrics.song_id == models.Song.id)
            .correlate(models.Song).scalar_subquery()
        )
        if min_lyric_chars is not None:
            query = query.filter(max_chars_sq >= min_lyric_chars)
        if max_lyric_chars is not None:
            query = query.filter(max_chars_sq <= max_lyric_chars)

    if sort_by == "title":
        order = models.Song.title_normalized.asc()
    elif sort_by == "created_at":
        order = models.Song.created_at.desc()
    elif sort_by == "last_updated_at":
        last_lyric_sq = (
            select(func.max(models.SongLyrics.created_at))
            .where(models.SongLyrics.song_id == models.Song.id)
            .correlate(models.Song).scalar_subquery()
        )
        last_sheet_sq = (
            select(func.max(models.SongSheet.created_at))
            .where(models.SongSheet.song_id == models.Song.id)
            .correlate(models.Song).scalar_subquery()
        )
        order = func.greatest(
            models.Song.created_at,
            func.coalesce(last_lyric_sq, models.Song.created_at),
            func.coalesce(last_sheet_sq, models.Song.created_at),
        ).desc()
    else:
        order = models.Song.last_viewed_at.desc().nulls_last()

    songs = (
        query
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .order_by(order)
        .offset(offset).limit(limit).all()
    )
    return [
        schemas.SongManageItem(
            id=song.id,
            title=song.title,
            author=song.author,
            lyric_count=len(song.lyrics),
            sheet_count=len(song.sheets),
            unverified_count=(
                sum(1 for s in song.sheets if s.verified_at is None) +
                sum(1 for l in song.lyrics if l.verified_at is None)
            ),
        )
        for song in songs
    ]


@router.get("/unverified-count", response_model=schemas.UnverifiedCountResponse)
def get_unverified_count(db: Session = Depends(get_db)):
    unverified_lyrics = db.query(models.SongLyrics.song_id).filter(models.SongLyrics.verified_at.is_(None)).distinct()
    unverified_sheets = db.query(models.SongSheet.song_id).filter(models.SongSheet.verified_at.is_(None)).distinct()
    song_ids = unverified_lyrics.union(unverified_sheets).subquery()
    count = db.query(func.count()).select_from(song_ids).scalar()
    return {"count": count or 0}


@router.post("/ai-fetch-lyrics")
async def ai_fetch_lyrics(title: str, author: str | None = None):
    import asyncio
    from utils.gemini import fetch_lyrics_from_gemini
    try:
        return await asyncio.to_thread(fetch_lyrics_from_gemini, title, author)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")


@router.get("/sync/preview", response_model=schemas.SyncPreviewResponse)
def sync_preview(
    sheet_name: str = "NewSheet",
    spreadsheet_id: str | None = None,
    db: Session = Depends(get_db),
):
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
            .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
            .filter(models.Song.title_normalized == title_norm)
            .first()
        )
        changes: list[str] = []
        action = "SKIP"
        song_id = None

        if song is None:
            action = "CREATE"
            changes.append("Tạo mới bài hát")
            if row["lyrics"]: changes.append("Thêm lời bài hát")
            if row["sheet_url"]: changes.append("Thêm sheet nhạc")
            if row["lyric_slide_url"]: changes.append("Thêm link slide lyric")
        else:
            song_id = song.id
            if row["author"] and row["author"] != song.author:
                changes.append("Cập nhật tác giả")
            if row["year"]:
                active_lyric = next(iter(song.lyrics), None)
                existing_year = str(active_lyric.composed_at.year) if active_lyric and active_lyric.composed_at else None
                if existing_year != row["year"]:
                    changes.append("Cập nhật năm sáng tác")
            if row["lyrics"]: changes.append("Cập nhật lời bài hát")
            if row["lyric_slide_url"]: changes.append("Cập nhật link slide lyric")
            if row["sheet_url"]:
                active_sheet = next(iter(song.sheets), None)
                if not active_sheet or active_sheet.sheet_drive_url != row["sheet_url"]:
                    changes.append("Cập nhật sheet nhạc")
            action = "UPDATE" if changes else "SKIP"

        raw_lyrics = row["lyrics"] or ""
        items.append(schemas.SyncPreviewItem(
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
        ))

    return schemas.SyncPreviewResponse(
        items=items,
        total=len(items),
        to_create=sum(1 for i in items if i.action == "CREATE"),
        to_update=sum(1 for i in items if i.action == "UPDATE"),
    )


@router.post("/sync/run", response_model=schemas.SyncRunResult)
def sync_run(
    sheet_name: str = "NewSheet",
    spreadsheet_id: str | None = None,
    db: Session = Depends(get_db),
):
    from utils.sheets import read_sheet_rows
    try:
        rows = read_sheet_rows(sheet_name, spreadsheet_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không thể đọc sheet: {e}")

    created = updated = skipped = 0
    errors: list[str] = []

    def _parse_year(year_str: str | None) -> "datetime | None":
        if not year_str:
            return None
        try:
            return datetime(int(year_str), 1, 1, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    for row in rows:
        try:
            title_norm = normalize_vn(row["song_title"])
            song = (
                db.query(models.Song)
                .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
                .filter(models.Song.title_normalized == title_norm)
                .first()
            )

            if song is None:
                song = models.Song(title=row["song_title"], title_normalized=title_norm, author=row["author"])
                db.add(song)
                db.flush()
                if row["lyrics"]:
                    db.add(models.SongLyrics(
                        song_id=song.id, lyrics=row["lyrics"],
                        slide_drive_url=row["lyric_slide_url"],
                        source_lyric="SHEET_SYNC",
                        composed_at=_parse_year(row["year"]),
                        verified_at=None,
                    ))
                if row["sheet_url"]:
                    db.add(models.SongSheet(song_id=song.id, sheet_drive_url=row["sheet_url"], verified_at=None))
                db.commit()
                created += 1
            else:
                changed = False
                if row["author"] and row["author"] != song.author:
                    song.author = row["author"]
                    changed = True
                if row["lyrics"]:
                    for lyr in list(song.lyrics): db.delete(lyr)
                    db.add(models.SongLyrics(
                        song_id=song.id, lyrics=row["lyrics"],
                        slide_drive_url=row["lyric_slide_url"],
                        source_lyric="SHEET_SYNC",
                        composed_at=_parse_year(row["year"]),
                        verified_at=None,
                    ))
                    changed = True
                if row["sheet_url"]:
                    for sht in list(song.sheets): db.delete(sht)
                    db.add(models.SongSheet(song_id=song.id, sheet_drive_url=row["sheet_url"], verified_at=None))
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


@router.get("/search", response_model=list[schemas.SongResponse])
def search_songs(q: str | None = None, offset: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    from sqlalchemy import case as sa_case
    query = db.query(models.Song)
    if q and len(q.strip()) > 0:
        q_norm = normalize_vn(q.strip())
        query = query.filter(models.Song.title_normalized.ilike(f"%{q_norm}%"))
        rank = sa_case(
            (models.Song.title_normalized == q_norm, 0),
            (models.Song.title_normalized.ilike(f"{q_norm}%"), 1),
            else_=2,
        )
        order = rank
    else:
        order = models.Song.title_normalized.asc()
    songs = (
        query
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .order_by(order, models.Song.title_normalized.asc())
        .offset(offset).limit(limit).all()
    )
    return songs


@router.get("/lyrics/{lyric_id}", response_model=schemas.SongLyricDetail)
def get_lyric_by_id(lyric_id: UUID, db: Session = Depends(get_db)):
    lyric = (
        db.query(models.SongLyrics)
        .options(joinedload(models.SongLyrics.song))
        .filter(models.SongLyrics.id == lyric_id)
        .first()
    )
    if not lyric:
        raise HTTPException(status_code=404, detail="Không tìm thấy lời bài hát")
    return schemas.SongLyricDetail(
        id=lyric.id,
        lyrics=lyric.lyrics,
        slide_drive_url=lyric.slide_drive_url,
        source_lyric=lyric.source_lyric,
        verified_at=lyric.verified_at,
        title=lyric.song.title,
        author=lyric.song.author,
    )


# ── Parameterized paths — after all static paths ────────────────────────────

@router.post("", response_model=schemas.SongResponse)
def create_song(data: schemas.SongCreate, db: Session = Depends(get_db)):
    song = models.Song(title=data.title, title_normalized=normalize_vn(data.title), author=data.author)
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


@router.get("/{song_id}", response_model=schemas.SongResponse)
def get_song(song_id: UUID, db: Session = Depends(get_db)):
    song = (
        db.query(models.Song)
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .filter(models.Song.id == song_id)
        .first()
    )
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    song.last_viewed_at = datetime.now(timezone.utc)
    db.commit()
    return song


@router.patch("/{song_id}", response_model=schemas.SongResponse)
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


@router.delete("/{song_id}", status_code=204)
def delete_song(song_id: UUID, db: Session = Depends(get_db)):
    song = db.query(models.Song).filter(models.Song.id == song_id, models.Song.deleted_at.is_(None)).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    song.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{song_id}/sheets", response_model=schemas.SongSheetResponse)
def add_sheet(song_id: UUID, data: schemas.SongSheetCreate, db: Session = Depends(get_db)):
    song = db.query(models.Song).filter(models.Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    sheet = models.SongSheet(
        song_id=song_id,
        sheet_drive_url=data.sheet_drive_url,
        tone_male=data.tone_male,
        tone_female=data.tone_female,
        verified_at=datetime.now(timezone.utc),
    )
    db.add(sheet)
    db.commit()
    db.refresh(sheet)
    return sheet


@router.post("/{song_id}/sheets/{sheet_id}/verify", response_model=schemas.SongSheetResponse)
def verify_sheet(song_id: UUID, sheet_id: UUID, db: Session = Depends(get_db)):
    sheet = db.query(models.SongSheet).filter(models.SongSheet.id == sheet_id, models.SongSheet.song_id == song_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Không tìm thấy sheet")
    sheet.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sheet)
    return sheet


@router.delete("/{song_id}/sheets/{sheet_id}", status_code=204)
def delete_sheet(song_id: UUID, sheet_id: UUID, db: Session = Depends(get_db)):
    sheet = db.query(models.SongSheet).filter(models.SongSheet.id == sheet_id, models.SongSheet.song_id == song_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Không tìm thấy sheet")
    db.delete(sheet)
    db.commit()


@router.post("/{song_id}/lyrics", response_model=schemas.SongLyricsResponse)
def add_lyric(song_id: UUID, data: schemas.SongLyricsCreate, db: Session = Depends(get_db)):
    song = db.query(models.Song).filter(models.Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát")
    lyric = models.SongLyrics(
        song_id=song_id,
        lyrics=data.lyrics,
        source_lyric=data.source_lyric,
        composed_at=data.composed_at,
        verified_at=datetime.now(timezone.utc),
    )
    db.add(lyric)
    db.commit()
    db.refresh(lyric)
    return lyric


@router.patch("/{song_id}/lyrics/{lyric_id}", response_model=schemas.SongLyricsResponse)
def update_lyric(song_id: UUID, lyric_id: UUID, data: schemas.SongLyricsUpdate, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id, models.SongLyrics.song_id == song_id
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Lyric not found")
    if data.lyrics is not None:
        lyric.lyrics = data.lyrics
    db.commit()
    db.refresh(lyric)
    return lyric


@router.post("/{song_id}/lyrics/{lyric_id}/verify", response_model=schemas.SongLyricsResponse)
def verify_lyric(song_id: UUID, lyric_id: UUID, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id, models.SongLyrics.song_id == song_id
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Không tìm thấy lyric")
    lyric.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lyric)
    return lyric


@router.post("/{song_id}/lyrics/{lyric_id}/generate-slide", response_model=schemas.SongLyricsResponse)
def generate_lyric_slide(song_id: UUID, lyric_id: UUID, db: Session = Depends(get_db)):
    from utils.slides import create_lyric_slide
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id, models.SongLyrics.song_id == song_id
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Lyric not found")
    song = db.query(models.Song).filter(models.Song.id == song_id).first()
    try:
        url = create_lyric_slide(song.title, song.author, lyric.lyrics)
    except Exception as e:
        logging.getLogger("slides").error("generate_lyric_slide error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"Slide generation failed: {e}")
    lyric.slide_drive_url = url
    db.commit()
    db.refresh(lyric)
    return lyric


@router.delete("/{song_id}/lyrics/{lyric_id}", status_code=204)
def delete_lyric(song_id: UUID, lyric_id: UUID, db: Session = Depends(get_db)):
    lyric = db.query(models.SongLyrics).filter(
        models.SongLyrics.id == lyric_id, models.SongLyrics.song_id == song_id
    ).first()
    if not lyric:
        raise HTTPException(status_code=404, detail="Không tìm thấy lyric")
    db.delete(lyric)
    db.commit()
