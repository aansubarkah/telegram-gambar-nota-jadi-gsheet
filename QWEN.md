# Telegram Gambar Nota Jadi GSheet Project Context

## Project Overview

A Telegram bot that extracts invoice/receipt data from images, PDFs, and text messages using Vision AI (Moonshotai/Kimi-K2.6 via NanoGPT API), then saves structured data to Google Sheets. Backed by SQLite database with a tier-based subscription model and daily usage limits. Runs on a VPS.

### Key Technologies

* **Python**: Core programming language
* **python-telegram-bot**: Telegram bot framework
* **gspread**: Google Sheets integration
* **httpx**: HTTP client for NanoGPT API calls (with retry + fallback)
* **SQLAlchemy**: SQLite ORM for user management and quota tracking
* **PyMuPDF (fitz)**: PDF to PNG conversion
* **Google Cloud Service Account**: Google Sheets API authentication

### Architecture

1. Telegram bot listens for incoming messages (text, photos, documents).
2. User sends image/PDF/text → downloaded to `uploads/` directory (temporary).
3. Media sent to NanoGPT API with `DEFAULT_PROMPT` or `TEXT_PROMPT` asking for structured JSON.
4. AI response parsed into invoice data (waktu, penjual, barang, harga, jumlah, service, pajak, ppn, subtotal).
5. Data appended to user's Google Sheet as new rows.
6. Activity logged to SQLite database for daily quota tracking.
7. User receives Telegram confirmation with extracted data summary.
8. Temporary files cleaned up.

## AI Model Configuration

- **Provider**: NanoGPT API (`https://nano-gpt.com/api/v1/chat/completions`)
- **Primary model**: `moonshotai/kimi-k2.6`
- **Fallbacks** (tried in order on 503/500/429):
  1. `google/gemma-4-31b-it`
  2. `xiaomi/mimo-v2.5`
  3. `stepfun/step-3.7-flash:thinking`
  4. `qwen3-vl-235b-a22b-instruct-original`
  5. `zai-org/glm-4.6v`
  6. `qwen25-vl-72b-instruct`
  7. `Qwen/Qwen3-VL-235B-A22B-Instruct`
  8. `qwen3-vl-235b-a22b-thinking`
- **Legacy provider**: Chutes API (`llm.chutes.ai`) — kept for reference only
- **Timeout**: 60s connect, 120s read
- **Temperature**: 0.1, **Max tokens**: 10000

## Running the Bot

### Production (VPS)
```bash
python app_with_database.py
```

### Testing
```bash
python test_text_parsing.py
python simple_text_test.py
```

## Key Files

| File | Purpose |
|---|---|
| `app_with_database.py` | **Production bot** — VPS entrypoint |
| `config.py` | All config (AI model, tiers, timeouts, admin IDs) |
| `credentials.py` | Secrets (gitignored) — API keys, tokens |
| `prompts.py` | AI prompts for image and text extraction |
| `init_database.py` | Creates SQLite tables |
| `data.db` | SQLite database (gitignored) |
| `app_multi_users_qwen.py` | Legacy bot (backup, Chutes API) |

## Tier System

| Tier | Daily Limit | Sheet |
|---|---|---|
| Free | 5 | Shared |
| Silver | 50 | Personal |
| Gold | 150 | Personal |
| Platinum | 300 | Personal |
| Admin | Unlimited | Any |

Daily limits reset at midnight WIB (Asia/Jakarta).

## Development Conventions

* **Logging**: Python `logging` module at INFO level
* **Error Handling**: `try...except` around all API calls, file ops, DB ops
* **Async**: `async`/`await` for all Telegram bot handlers
* **Single-file monolith**: `app_with_database.py` contains all bot logic inline
* **Config centralization**: All tuneable settings in `config.py`
* **Auto-registration**: New users created in SQLite on first interaction
