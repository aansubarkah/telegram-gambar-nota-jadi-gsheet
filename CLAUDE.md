# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Telegram bot that extracts invoice/receipt data from images, PDFs, and text messages using Vision AI (Moonshotai/Kimi-K2.6 via NanoGPT API, with fallback models), then saves the structured data to Google Sheets. The bot runs on a VPS with a tier-based subscription model backed by SQLite database with daily usage limits.

## Running the Bot

### Current Active Bot (VPS)
```bash
python app_with_database.py
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
- `app_multi_users_qwen.py` - Legacy production version (Chutes API + Qwen3-VL-235B)
- `app_with_database.py` - **Current production version** (NanoGPT API + Kimi-K2.6, SQLite database, tier system)

### Configuration Files
- `credentials.py` - Centralized credentials (gitignored)
  - Required: `TELEGRAM_BOT_TOKEN`, `GOOGLE_CREDENTIALS_FILE`, `SPREADSHEET_ID`, `NANOGPT_API_KEY`
  - Optional: `CHUTES_API_KEY` (legacy), `SPREADSHEET_ID_RIZAL` for specific users
- `config.py` - Centralized Config dataclass (tier limits, AI model, timeouts, file settings)
- `credentials.json` / `credentials_vps.json` - Google service account credentials (gitignored)
- `prompts.py` - AI prompts for invoice extraction
  - `DEFAULT_PROMPT` - For image/PDF processing
  - `TEXT_PROMPT` - For text message processing with special handling for multiple items
- `init_database.py` - Database initialization script (creates tables)

### Core Processing Flow

1. **User sends media** → Telegram bot receives update
2. **File download** → Saved to `uploads/` directory (temporary)
3. **AI Processing** (NanoGPT API with retry + fallback):
   - Images: Direct base64 encoding → NanoGPT API
   - PDFs: Each page converted to PNG → base64 → NanoGPT API
   - Text: Sent with TEXT_PROMPT → NanoGPT API
4. **JSON Extraction**: Response parsed to extract structured data
5. **Google Sheets**: Data appended with User ID and Unix Timestamp
6. **Database**: Activity logged for quota tracking (tier-based daily limits)
7. **Cleanup**: Temporary files deleted

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

### Tier System (Implemented in app_with_database.py)
- **Free**: 5 requests/day, shared Google Sheet
- **Silver**: 50 requests/day, personal Google Sheet
- **Gold**: 150 requests/day, personal Google Sheet
- **Platinum**: 300 requests/day, personal Google Sheet
- **Admin**: Unlimited, any Google Sheet

Daily limits reset at midnight WIB (Asia/Jakarta timezone).

Admin users (hardcoded in `config.py`): `33410730`, `6931060098`

### AI Model Configuration (config.py)
- **Primary**: `moonshotai/kimi-k2.6` (via NanoGPT API)
- **Fallbacks** (tried in order on 503/500/429):
  1. `google/gemma-4-31b-it`
  2. `xiaomi/mimo-v2.5`
  3. `stepfun/step-3.7-flash:thinking`
  4. `qwen3-vl-235b-a22b-instruct-original`
  5. `zai-org/glm-4.6v`
  6. `qwen25-vl-72b-instruct`
  7. `Qwen/Qwen3-VL-235B-A22B-Instruct`
  8. `qwen3-vl-235b-a22b-thinking`
- **API endpoint**: `https://nano-gpt.com/api/v1/chat/completions`
- **Timeout**: 60s connect, 120s read
- **Temperature**: 0.1, **Max tokens**: 10000

### Database (SQLite)
- Path: `data.db` (in project root)
- Tables: User, ActivityLog, Tier
- Managed via SQLAlchemy ORM
- Initialized via `init_database.py`

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
- PDF counts as 1 request regardless of page count

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
- Retry with exponential backoff on 503/500/429 errors
- Automatic model fallback chain (up to 9 models)
- Graceful handling of malformed AI responses
- Logging at INFO level for all operations
- Cleanup of temporary files even on error

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
- Model fallback chain exhaustion

### Service Account Setup
All Google Sheets must grant Editor access to:
- `telegram-bot-vps@gen-lang-client-0172843846.iam.gserviceaccount.com`
- `telegram-gsheets-gemini@gen-lang-client-0172843846.iam.gserviceaccount.com`

## Current Project State

**Status**: Tier-based subscription system with SQLite database is live on VPS

**Active Files**:
- Production (VPS): `app_with_database.py`
- Configuration: `config.py`, `credentials.py`, `prompts.py`
- Database: `init_database.py`, `data.db`
- Legacy: `app_multi_users_qwen.py` (backup)
- Planning: `PRD.md`, `PLANNING.md`, `TASKS.md`, `SCRATCHPAD.md`, `MIGRATION_GUIDE.md`
