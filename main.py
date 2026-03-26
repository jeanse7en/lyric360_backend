from datetime import date
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
import models
import schemas
from database import get_db
from fastapi.middleware.cors import CORSMiddleware

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

# API: Lấy tất cả buổi diễn (dùng cho trang nhạc công, bao gồm cả đã kết thúc)
@app.get("/api/sessions", response_model=list[schemas.SessionResponse])
def get_all_sessions(db: Session = Depends(get_db)):
    return (
        db.query(models.LiveSession)
        .order_by(
            (models.LiveSession.status != "live"),
            models.LiveSession.session_date.desc(),
        )
        .all()
    )


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


# API 1: Hỗ trợ Paging và Load mặc định
@app.get("/api/songs/search", response_model=list[schemas.SongResponse])
def search_songs(q: str | None = None, offset: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    query = db.query(models.Song)
    
    # Nếu có gõ tìm kiếm thì filter
    if q and len(q.strip()) > 0:
        query = query.filter(models.Song.title.ilike(f"%{q}%"))
        
    # Phân trang (Paging) và sắp xếp theo tên ABC
    songs = (
        query
        .options(selectinload(models.Song.sheets), selectinload(models.Song.lyrics))
        .order_by(models.Song.title)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return songs

# API 2: Đăng ký bài hát mới vào hàng đợi
@app.post("/api/queue/register", response_model=schemas.QueueResponse)
def register_queue(queue_data: schemas.QueueCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra session_id (Đêm diễn) có tồn tại và đang live không
    session_exists = db.query(models.LiveSession).filter(models.LiveSession.id == queue_data.session_id).first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn này")
    if session_exists.status != "live":
        raise HTTPException(status_code=400, detail="Đêm diễn chưa bắt đầu hoặc đã kết thúc")

    # 2. Kiểm tra bài hát có trong kho không
    song_exists = db.query(models.Song).filter(models.Song.id == queue_data.song_id).first()
    if not song_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát này")

    # 3. Kiểm tra bài hát đã được đăng ký trong đêm diễn chưa
    duplicate = db.query(models.QueueRegistration).filter(
        models.QueueRegistration.session_id == queue_data.session_id,
        models.QueueRegistration.song_id == queue_data.song_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Bài hát này đã được đăng ký trong đêm diễn")

    # 4. Tạo record
    new_registration = models.QueueRegistration(
        session_id=queue_data.session_id,
        song_id=queue_data.song_id,
        singer_name=queue_data.singer_name,
        booker_phone=queue_data.booker_phone,
        table_position=queue_data.table_position,
        status="waiting"
    )
    
    db.add(new_registration)
    db.commit()
    db.refresh(new_registration)
    
    # Ở đây sau này sẽ trigger background task để gửi tin nhắn Zalo
    
    return new_registration

