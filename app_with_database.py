"""
Telegram Invoice Bot with Database Integration.

This is the integrated version with:
- SQLite database for user management
- Tier-based quota system (free/silver/gold/platinum/admin)
- Activity logging
- Per-user Google Sheets
- Admin commands

Based on app_multi_users_qwen.py with Milestone 2 features added.
"""

import os
import time
import logging
import gspread
import gspread.exceptions
import json
import base64
import requests
import fitz  # PyMuPDF for PDF processing
from PIL import Image
import io
import csv
import pandas as pd

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
from datetime import datetime

from config import config, LEGACY_USER_MAPPING
from prompts import DEFAULT_PROMPT, TEXT_PROMPT
from database.db import init_db, get_db
from database.crud import (
    get_or_create_user,
    get_user_by_telegram_id,
    get_user_spreadsheet_id,
    check_quota,
    log_activity,
    get_today_usage,
    update_user_tier,
    update_user_sheet_id,
    get_stats,
    migrate_existing_users,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramInvoiceBotWithDB:
    """Telegram bot with database-backed user management and quota system."""
    
    # Track bulk processing sessions: {telegram_id: {"csv_path": str, "items_count": int}}
    bulk_sessions = {}

    @staticmethod
    async def convert_image_to_data(filepath, mime_type):
        """Convert image to structured data using NanoGPT API with vision model"""
        try:
            with open(filepath, 'rb') as f:
                image_bytes = f.read()

            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            # Prepare the prompt for vision model
            prompt = DEFAULT_PROMPT + "\n\nBerikan respons dalam format JSON array."

            # Make API request to NanoGPT API
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

            response = requests.post(
                config.NANOGPT_API_URL,
                headers=headers,
                json=payload,
                timeout=config.AI_TIMEOUT
            )

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

                # Parse JSON response
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

    @staticmethod
    def get_pdf_page_count(filepath):
        """Get the number of pages in a PDF file."""
        try:
            pdf_document = fitz.open(filepath)
            page_count = len(pdf_document)
            pdf_document.close()
            return page_count
        except Exception as e:
            logger.error(f"Error getting PDF page count: {e}")
            return 0

    @staticmethod
    async def convert_pdf_page_to_data(filepath, page_num):
        """Convert a single PDF page to structured data.
        
        Args:
            filepath: Path to the PDF file
            page_num: Page number (0-indexed)
            
        Returns:
            List of invoice data dicts or None on failure
        """
        try:
            # Open PDF file
            pdf_document = fitz.open(filepath)
            
            if page_num >= len(pdf_document):
                logger.error(f"Page {page_num} does not exist in PDF with {len(pdf_document)} pages")
                pdf_document.close()
                return None
            
            # Get the specific page
            page = pdf_document[page_num]

            # Convert page to image
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # Convert to base64
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            pdf_document.close()

            # Prepare prompt for vision model
            prompt = DEFAULT_PROMPT + "\n\nBerikan respons dalam format JSON array."

            # Make API request to NanoGPT API
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
                                    "url": f"data:image/png;base64,{img_base64}"
                                }
                            }
                        ]
                    }
                ],
                "temperature": config.AI_TEMPERATURE,
                "max_tokens": config.AI_MAX_TOKENS,
            }

            response = requests.post(
                config.NANOGPT_API_URL,
                headers=headers,
                json=payload,
                timeout=config.AI_TIMEOUT
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0].get('message', {}).get('content')

                if content:
                    # JSON extraction logic
                    try:
                        if content.startswith('```json'):
                            start_idx = content.find('{')
                            end_idx = content.rfind('}') + 1
                            if start_idx != -1 and end_idx != 0:
                                content = content[start_idx:end_idx]
                        elif content.startswith('```') and content.endswith('```'):
                            lines = content.split('\n')
                            if len(lines) > 2:
                                content = '\n'.join(lines[1:-1])
                        else:
                            start_idx = min(
                                content.find('[') if content.find('[') != -1 else len(content),
                                content.find('{') if content.find('{') != -1 else len(content)
                            )
                            if start_idx < len(content):
                                end_idx = max(
                                    content.rfind(']') if content.rfind(']') != -1 else 0,
                                    content.rfind('}') if content.rfind('}') != -1 else 0
                                )
                                if end_idx > 0:
                                    content = content[start_idx:end_idx + 1]

                        content = content.strip()
                        content = content.replace(',\n}', '\n}').replace(',\n]', '\n]').replace(',}', '}').replace(',]', ']')

                        try:
                            data = json.loads(content)
                        except json.JSONDecodeError:
                            if content.strip().startswith('{') and not content.strip().startswith('['):
                                content = '[' + content + ']'
                            data = json.loads(content)

                        if not isinstance(data, list):
                            data = [data]

                        return data if data else None
                        
                    except Exception as e:
                        logger.error(f"Error parsing PDF page {page_num + 1} JSON: {e}")
                        return None
            
            logger.error(f"API request failed for page {page_num + 1}: {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Error converting PDF page {page_num + 1} to data: {e}")
            return None

    @staticmethod
    async def convert_text_to_data(text):
        """Convert text message to structured data using NanoGPT API"""
        try:
            # Prepare the prompt for text processing
            prompt = TEXT_PROMPT + f"\n\nTEKS PESAN:\n{text}"

            # Make API request to NanoGPT API
            headers = {
                "Authorization": f"Bearer {config.NANOGPT_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": config.AI_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": config.AI_TEMPERATURE,
                "max_tokens": config.AI_MAX_TOKENS,
            }

            response = requests.post(
                config.NANOGPT_API_URL,
                headers=headers,
                json=payload,
                timeout=config.AI_TIMEOUT
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0].get('message', {}).get('content')

                if content is None:
                    logger.error(f"Content is None in text API response")
                    return None

                # Parse JSON response (same logic as image processing)
                try:
                    if content.startswith('```json'):
                        start_idx = content.find('[')
                        end_idx = content.rfind(']') + 1
                        if start_idx != -1 and end_idx != 0:
                            content = content[start_idx:end_idx]
                        else:
                            start_idx = content.find('{')
                            end_idx = content.rfind('}') + 1
                            if start_idx != -1 and end_idx != 0:
                                content = content[start_idx:end_idx]
                    elif content.startswith('```') and content.endswith('```'):
                        lines = content.split('\n')
                        if len(lines) > 2:
                            content = '\n'.join(lines[1:-1])
                    else:
                        start_idx = min(
                            content.find('[') if content.find('[') != -1 else len(content),
                            content.find('{') if content.find('{') != -1 else len(content)
                        )
                        if start_idx < len(content):
                            end_idx = max(
                                content.rfind(']') if content.rfind(']') != -1 else 0,
                                content.rfind('}') if content.rfind('}') != -1 else 0
                            )
                            if end_idx > 0:
                                content = content[start_idx:end_idx + 1]

                    # Clean up the content
                    content = content.strip()
                    content = content.replace(',\n}', '\n}').replace(',\n]', '\n]').replace(',}', '}').replace(',]', ']')

                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        if content.strip().startswith('{') and not content.strip().startswith('['):
                            content = '[' + content + ']'
                        data = json.loads(content)

                    if not isinstance(data, list):
                        data = [data]

                    if isinstance(data, list) and len(data) > 0:
                        return data
                    return None
                except Exception as e:
                    logger.error(f"Error parsing JSON response: {e}")
                    logger.error(f"Response content: {content}")
                    return None
            else:
                logger.error(f"API request failed with status code {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

        except requests.exceptions.Timeout as e:
            logger.error(f"Request timed out: {e}")
            return None
        except Exception as e:
            logger.error(f"Error converting text to data: {e}")
            return None

    def __init__(self, telegram_token, google_credentials_file, default_spreadsheet_id):
        self.telegram_token = telegram_token
        self.google_credentials_file = google_credentials_file
        self.default_spreadsheet_id = default_spreadsheet_id
        self.upload_dir = config.UPLOAD_DIR

        # Initialize Google Sheets client (will be set per-user)
        self.gc = None
        self.sheet = None

        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
            logger.info(f"Created upload directory: {self.upload_dir}")

    def is_bulk_mode(self, telegram_id):
        """Check if user is in bulk processing mode."""
        return telegram_id in self.bulk_sessions

    def get_bulk_csv_path(self, telegram_id):
        """Get the CSV file path for a bulk session."""
        return os.path.join(self.upload_dir, f"bulk_{telegram_id}.csv")

    def start_bulk_session(self, telegram_id):
        """Start a new bulk processing session."""
        csv_path = self.get_bulk_csv_path(telegram_id)
        
        # Create CSV file with headers
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(config.DEFAULT_SHEET_COLUMNS)
        
        self.bulk_sessions[telegram_id] = {
            "csv_path": csv_path,
            "items_count": 0,
            "requests_count": 0  # Track quota usage
        }
        return csv_path

    def append_to_bulk_csv(self, telegram_id, row_data):
        """Append a row to the bulk session CSV."""
        if telegram_id not in self.bulk_sessions:
            return False
        
        csv_path = self.bulk_sessions[telegram_id]["csv_path"]
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row_data)
        
        self.bulk_sessions[telegram_id]["items_count"] += 1
        return True

    def increment_bulk_request_count(self, telegram_id):
        """Increment the request count for quota tracking."""
        if telegram_id in self.bulk_sessions:
            self.bulk_sessions[telegram_id]["requests_count"] += 1

    def end_bulk_session(self, telegram_id):
        """End bulk session and return CSV path, items count, and requests count."""
        if telegram_id not in self.bulk_sessions:
            return None, 0, 0
        
        session = self.bulk_sessions.pop(telegram_id)
        return session["csv_path"], session["items_count"], session["requests_count"]

    def convert_csv_to_excel(self, csv_path):
        """Convert CSV file to Excel format."""
        excel_path = csv_path.replace('.csv', '.xlsx')
        df = pd.read_csv(csv_path, encoding='utf-8')
        df.to_excel(excel_path, index=False, engine='openpyxl')
        return excel_path

    def setup_google_sheets(self, credentials_file, spreadsheet_id):
        """Setup Google Sheets API connection for a specific spreadsheet"""
        try:
            logger.info(f"Setting up Google Sheets for spreadsheet: {spreadsheet_id[:20]}...")

            # Define the scope
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

            # Load credentials
            creds = Credentials.from_service_account_file(credentials_file, scopes=scope)

            # Authorize and get the spreadsheet
            self.gc = gspread.authorize(creds)
            spreadsheet = self.gc.open_by_key(spreadsheet_id)
            self.sheet = spreadsheet.sheet1

            # Check and create headers if needed
            try:
                existing_headers = self.sheet.row_values(1)
                expected_headers = config.DEFAULT_SHEET_COLUMNS

                if not existing_headers or existing_headers != expected_headers:
                    logger.info("Creating/updating headers in Google Sheet...")
                    self.sheet.update('A1', [expected_headers])
                    logger.info("✅ Headers created/updated successfully!")
                else:
                    logger.info("✅ Headers already exist and match expected format!")
            except gspread.exceptions.APIError as e:
                logger.error(f"Error checking headers: {e}")
                raise

            logger.info("✅ Google Sheets setup completed successfully!")

        except Exception as e:
            logger.error(f"❌ Error setting up Google Sheets: {e}")
            raise

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - auto-register user"""
        user_tg = update.effective_user

        # Auto-register or get user
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
                logger.info(f"New user registered: {user_tg.id} ({user_tg.username})")
                welcome_msg = "🎉 Welcome! You've been registered as a FREE tier user.\n\n"
            else:
                welcome_msg = f"👋 Welcome back, {user_tg.first_name}!\n\n"

            quota_status = check_quota(db, user, config.TIMEZONE)

        welcome_message = (
            f"{welcome_msg}"
            f"📋 Your tier: {quota_status.tier.upper()}\n"
            f"📊 Today's quota: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'}\n\n"
            "📸 Send me an invoice image, PDF, or text and I'll extract the data to Google Sheets!\n\n"
            "Available commands:\n"
            "/start - Show this welcome message\n"
            "/help - Show help information\n"
            "/status - Check bot status\n"
            "/checkid - Get your Telegram ID\n"
            "/usage - Check your quota usage\n"
            "/mysheet - View your Google Sheet (paid tiers)\n"
            "/upgrade - View tier upgrade options\n"
            "/startbulk - Start bulk processing (Platinum)\n"
            "/endbulk - End bulk & download files (Platinum)\n"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = (
            "📋 How to use this bot:\n\n"
            "1. Send an invoice image, PDF, or text message\n"
            "2. The bot will extract data using AI\n"
            "3. Data is saved to your Google Sheet\n"
            "4. You'll get a summary of extracted items\n\n"
            "📊 Tier System:\n"
            "• FREE: 5 requests/day, shared sheet\n"
            "• SILVER: 50 requests/day, your own sheet\n"
            "• GOLD: 150 requests/day, your own sheet\n"
            "• PLATINUM: 300 requests/day, bulk mode, your own sheet\n\n"
            "Commands:\n"
            "/start - Welcome message & registration\n"
            "/help - This help message\n"
            "/status - Check if bot is working\n"
            "/checkid - Get your Telegram ID\n"
            "/usage - Check quota usage\n"
            "/mysheet - View your Google Sheet\n"
            "/upgrade - View upgrade options\n\n"
            "💎 Platinum Commands:\n"
            "/startbulk - Start bulk processing mode\n"
            "/endbulk - End bulk & download CSV/Excel\n"
        )
        await update.message.reply_text(help_message)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            # Test Google Sheets connection
            self.setup_google_sheets(self.google_credentials_file, self.default_spreadsheet_id)
            row_count = len(self.sheet.get_all_records())
            status_message = f"✅ Bot is working!\n📊 Total records in default sheet: {row_count}"
        except Exception as e:
            status_message = f"❌ Error connecting to Google Sheets: {str(e)}"

        await update.message.reply_text(status_message)

    async def checkid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /checkid command"""
        user = update.effective_user
        await update.message.reply_text(
            f"🆔 Your Telegram ID is: `{user.id}`\n"
            f"Username: @{user.username if user.username else 'None'}\n"
            f"Name: {user.first_name} {user.last_name if user.last_name else ''}",
            parse_mode='Markdown'
        )

    async def usage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /usage command - show quota usage"""
        user_tg = update.effective_user

        with get_db() as db:
            user, _ = get_or_create_user(
                db,
                telegram_id=user_tg.id,
                username=user_tg.username,
                first_name=user_tg.first_name,
                last_name=user_tg.last_name,
                admin_user_ids=config.ADMIN_USER_IDS,
            )

            quota_status = check_quota(db, user, config.TIMEZONE)

        if quota_status.is_unlimited:
            usage_msg = (
                f"📊 Quota Status\n\n"
                f"👤 User: {user_tg.first_name}\n"
                f"🎖️ Tier: {quota_status.tier.upper()}\n"
                f"✅ Status: UNLIMITED\n"
                f"📈 Used today: {quota_status.used_today}\n"
            )
        else:
            percentage = (quota_status.used_today / quota_status.daily_limit * 100) if quota_status.daily_limit > 0 else 0
            usage_msg = (
                f"📊 Quota Status\n\n"
                f"👤 User: {user_tg.first_name}\n"
                f"🎖️ Tier: {quota_status.tier.upper()}\n"
                f"📈 Used: {quota_status.used_today}/{quota_status.daily_limit} ({percentage:.1f}%)\n"
                f"✨ Remaining: {quota_status.remaining}\n"
                f"🔄 Resets: Daily at midnight WIB\n"
            )

        await update.message.reply_text(usage_msg)

    async def mysheet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mysheet command - show user's Google Sheet URL"""
        user_tg = update.effective_user

        with get_db() as db:
            user = get_user_by_telegram_id(db, user_tg.id)

            if not user:
                await update.message.reply_text(
                    "❌ You're not registered yet. Send /start to register!"
                )
                return

            if user.google_sheet_id:
                sheet_url = f"https://docs.google.com/spreadsheets/d/{user.google_sheet_id}"
                msg = (
                    f"📊 Your Google Sheet\n\n"
                    f"🎖️ Tier: {user.tier.upper()}\n"
                    f"🔗 URL: {sheet_url}\n\n"
                    f"All your invoice data is saved here!"
                )
            else:
                default_url = "https://bit.ly/invoice-to-gsheets"
                msg = (
                    f"📊 Your Google Sheet\n\n"
                    f"🎖️ Tier: FREE\n"
                    f"🔗 URL: {default_url}\n\n"
                    f"You're using the shared sheet for free tier users.\n"
                    f"Upgrade to get your own private sheet! Use /upgrade"
                )

        await update.message.reply_text(msg)

    async def upgrade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /upgrade command - show tier options"""
        upgrade_msg = (
            "*UPGRADE & BOOST YOUR PRODUCTIVITY!*\n\n"
            "Stop wasting hours on manual data entry. Let AI do the work!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🆓 *FREE TIER*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✓ 5 invoices/day\n"
            "✓ Shared Google Sheet\n"
            "💰 *IDR 0*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🥈 *SILVER*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✓ 50 invoices/day\n"
            "✓ Your OWN private Google Sheet\n"
            "✓ Multi-page PDF support\n"
            "✓ Priority processing\n"
            "💰 *IDR 100.000/month*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🥇 *GOLD*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✓ 150 invoices/day\n"
            "✓ Your OWN private Google Sheet\n"
            "✓ Multi-page PDF support\n"
            "✓ Priority processing\n"
            "✓ Custom column order\n"
            "💰 *IDR 200.000/month*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💎 *PLATINUM*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✓ 300 invoices/day\n"
            "✓ Your OWN private Google Sheet\n"
            "✓ Multi-page PDF support\n"
            "✓ Priority processing\n"
            "✓ Custom column order\n"
            "✓ Custom AI prompt\n"
            "✓ Bulk processing mode\n"
            "✓ Dedicated support\n"
            "💰 *IDR 300.000/month*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💬 *Ready to upgrade?*\n"
            "Please visit https://lynk.id/basangdata/0gloz311vmzk or\n"
            "Contact @basangdata to get started!\n\n"
            f"📎 Your Telegram ID: `{update.effective_user.id}`\n"
            "_(Share this ID when contacting us)_"
        )
        await update.message.reply_text(upgrade_msg, parse_mode='Markdown')

    # ============================================================
    # BULK PROCESSING COMMANDS (Platinum+ only)
    # ============================================================

    async def startbulk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /startbulk command - Start bulk processing mode (Platinum+ only)"""
        user_tg = update.effective_user

        # Get or create user
        with get_db() as db:
            user, _ = get_or_create_user(
                db,
                telegram_id=user_tg.id,
                username=user_tg.username,
                first_name=user_tg.first_name,
                last_name=user_tg.last_name,
                admin_user_ids=config.ADMIN_USER_IDS,
            )
            user_tier = user.tier

        # Check if user has platinum tier or higher
        if user_tier not in ['platinum', 'admin']:
            await update.message.reply_text(
                "⛔ *Bulk Processing - Platinum Feature*\n\n"
                "This feature is only available for *PLATINUM* tier users!\n\n"
                "📦 *What is Bulk Processing?*\n"
                "• Process multiple invoices at once\n"
                "• Data saved to CSV instead of Google Sheets\n"
                "• Download CSV and Excel files when done\n"
                "• Perfect for batch processing!\n\n"
                "💎 Upgrade to PLATINUM to unlock this feature!\n"
                "Use /upgrade to see options.",
                parse_mode='Markdown'
            )
            return

        # Check if already in bulk mode
        if self.is_bulk_mode(user_tg.id):
            session = self.bulk_sessions[user_tg.id]
            await update.message.reply_text(
                f"⚠️ You're already in bulk processing mode!\n\n"
                f"📊 Current session:\n"
                f"• Items collected: {session['items_count']}\n"
                f"• Requests used: {session['requests_count']}\n\n"
                f"Send /endbulk to finish and download files,\n"
                f"or continue uploading more invoices."
            )
            return

        # Start bulk session
        csv_path = self.start_bulk_session(user_tg.id)
        logger.info(f"User {user_tg.id} started bulk session: {csv_path}")

        await update.message.reply_text(
            "🚀 *Bulk Processing Mode Started!*\n\n"
            "📦 You can now upload multiple invoices:\n"
            "• Images (PNG, JPG)\n"
            "• PDF documents\n"
            "• Text messages\n\n"
            "📊 All data will be collected in a CSV file.\n"
            "⚠️ Quota still applies (1 per image/page).\n\n"
            "When you're done, send /endbulk to:\n"
            "• Get your CSV file\n"
            "• Get your Excel file\n\n"
            "💡 _Tip: Upload as many invoices as you need!_",
            parse_mode='Markdown'
        )

    async def endbulk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /endbulk command - End bulk processing and send files"""
        user_tg = update.effective_user

        # Check if user is in bulk mode
        if not self.is_bulk_mode(user_tg.id):
            await update.message.reply_text(
                "❌ You're not in bulk processing mode!\n\n"
                "Use /startbulk to start a bulk processing session first."
            )
            return

        # Get session info and end it
        csv_path, items_count, requests_count = self.end_bulk_session(user_tg.id)

        if items_count == 0:
            # No data collected - just clean up
            try:
                if os.path.exists(csv_path):
                    os.remove(csv_path)
            except Exception as e:
                logger.error(f"Error cleaning up empty CSV: {e}")

            await update.message.reply_text(
                "⚠️ *Bulk Session Ended*\n\n"
                "No invoice data was collected during this session.\n"
                "No files to download.\n\n"
                "Use /startbulk to start a new session.",
                parse_mode='Markdown'
            )
            return

        try:
            await update.message.reply_text(
                f"🔄 Processing your bulk data...\n\n"
                f"📊 Items collected: {items_count}\n"
                f"📈 Requests used: {requests_count}"
            )

            # Convert CSV to Excel
            excel_path = self.convert_csv_to_excel(csv_path)

            # Send CSV file
            with open(csv_path, 'rb') as csv_file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=csv_file,
                    filename=f"invoice_data_{user_tg.id}.csv",
                    caption="📄 *CSV File*\n\nYour invoice data in CSV format.",
                    parse_mode='Markdown'
                )

            # Send Excel file
            with open(excel_path, 'rb') as excel_file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=excel_file,
                    filename=f"invoice_data_{user_tg.id}.xlsx",
                    caption="📊 *Excel File*\n\nYour invoice data in Excel format.",
                    parse_mode='Markdown'
                )

            # Clean up files
            try:
                os.remove(csv_path)
                os.remove(excel_path)
                logger.info(f"Cleaned up bulk files for user {user_tg.id}")
            except Exception as e:
                logger.error(f"Error cleaning up bulk files: {e}")

            await update.message.reply_text(
                "✅ *Bulk Processing Complete!*\n\n"
                f"📊 Summary:\n"
                f"• Total items: {items_count}\n"
                f"• Quota used: {requests_count}\n\n"
                "📁 Files sent:\n"
                "• ✓ CSV file\n"
                "• ✓ Excel file\n\n"
                "💡 _Use /startbulk to start another session._",
                parse_mode='Markdown'
            )

            logger.info(f"User {user_tg.id} completed bulk session: {items_count} items, {requests_count} requests")

        except Exception as e:
            logger.error(f"Error in endbulk: {e}")
            await update.message.reply_text(
                f"❌ Error processing bulk data: {str(e)}\n\n"
                "Please try /endbulk again or contact support."
            )

    # ============================================================
    # ADMIN COMMANDS
    # ============================================================

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

    async def setsheet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setsheet command (admin only) - Set user's Google Sheet ID"""
        user_tg = update.effective_user

        # Check if user is admin
        if not config.is_admin(user_tg.id):
            await update.message.reply_text("❌ This command is only available to administrators.")
            return

        # Parse arguments: /setsheet <telegram_id> <sheet_id>
        if len(context.args) != 2:
            await update.message.reply_text(
                "Usage: /setsheet <telegram_id> <google_sheet_id>\n\n"
                "Example: /setsheet 123456789 1aBcDeFg1234567890..."
            )
            return

        try:
            target_telegram_id = int(context.args[0])
            sheet_id = context.args[1]

            # Update user sheet ID
            with get_db() as db:
                user = update_user_sheet_id(db, target_telegram_id, sheet_id)
                db.commit()

                if user:
                    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
                    await update.message.reply_text(
                        f"✅ Google Sheet updated successfully!\n\n"
                        f"👤 User ID: {target_telegram_id}\n"
                        f"📊 Sheet ID: {sheet_id[:20]}...\n"
                        f"🔗 URL: {sheet_url}"
                    )
                    logger.info(f"Admin {user_tg.id} set sheet for user {target_telegram_id}")
                else:
                    await update.message.reply_text(
                        f"❌ User with Telegram ID {target_telegram_id} not found.\n"
                        f"User must send /start to the bot first to register."
                    )

        except ValueError:
            await update.message.reply_text("❌ Invalid Telegram ID. Must be a number.")
        except Exception as e:
            logger.error(f"Error in setsheet command: {e}")
            await update.message.reply_text(f"❌ Error updating sheet: {str(e)}")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command (admin only) - Show bot statistics"""
        user_tg = update.effective_user

        # Check if user is admin
        if not config.is_admin(user_tg.id):
            await update.message.reply_text("❌ This command is only available to administrators.")
            return

        try:
            with get_db() as db:
                stats = get_stats(db, config.TIMEZONE)

            # Format tier counts
            tier_breakdown = "\n".join(
                f"  • {tier.upper()}: {count}"
                for tier, count in sorted(stats['users_by_tier'].items())
            )

            stats_msg = (
                f"📊 Bot Statistics\n\n"
                f"👥 Total Users: {stats['total_users']}\n\n"
                f"By Tier:\n{tier_breakdown}\n\n"
                f"📈 Today's Activity:\n"
                f"  • Requests: {stats['today_requests']}\n"
                f"  • Successful: {stats['today_success']}\n\n"
                f"📊 All Time:\n"
                f"  • Total Requests: {stats['total_requests']}"
            )

            await update.message.reply_text(stats_msg)
            logger.info(f"Admin {user_tg.id} viewed stats")

        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await update.message.reply_text(f"❌ Error retrieving stats: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages and save to Google Sheets"""
        try:
            user_tg = update.effective_user
            message_text = update.message.text
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

                # Check quota
                quota_status = check_quota(db, user, config.TIMEZONE)

                if not quota_status.can_proceed:
                    # Log quota exceeded
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="text",
                        processing_status="limit_exceeded",
                        error_message="Daily quota exceeded"
                    )
                    db.commit()

                    await update.message.reply_text(
                        f"⛔ Daily quota exceeded!\n\n"
                        f"You've used {quota_status.used_today}/{quota_status.daily_limit} requests today.\n"
                        f"Your quota will reset tomorrow at midnight WIB.\n\n"
                        f"Want more requests? Use /upgrade to see tier options!"
                    )
                    return

                # Get spreadsheet ID
                target_spreadsheet_id = get_user_spreadsheet_id(
                    db,
                    user_tg.id,
                    self.default_spreadsheet_id
                )

                # Generate spreadsheet URL
                if user.google_sheet_id:
                    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{target_spreadsheet_id}"
                else:
                    spreadsheet_url = 'https://bit.ly/invoice-to-gsheets'

            # Check if user is in bulk mode
            is_bulk = self.is_bulk_mode(user_tg.id)

            # Setup Google Sheets client only if not in bulk mode
            if not is_bulk:
                self.setup_google_sheets(self.google_credentials_file, target_spreadsheet_id)

            # Process text to extract invoice data
            if is_bulk:
                await update.message.reply_text("🔄 [BULK] Processing text message...")
            else:
                await update.message.reply_text("🔄 Processing text message, please wait...")

            invoice_data = await self.convert_text_to_data(message_text)

            if invoice_data:
                # Track total items processed
                items_processed = 0

                for invoice in invoice_data:
                    # Prepare row data for each invoice
                    row_data = [
                        invoice.get('waktu', ''),
                        invoice.get('penjual', ''),
                        invoice.get('barang', ''),
                        invoice.get('harga', 0),
                        invoice.get('jumlah', 0),
                        invoice.get('service', 0),
                        invoice.get('pajak', 0),
                        invoice.get('ppn', 0),
                        invoice.get('subtotal', 0),
                        str(user_tg.id),
                        unix_timestamp
                    ]

                    # Append to CSV (bulk mode) or Google Sheets (normal mode)
                    if is_bulk:
                        self.append_to_bulk_csv(user_tg.id, row_data)
                    else:
                        self.sheet.append_row(row_data)
                    items_processed += 1

                # Increment bulk request count (1 request for text processing)
                if is_bulk:
                    self.increment_bulk_request_count(user_tg.id)

                # Log successful activity
                with get_db() as db:
                    user = get_user_by_telegram_id(db, user_tg.id)
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="text",
                        processing_status="success",
                        file_size_bytes=len(message_text.encode('utf-8')),
                        items_extracted=items_processed
                    )
                    db.commit()

                    # Get updated quota
                    quota_status = check_quota(db, user, config.TIMEZONE)

                # Send confirmation
                if is_bulk:
                    session = self.bulk_sessions[user_tg.id]
                    await update.message.reply_text(
                        f"✅ [BULK] Data extracted and added to batch!\n\n"
                        f"📊 Summary:\n"
                        f"📝 Items in this batch: {items_processed}\n"
                        f"🏪 Seller: {invoice_data[0].get('penjual', 'N/A')}\n"
                        f"💰 Total: {sum(inv.get('subtotal', 0) for inv in invoice_data):,.2f}\n\n"
                        f"📦 Bulk session:\n"
                        f"• Total items: {session['items_count']}\n"
                        f"• Requests used: {session['requests_count']}\n\n"
                        f"📈 Quota: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'}\n\n"
                        f"💡 Send /endbulk to download files."
                    )
                else:
                    await update.message.reply_text(
                        f"✅ Data extracted and saved successfully!\n\n"
                        f"📊 Summary:\n"
                        f"📝 Items processed: {items_processed}\n"
                        f"🏪 Seller: {invoice_data[0].get('penjual', 'N/A')}\n"
                        f"💰 Total (all items): {sum(inv.get('subtotal', 0) for inv in invoice_data):,.2f}\n"
                        f"⏰ Date: {invoice_data[0].get('waktu', 'N/A')}\n\n"
                        f"📄 See the full data in Google Sheets: {spreadsheet_url}\n\n"
                        f"📈 Quota: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'} used today"
                    )

            else:
                # Log failed activity
                with get_db() as db:
                    user = get_user_by_telegram_id(db, user_tg.id)
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="text",
                        processing_status="failed",
                        file_size_bytes=len(message_text.encode('utf-8')),
                        error_message="No invoice data found in text"
                    )
                    db.commit()

                await update.message.reply_text(
                    f"Hi, please upload a photo or document containing your invoice/receipt.\n"
                    f"The data will be extracted and saved to Google Sheets.\n\n"
                    f"Use /help to see how to use this bot."
                )

            logger.info(f"Processed message from {user_tg.username}: {message_text[:50]}")

        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error: {e}")
            
            # Log error
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
                "There was a problem saving data to Google Sheets. This could be due to:\n"
                "• Rate limiting (too many requests)\n"
                "• Permission issues with the spreadsheet\n"
                "• Temporary Google API issues\n\n"
                "Please try again in a moment. If this persists, contact support."
            )

        except requests.exceptions.Timeout as e:
            logger.error(f"Vision AI timeout: {e}")
            
            # Log error
            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                if user:
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="text",
                        processing_status="failed",
                        error_message="Vision AI timeout"
                    )
                    db.commit()

            await update.message.reply_text(
                "⏱️ Request Timeout!\n\n"
                "The AI model is taking too long to respond.\n"
                "This can happen during high traffic periods.\n\n"
                "Please try again in a moment."
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")

            # Log error
            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                if user:
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="text",
                        processing_status="failed",
                        error_message=str(e)[:500]
                    )
                    db.commit()

            await update.message.reply_text(
                "❌ Sorry, there was an error processing your message. Please try again."
            )

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

                # Initial quota check (will be refined for PDFs after page count)
                quota_status = check_quota(db, user, config.TIMEZONE)

                # Get spreadsheet ID
                target_spreadsheet_id = get_user_spreadsheet_id(
                    db,
                    user_tg.id,
                    self.default_spreadsheet_id
                )

                # Generate spreadsheet URL
                if user.google_sheet_id:
                    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{target_spreadsheet_id}"
                else:
                    spreadsheet_url = 'https://bit.ly/invoice-to-gsheets'

            # Check if user is in bulk mode
            is_bulk = self.is_bulk_mode(user_tg.id)

            # Setup Google Sheets client only if not in bulk mode
            if not is_bulk:
                self.setup_google_sheets(self.google_credentials_file, target_spreadsheet_id)

            # Determine file type
            if update.message.photo:
                file = update.message.photo[-1]
                file_type = "image"
                mime_type = "image/jpeg"
                file_extension = ".jpg"
            elif update.message.document:
                file = update.message.document
                mime_type = file.mime_type.lower()

                # Check for allowed file types
                if mime_type.startswith('image/'):
                    file_type = "image"
                    file_extension = ".jpg" if mime_type == "image/jpeg" else ".png"
                elif mime_type == "application/pdf":
                    file_type = "pdf"
                    file_extension = ".pdf"
                else:
                    await update.message.reply_text(
                        "❌ Invalid file type!\n\n"
                        "This bot accepts:\n"
                        "• Images (PNG, JPG, JPEG)\n"
                        "• PDF documents\n\n"
                        "Please upload a supported file type."
                    )
                    return
            else:
                return

            # Download file
            file_obj = await context.bot.get_file(file.file_id)
            temp_path = f"temp_{unix_timestamp}{file_extension}"
            await file_obj.download_to_drive(temp_path)
            file_size = os.path.getsize(temp_path)

            # ============================================================
            # Handle PDF: Each page counts as 1 quota
            # ============================================================
            if file_type == "pdf":
                # Get page count first
                page_count = self.get_pdf_page_count(temp_path)
                
                if page_count == 0:
                    os.remove(temp_path)
                    await update.message.reply_text(
                        "❌ Could not read the PDF file.\n"
                        "Please make sure the file is a valid PDF."
                    )
                    return

                # Check quota and determine how many pages can be processed
                pages_to_process = page_count
                partial_processing = False
                
                with get_db() as db:
                    user = get_user_by_telegram_id(db, user_tg.id)
                    quota_status = check_quota(db, user, config.TIMEZONE)
                    
                    if not quota_status.is_unlimited:
                        remaining_quota = quota_status.daily_limit - quota_status.used_today
                        
                        if remaining_quota <= 0:
                            # No quota left at all
                            log_activity(
                                db,
                                user_id=user.id,
                                file_type="pdf",
                                processing_status="limit_exceeded",
                                error_message=f"Daily quota exceeded (PDF has {page_count} pages)"
                            )
                            db.commit()
                            os.remove(temp_path)
                            
                            await update.message.reply_text(
                                f"⛔ Daily quota exceeded!\n\n"
                                f"You've used {quota_status.used_today}/{quota_status.daily_limit} requests today.\n"
                                f"Your quota will reset tomorrow at midnight WIB.\n\n"
                                f"Want more requests? Use /upgrade to see tier options!"
                            )
                            return
                        
                        if remaining_quota < page_count:
                            # Not enough quota for all pages - process what we can
                            pages_to_process = remaining_quota
                            partial_processing = True

                # Inform user about processing
                if partial_processing:
                    await update.message.reply_text(
                        f"⚠️ Processing PDF with limited quota...\n\n"
                        f"📄 This PDF has {page_count} pages\n"
                        f"📊 Your remaining quota: {pages_to_process}\n"
                        f"🔄 Will process first {pages_to_process} page(s) only\n\n"
                        f"💡 Use /upgrade for more quota to process all pages!"
                    )
                else:
                    await update.message.reply_text(
                        f"🔄 Processing PDF with {page_count} page(s)...\n"
                        f"Each page will be processed separately."
                    )
                
                all_invoice_data = []
                pages_processed = 0
                pages_failed = 0
                pages_skipped = page_count - pages_to_process
                
                for page_num in range(pages_to_process):
                    # Process this page
                    page_data = await self.convert_pdf_page_to_data(temp_path, page_num)
                    
                    # Log activity for this page
                    with get_db() as db:
                        user = get_user_by_telegram_id(db, user_tg.id)
                        
                        if page_data:
                            # Success - add to results and log
                            all_invoice_data.extend(page_data)
                            pages_processed += 1
                            
                            log_activity(
                                db,
                                user_id=user.id,
                                file_type="pdf_page",
                                processing_status="success",
                                file_size_bytes=file_size // page_count,  # Approximate per page
                                items_extracted=len(page_data)
                            )
                        else:
                            # Failed to extract from this page
                            pages_failed += 1
                            
                            log_activity(
                                db,
                                user_id=user.id,
                                file_type="pdf_page",
                                processing_status="failed",
                                file_size_bytes=file_size // page_count,
                                error_message=f"Failed to extract data from page {page_num + 1}"
                            )
                        
                        db.commit()
                    
                    # Progress update for multi-page PDFs
                    if pages_to_process > 1 and (page_num + 1) % 3 == 0:
                        await update.message.reply_text(
                            f"⏳ Progress: {page_num + 1}/{pages_to_process} pages processed..."
                        )

                # Clean up temp file
                os.remove(temp_path)

                # Write data to CSV (bulk mode) or Google Sheets (normal mode) and send response
                if all_invoice_data:
                    items_processed = 0
                    for invoice in all_invoice_data:
                        row_data = [
                            invoice.get('waktu', ''),
                            invoice.get('penjual', ''),
                            invoice.get('barang', ''),
                            invoice.get('harga', 0),
                            invoice.get('jumlah', 0),
                            invoice.get('service', 0),
                            invoice.get('pajak', 0),
                            invoice.get('ppn', 0),
                            invoice.get('subtotal', 0),
                            str(user_tg.id),
                            unix_timestamp
                        ]
                        if is_bulk:
                            self.append_to_bulk_csv(user_tg.id, row_data)
                        else:
                            self.sheet.append_row(row_data)
                        items_processed += 1

                    # Increment bulk request count (1 per page processed)
                    if is_bulk:
                        for _ in range(pages_to_process):
                            self.increment_bulk_request_count(user_tg.id)

                    # Get final quota status
                    with get_db() as db:
                        user = get_user_by_telegram_id(db, user_tg.id)
                        quota_status = check_quota(db, user, config.TIMEZONE)

                    # Build response message
                    skipped_msg = ""
                    if pages_skipped > 0:
                        skipped_msg = (
                            f"⚠️ Pages skipped (quota limit): {pages_skipped}\n"
                            f"📄 Skipped pages: {pages_to_process + 1}-{page_count}\n\n"
                            f"💡 To process remaining pages, wait for quota reset or /upgrade!\n\n"
                        )
                    
                    failed_msg = f"❌ Pages failed: {pages_failed}\n" if pages_failed > 0 else ""

                    if is_bulk:
                        session = self.bulk_sessions[user_tg.id]
                        await update.message.reply_text(
                            f"✅ [BULK] PDF processed {'partially' if pages_skipped > 0 else 'successfully'}!\n\n"
                            f"📊 Summary:\n"
                            f"📄 Pages processed: {pages_processed}/{page_count}\n"
                            f"{failed_msg}"
                            f"{skipped_msg}"
                            f"📝 Items extracted: {items_processed}\n"
                            f"🏪 Seller: {all_invoice_data[0].get('penjual', 'N/A')}\n"
                            f"💰 Total: {sum(inv.get('subtotal', 0) for inv in all_invoice_data):,.2f}\n\n"
                            f"📦 Bulk session:\n"
                            f"• Total items: {session['items_count']}\n"
                            f"• Requests used: {session['requests_count']}\n\n"
                            f"📈 Quota used: {pages_to_process} (1 per page)\n"
                            f"📊 Today's usage: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'}\n\n"
                            f"💡 Send /endbulk to download files."
                        )
                    else:
                        await update.message.reply_text(
                            f"✅ PDF processed {'partially' if pages_skipped > 0 else 'successfully'}!\n\n"
                            f"📊 Summary:\n"
                            f"📄 Pages processed: {pages_processed}/{page_count}\n"
                            f"{failed_msg}"
                            f"{skipped_msg}"
                            f"📝 Items extracted: {items_processed}\n"
                            f"🏪 Seller: {all_invoice_data[0].get('penjual', 'N/A')}\n"
                            f"💰 Total: {sum(inv.get('subtotal', 0) for inv in all_invoice_data):,.2f}\n\n"
                            f"📄 Google Sheets: {spreadsheet_url}\n\n"
                            f"📈 Quota used: {pages_to_process} (1 per page)\n"
                            f"📊 Today's usage: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'}"
                        )
                else:
                    skipped_info = ""
                    if pages_skipped > 0:
                        skipped_info = f"\n\n⚠️ Note: Only processed {pages_to_process}/{page_count} pages due to quota limit."
                    
                    await update.message.reply_text(
                        f"❌ Could not extract data from the PDF.\n"
                        f"Processed {pages_to_process} page(s), but no data could be extracted.\n"
                        f"Please make sure the PDF contains clear invoice/receipt images."
                        f"{skipped_info}"
                    )
                
                return

            # ============================================================
            # Handle Image: 1 quota per image (existing behavior)
            # ============================================================
            # Check quota for single image
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

                await update.message.reply_text(
                    f"⛔ Daily quota exceeded!\n\n"
                    f"You've used {quota_status.used_today}/{quota_status.daily_limit} requests today.\n"
                    f"Your quota will reset tomorrow at midnight WIB.\n\n"
                    f"Want more requests? Use /upgrade to see tier options!"
                )
                return

            if is_bulk:
                await update.message.reply_text("🔄 [BULK] Processing image...")
            else:
                await update.message.reply_text("🔄 Processing image, please wait...")
            
            invoice_data = await self.convert_image_to_data(temp_path, mime_type)
            os.remove(temp_path)

            if invoice_data:
                items_processed = 0
                for invoice in invoice_data:
                    row_data = [
                        invoice.get('waktu', ''),
                        invoice.get('penjual', ''),
                        invoice.get('barang', ''),
                        invoice.get('harga', 0),
                        invoice.get('jumlah', 0),
                        invoice.get('service', 0),
                        invoice.get('pajak', 0),
                        invoice.get('ppn', 0),
                        invoice.get('subtotal', 0),
                        str(user_tg.id),
                        unix_timestamp
                    ]
                    if is_bulk:
                        self.append_to_bulk_csv(user_tg.id, row_data)
                    else:
                        self.sheet.append_row(row_data)
                    items_processed += 1

                # Increment bulk request count (1 for image)
                if is_bulk:
                    self.increment_bulk_request_count(user_tg.id)

                with get_db() as db:
                    user = get_user_by_telegram_id(db, user_tg.id)
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type=file_type,
                        processing_status="success",
                        file_size_bytes=file_size,
                        items_extracted=items_processed
                    )
                    db.commit()
                    quota_status = check_quota(db, user, config.TIMEZONE)

                if is_bulk:
                    session = self.bulk_sessions[user_tg.id]
                    await update.message.reply_text(
                        f"✅ [BULK] Image processed and added to batch!\n\n"
                        f"📊 Summary:\n"
                        f"📝 Items: {items_processed}\n"
                        f"🏪 Seller: {invoice_data[0].get('penjual', 'N/A')}\n"
                        f"💰 Total: {sum(inv.get('subtotal', 0) for inv in invoice_data):,.2f}\n\n"
                        f"📦 Bulk session:\n"
                        f"• Total items: {session['items_count']}\n"
                        f"• Requests used: {session['requests_count']}\n\n"
                        f"📈 Quota: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'}\n\n"
                        f"💡 Send /endbulk to download files."
                    )
                else:
                    await update.message.reply_text(
                        f"✅ Data extracted and saved successfully!\n\n"
                        f"📊 Summary:\n"
                        f"📝 Items processed: {items_processed}\n"
                        f"🏪 Seller: {invoice_data[0].get('penjual', 'N/A')}\n"
                        f"💰 Total: {sum(inv.get('subtotal', 0) for inv in invoice_data):,.2f}\n"
                        f"⏰ Date: {invoice_data[0].get('waktu', 'N/A')}\n\n"
                        f"📄 Google Sheets: {spreadsheet_url}\n\n"
                        f"📈 Quota: {quota_status.used_today}/{quota_status.daily_limit if quota_status.daily_limit != -1 else '∞'} used today"
                    )
            else:
                with get_db() as db:
                    user = get_user_by_telegram_id(db, user_tg.id)
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type=file_type,
                        processing_status="failed",
                        file_size_bytes=file_size,
                        error_message="Could not extract data from file"
                    )
                    db.commit()

                await update.message.reply_text(
                    "❌ Could not extract data from the image.\n"
                    "Please make sure the image is clear and contains a valid receipt/invoice."
                )

        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error in media handler: {e}")
            
            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                if user:
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="image",
                        processing_status="failed",
                        error_message=f"Google Sheets API error: {str(e)[:400]}"
                    )
                    db.commit()

            await update.message.reply_text(
                "❌ Google Sheets Error!\n\n"
                "Data was extracted but could not be saved to Google Sheets. This could be due to:\n"
                "• Rate limiting (too many requests)\n"
                "• Permission issues with the spreadsheet\n"
                "• Temporary Google API issues\n\n"
                "Please try again in a moment. If this persists, contact support."
            )

        except requests.exceptions.Timeout as e:
            logger.error(f"Vision AI timeout in media handler: {e}")
            
            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                if user:
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="image",
                        processing_status="failed",
                        error_message="Vision AI timeout"
                    )
                    db.commit()

            await update.message.reply_text(
                "⏱️ Request Timeout!\n\n"
                "The AI model is taking too long to process your image.\n"
                "This can happen during high traffic or with complex images.\n\n"
                "Please try again in a moment."
            )

        except Exception as e:
            logger.error(f"Error processing media: {e}")

            with get_db() as db:
                user = get_user_by_telegram_id(db, user_tg.id)
                if user:
                    log_activity(
                        db,
                        user_id=user.id,
                        file_type="image",
                        processing_status="failed",
                        error_message=str(e)[:500]
                    )
                    db.commit()

            await update.message.reply_text(
                "❌ Sorry, there was an error processing your file. Please try again."
            )

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")

    def run(self):
        """Start the bot"""
        # Create application
        application = Application.builder().token(self.telegram_token).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("checkid", self.checkid_command))
        application.add_handler(CommandHandler("usage", self.usage_command))
        application.add_handler(CommandHandler("mysheet", self.mysheet_command))
        application.add_handler(CommandHandler("upgrade", self.upgrade_command))

        # Add bulk processing command handlers (Platinum+)
        application.add_handler(CommandHandler("startbulk", self.startbulk_command))
        application.add_handler(CommandHandler("endbulk", self.endbulk_command))

        # Add admin command handlers
        application.add_handler(CommandHandler("settier", self.settier_command))
        application.add_handler(CommandHandler("setsheet", self.setsheet_command))
        application.add_handler(CommandHandler("stats", self.stats_command))

        # Add message handlers
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Add media handlers
        application.add_handler(MessageHandler(
            filters.PHOTO |  # Handle photos
            (filters.Document.IMAGE & filters.Document.MimeType(['image/jpeg', 'image/png'])) |  # Handle image documents
            (filters.Document.PDF & filters.Document.MimeType('application/pdf')),  # Handle PDF documents
            self.handle_media
        ))

        # Add error handler
        application.add_error_handler(self.error_handler)

        # Start the bot
        logger.info("Starting bot with database integration...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Initialize and run the bot"""
    # Validate configuration
    if not all([config.TELEGRAM_BOT_TOKEN, config.GOOGLE_CREDENTIALS_FILE, config.DEFAULT_SPREADSHEET_ID]):
        logger.error("Missing required configuration. Please check config.py")
        return

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Migrate legacy users if any
    if LEGACY_USER_MAPPING:
        logger.info("Migrating legacy users...")
        with get_db() as db:
            migrated_count = migrate_existing_users(db, LEGACY_USER_MAPPING)
            db.commit()
        logger.info(f"Migrated {migrated_count} legacy users")

    # Create and run bot
    try:
        bot = TelegramInvoiceBotWithDB(
            telegram_token=config.TELEGRAM_BOT_TOKEN,
            google_credentials_file=config.GOOGLE_CREDENTIALS_FILE,
            default_spreadsheet_id=config.DEFAULT_SPREADSHEET_ID
        )
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == '__main__':
    main()
