"""
Initialize the database for the Telegram Invoice Bot.

This script:
1. Creates the database and tables
2. Seeds tier data
3. Migrates legacy users
4. Shows current database status
"""

import logging
from database.db import init_db, get_db
from database.crud import migrate_existing_users, get_all_users, get_stats
from database.models import Tier
from config import LEGACY_USER_MAPPING, config

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Initialize database and show status"""

    print("=" * 60)
    print("  Telegram Invoice Bot - Database Initialization")
    print("=" * 60)
    print()

    # Step 1: Initialize database
    print("📦 Step 1: Initializing database...")
    init_db()
    print("✅ Database initialized successfully!")
    print()

    # Step 2: Check tiers
    print("📊 Step 2: Checking tiers...")
    with get_db() as db:
        tiers = db.query(Tier).all()
        print(f"✅ Found {len(tiers)} tiers:")
        for tier in tiers:
            limit_str = "∞" if tier.daily_limit == -1 else str(tier.daily_limit)
            print(f"   • {tier.name.upper()}: {limit_str} requests/day")
    print()

    # Step 3: Migrate legacy users
    if LEGACY_USER_MAPPING:
        print("👥 Step 3: Migrating legacy users...")
        with get_db() as db:
            migrated_count = migrate_existing_users(db, LEGACY_USER_MAPPING)
            db.commit()
        print(f"✅ Migrated {migrated_count} legacy users")
    else:
        print("👥 Step 3: No legacy users to migrate")
    print()

    # Step 4: Show current users
    print("📋 Step 4: Current users in database:")
    with get_db() as db:
        users = get_all_users(db)
        if users:
            for user in users:
                sheet_status = "✅ Own sheet" if user.google_sheet_id else "🔗 Shared sheet"
                print(f"   • ID {user.telegram_id} | Tier: {user.tier.upper()} | {sheet_status}")
        else:
            print("   (No users yet - users will be auto-registered on first /start)")
    print()

    # Step 5: Show statistics
    print("📈 Step 5: Bot Statistics:")
    with get_db() as db:
        stats = get_stats(db, config.TIMEZONE)
        print(f"   • Total users: {stats['total_users']}")
        print(f"   • Total requests: {stats['total_requests']}")
        print(f"   • Today's requests: {stats['today_requests']}")
        print(f"   • Today's successful: {stats['today_success']}")
    print()

    print("=" * 60)
    print("  ✅ Database initialization complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Run the bot: python app_with_database.py")
    print("2. Send /start to the bot to register as a user")
    print("3. Admins can use /settier, /setsheet, /stats commands")
    print()


if __name__ == "__main__":
    main()
