# Development Scratchpad

> Use this file to keep notes on ongoing development work.
> When the work is completed, clean it out from this file, so that the contents only reflect ongoing work.

---

## NOTES

### Current Session: December 26, 2024

**Objective:** Implement Bulk Processing Feature for Platinum Tier

**Completed:**
- [x] Added `csv` and `pandas` imports
- [x] Created `bulk_sessions` class variable for tracking
- [x] Implemented bulk helper methods:
  - `is_bulk_mode()` - Check if user in bulk mode
  - `start_bulk_session()` - Create CSV file
  - `append_to_bulk_csv()` - Add row to CSV
  - `end_bulk_session()` - End and return paths
  - `convert_csv_to_excel()` - CSV to Excel conversion
- [x] Created `/startbulk` command (Platinum+ only)
- [x] Created `/endbulk` command
- [x] Modified `handle_message()` for bulk mode
- [x] Modified `handle_media()` for bulk mode (images + PDFs)
- [x] Updated help/start/upgrade commands
- [x] Added pandas + openpyxl to requirements-bot.txt
- [x] Updated memory.instructions.md

**Feature Summary:**
- Platinum users can use `/startbulk` to start bulk mode
- Data saves to CSV instead of Google Sheets
- `/endbulk` sends both CSV and Excel files
- Quota still applies (1 per image, 1 per PDF page)

### Previous Session: December 24, 2024

**Completed:**
- [x] Database Foundation (Milestone 1)
- [x] Bot Integration (Milestone 2)
- [x] Admin Features (Milestone 3)
- [x] Testing & Polish (Milestone 4)

---

## Code Snippets to Reference

### Current User Mapping (to migrate)
```python
# From app_multi_users_qwen.py - line 477
self.IDS_SPREADSHEETS = {
    '33410730': '1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU'
}
```
This hardcoded dictionary will be replaced with database lookup.

### Tier Limits Reference
```python
TIER_LIMITS = {
    "free": 5,
    "silver": 50,
    "gold": 150,
    "platinum": 300,
    "admin": -1  # unlimited
}
```

### Timezone for Daily Reset
```python
from datetime import datetime
import pytz

wib = pytz.timezone('Asia/Jakarta')
now_wib = datetime.now(wib)
today_start = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
```

---

## Questions to Resolve

1. ~~Should new users auto-register as free tier?~~ → YES
2. ~~Admin by config or database?~~ → CONFIG (ADMIN_USER_IDS list)
3. ~~What timezone for daily reset?~~ → WIB (Asia/Jakarta)
4. ~~Does PDF count as 1 or per-page?~~ → 1 per file

---

## Ideas for Later

- Add `/export` command to export user's own activity logs
- Add weekly/monthly usage summary messages
- Add referral system for upgrades
- Telegram inline keyboard for tier selection
- Prompt template library (common invoice formats)
- Visual prompt builder in web dashboard

## Custom Prompt Design Notes

**Use Case Examples:**
1. User A wants: `date → product → qty → price → total`
2. User B wants: `product → date → supplier → amount`
3. User C wants: `tanggal → nama_barang → harga` (Indonesian)

**Implementation:**
- Store full prompt text in `custom_prompt` column
- Store column order as JSON array: `["date", "product", "qty", "price"]`
- AI processor uses user's prompt if set, else DEFAULT_PROMPT
- Sheet service creates headers from `sheet_columns` if set

---

## Errors/Issues Encountered

(None yet - just starting)

---

## Session Log

| Date | Session Focus | Outcome |
|------|---------------|---------|
| 2024-12-24 | Planning & Documentation | Created PRD, PLANNING, TASKS, SCRATCHPAD || 2024-12-24 | Database & Bot Integration | Milestones 1-4 complete |
| 2024-12-26 | Bulk Processing Feature | Milestone 5 complete |
---

## Files Modified This Session

- `app_with_database.py` - Added bulk processing feature
- `requirements-bot.txt` - Added pandas, openpyxl
- `.github/instructions/memory.instructions.md` - Updated
- `PRD.md` - Updated with FR-7
- `PLANNING.md` - Updated with bulk methods
- `TASKS.md` - Updated with Milestone 5
- `SCRATCHPAD.md` - Updated

---

## Dependencies to Add

```
# Already in requirements-bot.txt
sqlalchemy>=2.0.0
pytz>=2023.0
pandas>=2.0.0      # Added Dec 26 for bulk export
openpyxl>=3.0.0    # Added Dec 26 for Excel export
```

---

## Database Migration Notes

When migrating from hardcoded users:
1. Run migration script to insert existing users
2. Verify data in SQLite
3. Test bot with database
4. Remove old IDS_SPREADSHEETS code

Migration script pseudocode:
```python
# Migrate existing users
old_mapping = {
    '33410730': '1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU'
}

for telegram_id, sheet_id in old_mapping.items():
    create_user(
        telegram_id=int(telegram_id),
        tier='silver',  # or appropriate tier
        google_sheet_id=sheet_id
    )
```
