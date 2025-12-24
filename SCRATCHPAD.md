# Development Scratchpad

> Use this file to keep notes on ongoing development work.
> When the work is completed, clean it out from this file, so that the contents only reflect ongoing work.

---

## NOTES

### Current Session: December 24, 2024

**Objective:** ~~Set up planning documents~~ → Implement Database Foundation

**Completed:**
- [x] Analyzed existing codebase structure
- [x] Created PRD.md with full requirements
- [x] Created PLANNING.md with architecture
- [x] Created TASKS.md with milestones
- [x] Created SCRATCHPAD.md (this file)
- [x] Added custom prompt per user feature to PRD
- [x] Added custom sheet column order feature
- [x] Updated AI model to Qwen/Qwen3-VL-235B-A22B-Instruct
- [x] **MILESTONE 1 COMPLETE:** Database Foundation
  - Created `database/` directory with models, db.py, crud.py
  - Created `config.py` with centralized settings
  - Database initialized with 5 tiers (free, silver, gold, platinum, admin)
  - All CRUD operations tested and working

**Next Steps:**
1. Start Milestone 2: Bot Integration
2. Refactor bot to use database for user lookup
3. Add quota checking before processing

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
| 2024-12-24 | Planning & Documentation | Created PRD, PLANNING, TASKS, SCRATCHPAD |

---

## Files Modified This Session

- `PRD.md` - Created
- `PLANNING.md` - Created
- `TASKS.md` - Created
- `SCRATCHPAD.md` - Created

---

## Dependencies to Add

```
# Add to requirements.txt
sqlalchemy>=2.0.0
pytz
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
