from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

import models
import schemas
from utils.settings import get_setting_value


def check_session_limits(session: models.LiveSession, queue_data: schemas.QueueCreate, db: Session) -> None:
    """Raises 400 if the session queue is full or the user has hit their daily quota."""
    if session.is_private:
        return

    queue_limit = int(get_setting_value("queue_limit", db))
    current_count = db.query(models.QueueRegistration).filter(
        models.QueueRegistration.session_id == queue_data.session_id,
    ).count()
    if current_count >= queue_limit:
        raise HTTPException(status_code=400, detail=f"Đêm diễn đã đủ {queue_limit} lượt đăng ký")

    user_quota = int(get_setting_value("user_quota", db))
    user_reg_query = db.query(models.QueueRegistration).join(
        models.LiveSession,
        models.QueueRegistration.session_id == models.LiveSession.id,
    ).filter(
        models.LiveSession.session_date == session.session_date,
    )
    if queue_data.user_id:
        user_reg_query = user_reg_query.filter(models.QueueRegistration.user_id == queue_data.user_id)
    elif queue_data.booker_phone:
        user_reg_query = user_reg_query.filter(models.QueueRegistration.booker_phone == queue_data.booker_phone)
    else:
        user_reg_query = user_reg_query.filter(models.QueueRegistration.singer_name == queue_data.singer_name)
    if user_reg_query.count() >= user_quota:
        raise HTTPException(status_code=400, detail=f"Mỗi khách chỉ được đăng ký tối đa {user_quota} bài trong ngày")


def assign_preorder_number(
    queue_data: schemas.QueueCreate,
    db: Session,
    allow_over_limit: bool = False,
) -> schemas.QueueCreate:
    """Validates or auto-assigns preorder_number. Returns updated queue_data.

    When allow_over_limit=True (admin path) auto-assign goes beyond queue_limit so a
    slot is always found rather than raising 400.
    """
    queue_limit_val = int(get_setting_value("queue_limit", db))

    session_lock_key = int(UUID(str(queue_data.session_id)).int % (2**63))
    db.execute(select(func.pg_advisory_xact_lock(session_lock_key)))

    if queue_data.preorder_number is not None:
        if not allow_over_limit and not (1 <= queue_data.preorder_number <= queue_limit_val):
            raise HTTPException(status_code=400, detail=f"Số thứ tự phải từ 1 đến {queue_limit_val}")
        slot_taken = db.query(models.QueueRegistration).filter(
            models.QueueRegistration.session_id == queue_data.session_id,
            models.QueueRegistration.preorder_number == queue_data.preorder_number,
            models.QueueRegistration.status != "done",
        ).first()
        if slot_taken:
            raise HTTPException(status_code=409, detail=f"Số thứ tự {queue_data.preorder_number} đã được đăng ký")
    else:
        taken = {
            row.preorder_number
            for row in db.query(models.QueueRegistration.preorder_number).filter(
                models.QueueRegistration.session_id == queue_data.session_id,
                models.QueueRegistration.preorder_number.isnot(None),
                models.QueueRegistration.status != "done",
            ).all()
        }
        upper = max(queue_limit_val, max(taken, default=0)) + 1 if allow_over_limit else queue_limit_val
        auto_slot = next((n for n in range(1, upper + 1) if n not in taken), None)
        if auto_slot is None:
            raise HTTPException(status_code=400, detail="Không còn số thứ tự trống")
        queue_data = queue_data.model_copy(update={"preorder_number": auto_slot})

    return queue_data


def check_song(queue_data: schemas.QueueCreate, db: Session) -> None:
    """Validates song_id exists and (unless allow_duplicate) is not already queued."""
    if not queue_data.song_id and not queue_data.free_text_song_name:
        raise HTTPException(status_code=400, detail="Vui lòng chọn hoặc nhập tên bài hát")

    if queue_data.song_id:
        if not db.query(models.Song).filter(models.Song.id == queue_data.song_id).first():
            raise HTTPException(status_code=404, detail="Không tìm thấy bài hát này")

        if not queue_data.allow_duplicate:
            duplicate = db.query(models.QueueRegistration).filter(
                models.QueueRegistration.session_id == queue_data.session_id,
                models.QueueRegistration.song_id == queue_data.song_id,
                models.QueueRegistration.status != "done",
            ).first()
            if duplicate:
                raise HTTPException(status_code=409, detail="Bài hát này đã được đăng ký trong đêm diễn")


def find_or_create_user(queue_data: schemas.QueueCreate, db: Session) -> UUID:
    """Returns user_id, creating a User record if needed."""
    user_id = queue_data.user_id
    if user_id:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user and queue_data.booker_phone and not user.phone_zalo:
            user.phone_zalo = queue_data.booker_phone
            db.flush()
    else:
        user = None
        if queue_data.booker_phone:
            user = db.query(models.User).filter(
                models.User.name == queue_data.singer_name,
                models.User.phone_zalo == queue_data.booker_phone,
            ).first()
        if not user:
            user = db.query(models.User).filter(models.User.name == queue_data.singer_name).first()
        if not user:
            user = models.User(
                name=queue_data.singer_name,
                phone_zalo=queue_data.booker_phone or None,
                role="customer",
            )
            db.add(user)
            db.flush()
        user_id = user.id
    return user_id


def create_registration(
    queue_data: schemas.QueueCreate,
    user_id: UUID,
    db: Session,
) -> models.QueueRegistration:
    """Creates and commits a QueueRegistration record."""
    reg = models.QueueRegistration(
        session_id=queue_data.session_id,
        song_id=queue_data.song_id,
        free_text_song_name=queue_data.free_text_song_name,
        user_id=user_id,
        singer_name=queue_data.singer_name,
        booker_phone=queue_data.booker_phone,
        table_position=queue_data.table_position,
        drinks=queue_data.drinks or [],
        status="waiting",
        preorder_number=queue_data.preorder_number,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg
