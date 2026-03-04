import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

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
    allow_origins=[settings.frontend_origin, '*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
def startup() -> None:
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
