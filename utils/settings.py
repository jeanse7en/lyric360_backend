from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import models

DEFAULT_SETTINGS: dict[str, str] = {
    "drinks": '[{"id":"bia_tiger","label":"Bia Tiger"},{"id":"bia_heineken","label":"Bia Heineken"},{"id":"bia_333","label":"Bia 333"},{"id":"ruou_vang_do","label":"Rượu vang đỏ"},{"id":"ruou_vang_trang","label":"Rượu vang trắng"},{"id":"coca_cola","label":"Coca Cola"},{"id":"pepsi","label":"Pepsi"},{"id":"nuoc_suoi","label":"Nước suối"},{"id":"tra_da","label":"Trà đá"},{"id":"nuoc_cam","label":"Nước cam"}]',
    "queue_limit": "30",
    "user_quota": "1",
    "song_font_size": "24",
    "song_one_page": "true",
    "copy_fb_template": "🎵 Bài hát: [Bài hát]\n✍️ Tác giả: [Tác giả]\n🎤 Khách hát: [Người hát]",
    "preorder_list": "[]",
}


def get_venue_id(db: Session):
    venue_id = db.execute(text("SELECT id FROM venues LIMIT 1")).scalar()
    if not venue_id:
        raise HTTPException(status_code=400, detail="Không tìm thấy venue")
    return venue_id


def get_setting_value(key: str, db: Session) -> str:
    venue_id = get_venue_id(db)
    row = db.query(models.VenueSetting).filter(
        models.VenueSetting.venue_id == venue_id,
        models.VenueSetting.key == key,
    ).first()
    return row.value if row else DEFAULT_SETTINGS.get(key, "")
