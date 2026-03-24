from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
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

# API 1: Hỗ trợ Paging và Load mặc định
@app.get("/api/songs/search", response_model=list[schemas.SongResponse])
def search_songs(q: str | None = None, offset: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    query = db.query(models.Song)
    
    # Nếu có gõ tìm kiếm thì filter
    if q and len(q.strip()) > 0:
        query = query.filter(models.Song.title.ilike(f"%{q}%"))
        
    # Phân trang (Paging) và sắp xếp theo tên ABC
    songs = query.order_by(models.Song.title).offset(offset).limit(limit).all()
    return songs

# API 2: Đăng ký bài hát mới vào hàng đợi
@app.post("/api/queue/register", response_model=schemas.QueueResponse)
def register_queue(queue_data: schemas.QueueCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra session_id (Đêm diễn) có tồn tại và đang live không
    session_exists = db.query(models.LiveSession).filter(models.LiveSession.id == queue_data.session_id).first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đêm diễn này")

    # 2. Kiểm tra bài hát có trong kho không
    song_exists = db.query(models.Song).filter(models.Song.id == queue_data.song_id).first()
    if not song_exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài hát này")

    # 3. Tạo record
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

