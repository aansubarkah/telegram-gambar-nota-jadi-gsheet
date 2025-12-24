"""
SQLAlchemy ORM models for Telegram Invoice Bot.

Tables:
- User: Telegram users with tier and settings
- ActivityLog: Activity logging for usage tracking
- Tier: Reference table for tier limits
"""

from datetime import datetime
from typing import Optional
import json

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Tier(Base):
    """Reference table for user tiers and their limits."""
    
    __tablename__ = "tiers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    daily_limit = Column(Integer, nullable=False)  # -1 means unlimited
    price_monthly = Column(Integer, default=0)
    
    # Relationship
    users = relationship("User", back_populates="tier_info")
    
    def __repr__(self):
        return f"<Tier(name='{self.name}', daily_limit={self.daily_limit})>"


class User(Base):
    """Telegram user with tier, settings, and Google Sheet assignment."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    
    # Tier information
    tier = Column(String(50), ForeignKey("tiers.name"), nullable=False, default="free")
    
    # Google Sheets
    google_sheet_id = Column(String(255), nullable=True)
    
    # Custom AI prompt (nullable, falls back to default)
    custom_prompt = Column(Text, nullable=True)
    
    # Custom sheet column order (JSON array, e.g., '["date", "product", "qty"]')
    sheet_columns = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tier_info = relationship("Tier", back_populates="users")
    activity_logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, tier='{self.tier}')>"
    
    @property
    def daily_limit(self) -> int:
        """Get daily limit from tier. Returns -1 for unlimited."""
        if self.tier_info:
            return self.tier_info.daily_limit
        # Fallback defaults
        limits = {"free": 5, "silver": 50, "gold": 150, "platinum": 300, "admin": -1}
        return limits.get(self.tier, 5)
    
    @property
    def sheet_columns_list(self) -> Optional[list]:
        """Parse sheet_columns JSON to list."""
        if self.sheet_columns:
            try:
                return json.loads(self.sheet_columns)
            except json.JSONDecodeError:
                return None
        return None
    
    @sheet_columns_list.setter
    def sheet_columns_list(self, columns: list):
        """Set sheet_columns from list."""
        if columns:
            self.sheet_columns = json.dumps(columns)
        else:
            self.sheet_columns = None


class ActivityLog(Base):
    """Activity log for tracking usage and debugging."""
    
    __tablename__ = "activity_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Timestamp with index for efficient date queries
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # File information (we never store the actual file)
    file_type = Column(String(50), nullable=False)  # "image", "pdf", "text"
    file_size_bytes = Column(Integer, nullable=True)
    
    # Processing result
    processing_status = Column(String(50), nullable=False)  # "success", "failed", "limit_exceeded"
    items_extracted = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="activity_logs")
    
    # Index for efficient user + date queries
    __table_args__ = (
        Index("ix_activity_user_timestamp", "user_id", "timestamp"),
    )
    
    def __repr__(self):
        return f"<ActivityLog(user_id={self.user_id}, file_type='{self.file_type}', status='{self.processing_status}')>"


# Default tier data for seeding
DEFAULT_TIERS = [
    {"name": "free", "daily_limit": 5, "price_monthly": 0},
    {"name": "silver", "daily_limit": 50, "price_monthly": 0},
    {"name": "gold", "daily_limit": 150, "price_monthly": 0},
    {"name": "platinum", "daily_limit": 300, "price_monthly": 0},
    {"name": "admin", "daily_limit": -1, "price_monthly": 0},  # -1 = unlimited
]
