# PLANNING.md

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram User                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Telegram Bot API                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Bot Application                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Handlers   │  │   Services   │  │   Database   │          │
│  │  - commands  │  │  - ai_proc   │  │   - models   │          │
│  │  - media     │  │  - sheets    │  │   - crud     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Chutes AI  │    │ Google Sheets│    │    SQLite    │
│  (Vision AI) │    │     API      │    │   Database   │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## Component Design

### 1. Handlers Layer (`bot/handlers/`)

**commands.py** - Telegram command handlers
- `start_command()` - Welcome + auto-register user
- `help_command()` - Show help
- `status_command()` - Bot status
- `checkid_command()` - Show Telegram ID
- `usage_command()` - Show quota usage
- `mysheet_command()` - Show Google Sheet URL
- `upgrade_command()` - Show tier options
- `settier_command()` - Admin: change tier
- `setsheet_command()` - Admin: set sheet ID
- `setprompt_command()` - Admin: set custom prompt
- `setcolumns_command()` - Admin: set sheet column order
- `stats_command()` - Admin: bot statistics

**media.py** - Media processing handlers
- `handle_photo()` - Process photo messages
- `handle_document()` - Process PDF/image documents
- `handle_text()` - Process text messages with invoice data

### 2. Services Layer (`bot/services/`)

**ai_processor.py** - Vision AI integration
- `convert_image_to_data()` - Extract data from image
- `convert_pdf_to_data()` - Extract data from PDF pages
- `convert_text_to_data()` - Extract data from text
- `parse_json_response()` - Parse AI response to structured data

**sheets.py** - Google Sheets operations
- `get_sheets_client()` - Initialize gspread client
- `get_or_create_sheet()` - Get sheet, create headers if needed
- `append_invoice_data()` - Append extracted data to sheet

### 3. Database Layer (`database/`)

**models.py** - SQLAlchemy ORM models
- `User` - User model with tier info
- `ActivityLog` - Activity logging model
- `Tier` - Tier reference model

**db.py** - Database connection
- `engine` - SQLAlchemy engine
- `SessionLocal` - Session factory
- `init_db()` - Initialize database and create tables
- `get_db()` - Get database session

**crud.py** - CRUD operations
- `get_user_by_telegram_id()` - Find user
- `create_user()` - Register new user
- `update_user_tier()` - Change user tier
- `update_user_sheet()` - Set user's sheet ID
- `log_activity()` - Log user activity
- `get_today_usage()` - Count today's requests
- `check_quota()` - Check if user can make request
- `get_all_users()` - List all users (admin)
- `get_stats()` - Get bot statistics (admin)
- `update_user_prompt()` - Set user's custom AI prompt
- `update_user_sheet_columns()` - Set user's custom sheet column order
- `get_user_prompt()` - Get prompt (custom or default fallback)

### 4. Configuration (`config.py`)

```python
# Centralized configuration
class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN: str
    ADMIN_USER_IDS: list[int]  # List of admin Telegram IDs
    
    # Google Sheets
    GOOGLE_CREDENTIALS_FILE: str
    DEFAULT_SPREADSHEET_ID: str  # For free tier users
    
    # AI API
    CHUTES_API_KEY: str
    AI_MODEL: str = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    AI_TIMEOUT: tuple = (60, 120)
    
    # Database
    DATABASE_URL: str = "sqlite:///data.db"
    
    # Tier Limits
    TIER_LIMITS: dict = {
        "free": 5,
        "silver": 50,
        "gold": 150,
        "platinum": 300,
        "admin": -1  # unlimited
    }
    
    # Timezone for daily reset
    TIMEZONE: str = "Asia/Jakarta"  # WIB
```

---

## Development Workflow

### Phase 1: Database Setup (Current Sprint)
1. Create SQLAlchemy models
2. Create database initialization script
3. Create CRUD operations
4. Migrate existing hardcoded user mappings to database

### Phase 2: Bot Refactoring
1. Refactor bot to use database for user lookup
2. Add quota checking before processing
3. Implement new commands (/usage, /upgrade, /mysheet)
4. Add activity logging

### Phase 3: Admin Features
1. Implement admin-only commands
2. Add /settier command
3. Add /setsheet command
4. Add /stats command

### Phase 4: Testing & Polish
1. Test all tier limits
2. Test daily reset logic
3. Test edge cases (new users, quota exceeded, etc.)
4. Error handling improvements

---

## Key Design Decisions

### 1. SQLite over PostgreSQL
- **Reason:** Single client, simple deployment, easy backup
- **Migration path:** SQLAlchemy ORM allows easy switch to PostgreSQL later

### 2. Admin by Config (not Database)
- **Reason:** Security - admin list in code/env, not changeable via bot
- **Implementation:** `ADMIN_USER_IDS` list in config

### 3. Daily Reset at Midnight WIB
- **Reason:** Target users are in Indonesia (WIB timezone)
- **Implementation:** Use `datetime` with `pytz` timezone

### 4. PDF Counts as 1 Request
- **Reason:** Fairness - 10-page PDF shouldn't use 10 quota slots
- **Implementation:** Log once per file, not per page

### 5. Free Tier Uses Shared Sheet
- **Reason:** Reduces setup friction, easy onboarding
- **Implementation:** Only paid tiers store custom `google_sheet_id`

---

## API Contracts

### Quota Check Response
```python
@dataclass
class QuotaStatus:
    can_proceed: bool
    used_today: int
    daily_limit: int
    tier: str
    
    @property
    def remaining(self) -> int:
        if self.daily_limit == -1:
            return float('inf')
        return self.daily_limit - self.used_today
```

### Activity Log Entry
```python
def log_activity(
    user_id: int,
    file_type: Literal["image", "pdf", "text"],
    file_size_bytes: int | None,
    processing_status: Literal["success", "failed", "limit_exceeded"],
    items_extracted: int = 0,
    error_message: str | None = None
) -> ActivityLog
```

---

## Testing Strategy

1. **Unit Tests:** Database CRUD operations
2. **Integration Tests:** Bot command handlers with mock database
3. **Manual Testing:** End-to-end with real Telegram
4. **Edge Cases:**
   - New user first message
   - Exactly at quota limit
   - Just past midnight reset
   - Invalid PDF/image
   - API timeout

---

## Rollback Strategy

If issues arise after deployment:
1. Keep old `app_multi_users_qwen.py` as backup
2. Database can be deleted and recreated (SQLite is just a file)
3. Old hardcoded `IDS_SPREADSHEETS` can be used as fallback

---

## Future Considerations (Out of Scope Now)

- **Web Dashboard:** FastAPI + Jinja2 for admin monitoring
- **Payment Integration:** Midtrans for Indonesian payments
- **Caching:** Redis for quota counts (when scaling)
- **Webhook Mode:** For production deployment efficiency
