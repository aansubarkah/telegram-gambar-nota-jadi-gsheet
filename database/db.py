"""
Database connection and session management.

Usage:
    from database.db import init_db, get_db
    
    # Initialize database (create tables, seed data)
    init_db()
    
    # Use in functions
    with get_db() as db:
        user = db.query(User).filter_by(telegram_id=123).first()
"""

import os
import sys
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Handle imports for both package and direct execution
if __name__ == "__main__":
    # Add parent directory to path for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from models import Base, Tier, DEFAULT_TIERS
else:
    from database.models import Base, Tier, DEFAULT_TIERS

logger = logging.getLogger(__name__)

# Database path - relative to project root
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite with threading
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Usage:
        with get_db() as db:
            user = db.query(User).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize the database.
    Creates all tables and seeds tier reference data.
    """
    logger.info(f"Initializing database at {DATABASE_PATH}")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
    
    # Seed tier data
    seed_tiers()


def seed_tiers() -> None:
    """
    Seed the tiers table with default tier data.
    Only inserts if tiers don't exist yet.
    """
    with get_db() as db:
        existing_tiers = db.query(Tier).count()
        
        if existing_tiers == 0:
            logger.info("Seeding tiers table with default data...")
            for tier_data in DEFAULT_TIERS:
                tier = Tier(**tier_data)
                db.add(tier)
            db.commit()
            logger.info(f"Seeded {len(DEFAULT_TIERS)} tiers")
        else:
            logger.info(f"Tiers table already has {existing_tiers} entries, skipping seed")


def reset_db() -> None:
    """
    Reset the database by dropping and recreating all tables.
    WARNING: This will delete all data!
    """
    logger.warning("Resetting database - all data will be deleted!")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_tiers()
    logger.info("Database reset complete")


if __name__ == "__main__":
    # Quick test when running directly
    logging.basicConfig(level=logging.INFO)
    init_db()
    print(f"✅ Database initialized at {DATABASE_PATH}")
    
    with get_db() as db:
        tiers = db.query(Tier).all()
        print(f"📊 Tiers in database: {[t.name for t in tiers]}")
