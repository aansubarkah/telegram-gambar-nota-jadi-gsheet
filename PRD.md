# Project Requirement Document (PRD)

## Project Overview

**Project Name:** Telegram Invoice-to-GSheets Bot  
**Version:** 2.0 (with tier system)  
**Last Updated:** December 24, 2024

### Description
A Telegram bot that extracts invoice/receipt data from images, PDFs, and text messages using Vision AI (Qwen/Qwen3-VL-235B-A22B-Instruct via Chutes API), then saves the structured data to Google Sheets. The bot supports multiple user tiers with daily usage limits and per-user Google Sheet assignments.

---

## Functional Requirements

### FR-1: User Tier System

| Tier | Daily Limit | Google Sheet | Bulk Mode | Price |
|------|-------------|--------------|-----------|-------|
| Free | 5 images/day | Default shared sheet | ❌ | Free |
| Silver | 50 images/day | User's own sheet | ❌ | TBD |
| Gold | 150 images/day | User's own sheet | ❌ | TBD |
| Platinum | 300 images/day | User's own sheet | ✅ | TBD |
| Admin | Unlimited | Any sheet | ✅ | N/A |

**Requirements:**
- FR-1.1: New users automatically registered as "free" tier
- FR-1.2: System must check remaining quota before processing each request
- FR-1.3: Daily limits reset at midnight WIB (UTC+7)
- FR-1.4: Users must receive clear feedback when quota is exceeded
- FR-1.5: Paid tiers (Silver+) must have their own Google Sheet ID stored in database

### FR-2: Database & User Management

**Requirements:**
- FR-2.1: Use SQLite database for storing user data and activity logs
- FR-2.2: Store for each user: telegram_id, username, first_name, tier, google_sheet_id, created_at, updated_at
- FR-2.3: Never store original files/images - only metadata (file_type, file_size_bytes, timestamp)
- FR-2.4: Log every activity: timestamp, user_id, file_type (image/pdf/text), file_size, processing_status, items_extracted, error_message
- FR-2.5: Admin users identified by Telegram ID list in config (simple approach for MVP)

### FR-3: Bot Commands

| Command | Description | Access |
|---------|-------------|--------|
| `/start` | Welcome message + auto-register user | All |
| `/help` | Show help information | All |
| `/status` | Check bot status | All |
| `/checkid` | Show user's Telegram ID | All |
| `/usage` | Show today's usage vs daily limit | All |
| `/mysheet` | Show linked Google Sheet URL | Paid tiers |
| `/upgrade` | Show tier upgrade options | All |
| `/startbulk` | Start bulk processing mode | Platinum+ |
| `/endbulk` | End bulk mode & download CSV/Excel | Platinum+ |
| `/settier <user_id> <tier>` | Change user's tier | Admin only |
| `/setsheet <user_id> <sheet_id>` | Set user's Google Sheet ID | Admin only |
| `/stats` | Show overall bot statistics | Admin only |

### FR-4: Media Processing

**Requirements:**
- FR-4.1: Accept images (PNG, JPG, JPEG, WEBP, HEIC, HEIF)
- FR-4.2: Accept PDF documents (process each page as image)
- FR-4.3: Accept text messages containing invoice data
- FR-4.4: Extract structured data: waktu, penjual, barang, harga, jumlah, service, pajak, ppn, subtotal
- FR-4.5: Append extracted data to user's assigned Google Sheet
- FR-4.6: Count each processed file against user's daily quota (PDF counts as 1 regardless of pages)

### FR-5: Google Sheets Integration

**Requirements:**
- FR-5.1: Free tier users use the default shared Google Sheet (`DEFAULT_SPREADSHEET_ID` in config)
- FR-5.2: Paid tier users have their own Google Sheet (stored in `google_sheet_id` column in database)
- FR-5.3: Lookup logic: If user's `google_sheet_id` is set → use it; else → use default
- FR-5.4: Default sheet headers: waktu, penjual, barang, harga, jumlah, service, pajak, ppn, subtotal, User ID, Unix Timestamp
- FR-5.5: Auto-create headers if sheet is empty
- FR-5.6: Paid tier users can have custom column order/structure (stored as JSON in database)

### FR-6: Custom Prompts Per User

**Requirements:**
- FR-6.1: Each user can have a custom AI prompt for data extraction
- FR-6.2: Custom prompts stored in database (nullable, falls back to default)
- FR-6.3: Custom prompts define which fields to extract and their order
- FR-6.4: Admin can set/update user's custom prompt via command
- FR-6.5: Custom sheet structure must match custom prompt output fields

### FR-7: Bulk Processing Mode (Platinum+)

**Requirements:**
- FR-7.1: Platinum and Admin tiers can use bulk processing mode
- FR-7.2: `/startbulk` command starts a bulk session, creating a CSV file
- FR-7.3: In bulk mode, data appends to CSV instead of Google Sheets
- FR-7.4: `/endbulk` command ends session, converts CSV to Excel, sends both files
- FR-7.5: Quota still applies in bulk mode (1 per image, 1 per PDF page)
- FR-7.6: CSV stored temporarily as `uploads/bulk_{telegram_id}.csv`
- FR-7.7: Files are cleaned up after sending to user
- FR-7.8: Session state tracks items count and requests count

---

## Non-Functional Requirements

### NFR-1: Architecture

- NFR-1.1: Modular code structure with clear separation of concerns
- NFR-1.2: Database layer using SQLAlchemy ORM for future migration flexibility
- NFR-1.3: Configuration centralized in single config file
- NFR-1.4: All sensitive credentials in environment variables or separate credentials file (gitignored)

### NFR-2: Performance

- NFR-2.1: Database queries should be optimized with proper indexes
- NFR-2.2: API timeout handling for Vision AI requests (60s connect, 120s read)
- NFR-2.3: Graceful error handling with user-friendly messages

### NFR-3: Security

- NFR-3.1: Never store original files/images
- NFR-3.2: Credentials files must be gitignored
- NFR-3.3: Admin commands restricted to admin user IDs only

### NFR-4: Maintainability

- NFR-4.1: Clean, well-documented code
- NFR-4.2: Logging for all important operations
- NFR-4.3: Type hints where beneficial

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Bot Framework | python-telegram-bot |
| Database | SQLite + SQLAlchemy ORM |
| Vision AI | Chutes API (Qwen3 VL 235B A22 Instruct) |
| Google Sheets | gspread + google-oauth2 |
| PDF Processing | PyMuPDF (fitz) |
| Image Processing | Pillow |
| Future Dashboard | FastAPI + Jinja2 (Phase 2) |

---

## Project Structure

```
telegram-gambar-nota-jadi-gsheet/
├── bot/
│   ├── __init__.py
│   ├── app.py              # Main bot class
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py     # Command handlers
│   │   └── media.py        # Photo/PDF/text handlers
│   └── services/
│       ├── __init__.py
│       ├── ai_processor.py # Image-to-data conversion
│       └── sheets.py       # Google Sheets operations
├── database/
│   ├── __init__.py
│   ├── models.py           # SQLAlchemy models
│   ├── db.py               # Database connection
│   └── crud.py             # CRUD operations
├── config.py               # Centralized configuration
├── main.py                 # Entry point
├── data.db                 # SQLite database (gitignored)
├── credentials.json        # Google credentials (gitignored)
├── requirements.txt
├── PRD.md
├── PLANNING.md
├── TASKS.md
└── SCRATCHPAD.md
```

---

## Database Schema

### Table: users
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT |
| telegram_id | INTEGER | UNIQUE, NOT NULL |
| username | TEXT | NULLABLE |
| first_name | TEXT | NULLABLE |
| last_name | TEXT | NULLABLE |
| tier | TEXT | NOT NULL, DEFAULT 'free' |
| daily_limit | INTEGER | NOT NULL, DEFAULT 5 |
| google_sheet_id | TEXT | NULLABLE |
| custom_prompt | TEXT | NULLABLE (user's custom AI prompt) |
| sheet_columns | TEXT | NULLABLE (JSON array of column names) |
| created_at | DATETIME | NOT NULL, DEFAULT NOW |
| updated_at | DATETIME | NOT NULL, DEFAULT NOW |

### Table: activity_logs
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT |
| user_id | INTEGER | FOREIGN KEY → users.id |
| timestamp | DATETIME | NOT NULL, DEFAULT NOW |
| file_type | TEXT | NOT NULL (image/pdf/text) |
| file_size_bytes | INTEGER | NULLABLE |
| processing_status | TEXT | NOT NULL (success/failed/limit_exceeded) |
| items_extracted | INTEGER | DEFAULT 0 |
| error_message | TEXT | NULLABLE |

### Table: tiers (Reference Table)
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | UNIQUE, NOT NULL |
| daily_limit | INTEGER | NOT NULL |
| price_monthly | INTEGER | DEFAULT 0 |

**Initial Data:**
```sql
INSERT INTO tiers VALUES (1, 'free', 5, 0);
INSERT INTO tiers VALUES (2, 'silver', 50, 0);
INSERT INTO tiers VALUES (3, 'gold', 150, 0);
INSERT INTO tiers VALUES (4, 'platinum', 300, 0);
INSERT INTO tiers VALUES (5, 'admin', -1, 0);  -- -1 = unlimited
```

---

## Out of Scope (Future Phases)

- Payment integration (Midtrans)
- Web dashboard for monitoring
- Multi-language support
- Webhook mode (currently using polling)
- User self-service tier management

---

## Success Criteria

1. ✅ Users can process images/PDFs/text and see data in Google Sheets
2. ✅ Free users are limited to 5 requests per day
3. ✅ Paid users get their assigned Google Sheet
4. ✅ Admin can manage user tiers via commands
5. ✅ All activity is logged without storing original files
6. ✅ Daily limits reset correctly at midnight WIB
