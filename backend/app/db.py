from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.settings import settings

# Cloud Run은 요청이 없는 동안 인스턴스를 얼리고 Cloud SQL은 유휴 커넥션을 끊는다.
# pool_pre_ping이 없으면 한동안 조용하다가 들어온 첫 요청이 죽은 커넥션을 집어 실패한다.
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
