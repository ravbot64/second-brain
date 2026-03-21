from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# For SQLite: check_same_thread=False
# For PostgreSQL: configure health checks and keepalive to reduce dropped stale connections.
connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if settings.DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    engine_kwargs.update(
        {
            "pool_recycle": 300,
            "pool_timeout": 30,
            "pool_size": 5,
            "max_overflow": 10,
            "pool_use_lifo": True,
        }
    )

engine = create_engine(settings.DB_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
