from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from utils.audit import log_audit
from utils.network import client_ip, client_mac, client_user_agent

router = APIRouter(prefix="/api/users", tags=["users"])


# Static paths — must be declared before /{user_id}

@router.get("", response_model=list[schemas.UserListItem])
def list_users(q: str = "", offset: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(models.User)
    if q.strip():
        q_like = f"%{q.strip()}%"
        query = query.filter(
            models.User.name.ilike(q_like) |
            models.User.phone_zalo.ilike(q_like)
        )
    return query.order_by(models.User.name).offset(offset).limit(limit).all()


@router.get("/search", response_model=list[schemas.UserResponse])
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


# Parameterized paths — after static paths

@router.get("/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.patch("/{user_id}", response_model=schemas.UserListItem)
def update_user(request: Request, user_id: str, data: schemas.UserUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    before_snapshot = {"user_name": user.name, "phone_number": user.phone_zalo}

    if data.name is not None:
        user.name = data.name
    if data.phone_zalo is not None:
        user.phone_zalo = data.phone_zalo or None
    if data.facebook_link is not None:
        user.facebook_link = data.facebook_link or None

    after_snapshot = {"user_name": user.name, "phone_number": user.phone_zalo}
    log_audit(
        db,
        entity_type="user",
        action="update",
        entity_id=user.id,
        before=before_snapshot,
        after=after_snapshot,
        mac_address=client_mac(request),
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(request: Request, user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    before_snapshot = {"user_name": user.name, "phone_number": user.phone_zalo}
    user_id_uuid = user.id
    db.delete(user)
    log_audit(
        db,
        entity_type="user",
        action="delete",
        entity_id=user_id_uuid,
        before=before_snapshot,
        after=None,
        mac_address=client_mac(request),
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    db.commit()
