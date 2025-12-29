# Code Review: `app_with_database.py`

**Date:** 2025-12-29  
**File:** `app_with_database.py`  
**Lines:** 1-1893

---

## Executive Summary

This review identified **12 flaws** in the Telegram Invoice Bot code, categorized by severity:

| Severity | Count | Issues |
|----------|--------|---------|
| 🔴 Critical | 4 | Out of scope variables, blocking async calls, shared client, class-level sessions |
| 🟡 High | 4 | Incorrect filter syntax, hardcoded sheet1, DB operations in loop, exception handler scope |
| 🟢 Medium | 4 | Download before quota check, no input validation, duplicated JSON parsing, no rate limiting |

---

## 🔴 CRITICAL FLAWS

### 1. Out of Scope Variables in Image Quota Check

**Location:** Lines 1633-1650

```python
# Line 1633 - CRITICAL BUG
if not quota_status.can_proceed:
    log_activity(
        db,  # ❌ 'db' is NOT in scope here!
        user_id=user.id,  # ❌ 'user' is NOT in scope here!
```

**Problem:** The variables `db` and `user` are referenced but they're not in scope at this point. They were defined inside a `with get_db() as db:` block at lines 1347-1374, which has already exited.

**Impact:** This will cause a `NameError` when processing images after PDF processing logic.

**Fix:** Move the quota check inside the database context manager or re-fetch the user:

```python
# Fix option 1: Move quota check earlier
with get_db() as db:
    user = get_user_by_telegram_id(db, user_tg.id)
    quota_status = check_quota(db, user, config.TIMEZONE)
    
    if not quota_status.can_proceed:
        log_activity(
            db,
            user_id=user.id,
            file_type="image",
            processing_status="limit_exceeded",
            error_message="Daily quota exceeded"
        )
        db.commit()
        os.remove(temp_path)
        # ... rest of error handling
```

---

### 2. Blocking Synchronous Calls in Async Methods

**Locations:** 
- Lines 105-110 ([`convert_image_to_data`](app_with_database.py:105-110))
- Lines 280-284 ([`convert_pdf_page_to_data`](app_with_database.py:280-284))
- Lines 367-371 ([`convert_text_to_data`](app_with_database.py:367-371))

```python
# Lines 105-110 - Blocks the event loop
response = requests.post(
    config.NANOGPT_API_URL,
    headers=headers,
    json=payload,
    timeout=config.AI_TIMEOUT
)
```

**Problem:** The methods use synchronous `requests.post()` calls inside async methods. This blocks the entire event loop, preventing the bot from handling other users' requests while waiting for API responses.

**Impact:** Poor performance, bot becomes unresponsive during AI API calls, cannot handle concurrent users effectively.

**Fix:** Use `aiohttp` or `httpx` for async HTTP requests:

```python
import aiohttp

async def convert_image_to_data(filepath, mime_type):
    """Convert image to structured data using NanoGPT API with vision model"""
    try:
        with open(filepath, 'rb') as f:
            image_bytes = f.read()

        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        prompt = DEFAULT_PROMPT + "\n\nBerikan respons dalam format JSON array."

        headers = {
            "Authorization": f"Bearer {config.NANOGPT_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": config.AI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": config.AI_TEMPERATURE,
            "max_tokens": config.AI_MAX_TOKENS,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.NANOGPT_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=config.AI_TIMEOUT)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # ... rest of processing
```

---

### 3. Shared Google Sheets Client

**Locations:** Lines 451-452, 527-529, 1161, 1381, 882

```python
# Lines 451-452
self.gc = None
self.sheet = None

# Line 528
self.gc = gspread.authorize(creds)
spreadsheet = self.gc.open_by_key(spreadsheet_id)
self.sheet = spreadsheet.sheet1
```

**Problem:** The Google Sheets client (`self.gc`) and sheet (`self.sheet`) are instance variables that get overwritten for each user. If two users process files simultaneously, they could interfere with each other's spreadsheet connections.

**Impact:** Data could be written to the wrong user's spreadsheet, race conditions, data corruption.

**Fix:** Create a new Google Sheets client per request or use a connection pool with proper locking:

```python
async def setup_google_sheets(self, credentials_file, spreadsheet_id):
    """Setup Google Sheets API connection for a specific spreadsheet"""
    try:
        logger.info(f"Setting up Google Sheets for spreadsheet: {spreadsheet_id[:20]}...")

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(credentials_file, scopes=scope)

        # Create new client for this request (not stored in self)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        sheet = spreadsheet.sheet1

        # Check and create headers if needed
        try:
            existing_headers = sheet.row_values(1)
            expected_headers = config.DEFAULT_SHEET_COLUMNS

            if not existing_headers or existing_headers != expected_headers:
                logger.info("Creating/updating headers in Google Sheet...")
                sheet.update('A1', [expected_headers])
                logger.info("✅ Headers created/updated successfully!")
            else:
                logger.info("✅ Headers already exist and match expected format!")
        except gspread.exceptions.APIError as e:
            logger.error(f"Error checking headers: {e}")
            raise

        logger.info("✅ Google Sheets setup completed successfully!")
        return sheet  # Return the sheet instead of storing in self

    except Exception as e:
        logger.error(f"❌ Error setting up Google Sheets: {e}")
        raise
```

Then update all usage sites to capture the returned sheet:

```python
# Example in handle_message
if not is_bulk:
    sheet = self.setup_google_sheets(self.google_credentials_file, target_spreadsheet_id)
    # Use the local 'sheet' variable instead of self.sheet
    if not is_bulk and rows_to_write:
        sheet.append_rows(rows_to_write, value_input_option='USER_ENTERED')
```

---

### 4. Class-Level `bulk_sessions` Dictionary

**Location:** Line 61

```python
# Line 61
class TelegramInvoiceBotWithDB:
    bulk_sessions = {}  # ❌ Shared across all instances
```

**Problem:** [`bulk_sessions`](app_with_database.py:61) is a class variable shared across all instances. This is problematic because:
- Lost on bot restart
- Not thread-safe for concurrent access
- Doesn't work with multiple bot instances (horizontal scaling)

**Impact:** Bulk sessions can be lost, race conditions, data loss on restart.

**Fix:** Use a database-backed session store or Redis for persistence:

```python
# Option 1: Database-backed sessions
# Add to database/models.py:
class BulkSession(Base):
    __tablename__ = "bulk_sessions"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, unique=True)
    csv_path = Column(String, nullable=False)
    items_count = Column(Integer, default=0)
    requests_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="bulk_sessions")

# Update User model:
User.bulk_sessions = relationship("BulkSession", back_populates="user", cascade="all, delete-orphan")

# Then in the bot class:
def get_bulk_session(self, telegram_id):
    """Get bulk session from database."""
    with get_db() as db:
        return db.query(BulkSession).filter_by(telegram_id=telegram_id).first()

def start_bulk_session(self, telegram_id):
    """Start a new bulk processing session."""
    csv_path = self.get_bulk_csv_path(telegram_id)
    
    # Create CSV file with headers
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(config.DEFAULT_SHEET_COLUMNS)
    
    # Store in database
    with get_db() as db:
        session = BulkSession(
            telegram_id=telegram_id,
            csv_path=csv_path,
            items_count=0,
            requests_count=0
        )
        db.add(session)
        db.commit()
    
    return csv_path

# Option 2: Use Redis (recommended for production)
import redis

class TelegramInvoiceBotWithDB:
    def __init__(self, ...):
        self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    def get_bulk_session(self, telegram_id):
        """Get bulk session from Redis."""
        key = f"bulk_session:{telegram_id}"
        data = self.redis.hgetall(key)
        return {k: int(v) if v.isdigit() else v for k, v in data.items()} if data else None
    
    def start_bulk_session(self, telegram_id):
        """Start a new bulk processing session."""
        csv_path = self.get_bulk_csv_path(telegram_id)
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(config.DEFAULT_SHEET_COLUMNS)
        
        key = f"bulk_session:{telegram_id}"
        self.redis.hset(key, mapping={
            "csv_path": csv_path,
            "items_count": 0,
            "requests_count": 0
        })
        self.redis.expire(key, 86400)  # Expire after 24 hours
        
        return csv_path
```

---

## 🟡 HIGH SEVERITY FLAWS

### 5. Incorrect Filter Syntax

**Location:** Lines 1843-1848

```python
# Lines 1843-1848
application.add_handler(MessageHandler(
    filters.PHOTO |  # ✓ Correct
    (filters.Document.IMAGE & filters.Document.MimeType(['image/jpeg', 'image/png'])) |  # ❌ filters.Document.IMAGE doesn't exist
    (filters.Document.PDF & filters.Document.MimeType('application/pdf')),  # ❌ filters.Document.PDF doesn't exist
    self.handle_media
))
```

**Problem:** `filters.Document.IMAGE` and `filters.Document.PDF` are not valid python-telegram-bot filters.

**Impact:** The media handler won't receive document events, breaking PDF and image document uploads.

**Fix:** Use only `filters.Document.MimeType()`:

```python
# Fixed version
application.add_handler(MessageHandler(
    filters.PHOTO |  # Handle photos
    filters.Document.MimeType(['image/jpeg', 'image/png']) |  # Handle image documents
    filters.Document.MimeType('application/pdf'),  # Handle PDF documents
    self.handle_media
))
```

---

### 6. Hardcoded `sheet1`

**Location:** Line 529

```python
# Line 529
self.sheet = spreadsheet.sheet1  # ❌ Always uses first sheet
```

**Problem:** The code always accesses `sheet1`, regardless of user configuration or sheet naming.

**Impact:** Cannot use custom sheet names or multiple sheets per spreadsheet.

**Fix:** Allow configurable sheet names or use the first sheet by index:

```python
# Option 1: Use first sheet by index
self.sheet = spreadsheet.get_worksheet(0)

# Option 2: Allow custom sheet names
def setup_google_sheets(self, credentials_file, spreadsheet_id, sheet_name=None):
    """Setup Google Sheets API connection for a specific spreadsheet"""
    try:
        # ... setup code ...
        
        spreadsheet = self.gc.open_by_key(spreadsheet_id)
        
        # Use custom sheet name if provided, otherwise use first sheet
        if sheet_name:
            try:
                self.sheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                self.sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        else:
            self.sheet = spreadsheet.get_worksheet(0)
        
        # ... rest of setup ...
```

---

### 7. Database Operations Inside Loop

**Location:** Lines 1494-1523

```python
# Lines 1494-1523 - Opens new DB context for EACH page
for page_num in range(pages_to_process):
    # Process this page
    page_data = await self.convert_pdf_page_to_data(temp_path, page_num)
    
    # Log activity for this page
    with get_db() as db:  # ❌ Opens new connection for each page
        user = get_user_by_telegram_id(db, user_tg.id)
        # ... logging operations
        db.commit()
```

**Problem:** A new database context is opened and committed for each PDF page, which is inefficient.

**Impact:** Poor performance with large PDFs, unnecessary database overhead.

**Fix:** Open the database context once outside the loop:

```python
# Fixed version
# Log activity for all pages at once after processing
all_page_results = []  # Track results for all pages

for page_num in range(pages_to_process):
    # Process this page
    page_data = await self.convert_pdf_page_to_data(temp_path, page_num)
    
    if page_data:
        all_invoice_data.extend(page_data)
        pages_processed += 1
        all_page_results.append({
            "page_num": page_num,
            "status": "success",
            "items_extracted": len(page_data)
        })
    else:
        pages_failed += 1
        all_page_results.append({
            "page_num": page_num,
            "status": "failed",
            "error": f"Failed to extract data from page {page_num + 1}"
        })
    
    # Progress update for multi-page PDFs
    if pages_to_process > 1 and (page_num + 1) % 3 == 0:
        await update.message.reply_text(
            f"⏳ Progress: {page_num + 1}/{pages_to_process} pages processed..."
        )

# Log all page activities at once (single DB connection)
with get_db() as db:
    user = get_user_by_telegram_id(db, user_tg.id)
    for result in all_page_results:
        log_activity(
            db,
            user_id=user.id,
            file_type="pdf_page",
            processing_status=result["status"],
            file_size_bytes=file_size // page_count,
            items_extracted=result.get("items_extracted", 0),
            error_message=result.get("error")
        )
    db.commit()
```

---

### 8. Exception Handler Scope Issues

**Location:** Lines 1272-1338

```python
# Lines 1272-1295
except gspread.exceptions.APIError as e:
    logger.error(f"Google Sheets API error: {e}")
    
    with get_db() as db:
        user = get_user_by_telegram_id(db, user_tg.id)  # ❌ user_tg might not be defined
```

**Problem:** The exception handlers reference `user_tg` which might not be defined if an error occurs early in the function.

**Impact:** `NameError` in exception handlers, masking the original error.

**Fix:** Initialize `user_tg` at the start of the function or use safer error handling:

```python
# Fixed version - initialize user_tg at start
async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages and save to Google Sheets"""
    user_tg = None  # Initialize early
    
    try:
        user_tg = update.effective_user
        message_text = update.message.text
        unix_timestamp = int(time.time())

        # ... rest of function ...

    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error: {e}")
        
        # Safe error logging - check if user_tg exists
        if user_tg:
            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                if user:
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="text",
                        processing_status="failed",
                        error_message=f"Google Sheets API error: {str(e)[:400]}"
                    )
                    db.commit()

        await update.message.reply_text(
            "❌ Google Sheets Error!\n\n"
            "There was a problem saving data to Google Sheets..."
        )
```

---

## 🟢 MEDIUM SEVERITY FLAWS

### 9. File Downloaded Before Quota Check

**Location:** Lines 1413-1416, 1633

```python
# Lines 1413-1416 - File downloaded before quota check
file_obj = await context.bot.get_file(file.file_id)
temp_path = f"temp_{unix_timestamp}{file_extension}"
await file_obj.download_to_drive(temp_path)
file_size = os.path.getsize(temp_path)

# ... PDF processing logic ...

# Line 1633 - Quota check happens AFTER download
if not quota_status.can_proceed:
```

**Problem:** Files are downloaded before checking if the user has quota available.

**Impact:** Wastes bandwidth and storage for users who have exceeded their quota.

**Fix:** Check quota before downloading files:

```python
# Fixed version - check quota first
async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos and documents"""
    try:
        user_tg = update.effective_user
        unix_timestamp = int(time.time())

        # Get or create user in database
        with get_db() as db:
            user, created = get_or_create_user(
                db,
                telegram_id=user_tg.id,
                username=user_tg.username,
                first_name=user_tg.first_name,
                last_name=user_tg.last_name,
                admin_user_ids=config.ADMIN_USER_IDS,
            )

            if created:
                logger.info(f"New user auto-registered: {user_tg.id}")

            # Check quota BEFORE downloading file
            quota_status = check_quota(db, user, config.TIMEZONE)

        # Determine file type
        if update.message.photo:
            file_type = "image"
            file_extension = ".jpg"
        elif update.message.document:
            file = update.message.document
            mime_type = file.mime_type.lower()

            if mime_type.startswith('image/'):
                file_type = "image"
                file_extension = ".jpg" if mime_type == "image/jpeg" else ".png"
            elif mime_type == "application/pdf":
                file_type = "pdf"
                file_extension = ".pdf"
            else:
                await update.message.reply_text("❌ Invalid file type!...")
                return
        else:
            return

        # Check quota for single image BEFORE downloading
        if file_type == "image" and not quota_status.can_proceed:
            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                log_activity(
                    db,
                    user_id=user.id,
                    file_type="image",
                    processing_status="limit_exceeded",
                    error_message="Daily quota exceeded"
                )
                db.commit()

            await update.message.reply_text(
                f"⛔ Daily quota exceeded!\n\n"
                f"You've used {quota_status.used_today}/{quota_status.daily_limit} requests today."
            )
            return

        # NOW download the file
        file_obj = await context.bot.get_file(file.file_id)
        temp_path = f"temp_{unix_timestamp}{file_extension}"
        await file_obj.download_to_drive(temp_path)
        file_size = os.path.getsize(temp_path)
        
        # ... rest of processing ...
```

---

### 10. No Input Validation on User Input

**Location:** Lines 970-976, 1026-1031

```python
# Lines 970-976 - No validation on telegram_id
try:
    target_telegram_id = int(context.args[0])  # Could be negative or extremely large
```

**Problem:** No validation that the Telegram ID is a valid positive integer.

**Impact:** Potential security issues, database errors with invalid IDs.

**Fix:** Add validation to ensure ID is a positive integer within reasonable range:

```python
# Fixed version - add validation
async def settier_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settier command (admin only) - Change user's tier"""
    user_tg = update.effective_user

    # Check if user is admin
    if not config.is_admin(user_tg.id):
        await update.message.reply_text("❌ This command is only available to administrators.")
        return

    # Parse arguments: /settier <telegram_id> <tier>
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /settier <telegram_id> <tier>\n\n"
            "Available tiers: free, silver, gold, platinum, admin\n"
            "Example: /settier 123456789 silver"
        )
        return

    try:
        target_telegram_id = int(context.args[0])
        
        # Validate Telegram ID
        if target_telegram_id <= 0:
            await update.message.reply_text("❌ Invalid Telegram ID. Must be a positive number.")
            return
        
        if target_telegram_id > 9999999999:  # Reasonable upper bound
            await update.message.reply_text("❌ Invalid Telegram ID. Number is too large.")
            return
        
        new_tier = context.args[1].lower()

        # Validate tier
        valid_tiers = ["free", "silver", "gold", "platinum", "admin"]
        if new_tier not in valid_tiers:
            await update.message.reply_text(
                f"❌ Invalid tier: {new_tier}\n"
                f"Valid tiers: {', '.join(valid_tiers)}"
            )
            return

        # Update user tier
        with get_db() as db:
            user = update_user_tier(db, target_telegram_id, new_tier)
            db.commit()

            if user:
                await update.message.reply_text(
                    f"✅ User tier updated successfully!\n\n"
                    f"👤 User ID: {target_telegram_id}\n"
                    f"🎖️ New Tier: {new_tier.upper()}\n"
                    f"📊 Daily Limit: {user.daily_limit if user.daily_limit != -1 else '∞'}"
                )
                logger.info(f"Admin {user_tg.id} changed user {target_telegram_id} to tier {new_tier}")
            else:
                await update.message.reply_text(
                    f"❌ User with Telegram ID {target_telegram_id} not found.\n"
                    f"User must send /start to the bot first to register."
                )

    except ValueError:
        await update.message.reply_text("❌ Invalid Telegram ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error in settier command: {e}")
        await update.message.reply_text(f"❌ Error updating tier: {str(e)}")
```

---

### 11. Duplicated JSON Parsing Logic

**Locations:** Lines 132-187, 293-329, 384-431

```python
# Lines 132-187 - Repeated JSON parsing logic
try:
    data = json.loads(content)
except json.JSONDecodeError:
    if content.strip().startswith('{') and not content.strip().startswith('['):
        content = '[' + content + ']'
    data = json.loads(content)
```

**Problem:** The JSON parsing logic is duplicated across three methods with identical code.

**Impact:** Code duplication, maintenance burden, potential for inconsistencies.

**Fix:** Extract to a shared utility method:

```python
# Add as a static method or module-level function
@staticmethod
def parse_json_response(content):
    """
    Parse JSON response from AI API with robust error handling.
    
    Args:
        content: Raw response content from API
        
    Returns:
        List of parsed data or None if parsing fails
    """
    try:
        # Extract JSON from markdown code blocks if present
        if content.startswith('```json'):
            # Find the start and end of the JSON content
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            if start_idx != -1 and end_idx != 0:
                content = content[start_idx:end_idx]
        elif content.startswith('```') and content.endswith('```'):
            # Remove markdown code blocks
            lines = content.split('\n')
            # Skip first and last lines (markdown code block markers)
            if len(lines) > 2:
                content = '\n'.join(lines[1:-1])
        else:
            # Handle cases where content starts with emojis or other non-JSON characters
            # Find the first occurrence of '[' or '{' to identify start of JSON
            start_idx = min(
                content.find('[') if content.find('[') != -1 else len(content),
                content.find('{') if content.find('{') != -1 else len(content)
            )
            if start_idx < len(content):
                # Find the last occurrence of ']' or '}' to identify end of JSON
                end_idx = max(
                    content.rfind(']') if content.rfind(']') != -1 else 0,
                    content.rfind('}') if content.rfind('}') != -1 else 0
                )
                if end_idx > 0:
                    content = content[start_idx:end_idx + 1]

        # Clean up the content - remove trailing commas
        content = content.strip()
        # Remove trailing comma before closing brace or bracket
        content = content.replace(',\n}', '\n}').replace(',\n]', '\n]').replace(',}', '}').replace(',]', ']')

        # Try to parse the cleaned content
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # If parsing fails, try to fix common issues
            # Check if it's a single object that should be in an array
            if content.strip().startswith('{') and not content.strip().startswith('['):
                content = '[' + content + ']'
            data = json.loads(content)

        # If it's not a list, wrap it
        if not isinstance(data, list):
            data = [data]

        if isinstance(data, list) and len(data) > 0:
            return data  # Return all data
        return None
    except Exception as e:
        logger.error(f"Error parsing JSON response: {e}")
        logger.error(f"Response content: {content}")
        return None

# Then use in all three methods:
async def convert_image_to_data(filepath, mime_type):
    """Convert image to structured data using NanoGPT API with vision model"""
    try:
        # ... API call code ...
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"API Response structure: {result.keys() if isinstance(result, dict) else 'Not a dict'}")

            # Validate response structure
            if not isinstance(result, dict) or 'choices' not in result:
                logger.error(f"Invalid API response structure: {result}")
                return None

            if not result['choices'] or len(result['choices']) == 0:
                logger.error(f"Empty choices in API response: {result}")
                return None

            content = result['choices'][0].get('message', {}).get('content')

            if content is None:
                logger.error(f"Content is None in API response: {result}")
                return None

            # Use shared parsing method
            return self.parse_json_response(content)
        else:
            logger.error(f"API request failed with status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None

    except requests.exceptions.Timeout as e:
        logger.error(f"Request timed out: {e}")
        logger.error("The model is taking too long to respond. Please try again.")
        return None
    except Exception as e:
        logger.error(f"Error converting image to data: {e}")
        return None
```

---

### 12. No Rate Limiting on API Calls

**Problem:** There's no rate limiting on the NanoGPT API calls. If multiple users make requests simultaneously, it could hit API limits.

**Impact:** API rate limit errors, service disruption.

**Fix:** Implement rate limiting using `asyncio.Semaphore` or a rate limiter library:

```python
import asyncio

class TelegramInvoiceBotWithDB:
    """Telegram bot with database-backed user management and quota system."""
    
    # Rate limiter for API calls
    _api_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent API calls
    _rate_limiter_lock = asyncio.Lock()
    _last_api_call_time = 0
    _min_api_interval = 0.5  # Minimum 0.5 seconds between API calls
    
    @staticmethod
    async def _rate_limit():
        """Apply rate limiting to API calls."""
        async with TelegramInvoiceBotWithDB._rate_limiter_lock:
            now = time.time()
            time_since_last_call = now - TelegramInvoiceBotWithDB._last_api_call_time
            if time_since_last_call < TelegramInvoiceBotWithDB._min_api_interval:
                await asyncio.sleep(TelegramInvoiceBotWithDB._min_api_interval - time_since_last_call)
            TelegramInvoiceBotWithDB._last_api_call_time = time.time()

    async def convert_image_to_data(filepath, mime_type):
        """Convert image to structured data using NanoGPT API with vision model"""
        async with self._api_semaphore:  # Limit concurrent calls
            await self._rate_limit()  # Apply rate limiting
            
            try:
                # ... rest of the method ...
```

Or use a dedicated rate limiter library:

```python
# Install: pip install aiolimiter
from aiolimiter import AsyncLimiter

class TelegramInvoiceBotWithDB:
    """Telegram bot with database-backed user management and quota system."""
    
    # Rate limiter: 10 requests per second
    _api_limiter = AsyncLimiter(10, 1.0)
    
    async def convert_image_to_data(filepath, mime_type):
        """Convert image to structured data using NanoGPT API with vision model"""
        async with self._api_limiter:
            try:
                # ... rest of the method ...
```

---

## Flake8 Linting Results

The linter detected 36 other issues:

| Code | Count | Description |
|-------|--------|-------------|
| **F401** | 2 | Unused imports (datetime.datetime, get_today_usage) |
| **F541** | 2 | f-string is missing placeholders |
| **E501** | 9 | Line too long (>120 characters) |
| **W293** | 23 | Blank line contains whitespace |

### Unused Imports
- **Line 31:** `from datetime import datetime` - imported but never used
- **Line 36:** `get_today_usage` - imported but never used

### F-String Without Placeholders
- **Line 379:** `logger.error(f"Content is None in text API response")` - should be a regular string
- **Line 1265:** `f"Hi, please upload a photo or document containing your invoice/receipt.\n"` - should be a regular string

### Long Lines
Multiple lines exceed 120 characters, particularly in:
- Lines 165, 317, 413 (JSON cleaning operations)
- Lines 578, 667, 1235, 1247, 1598, 1613, 1618, 1717, 1729 (quota status messages)

### Whitespace Issues
23 blank lines contain trailing whitespace.

---

## Summary Table

| Severity | Issue | Line(s) | Impact |
|----------|-------|---------|--------|
| 🔴 Critical | Out of scope variables | 1633-1650 | `NameError` crash |
| 🔴 Critical | Blocking sync calls in async | 105-110, 280-284, 367-371 | Poor performance, unresponsive bot |
| 🔴 Critical | Shared Google Sheets client | 451-452, 527-529 | Data corruption, wrong spreadsheet |
| 🔴 Critical | Class-level bulk_sessions | 61 | Lost sessions, race conditions |
| 🟡 High | Incorrect filter syntax | 1843-1848 | PDF/image documents not processed |
| 🟡 High | Hardcoded sheet1 | 529 | Cannot use custom sheets |
| 🟡 High | DB operations in loop | 1494-1523 | Poor performance with large PDFs |
| 🟡 High | Exception handler scope | 1272-1338 | `NameError` masking real errors |
| 🟢 Medium | Download before quota check | 1413-1416, 1633 | Wasted bandwidth |
| 🟢 Medium | No input validation | 970-976, 1026-1031 | Security risks |
| 🟢 Medium | Duplicated JSON parsing | 132-187, 293-329, 384-431 | Maintenance burden |
| 🟢 Medium | No API rate limiting | Throughout | API limit errors |

---

## Recommended Priority Fixes

1. **Fix out of scope variables** (immediate - causes crashes)
2. **Replace blocking calls with async** (immediate - affects performance)
3. **Fix Google Sheets client sharing** (immediate - data integrity)
4. **Fix filter syntax** (high - breaks functionality)
5. **Move bulk_sessions to database/Redis** (high - reliability)

---

## Additional Recommendations

### Code Quality
- Add type hints throughout the codebase
- Implement comprehensive unit tests
- Add docstrings for all public methods
- Use a configuration management library (e.g., pydantic-settings)

### Security
- Implement input validation for all user inputs
- Add rate limiting for all external API calls
- Sanitize all file paths to prevent path traversal attacks
- Implement proper error handling without exposing sensitive information

### Performance
- Use async/await consistently throughout
- Implement connection pooling for database and API calls
- Add caching for frequently accessed data
- Implement proper logging with structured log formats

### Monitoring
- Add metrics collection for monitoring bot performance
- Implement health check endpoints
- Add alerting for critical failures
- Track quota usage patterns for capacity planning

---

**Review Completed:** 2025-12-29  
**Reviewer:** Kilo Code
