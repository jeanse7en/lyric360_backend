from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from utils.settings import DEFAULT_SETTINGS, get_venue_id as _get_venue_id

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[schemas.SettingResponse])
def get_all_settings(db: Session = Depends(get_db)):
    venue_id = _get_venue_id(db)
    rows = db.query(models.VenueSetting).filter(models.VenueSetting.venue_id == venue_id).all()
    saved = {r.key: r.value for r in rows}
    return [
        schemas.SettingResponse(key=key, value=saved.get(key, default_val))
        for key, default_val in DEFAULT_SETTINGS.items()
    ]


@router.get("/{key}", response_model=schemas.SettingResponse)
def get_setting(key: str, db: Session = Depends(get_db)):
    venue_id = _get_venue_id(db)
    row = db.query(models.VenueSetting).filter(
        models.VenueSetting.venue_id == venue_id,
        models.VenueSetting.key == key,
    ).first()
    if row:
        return schemas.SettingResponse(key=row.key, value=row.value)
    if key in DEFAULT_SETTINGS:
        return schemas.SettingResponse(key=key, value=DEFAULT_SETTINGS[key])
    raise HTTPException(status_code=404, detail="Không tìm thấy cài đặt")


@router.put("/{key}", response_model=schemas.SettingResponse)
def upsert_setting(key: str, data: schemas.SettingUpdate, db: Session = Depends(get_db)):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(status_code=400, detail="Khóa cài đặt không hợp lệ")
    venue_id = _get_venue_id(db)
    row = db.query(models.VenueSetting).filter(
        models.VenueSetting.venue_id == venue_id,
        models.VenueSetting.key == key,
    ).first()
    if row:
        row.value = data.value
    else:
        row = models.VenueSetting(venue_id=venue_id, key=key, value=data.value)
        db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.SettingResponse(key=row.key, value=row.value)
