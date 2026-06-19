from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from database import get_db

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditLogResponse])
def list_audit_logs(
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(models.AuditLog).options(joinedload(models.AuditLog.actor))
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_id:
        query = query.filter(models.AuditLog.entity_id == entity_id)
    if actor_user_id:
        query = query.filter(models.AuditLog.actor_user_id == actor_user_id)
    if ip_address:
        query = query.filter(models.AuditLog.ip_address.ilike(f"%{ip_address}%"))

    logs = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for log in logs:
        r = schemas.AuditLogResponse.model_validate(log)
        r.actor_name = log.actor.name if log.actor else None
        results.append(r)
    return results
