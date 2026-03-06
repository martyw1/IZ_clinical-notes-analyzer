import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.models import Role, User

os.makedirs(settings.upload_dir, exist_ok=True)
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins_list,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def wait_for_database(max_attempts: int = 8, initial_delay: float = 0.5) -> None:
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text('SELECT 1'))
            return
        except SQLAlchemyError:
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2


@app.on_event('startup')
def startup() -> None:
    wait_for_database()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == 'admin')).scalar_one_or_none()
        if not admin:
            db.add(
                User(
                    username='admin',
                    password_hash=hash_password('r3'),
                    role=Role.admin,
                    must_reset_password=True,
                )
            )
            db.commit()
    finally:
        db.close()


@app.get('/health')
def health():
    return {'status': 'ok'}


app.include_router(router)
