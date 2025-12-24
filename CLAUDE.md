# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Telegram bot that extracts invoice/receipt data from images, PDFs, and text messages using Vision AI (Qwen/Qwen3-VL-235B-A22B-Instruct via Chutes API), then saves the structured data to Google Sheets. The project is transitioning from a simple multi-user system to a tier-based subscription model with daily usage limits.

## Running the Bot

### Current Active Bot
```bash
python app_multi_users_qwen.py
```

### Testing Text Parsing
```bash
python test_text_parsing.py
python simple_text_test.py
```

## Key Architecture Components

### Bot Versions (Evolution)
- `app.py` - Original single-user version
- `app_excelid.py` - ExcelID integration version
- `app_multi_users.py` - Multi-user support (older)
- `app_multi_users_qwen.py` - **Current production version** using Chutes API with Qwen/Qwen3-VL-235B-A22B-Instruct model

### Configuration Files
- `credentials.py` - Centralized credentials (gitignored)
  - Required: `TELEGRAM_BOT_TOKEN`, `GOOGLE_CREDENTIALS_FILE`, `SPREADSHEET_ID`, `CHUTES_API_KEY`
  - Optional: `SPREADSHEET_ID_RIZAL` for specific users
- `credentials.json` - Google service account credentials (gitignored)
- `prompts.py` - AI prompts for invoice extraction
  - `DEFAULT_PROMPT` - For image/PDF processing
  - `TEXT_PROMPT` - For text message processing with special handling for multiple items

### Core Processing Flow

1. **User sends media** → Telegram bot receives update
2. **File download** → Saved to `uploads/` directory (temporary)
3. **AI Processing**:
   - Images: Direct base64 encoding → Chutes API
   - PDFs: Each page converted to PNG → base64 → Chutes API
   - Text: Sent with TEXT_PROMPT → Chutes API
4. **JSON Extraction**: Response parsed to extract structured data
5. **Google Sheets**: Data appended with User ID and Unix Timestamp
6. **Cleanup**: Temporary files deleted

### Data Structure (Invoice Fields)
Each extracted invoice item contains:
- `waktu` - Transaction datetime (format: %d/%m/%Y %H:%M:%S)
- `penjual` - Seller name
- `barang` - Item name
- `harga` - Unit price
- `jumlah` - Quantity
- `service` - Service charge
- `pajak` - Tax
- `ppn` - VAT (PPN)
- `subtotal` - Total amount (harga × jumlah)

Plus metadata:
- User ID (Telegram user ID as string)
- Unix Timestamp (epoch time)

### Multi-User System
Current implementation (hardcoded):
```python
self.IDS_SPREADSHEETS = {
    '33410730': '1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU'
}
```

**Planned migration**: Move to SQLite database with tier system (see TASKS.md and PRD.md)

## Development Workflow

### Planned Refactoring (See PLANNING.md and TASKS.md)
The codebase is being restructured to support a tier-based system:

1. **Database Layer** (`database/`):
   - `models.py` - SQLAlchemy models (User, ActivityLog, Tier)
   - `db.py` - Database connection and initialization
   - `crud.py` - CRUD operations for users and activity logs

2. **Bot Layer** (`bot/`):
   - `handlers/commands.py` - Command handlers (/start, /usage, /settier, etc.)
   - `handlers/media.py` - Photo/PDF/text processing handlers
   - `services/ai_processor.py` - AI integration (Chutes API)
   - `services/sheets.py` - Google Sheets operations

3. **Configuration** (`config.py`):
   - Centralized Config class with tier limits and admin settings

### Tier System (Planned)
- **Free**: 5 requests/day, shared Google Sheet
- **Silver**: 50 requests/day, personal Google Sheet
- **Gold**: 150 requests/day, personal Google Sheet
- **Platinum**: 300 requests/day, personal Google Sheet
- **Admin**: Unlimited, any Google Sheet

Daily limits reset at midnight WIB (Asia/Jakarta timezone).

## Important Implementation Details

### AI Response Parsing
The bot includes robust JSON extraction logic to handle:
- Markdown code blocks (```json ... ```)
- Leading emojis or non-JSON characters
- Single objects that should be wrapped in arrays
- Trailing commas in JSON
- Both single-item and multi-item responses

### PDF Processing
- Each PDF page is converted to PNG at 2x zoom (for quality)
- All pages are processed sequentially
- Results from all pages are combined into a single dataset
- PDF counts as 1 request regardless of page count (planned quota system)

### Text Message Processing
Special handling for messages with multiple line items:
- Each line starting with "-" or bullet point = separate item
- Supports shorthand (e.g., "1.125k" = 1,125,000)
- Ignores "total" summary lines

### Google Sheets Integration
- Uses service account authentication (`gspread` library)
- Automatically creates headers if sheet is empty
- Appends data row by row (not batch)
- Service account email must have Editor access to target sheets

### Error Handling
- API timeout: 60s connect, 120s read (vision models are slow)
- Graceful handling of malformed AI responses
- Logging at INFO level for all operations
- Cleanup of temporary files even on error

## Migration Strategy

When implementing the database-backed tier system:
1. Keep `app_multi_users_qwen.py` as backup
2. Build new modular structure alongside existing code
3. Test thoroughly with SQLite database
4. Migrate existing users from `IDS_SPREADSHEETS` to database
5. Switch entry point when ready

## Testing Considerations

### Edge Cases to Test
- New user first interaction (auto-registration)
- Exactly at quota limit
- Just after midnight reset (timezone-aware)
- Invalid/corrupted images or PDFs
- AI API timeout scenarios
- Google Sheets permission errors
- Multiple items in single image/text
- Messages with non-standard date formats

### Service Account Setup
All Google Sheets must grant Editor access to:
- `telegram-bot-vps@gen-lang-client-0172843846.iam.gserviceaccount.com`
- `telegram-gsheets-gemini@gen-lang-client-0172843846.iam.gserviceaccount.com`

## Current Project State

**Status**: Transitioning from simple multi-user bot to tier-based subscription system

**Active Files**:
- Production: `app_multi_users_qwen.py`
- Configuration: `credentials.py`, `prompts.py`
- Planning: `PRD.md`, `PLANNING.md`, `TASKS.md`, `SCRATCHPAD.md`

**Next Steps**: See TASKS.md Milestone 1 (Database Foundation)
