import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import sessions, songs, queue, users, settings, audit

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

app = FastAPI(title="Lyric360 API Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(songs.router)
app.include_router(queue.router)
app.include_router(users.router)
app.include_router(settings.router)
app.include_router(audit.router)


@app.get("/")
def read_root():
    return {"message": "Lyric360 Backend is running smoothly!"}
