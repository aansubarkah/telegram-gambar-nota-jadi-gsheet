"""
CRUD operations for the Telegram Invoice Bot database.

All database operations should go through these functions
to maintain consistency and make testing easier.
"""

from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Literal, List
import logging

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database.models import User, ActivityLog

logger = logging.getLogger(__name__)

# Default timezone for daily reset (WIB - Indonesia)
DEFAULT_TIMEZONE = "Asia/Jakarta"


@dataclass
class QuotaStatus:
    """Status of user's daily quota."""
    can_proceed: bool
    used_today: int
    daily_limit: int
    tier: str
    
    @property
    def remaining(self) -> int:
        """Get remaining quota. Returns large number for unlimited."""
        if self.daily_limit == -1:
            return 999999  # Effectively unlimited
        return max(0, self.daily_limit - self.used_today)
    
    @property
    def is_unlimited(self) -> bool:
        """Check if user has unlimited quota."""
        return self.daily_limit == -1


# ============================================================
# User CRUD Operations
# ============================================================

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    """
    Find a user by their Telegram ID.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        
    Returns:
        User object or None if not found
    """
    return db.query(User).filter(User.telegram_id == telegram_id).first()


def get_user_spreadsheet_id(db: Session, telegram_id: int, default_spreadsheet_id: str) -> str:
    """
    Get the spreadsheet ID for a user.
    
    Logic:
    - If user has google_sheet_id set → return it (paid tier)
    - If user's google_sheet_id is NULL → return default (free tier)
    - If user doesn't exist → return default
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        default_spreadsheet_id: Default spreadsheet ID for free tier
        
    Returns:
        Google Spreadsheet ID to use
    """
    user = get_user_by_telegram_id(db, telegram_id)
    
    if user and user.google_sheet_id:
        return user.google_sheet_id
    
    return default_spreadsheet_id


def create_user(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    tier: str = "free",
    google_sheet_id: Optional[str] = None,
) -> User:
    """
    Create a new user.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID (required)
        username: Telegram username (optional)
        first_name: User's first name (optional)
        last_name: User's last name (optional)
        tier: User tier (default: "free")
        google_sheet_id: User's Google Sheet ID (optional)
        
    Returns:
        Created User object
    """
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        tier=tier,
        google_sheet_id=google_sheet_id,
    )
    db.add(user)
    db.flush()  # Get the ID without committing
    logger.info(f"Created user: telegram_id={telegram_id}, tier={tier}")
    return user


def get_or_create_user(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    admin_user_ids: list[int] = None,
) -> tuple[User, bool]:
    """
    Get existing user or create a new one.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        username: Telegram username
        first_name: User's first name
        last_name: User's last name
        admin_user_ids: List of telegram IDs that should be admin tier
        
    Returns:
        Tuple of (User, created: bool)
    """
    if admin_user_ids is None:
        admin_user_ids = []
    
    user = get_user_by_telegram_id(db, telegram_id)
    
    if user:
        # Update user info if changed
        if username and user.username != username:
            user.username = username
        if first_name and user.first_name != first_name:
            user.first_name = first_name
        if last_name and user.last_name != last_name:
            user.last_name = last_name
        # Auto-upgrade to admin if in admin list but not already admin
        if telegram_id in admin_user_ids and user.tier != "admin":
            user.tier = "admin"
            logger.info(f"Auto-upgraded user {telegram_id} to admin tier")
        return user, False
    
    # Determine tier: admin if in admin list, free otherwise
    tier = "admin" if telegram_id in admin_user_ids else "free"
    
    # Create new user
    user = create_user(
        db,
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        tier=tier,
    )
    return user, True


def update_user_tier(db: Session, telegram_id: int, new_tier: str) -> Optional[User]:
    """
    Update a user's tier.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        new_tier: New tier name (free, silver, gold, platinum, admin)
        
    Returns:
        Updated User object or None if user not found
    """
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        old_tier = user.tier
        user.tier = new_tier
        user.updated_at = datetime.utcnow()
        logger.info(f"Updated user {telegram_id} tier: {old_tier} -> {new_tier}")
        return user
    return None


def update_user_sheet_id(db: Session, telegram_id: int, sheet_id: str) -> Optional[User]:
    """
    Update a user's Google Sheet ID.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        sheet_id: Google Sheet ID
        
    Returns:
        Updated User object or None if user not found
    """
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        user.google_sheet_id = sheet_id
        user.updated_at = datetime.utcnow()
        logger.info(f"Updated user {telegram_id} sheet_id: {sheet_id[:20]}...")
        return user
    return None


def update_user_prompt(db: Session, telegram_id: int, custom_prompt: Optional[str]) -> Optional[User]:
    """
    Update a user's custom AI prompt.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        custom_prompt: Custom prompt text (None to use default)
        
    Returns:
        Updated User object or None if user not found
    """
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        user.custom_prompt = custom_prompt
        user.updated_at = datetime.utcnow()
        logger.info(f"Updated user {telegram_id} custom_prompt: {'set' if custom_prompt else 'cleared'}")
        return user
    return None


def update_user_sheet_columns(db: Session, telegram_id: int, columns: Optional[List[str]]) -> Optional[User]:
    """
    Update a user's custom sheet column order.
    
    Args:
        db: Database session
        telegram_id: User's Telegram ID
        columns: List of column names (None to use default)
        
    Returns:
        Updated User object or None if user not found
    """
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        user.sheet_columns_list = columns  # Uses the property setter
        user.updated_at = datetime.utcnow()
        logger.info(f"Updated user {telegram_id} sheet_columns: {columns}")
        return user
    return None


def get_all_users(db: Session, tier: Optional[str] = None) -> List[User]:
    """
    Get all users, optionally filtered by tier.
    
    Args:
        db: Database session
        tier: Optional tier filter
        
    Returns:
        List of User objects
    """
    query = db.query(User)
    if tier:
        query = query.filter(User.tier == tier)
    return query.order_by(User.created_at.desc()).all()


# ============================================================
# Activity Log Operations
# ============================================================

def log_activity(
    db: Session,
    user_id: int,
    file_type: Literal["image", "pdf", "text"],
    processing_status: Literal["success", "failed", "limit_exceeded"],
    file_size_bytes: Optional[int] = None,
    items_extracted: int = 0,
    error_message: Optional[str] = None,
) -> ActivityLog:
    """
    Log a user activity.
    
    Args:
        db: Database session
        user_id: Database user ID (not Telegram ID)
        file_type: Type of file processed
        processing_status: Result of processing
        file_size_bytes: Size of file in bytes
        items_extracted: Number of items extracted
        error_message: Error message if failed
        
    Returns:
        Created ActivityLog object
    """
    log = ActivityLog(
        user_id=user_id,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        processing_status=processing_status,
        items_extracted=items_extracted,
        error_message=error_message,
    )
    db.add(log)
    db.flush()
    return log


def get_today_usage(db: Session, user_id: int, timezone: str = DEFAULT_TIMEZONE) -> int:
    """
    Get count of successful requests for today (in specified timezone).
    
    Args:
        db: Database session
        user_id: Database user ID
        timezone: Timezone for "today" calculation (default: Asia/Jakarta)
        
    Returns:
        Number of successful requests today
    """
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Convert to UTC for database query
    today_start_utc = today_start.astimezone(pytz.UTC).replace(tzinfo=None)
    
    count = db.query(func.count(ActivityLog.id)).filter(
        and_(
            ActivityLog.user_id == user_id,
            ActivityLog.timestamp >= today_start_utc,
            ActivityLog.processing_status == "success",
        )
    ).scalar()
    
    return count or 0


def check_quota(db: Session, user: User, timezone: str = DEFAULT_TIMEZONE) -> QuotaStatus:
    """
    Check if user can make a request based on their daily quota.
    
    Args:
        db: Database session
        user: User object
        timezone: Timezone for quota reset
        
    Returns:
        QuotaStatus with quota information
    """
    daily_limit = user.daily_limit
    
    # Admin has unlimited access
    if daily_limit == -1:
        return QuotaStatus(
            can_proceed=True,
            used_today=get_today_usage(db, user.id, timezone),
            daily_limit=-1,
            tier=user.tier,
        )
    
    used_today = get_today_usage(db, user.id, timezone)
    can_proceed = used_today < daily_limit
    
    return QuotaStatus(
        can_proceed=can_proceed,
        used_today=used_today,
        daily_limit=daily_limit,
        tier=user.tier,
    )


# ============================================================
# Statistics Operations (Admin)
# ============================================================

def get_stats(db: Session, timezone: str = DEFAULT_TIMEZONE) -> dict:
    """
    Get overall bot statistics for admin dashboard.
    
    Args:
        db: Database session
        timezone: Timezone for date calculations
        
    Returns:
        Dictionary with stats
    """
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start.astimezone(pytz.UTC).replace(tzinfo=None)
    
    # Total users by tier
    tier_counts = dict(
        db.query(User.tier, func.count(User.id))
        .group_by(User.tier)
        .all()
    )
    
    # Today's activity
    today_requests = db.query(func.count(ActivityLog.id)).filter(
        ActivityLog.timestamp >= today_start_utc
    ).scalar() or 0
    
    today_success = db.query(func.count(ActivityLog.id)).filter(
        and_(
            ActivityLog.timestamp >= today_start_utc,
            ActivityLog.processing_status == "success",
        )
    ).scalar() or 0
    
    # Total activity
    total_requests = db.query(func.count(ActivityLog.id)).scalar() or 0
    
    return {
        "total_users": sum(tier_counts.values()),
        "users_by_tier": tier_counts,
        "today_requests": today_requests,
        "today_success": today_success,
        "total_requests": total_requests,
    }


# ============================================================
# Migration Helper
# ============================================================

def migrate_existing_users(db: Session, user_mapping: dict[str, str], admin_user_ids: list[int] = None) -> int:
    """
    Migrate existing users from hardcoded mapping to database.
    
    Args:
        db: Database session
        user_mapping: Dict of {telegram_id: google_sheet_id}
        admin_user_ids: List of telegram IDs that should be admin tier
        
    Returns:
        Number of users migrated
    """
    if admin_user_ids is None:
        admin_user_ids = []
    
    migrated = 0
    
    for telegram_id_str, sheet_id in user_mapping.items():
        telegram_id = int(telegram_id_str)
        
        # Check if already exists
        existing = get_user_by_telegram_id(db, telegram_id)
        if existing:
            logger.info(f"User {telegram_id} already exists, skipping")
            continue
        
        # Determine tier: admin if in admin list, silver otherwise
        tier = "admin" if telegram_id in admin_user_ids else "silver"
        
        create_user(
            db,
            telegram_id=telegram_id,
            tier=tier,
            google_sheet_id=sheet_id,
        )
        migrated += 1
        logger.info(f"Migrated user {telegram_id} as {tier} with sheet {sheet_id[:20]}...")
    
    return migrated
