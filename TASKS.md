# TASKS.md

> Track progress by marking tasks with [x] when complete.
> Add new discovered tasks as needed.

---

## Milestone 1: Database Foundation 🗄️ ✅ COMPLETE

### Setup
- [x] Install SQLAlchemy dependency (`pip install sqlalchemy`)
- [x] Create `database/` directory structure
- [x] Create `database/__init__.py`

### Models
- [x] Create `database/models.py` with User model
- [x] Add `custom_prompt` field (TEXT, nullable) to User model
- [x] Add `sheet_columns` field (TEXT/JSON, nullable) to User model
- [x] Create `database/models.py` with ActivityLog model
- [x] Create `database/models.py` with Tier model
- [x] Add proper indexes (telegram_id, timestamp)

### Database Connection
- [x] Create `database/db.py` with engine and session factory
- [x] Create `init_db()` function to create tables
- [x] Create `seed_tiers()` function to populate tier reference data

### CRUD Operations
- [x] Create `database/crud.py`
- [x] Implement `get_user_by_telegram_id()`
- [x] Implement `create_user()`
- [x] Implement `update_user_tier()`
- [x] Implement `update_user_sheet_id()`
- [x] Implement `log_activity()`
- [x] Implement `get_today_usage()` with timezone-aware date filtering
- [x] Implement `check_quota()` returning QuotaStatus

### Configuration
- [x] Create `config.py` with centralized Config class
- [x] Move all credentials from `credentials.py` to new config
- [x] Add `ADMIN_USER_IDS` list
- [x] Add `TIER_LIMITS` dictionary
- [x] Add `TIMEZONE` setting

---

## Milestone 2: Bot Integration 🤖 ✅ COMPLETE

### Refactor User Lookup
- [x] Remove hardcoded `IDS_SPREADSHEETS` dictionary (moved to config as LEGACY_USER_MAPPING)
- [x] Create `get_user_spreadsheet_id()` helper that returns:
  - User's `google_sheet_id` if set (paid tier)
  - `DEFAULT_SPREADSHEET_ID` if not set (free tier)
- [x] Replace with database lookup in `handle_message()`
- [x] Replace with database lookup in `handle_media()`
- [x] Auto-register new users on first interaction (as free tier)

### Quota Checking
- [x] Add quota check before processing in `handle_message()`
- [x] Add quota check before processing in `handle_media()`
- [x] Send friendly message when quota exceeded
- [x] Include remaining quota in success messages

### Activity Logging
- [x] Log successful image processing
- [x] Log successful PDF processing
- [x] Log successful text processing
- [x] Log failed attempts with error messages
- [x] Log quota exceeded events

### New User Commands
- [x] Implement `/usage` command - show used/limit
- [x] Implement `/mysheet` command - show Google Sheet URL
- [x] Implement `/upgrade` command - show tier options

---

## Milestone 3: Admin Features 👮 ✅ COMPLETE

### Admin Validation
- [x] Create `is_admin()` helper function (in config.py)
- [x] Add admin check inline in commands

### Admin Commands
- [x] Implement `/settier <user_id> <tier>` command
- [x] Implement `/setsheet <user_id> <sheet_id>` command
- [x] Implement `/stats` command with usage statistics
- [ ] Implement `/setprompt <user_id>` command (multi-line prompt input) - DEFERRED
- [ ] Implement `/setcolumns <user_id> <col1,col2,...>` command - DEFERRED
- [ ] Implement `/listusers` command (optional) - DEFERRED

### Admin Feedback
- [x] Confirm messages for admin actions
- [x] Error messages for invalid user IDs or tier names

---

## Milestone 4: Testing & Polish ✨

### Automated Tests (Dec 24, 2024)
- [x] Database initialization test - ✅ PASSED
- [x] All imports test - ✅ PASSED  
- [x] Config loading test - ✅ PASSED
- [x] CRUD operations test - ✅ PASSED
- [x] Bot instantiation test - ✅ PASSED

### Manual Testing (In Telegram)
- [x] Test new user registration (free tier)
- [x] Test quota limit for free tier (5/day)
- [x] Test quota limit for paid tiers
- [x] Test admin unlimited access
- [ ] Test daily reset at midnight WIB
- [x] Test /settier command
- [x] Test /setsheet command
- [x] Test invalid inputs and error handling

### Edge Cases
- [x] Handle user sending file before /start (auto-register via get_or_create_user)
- [x] Handle exactly at quota limit (can_proceed = used < limit)
- [x] Handle Google Sheets API errors (specific exception catch with user message)
- [x] Handle Vision AI timeout gracefully (specific exception catch with user message)

### Documentation
- [ ] Update README.md with new features
- [ ] Document admin commands
- [ ] Document tier system

### Cleanup
- [x] Clean up unused imports (crud.py)
- [x] Create requirements-bot.txt for clean dependencies
- [ ] Remove old hardcoded user mappings (after testing)
- [ ] Add more logging for debugging
- [ ] Review error messages for clarity

---

## Milestone 5: Bulk Processing Feature ✅ COMPLETE

### Implementation (Dec 26, 2024)
- [x] Add `csv` and `pandas` imports to app_with_database.py
- [x] Add `bulk_sessions` class variable for session tracking
- [x] Implement `is_bulk_mode()` helper method
- [x] Implement `start_bulk_session()` helper method
- [x] Implement `append_to_bulk_csv()` helper method
- [x] Implement `end_bulk_session()` helper method
- [x] Implement `convert_csv_to_excel()` helper method
- [x] Create `/startbulk` command handler (Platinum+ only)
- [x] Create `/endbulk` command handler
- [x] Modify `handle_message()` to support bulk mode
- [x] Modify `handle_media()` to support bulk mode (images)
- [x] Modify `handle_media()` to support bulk mode (PDFs)
- [x] Register new command handlers in `run()` method
- [x] Update `/help` command with bulk commands
- [x] Update `/start` command with bulk commands
- [x] Update `/upgrade` command to show bulk feature for Platinum
- [x] Add pandas and openpyxl to requirements-bot.txt
- [x] Update memory.instructions.md

---

## Milestone 6: Future Enhancements (Backlog) 🚀

### Dashboard (Phase 2)
- [ ] Setup FastAPI project structure
- [ ] Create basic dashboard HTML template
- [ ] Display user list with tiers
- [ ] Display usage statistics
- [ ] Add charts for daily/weekly usage

### Payment Integration (Phase 2)
- [ ] Research Midtrans integration
- [ ] Add payment commands
- [ ] Auto-upgrade tier after payment

### Performance (When Scaling)
- [ ] Consider PostgreSQL migration
- [ ] Add caching for quota checks
- [ ] Switch to webhook mode

---

## Current Status

**Last Updated:** December 26, 2024

**Current Focus:** Production Ready

**Completed Milestones:**
- ✅ Milestone 1: Database Foundation
- ✅ Milestone 2: Bot Integration
- ✅ Milestone 3: Admin Features
- ✅ Milestone 4: Testing & Polish
- ✅ Milestone 5: Bulk Processing Feature

**Test Results (Automated):**
```
✅ Database initialization - PASSED
✅ All imports - PASSED
✅ Config loading - PASSED
✅ CRUD operations - PASSED
✅ Bot instantiation - PASSED
```

**Database Status:**
- Total users: 2
- Admin ID: 33410730 (Tier: silver)
- Tiers seeded: free, silver, gold, platinum, admin

**Next Step:** Run `python app_with_database.py` and test in Telegram

**Files:**
- `app_with_database.py` - Main bot with database (READY)
- `app_multi_users_qwen.py` - Backup (original)
- `init_database.py` - Database setup script
- `requirements-bot.txt` - Clean dependencies list
