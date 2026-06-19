from typing import Optional
from sqlalchemy.orm import Session
import models


def log_audit(
    db: Session,
    entity_type: str,
    action: str,
    entity_id,
    before: Optional[dict],
    after: Optional[dict],
    actor_user_id=None,
    mac_address: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    entry = models.AuditLog(
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        mac_address=mac_address,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
