from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./retail_intelligence.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class EventRecord(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, index=True)
    id_token = Column(String, unique=True, index=True)
    store_code = Column(String, index=True)
    store_id = Column(String, index=True)
    camera_id = Column(String)
    track_id = Column(Integer, index=True)
    timestamp = Column(String)
    zone_id = Column(String, nullable=True)
    zone_name = Column(String, nullable=True)
    dwell_ms = Column(Integer, default=0)         # Added missing column!
    is_staff = Column(Boolean, default=False)     # Added missing column!