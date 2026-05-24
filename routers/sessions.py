import os
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import nullslast
from sqlalchemy.orm import Session, selectinload

import models
import schemas
from database import get_db
from utils.settings import get_venue_id as _get_venue_id, get_setting_value as _get_setting_value

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[schemas.SessionDetailResponse])
def get_all_sessions(
    name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
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
                models.SongLyrics.song_id.in_([r.song_id for r in s.registrations]),
            ).union(
                db.query(models.SongSheet.song_id).filter(
                    models.SongSheet.verified_at.is_(None),
                    models.SongSheet.song_id.in_([r.song_id for r in s.registrations]),
                )
            ).distinct().count()
        ) if s.registrations else 0
        free_text_song_count = sum(1 for r in s.registrations if r.free_text_song_name)
        result.append(schemas.SessionDetailResponse(
            id=s.id,
            name=s.name,
            session_date=s.session_date,
            status=s.status,
            is_private=s.is_private,
            started_at=s.started_at,
            ended_at=s.ended_at,
            order_count=len(s.registrations),
            unverified_song_count=song_ids_with_unverified,
            free_text_song_count=free_text_song_count,
        ))
    return result


@router.post("", response_model=schemas.SessionResponse)
def create_session(data: schemas.SessionCreate, db: Session = Depends(get_db)):
    import json as _json
    venue_id = _get_venue_id(db)
    session = models.LiveSession(
        venue_id=venue_id,
        name=data.name,
        session_date=data.session_date,
        status="planned",
        is_private=data.is_private,
    )
    db.add(session)
    db.flush()

    try:
        raw = _get_setting_value("preorder_list", db)
        preorder_list = _json.loads(raw) if raw else []
    except Exception:
        preorder_list = []
    for entry in preorder_list:
        user_id = entry.get("user_id")
        song_id = entry.get("song_id")
        preorder_number = entry.get("preorder_number")
        singer_name = entry.get("user_name", "")
        if not user_id or not song_id or not preorder_number:
            continue
        db.add(models.QueueRegistration(
            session_id=session.id,
            song_id=song_id,
            user_id=user_id,
            singer_name=singer_name,
            status="waiting",
            preorder_number=preorder_number,
        ))

    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/start", response_model=schemas.SessionResponse)
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


@router.post("/{session_id}/stop", response_model=schemas.SessionResponse)
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


@router.patch("/{session_id}", response_model=schemas.SessionResponse)
def update_session(session_id: UUID, data: schemas.SessionUpdate, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    if data.name is not None:
        session.name = data.name or None
    if data.session_date is not None:
        session.session_date = data.session_date
    if data.is_private is not None:
        session.is_private = data.is_private
    if data.album_url is not None:
        session.album_url = data.album_url or None
    db.commit()
    db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: UUID, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    db.delete(session)
    db.commit()


# Static paths — must be declared before /{session_id}

@router.get("/available", response_model=list[schemas.SessionDetailResponse])
def get_available_sessions(db: Session = Depends(get_db)):
    sessions = (
        db.query(models.LiveSession)
        .filter(
            models.LiveSession.status.in_(["live", "planned"]),
            models.LiveSession.session_date >= date.today(),
            models.LiveSession.is_private == False,
        )
        .order_by(
            (models.LiveSession.status != "live"),
            models.LiveSession.session_date.asc(),
        )
        .all()
    )
    return [
        schemas.SessionDetailResponse(
            id=s.id,
            name=s.name,
            session_date=s.session_date,
            status=s.status,
            is_private=s.is_private,
            started_at=s.started_at,
            ended_at=s.ended_at,
            order_count=db.query(models.QueueRegistration)
                .filter(models.QueueRegistration.session_id == s.id)
                .count(),
        )
        for s in sessions
    ]


@router.get("/live", response_model=schemas.LiveSessionPresenting)
def get_live_session(db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.status == "live").first()
    if not session:
        raise HTTPException(status_code=404, detail="Không có buổi diễn đang live")
    return session


# Parameterized paths — must be after all static paths above

@router.get("/{session_id}", response_model=schemas.SessionDetailResponse)
def get_session(session_id: UUID, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    order_count = db.query(models.QueueRegistration).filter(models.QueueRegistration.session_id == session_id).count()
    return schemas.SessionDetailResponse(
        id=session.id,
        name=session.name,
        session_date=session.session_date,
        status=session.status,
        is_private=session.is_private,
        started_at=session.started_at,
        ended_at=session.ended_at,
        order_count=order_count,
    )


@router.patch("/{session_id}/present")
def set_presenting_lyric(session_id: UUID, body: schemas.PresentBody, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    session.presenting_lyric_url = body.url
    db.commit()
    return {"ok": True}


@router.get("/{session_id}/booked-songs", response_model=schemas.SessionBookingInfo)
def get_session_booked_songs(session_id: str, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    registrations = (
        db.query(models.QueueRegistration)
        .filter(models.QueueRegistration.session_id == session_id)
        .all()
    )
    booked_song_ids = [reg.song_id for reg in registrations if reg.song_id is not None]
    taken_preorder_numbers = [reg.preorder_number for reg in registrations if reg.preorder_number is not None]
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
    return schemas.SessionBookingInfo(
        booked_song_ids=booked_song_ids,
        user_registration=user_registration,
        taken_preorder_numbers=taken_preorder_numbers,
    )


@router.get("/{session_id}/queue", response_model=list[schemas.SessionQueueItem])
def get_session_queue(session_id: str, db: Session = Depends(get_db)):
    registrations = (
        db.query(models.QueueRegistration)
        .filter(models.QueueRegistration.session_id == session_id)
        .options(
            selectinload(models.QueueRegistration.song).selectinload(models.Song.lyrics),
            selectinload(models.QueueRegistration.song).selectinload(models.Song.sheets),
        )
        .order_by(
            nullslast(models.QueueRegistration.preorder_number.asc()),
            models.QueueRegistration.created_at.asc(),
        )
        .all()
    )
    result = []
    for reg in registrations:
        song = None
        if reg.song:
            lyrics = [schemas.SessionQueueVerifiable(id=l.id, verified_at=l.verified_at) for l in reg.song.lyrics]
            sheets = [schemas.SessionQueueVerifiable(id=s.id, verified_at=s.verified_at) for s in reg.song.sheets]
            song = schemas.SessionQueueSong(
                id=reg.song.id,
                title=reg.song.title,
                author=reg.song.author,
                song_lyrics=lyrics,
                song_sheets=sheets,
            )
        result.append(schemas.SessionQueueItem(
            id=reg.id,
            session_id=reg.session_id,
            user_id=reg.user_id,
            singer_name=reg.singer_name,
            booker_phone=reg.booker_phone,
            table_position=reg.table_position,
            drinks=reg.drinks or [],
            status=reg.status,
            created_at=reg.created_at,
            actual_start=reg.actual_start,
            actual_end=reg.actual_end,
            actual_tone=reg.actual_tone,
            note=reg.note,
            rating=reg.rating,
            free_text_song_name=reg.free_text_song_name,
            preorder_number=reg.preorder_number,
            video_url=reg.video_url,
            want_facebook_post=reg.want_facebook_post,
            songs=song,
        ))
    return result


@router.post("/{session_id}/queue/{reg_id}/play")
def play_queue_registration(session_id: UUID, reg_id: UUID, db: Session = Depends(get_db)):
    db.query(models.QueueRegistration).filter(
        models.QueueRegistration.session_id == session_id,
        models.QueueRegistration.status == "playing",
    ).update({"status": "done"})
    reg = db.query(models.QueueRegistration).filter(models.QueueRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    reg.status = "playing"
    reg.actual_start = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.get("/{session_id}/video-segments", response_model=schemas.SessionVideoResponse)
def get_session_video_segments(session_id: str, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")

    regs = (
        db.query(models.QueueRegistration)
        .filter(
            models.QueueRegistration.session_id == session_id,
            models.QueueRegistration.actual_start.isnot(None),
            models.QueueRegistration.actual_end.isnot(None),
        )
        .order_by(models.QueueRegistration.actual_start)
        .all()
    )

    reference = session.camera_start
    if reference is None and regs:
        reference = regs[0].actual_start

    segments = []
    for reg in regs:
        duration_sec = (reg.actual_end - reg.actual_start).total_seconds()
        if duration_sec <= 0:
            continue
        song_title = (reg.song.title if reg.song else None) or reg.free_text_song_name or "Không rõ"
        segments.append(schemas.VideoSegmentResponse(
            registration_id=reg.id,
            song_title=song_title,
            singer_name=reg.singer_name,
            booker_phone=reg.booker_phone,
            actual_start_iso=reg.actual_start.isoformat(),
            actual_end_iso=reg.actual_end.isoformat(),
            video_url=reg.video_url,
        ))

    if session.started_at:
        local_time = session.started_at.astimezone()
        date_str = local_time.strftime("%Y/%m/%d %H:%M")
    else:
        date_str = str(session.session_date)
    folder_name = f"[{date_str}]{str(session.id)[:8]}"

    return schemas.SessionVideoResponse(
        session_id=session.id,
        camera_start=session.camera_start,
        video_folder_id=session.video_folder_id,
        video_folder_name=folder_name,
        parent_folder_id=os.getenv("VIDEO_OUTPUT_FOLDER_ID", "") or "root",
        segments=segments,
    )


@router.patch("/{session_id}/video-folder")
def set_session_video_folder(session_id: str, body: dict, db: Session = Depends(get_db)):
    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")
    session.video_folder_id = body.get("folder_id")
    db.commit()
    return {"folder_id": session.video_folder_id}


@router.post("/{session_id}/link-photos-videos")
def link_photos_videos(session_id: str, db: Session = Depends(get_db)):
    from utils.photos import list_videos_on_date, find_video_for_song

    session = db.query(models.LiveSession).filter(models.LiveSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi diễn")

    session_date_str = str(session.session_date)
    try:
        videos = list_videos_on_date(session_date_str)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lỗi Google Photos: {e}")

    if not videos:
        return {"linked": 0, "skipped": 0, "message": "Không tìm thấy video nào trong ngày này trên Google Photos"}

    regs = (
        db.query(models.QueueRegistration)
        .filter(
            models.QueueRegistration.session_id == session_id,
            models.QueueRegistration.actual_start.isnot(None),
            models.QueueRegistration.actual_end.isnot(None),
            models.QueueRegistration.video_url.is_(None),
        )
        .all()
    )

    linked = 0
    skipped = 0
    for reg in regs:
        url = find_video_for_song(videos, reg.actual_start, reg.actual_end)
        if url:
            reg.video_url = url
            linked += 1
        else:
            skipped += 1

    db.commit()
    return {"linked": linked, "skipped": skipped, "total_videos": len(videos)}
