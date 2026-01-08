---
applyTo: '**'
---

# Project Memory: Telegram Invoice-to-GSheets Bot

## Project Context
- **Purpose:** Telegram bot that extracts invoice data from images/PDFs/text using Vision AI and saves to Google Sheets
- **Current State:** `app_with_database.py` - fully integrated with tier system
- **Target:** 1 prospect client initially, scalable to more

## Key Decisions Made (Dec 24, 2024)
1. **Database:** SQLite with SQLAlchemy ORM (data.db)
2. **Admin identification:** Config-based (ADMIN_USER_IDS list), auto-assigns admin tier
3. **New user registration:** Auto-register as "free" tier (admin if in ADMIN_USER_IDS)
4. **Daily reset timezone:** Midnight WIB (Asia/Jakarta)
5. **PDF quota:** Each page counts as 1 request (changed Dec 24)
6. **Custom prompts:** Each user can have custom AI prompt (stored in DB)
7. **Custom sheet columns:** Each user can have custom column order (JSON)
8. **AI Provider:** NanoGPT (https://nano-gpt.com/api/v1/chat/completions)
9. **AI Model:** gpt-4o (vision-capable)

## Tier System
| Tier | Daily Limit |
|------|-------------|
| free | 5 |
| silver | 50 |
| gold | 150 |
| platinum | 300 |
| admin | unlimited |

## Key Files
- `app_with_database.py` - Main bot with database integration (~1400 lines)
- `database/models.py` - SQLAlchemy models (User, ActivityLog, Tier)
- `database/crud.py` - CRUD operations with admin auto-assignment
- `database/db.py` - Database engine and session management
- `config.py` - Centralized config with ADMIN_USER_IDS
- `credentials.py` - API keys and secrets
- `prompts.py` - AI prompts for data extraction

## Recent Changes (Dec 24, 2024)
- ✅ Implemented per-page PDF processing
- ✅ Each PDF page = 1 quota usage
- ✅ Partial PDF processing: processes as many pages as quota allows
- ✅ Admin auto-upgrade on login via `get_or_create_user()`
- ✅ Fixed admin ID 33410730 tier assignment

## Recent Changes (Dec 26, 2024)
- ✅ Added bulk processing feature for Platinum tier
- ✅ New commands: /startbulk, /endbulk
- ✅ Bulk mode saves to CSV instead of Google Sheets
- ✅ Exports both CSV and Excel files on /endbulk
- ✅ Quota still applies in bulk mode (1 per image/page)
- ✅ Added pandas and openpyxl to requirements-bot.txt

## Bulk Processing Feature (Platinum+)
- /startbulk: Starts bulk session, creates CSV file
- User uploads images/PDFs/text as normal
- Data appends to CSV (not Google Sheets)
- /endbulk: Converts CSV to Excel, sends both files, cleans up
- Quota counter still applies (1 per image, 1 per PDF page)
- CSV stored as: uploads/bulk_{telegram_id}.csv

## PDF Processing Behavior
- Each page = 1 quota usage
- If user has less quota than pages, bot processes what it can
- Example: 3 quota left + 5 page PDF = processes first 3 pages, warns about skipped 2
- Skipped pages shown in summary with upgrade prompt

## Admin User
- Telegram ID: 33410730
- Sheet: 1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU

## Recent Changes (Dec 26, 2024 - Batch #2)
- ✅ Optimized Google Sheets API calls to avoid rate limits
- ✅ Changed individual `append_row()` calls to batch `append_rows()` 
- ✅ All 3 handlers now batch write: text, PDF, image
- ✅ Single API call per invoice processing (was N calls for N items)

## Recent Changes (Jan 8, 2026)
- ✅ Added session-based image buffering to `app_excelid.py`
- ✅ Multi-image Q&A: Users can send multiple images, then ask questions
- ✅ Follow-up support: Same images can be queried multiple times
- ✅ Conversation history preserved for context in follow-ups
- ✅ New commands: /status, /clear for session management
- ✅ Group vs DM behavior: Silent buffering in groups, @mention to trigger

## Session-Based Image Q&A (app_excelid.py)
**Flow:**
1. User sends images → buffered (silent in groups, acknowledged in DM)
2. User sends text question → processes all buffered images
3. Follow-up questions use same images + conversation history
4. Sending NEW image → clears old session, starts fresh
5. Session expires after 30 min inactivity

**Trigger Mechanism:**
| Context | Trigger |
|---------|---------|
| Group | @mention bot |
| Direct | Any text message |

**Commands:**
- `/status` - Shows buffered images count, history count
- `/clear` - Clears session manually

**Config:**
- SESSION_TIMEOUT_MINUTES = 30
- MAX_IMAGES_PER_SESSION = 10
- MAX_HISTORY_PAIRS = 10

## Milestone Status
- ✅ Milestone 1: Database Foundation
- ✅ Milestone 2: Bot Integration  
- ✅ Milestone 3: Admin Features
- 🔄 Milestone 4: Testing & Polish
