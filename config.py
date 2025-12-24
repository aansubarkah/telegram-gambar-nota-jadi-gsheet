"""
Centralized configuration for Telegram Invoice Bot.

This module consolidates all settings in one place.
Sensitive credentials are still imported from credentials.py for backward compatibility.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List

# Import existing credentials for backward compatibility
from credentials import (
    TELEGRAM_BOT_TOKEN,
    GOOGLE_CREDENTIALS_FILE,
    SPREADSHEET_ID,
    CHUTES_API_KEY,
)


@dataclass
class Config:
    """Application configuration."""
    
    # ============================================================
    # Telegram Settings
    # ============================================================
    TELEGRAM_BOT_TOKEN: str = TELEGRAM_BOT_TOKEN
    
    # List of Telegram user IDs with admin privileges
    # These users can use admin commands and have unlimited quota
    ADMIN_USER_IDS: List[int] = field(default_factory=lambda: [
        33410730,  # Aan
        6931060098,  # Basang Data
    ])
    
    # ============================================================
    # Google Sheets Settings
    # ============================================================
    GOOGLE_CREDENTIALS_FILE: str = GOOGLE_CREDENTIALS_FILE
    
    # Default spreadsheet for free tier users
    DEFAULT_SPREADSHEET_ID: str = SPREADSHEET_ID
    
    # Default column headers for Google Sheets
    DEFAULT_SHEET_COLUMNS: List[str] = field(default_factory=lambda: [
        "waktu",
        "penjual",
        "barang",
        "harga",
        "jumlah",
        "service",
        "pajak",
        "ppn",
        "subtotal",
        "User ID",
        "Unix Timestamp",
    ])
    
    # ============================================================
    # AI API Settings
    # ============================================================
    CHUTES_API_KEY: str = CHUTES_API_KEY
    CHUTES_API_URL: str = "https://llm.chutes.ai/v1/chat/completions"
    
    # Qwen3 VL 235B A22 Instruct model
    AI_MODEL: str = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    
    # Timeout settings (connect_timeout, read_timeout)
    AI_TIMEOUT: tuple = (60, 120)
    
    # AI generation settings
    AI_TEMPERATURE: float = 0.1
    AI_MAX_TOKENS: int = 2000
    
    # ============================================================
    # Database Settings
    # ============================================================
    DATABASE_PATH: str = os.path.join(os.path.dirname(__file__), "data.db")
    DATABASE_URL: str = field(default="")
    
    def __post_init__(self):
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"sqlite:///{self.DATABASE_PATH}"
    
    # ============================================================
    # Tier System Settings
    # ============================================================
    TIER_LIMITS: Dict[str, int] = field(default_factory=lambda: {
        "free": 5,
        "silver": 50,
        "gold": 150,
        "platinum": 300,
        "admin": -1,  # -1 means unlimited
    })
    
    # ============================================================
    # Timezone Settings
    # ============================================================
    # Timezone for daily quota reset (midnight in this timezone)
    TIMEZONE: str = "Asia/Jakarta"  # WIB (UTC+7)
    
    # ============================================================
    # File Upload Settings
    # ============================================================
    UPLOAD_DIR: str = "uploads"
    
    # Allowed file extensions
    ALLOWED_IMAGE_EXTENSIONS: List[str] = field(default_factory=lambda: [
        "png", "jpeg", "jpg", "webp", "heic", "heif"
    ])
    ALLOWED_DOCUMENT_EXTENSIONS: List[str] = field(default_factory=lambda: [
        "pdf"
    ])
    
    # ============================================================
    # Helper Methods
    # ============================================================
    
    def is_admin(self, telegram_id: int) -> bool:
        """Check if a user is an admin."""
        return telegram_id in self.ADMIN_USER_IDS
    
    def get_tier_limit(self, tier: str) -> int:
        """Get daily limit for a tier."""
        return self.TIER_LIMITS.get(tier, 5)  # Default to free tier limit


# Global config instance
config = Config()


# ============================================================
# Legacy User Mapping (for migration)
# ============================================================
# These users will be migrated to the database on first run
LEGACY_USER_MAPPING = {
    "33410730": "1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU",
}
