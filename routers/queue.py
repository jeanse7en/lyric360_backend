import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

import models
import schemas
from database import get_db, SessionLocal
from utils.text import normalize_vn
from utils.queue_service import (
    assign_preorder_number,
    check_session_limits,
    check_song,
    create_registration,
    find_or_create_user,
)

router = APIRouter(tags=["queue"])


def _ingest_free_text_song(registration_id: UUID, title: str):
    """Background task: create Song, AI-fetch lyrics, generate slide, link back to registration."""
    from utils.gemini import fetch_lyrics_from_gemini
    from utils.slides import create_lyric_slide

    log = logging.getLogger("ingest_free_text")
    db = SessionLocal()
    try:
        song = models.Song(title=title, title_normalized=normalize_vn(title))
        db.add(song)
        db.flush()

        try:
            result = fetch_lyrics_from_gemini(title, author=None)
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
            lyric = models.SongLyrics(song_id=song.id, lyrics=lyrics_text, source_lyric="AI")
            db.add(lyric)
            db.flush()
            try:
                slide_url = create_lyric_slide(title, song.author, lyrics_text)
                lyric.slide_drive_url = slide_url
            except Exception:
                log.warning("Slide generation failed for '%s':\n%s", title, traceback.format_exc())

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


@router.post("/api/queue/register", response_model=schemas.QueueResponse)
def register_queue(queue_data: schemas.QueueCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    session_exists = db.query(models.LiveSession).filter(models.LiveSession.id == queue_data.session_id).first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn này")
    if session_exists.status == "ended":
        raise HTTPException(status_code=400, detail="Đêm diễn đã kết thúc")

    check_session_limits(session_exists, queue_data, db)
    queue_data = assign_preorder_number(queue_data, db)
    check_song(queue_data, db)

    user_id = find_or_create_user(queue_data, db)
    new_registration = create_registration(queue_data, user_id, db)

    if queue_data.free_text_song_name and not queue_data.song_id:
        background_tasks.add_task(_ingest_free_text_song, new_registration.id, queue_data.free_text_song_name)

    # TODO: trigger Zalo notification

    return schemas.QueueResponse(
        id=new_registration.id,
        singer_name=new_registration.singer_name,
        status=new_registration.status,
        created_at=new_registration.created_at,
        order_number=new_registration.preorder_number or 0,
        user_id=user_id,
    )


@router.post("/api/admin/queue/register", response_model=schemas.QueueResponse)
def admin_register_queue(queue_data: schemas.QueueCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    session_exists = db.query(models.LiveSession).filter(models.LiveSession.id == queue_data.session_id).first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn này")
    if session_exists.status == "ended":
        raise HTTPException(status_code=400, detail="Đêm diễn đã kết thúc")

    queue_data = assign_preorder_number(queue_data, db, allow_over_limit=True)
    queue_data = queue_data.model_copy(update={"allow_duplicate": True})
    check_song(queue_data, db)

    user_id = find_or_create_user(queue_data, db)
    new_registration = create_registration(queue_data, user_id, db)

    if queue_data.free_text_song_name and not queue_data.song_id:
        background_tasks.add_task(_ingest_free_text_song, new_registration.id, queue_data.free_text_song_name)

    return schemas.QueueResponse(
        id=new_registration.id,
        singer_name=new_registration.singer_name,
        status=new_registration.status,
        created_at=new_registration.created_at,
        order_number=new_registration.preorder_number or 0,
        user_id=user_id,
    )


@router.get("/api/queue/user/{user_id}", response_model=list[schemas.UserQueueItem])
def get_user_queue(user_id: str, db: Session = Depends(get_db)):
    registrations = (
        db.query(models.QueueRegistration)
        .options(
            selectinload(models.QueueRegistration.song).selectinload(models.Song.lyrics),
            selectinload(models.QueueRegistration.session),
        )
        .filter(models.QueueRegistration.user_id == user_id)
        .order_by(models.QueueRegistration.created_at.desc())
        .limit(50)
        .all()
    )
    result = []
    for reg in registrations:
        if reg.song:
            active_lyrics = list(reg.song.lyrics)
            lyric_with_slide = next((l for l in active_lyrics if l.slide_drive_url), None)
            lyric_with_text  = next((l for l in active_lyrics if l.lyrics), None)
            title = reg.song.title
            author = reg.song.author
            slide_url = lyric_with_slide.slide_drive_url if lyric_with_slide else None
            lyric_id = lyric_with_text.id if lyric_with_text else None
            lyrics_text = lyric_with_text.lyrics if lyric_with_text else None
            all_lyrics = [schemas.LyricSummary(id=l.id, source_lyric=l.source_lyric, composed_at=l.composed_at) for l in active_lyrics]
        else:
            title = reg.free_text_song_name or ""
            author = None
            slide_url = None
            lyric_id = None
            lyrics_text = None
            all_lyrics = []
        result.append(schemas.UserQueueItem(
            registration_id=reg.id,
            song_id=reg.song_id,
            song_title=title,
            song_author=author,
            slide_drive_url=slide_url,
            lyric_id=lyric_id,
            lyrics_text=lyrics_text,
            lyrics=all_lyrics,
            status=reg.status,
            session_date=str(reg.session.session_date),
            session_id=reg.session_id,
            drinks=reg.drinks or [],
            video_url=reg.video_url,
            want_facebook_post=reg.want_facebook_post,
            order_number=reg.preorder_number,
            album_url=reg.session.album_url,
        ))
    return result


@router.patch("/api/queue/registrations/{reg_id}")
def update_queue_registration(reg_id: str, update: schemas.QueueUpdate, db: Session = Depends(get_db)):
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    if reg.status == "done":
        raise HTTPException(status_code=400, detail="Không thể sửa bài đã hát xong")

    if update.session_id and str(update.session_id) != str(reg.session_id):
        session = db.query(models.LiveSession).filter(models.LiveSession.id == update.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn")
        if session.status == "ended":
            raise HTTPException(status_code=400, detail="Đêm diễn đã kết thúc")
        reg.session_id = update.session_id

    if update.song_id is not None and str(update.song_id) != str(reg.song_id):
        duplicate = db.query(models.QueueRegistration).filter(
            models.QueueRegistration.session_id == reg.session_id,
            models.QueueRegistration.song_id == update.song_id,
            models.QueueRegistration.id != reg.id,
            models.QueueRegistration.status != "done",
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Bài hát này đã được đăng ký trong đêm diễn")
        reg.song_id = update.song_id
        reg.free_text_song_name = None

    if update.free_text_song_name is not None:
        reg.free_text_song_name = update.free_text_song_name
        reg.song_id = None

    if update.drinks is not None:
        reg.drinks = update.drinks

    if "user_id" in update.model_fields_set:
        reg.user_id = update.user_id

    if update.singer_name is not None:
        reg.singer_name = update.singer_name

    if update.booker_phone is not None:
        reg.booker_phone = update.booker_phone

    if "preorder_number" in update.model_fields_set:
        if update.preorder_number is not None:
            conflict = db.query(models.QueueRegistration).filter(
                models.QueueRegistration.session_id == reg.session_id,
                models.QueueRegistration.preorder_number == update.preorder_number,
                models.QueueRegistration.id != reg.id,
                models.QueueRegistration.status != "done",
            ).first()
            if conflict:
                raise HTTPException(status_code=409, detail=f"Số thứ tự {update.preorder_number} đã được đăng ký")
        reg.preorder_number = update.preorder_number

    db.commit()
    return {"ok": True}


@router.post("/api/queue/registrations/{reg_id}/stop")
def stop_queue_registration(reg_id: UUID, db: Session = Depends(get_db)):
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    reg.status = "done"
    reg.actual_end = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.patch("/api/queue/registrations/{reg_id}/note")
def update_queue_note(reg_id: UUID, data: schemas.QueueNoteUpdate, db: Session = Depends(get_db)):
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    if data.actual_tone is not None:
        reg.actual_tone = data.actual_tone
    if data.note is not None:
        reg.note = data.note
    if data.rating is not None:
        reg.rating = data.rating
    db.commit()
    return {"ok": True}


@router.patch("/api/queue/registrations/{reg_id}/video-url")
def update_registration_video_url(reg_id: str, body: schemas.VideoUrlUpdate, db: Session = Depends(get_db)):
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    reg.video_url = body.video_url
    db.commit()
    return {"video_url": reg.video_url}


@router.post("/api/queue/registrations/{reg_id}/facebook-post")
def request_facebook_post(reg_id: str, db: Session = Depends(get_db)):
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    reg.want_facebook_post = True
    db.commit()
    return {"want_facebook_post": True}


@router.delete("/api/queue/registrations/{reg_id}", status_code=204)
def delete_queue_registration(reg_id: str, db: Session = Depends(get_db)):
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    if reg.status == "done":
        raise HTTPException(status_code=400, detail="Không thể xoá bài đã hát xong")
    db.delete(reg)
    db.commit()
