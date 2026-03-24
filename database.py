import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Lưu ý: Lấy chuỗi kết nối Transaction Pooler (Port 6543) trên Supabase
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,               # Giữ sẵn 10 connection mở liên tục
    max_overflow=20,            # Khi quá tải, cho phép mở thêm tối đa 20 connection nữa
    pool_pre_ping=True,         # CỰC KỲ QUAN TRỌNG: Ping thử database trước khi mượn connection để tránh lỗi mạng
    pool_recycle=1800           # Reset connection sau 30 phút để tránh bị Supabase ngắt ngầm
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()