import csv
import os
import datetime as dt
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. Database Alignment
SQLALCHEMY_DATABASE_URL = "sqlite:///./retail_intelligence.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class POSTransaction(Base):
    __tablename__ = "pos_transactions"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, unique=True, index=True)
    store_id = Column(String, index=True)
    timestamp = Column(String, index=True)  # Standardized ISO format
    brand_name = Column(String)
    total_amount = Column(Float)

Base.metadata.create_all(bind=engine)

def parse_to_iso(date_str, time_str):
    """Converts DD-MM-YYYY and HH:MM:SS format to ISO 8601 UTC format."""
    try:
        day, month, year = map(int, date_str.split('-'))
        hour, minute, second = map(int, time_str.split(':'))
        obj = dt.datetime(year, month, day, hour, minute, second)
        return obj.isoformat() + "Z"
    except Exception:
        return None

def ingest_pos_csv(csv_path="POS - sample transactionsb1e826f.csv"):
    if not os.path.exists(csv_path):
        print(f"❌ Cannot find CSV file at: {csv_path}")
        return

    db = SessionLocal()
    print(f"🚀 Parsing and Ingesting {csv_path} into SQLite...")
    
    count = 0
    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            iso_ts = parse_to_iso(row['order_date'], row['order_time'])
            if not iso_ts:
                continue
                
            # Verify transaction uniqueness to guarantee idempotent records
            existing = db.query(POSTransaction).filter(POSTransaction.order_id == int(row['order_id'])).first()
            if existing:
                continue

            tx = POSTransaction(
                order_id=int(row['order_id']),
                store_id=row['store_id'],
                timestamp=iso_ts,
                brand_name=row['brand_name'],
                total_amount=float(row['total_amount'])
            )
            db.add(tx)
            count += 1
            
            if count % 100 == 0:
                db.commit()

    db.commit()
    db.close()
    print(f"✅ POS Ingestion Complete! Inserted {count} native transaction records.")

if __name__ == "__main__":
    ingest_pos_csv()