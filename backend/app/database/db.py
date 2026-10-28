from sqlalchemy import create_engine, Column, String, Float, Integer, Boolean, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from pathlib import Path

DB_FILE = Path(__file__).resolve().parent.parent.parent / "production_scheduler.db"
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class JobModel(Base):
    __tablename__ = "jobs"
    job_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    product_type = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    arrival_time = Column(Float, default=0.0)
    due_date = Column(Float, nullable=False)
    priority = Column(Integer, default=3)
    status = Column(String, default="PENDING")
    operations_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class MachineModel(Base):
    __tablename__ = "machines"
    machine_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    capability = Column(String, nullable=False)
    status = Column(String, default="IDLE")
    current_job_id = Column(String, nullable=True)
    current_operation_seq = Column(Integer, nullable=True)
    remaining_processing_time = Column(Float, default=0.0)
    total_busy_time = Column(Float, default=0.0)

class ScheduleRecordModel(Base):
    __tablename__ = "schedule_records"
    schedule_id = Column(String, primary_key=True, index=True)
    algorithm = Column(String, nullable=False)
    created_at_sim_time = Column(Float, default=0.0)
    tasks_json = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    explanation_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
