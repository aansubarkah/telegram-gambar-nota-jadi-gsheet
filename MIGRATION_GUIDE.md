# Migration Guide: From app_multi_users_qwen.py to app_with_database.py

## Overview

This guide helps you migrate from the hardcoded multi-user bot to the database-backed tier system.

## What's New in app_with_database.py

### Features Added
- ✅ SQLite database for user management
- ✅ Tier-based quota system (free/silver/gold/platinum/admin)
- ✅ Activity logging for all operations
- ✅ Daily quota limits that reset at midnight WIB
- ✅ Auto-registration of new users
- ✅ New user commands: `/usage`, `/mysheet`, `/upgrade`
- ✅ Admin commands: `/settier`, `/setsheet`, `/stats`

### Database Structure
- **users**: Telegram users with tier, Google Sheet ID, and settings
- **activity_logs**: All user activities for quota tracking
- **tiers**: Reference table for tier limits

## Migration Steps

### Step 1: Install Dependencies

Make sure you have SQLAlchemy and pytz installed:

```bash
pip install sqlalchemy pytz
```

### Step 2: Backup Current Setup

Keep your existing bot as backup:

```bash
# The old bot file is already saved as app_multi_users_qwen.py
# No action needed - just keep it!
```

### Step 3: Initialize Database

Run the initialization script:

```bash
python init_database.py
```

This will:
1. Create `data.db` with all tables
2. Seed tier data
3. Migrate users from `LEGACY_USER_MAPPING` in config.py
4. Show current database status

### Step 4: Verify Configuration

Check `config.py` and ensure:

```python
# Admin user IDs
ADMIN_USER_IDS: List[int] = field(default_factory=lambda: [
    33410730,  # Your Telegram ID
])

# Default spreadsheet for free tier
DEFAULT_SPREADSHEET_ID: str = SPREADSHEET_ID

# Legacy user mapping (for migration)
LEGACY_USER_MAPPING = {
    "33410730": "1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU",
}
```

### Step 5: Run the New Bot

```bash
python app_with_database.py
```

### Step 6: Test the Bot

1. **User Commands**:
   - Send `/start` - Should auto-register you
   - Send `/usage` - Check your quota
   - Send `/mysheet` - View your Google Sheet URL
   - Send `/upgrade` - See tier options

2. **Admin Commands** (if you're in ADMIN_USER_IDS):
   - `/settier <user_id> <tier>` - Change user's tier
   - `/setsheet <user_id> <sheet_id>` - Set user's sheet
   - `/stats` - View bot statistics

3. **Send Invoice**:
   - Send an image, PDF, or text with invoice data
   - Should extract data and save to Google Sheets
   - Should show quota usage in response

## Database Management

### View Database

```bash
sqlite3 data.db
.tables
SELECT * FROM users;
SELECT * FROM activity_logs LIMIT 10;
SELECT * FROM tiers;
.quit
```

### Reset Database (WARNING: Deletes all data!)

```python
from database.db import reset_db
reset_db()
```

Or simply delete the file:

```bash
rm data.db
python init_database.py  # Reinitialize
```

## Quota System Behavior

### Free Tier (5/day)
- Shares default Google Sheet
- Quota resets at midnight WIB
- Can upgrade via admin

### Paid Tiers (Silver/Gold/Platinum)
- Get their own Google Sheet ID
- Higher daily limits (50/150/300)
- Admin sets via `/setsheet`

### Admin Tier
- Unlimited requests
- Can access all admin commands

## Common Tasks

### Add a New Paid User

```bash
# 1. User sends /start to bot (auto-registers as free tier)
# 2. Admin changes tier
/settier 123456789 silver

# 3. Admin sets their Google Sheet
/setsheet 123456789 1aBcDeFg1234567890...
```

### Check User Activity

```python
from database.db import get_db
from database.crud import get_user_by_telegram_id, get_today_usage

with get_db() as db:
    user = get_user_by_telegram_id(db, 123456789)
    usage = get_today_usage(db, user.id)
    print(f"User {user.telegram_id} used {usage} requests today")
```

### View All Users

```bash
/stats  # As admin in bot

# Or in Python:
from database.db import get_db
from database.crud import get_all_users

with get_db() as db:
    users = get_all_users(db)
    for user in users:
        print(f"{user.telegram_id} | {user.tier} | Sheet: {user.google_sheet_id or 'default'}")
```

## Rollback Plan

If you need to rollback to the old bot:

```bash
# Stop the new bot (Ctrl+C)

# Run the old bot
python app_multi_users_qwen.py
```

The old bot will work independently - database won't affect it.

## Differences from Old Bot

| Feature | Old (app_multi_users_qwen.py) | New (app_with_database.py) |
|---------|-------------------------------|---------------------------|
| User Storage | Hardcoded dict | SQLite database |
| Quota System | None | Tier-based daily limits |
| Activity Logs | None | Full activity tracking |
| Auto-registration | No | Yes (on /start) |
| Admin Commands | None | /settier, /setsheet, /stats |
| User Commands | Basic | Added /usage, /mysheet, /upgrade |

## Troubleshooting

### Database locked error
- Close any SQLite viewers
- Only one bot instance should run

### User not found for admin commands
- User must send /start first
- Check Telegram ID is correct

### Quota not resetting
- Check server timezone setting
- Default: Asia/Jakarta (WIB)
- Configure in config.py: `TIMEZONE`

### Migration didn't work
- Check LEGACY_USER_MAPPING in config.py
- Run `python init_database.py` again
- Check logs for errors

## Support

For issues:
1. Check logs in terminal
2. Verify database with `python init_database.py`
3. Check config.py settings
4. Review TASKS.md and PLANNING.md
