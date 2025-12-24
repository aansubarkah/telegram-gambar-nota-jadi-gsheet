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
8. **AI Model:** Qwen3 VL 235B A22 Instruct (via Chutes API)

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

## PDF Processing Behavior
- Each page = 1 quota usage
- If user has less quota than pages, bot processes what it can
- Example: 3 quota left + 5 page PDF = processes first 3 pages, warns about skipped 2
- Skipped pages shown in summary with upgrade prompt

## Admin User
- Telegram ID: 33410730
- Sheet: 1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU

## Milestone Status
- ✅ Milestone 1: Database Foundation
- ✅ Milestone 2: Bot Integration  
- ✅ Milestone 3: Admin Features
- 🔄 Milestone 4: Testing & Polish
