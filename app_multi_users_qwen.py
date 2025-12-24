import os
import time
import logging
import gspread
import json
import pandas as pd
import base64
import requests
import fitz  # PyMuPDF for PDF processing
from PIL import Image
import io

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
from datetime import datetime
from pydantic import BaseModel
from credentials import TELEGRAM_BOT_TOKEN, GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID, GEMINI_API_KEY, SPREADSHEET_ID_RIZAL, CHUTES_API_KEY
from prompts import DEFAULT_PROMPT, TEXT_PROMPT

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramGoogleSheetsBot:
    @staticmethod
    async def convert_image_to_data(filepath, mime_type):
        """Convert image to structured data using Chutes API with Qwen model"""
        try:
            with open(filepath, 'rb') as f:
                image_bytes = f.read()
            
            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Prepare the prompt for Qwen model
            prompt = DEFAULT_PROMPT + "\n\nBerikan respons dalam format JSON array."
            
            # Make API request to Chutes API
            headers = {
                "Authorization": f"Bearer {CHUTES_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "Qwen/Qwen3-VL-235B-A22B-Instruct",
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
                "temperature": 0.1,  # Lower temperature for faster, more deterministic responses
                "max_tokens": 2000,  # Limit response length
            }
            
            response = requests.post(
                "https://llm.chutes.ai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=(60, 120)  # (connect timeout, read timeout) - 120 seconds read timeout for vision models
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
    async def convert_pdf_to_data(filepath):
        """Convert PDF to structured data by processing each page as an image"""
        try:
            # Open PDF file
            pdf_document = fitz.open(filepath)
            all_invoice_data = []
            
            # Process each page
            for page_num in range(len(pdf_document)):
                # Get the page
                page = pdf_document[page_num]
                
                # Convert page to image
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                # Convert to base64
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                # Prepare prompt for Qwen model
                prompt = DEFAULT_PROMPT + "\n\nBerikan respons dalam format JSON array."
                
                # Make API request to Chutes API
                headers = {
                    "Authorization": f"Bearer {CHUTES_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "Qwen/Qwen3-VL-235B-A22B-Instruct",
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
                    "temperature": 0.1,  # Lower temperature for faster, more deterministic responses
                    "max_tokens": 2000,  # Limit response length
                }
                
                response = requests.post(
                    "https://llm.chutes.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=(60, 120)  # (connect timeout, read timeout) - 120 seconds read timeout for vision models
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"PDF API Response structure: {result.keys() if isinstance(result, dict) else 'Not a dict'}")

                    # Validate response structure
                    if not isinstance(result, dict) or 'choices' not in result:
                        logger.error(f"Invalid PDF API response structure: {result}")
                        continue

                    if not result['choices'] or len(result['choices']) == 0:
                        logger.error(f"Empty choices in PDF API response: {result}")
                        continue

                    content = result['choices'][0].get('message', {}).get('content')

                    if content is None:
                        logger.error(f"Content is None in PDF API response: {result}")
                        continue

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
                        
                        # Add page info to each invoice item for tracking
                        for item in data:
                            item['page'] = page_num + 1
                        
                        all_invoice_data.extend(data)
                        
                    except Exception as e:
                        logger.error(f"Error parsing JSON response from page {page_num + 1}: {e}")
                        logger.error(f"Response content: {content}")
                else:
                    logger.error(f"API request failed for page {page_num + 1} with status code {response.status_code}")
                    logger.error(f"Response: {response.text}")
            
            # Close PDF document
            pdf_document.close()
            
            # Return all collected data
            if all_invoice_data:
                return all_invoice_data
            else:
                return None
                
        except requests.exceptions.Timeout as e:
            logger.error(f"PDF processing timed out: {e}")
            logger.error("The model is taking too long to respond. Please try again.")
            return None
        except Exception as e:
            logger.error(f"Error converting PDF to data: {e}")
            return None
    
    @staticmethod
    async def convert_text_to_data(text_message):
        """Convert text message to structured data using Chutes API with Qwen model"""
        try:
            # Prepare the prompt for Qwen model
            prompt = TEXT_PROMPT + f"\n\nTeks pesan:\n{text_message}\n\nBerikan respons dalam format JSON array."
            
            # Make API request to Chutes API
            headers = {
                "Authorization": f"Bearer {CHUTES_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "Qwen/Qwen3-VL-235B-A22B-Instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1,  # Lower temperature for faster, more deterministic responses
                "max_tokens": 2000,  # Limit response length
            }
            
            response = requests.post(
                "https://llm.chutes.ai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=(60, 120)  # (connect timeout, read timeout)
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Text API Response structure: {result.keys() if isinstance(result, dict) else 'Not a dict'}")

                # Validate response structure
                if not isinstance(result, dict) or 'choices' not in result:
                    logger.error(f"Invalid Text API response structure: {result}")
                    return None

                if not result['choices'] or len(result['choices']) == 0:
                    logger.error(f"Empty choices in Text API response: {result}")
                    return None

                content = result['choices'][0].get('message', {}).get('content')

                if content is None:
                    logger.error(f"Content is None in Text API response: {result}")
                    return None

                # Parse JSON response
                try:
                    # Extract JSON from markdown code blocks if present
                    if content.startswith('```json'):
                        # Find the start and end of the JSON content
                        start_idx = content.find('[')
                        end_idx = content.rfind(']') + 1
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
            logger.error(f"Error converting text to data: {e}")
            return None
    
    @staticmethod
    def get_file_extension(filename):
        """
        Gets the file extension and checks if it's one of the allowed image types.

        Args:
            filename: The name of the file.

        Returns:
            tuple: (file_extension, mime_type) if it's an allowed image type, otherwise (None, None)
        """
        allowed_extensions = ['png', 'jpeg', 'jpg', 'webp', 'heic', 'heif', 'pdf']
        _, file_extension = os.path.splitext(filename)
        if file_extension:
            file_extension = file_extension[1:].lower()  # Remove the leading dot and convert to lowercase
            if file_extension in allowed_extensions:
                if file_extension == 'png': mime_type = 'image/png'
                elif file_extension == 'webp': mime_type = 'image/webp'
                elif file_extension == 'heic': mime_type = 'image/heif'
                elif file_extension == 'heif': mime_type = 'image/heif'
                elif file_extension == 'pdf': mime_type = 'application/pdf'
                else: mime_type = 'image/jpeg'

                return [file_extension, mime_type]
        return [None, None]

    def __init__(self, telegram_token, google_credentials_file, spreadsheet_id):
        self.telegram_token = telegram_token
        self.default_spreadsheet_id = spreadsheet_id  # Store the default spreadsheet ID
        self.upload_dir = 'uploads'
        # Define user-specific spreadsheet IDs
        self.IDS_SPREADSHEETS = {
            '33410730': '1OwBzgxICijfhhZ2TttbouKhdSlDLFyHYixwd7Iwo-UU'
            # Add more user IDs and their corresponding spreadsheet IDs here
            # Example: '123456789': 'spreadsheet_id_for_user_123456789'
        }

        # Initialize Google Sheets client with the default spreadsheet
        self.setup_google_sheets(google_credentials_file, spreadsheet_id)

        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
            logger.info(f"Created upload directory: {self.upload_dir}")

    def setup_google_sheets(self, credentials_file, spreadsheet_id=None):
        """Setup Google Sheets API connection"""
        # Use the provided spreadsheet_id or fall back to the default one
        target_spreadsheet_id = spreadsheet_id if spreadsheet_id else self.default_spreadsheet_id
        
        try:
            print(f"Attempting to load credentials from: {credentials_file}")

            # Check if credentials file exists
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(f"Credentials file not found: {credentials_file}")

            # Define the scope
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]

            # Load credentials
            print("Loading Google credentials...")
            creds = Credentials.from_service_account_file(credentials_file, scopes=scope)

            print("Authorizing Google Sheets client...")
            self.gc = gspread.authorize(creds)

            # Open the spreadsheet
            print(f"Opening spreadsheet with ID: {target_spreadsheet_id}")
            self.sheet = self.gc.open_by_key(target_spreadsheet_id).sheet1

            # Define expected headers
            expected_headers = [
                'waktu',
                'penjual',
                'barang',
                'harga',
                'jumlah',
                'service',
                'pajak',
                'ppn',
                'subtotal',
                'User ID',
                'Unix Timestamp'
            ]

            # Check if sheet is empty or needs header update
            try:
                current_headers = self.sheet.row_values(1)  # Get first row
                
                # If sheet is empty or headers don't match
                if not current_headers or current_headers != expected_headers:
                    # Clear existing content if any
                    if current_headers:
                        self.sheet.clear()
                    
                    # Set new headers
                    self.sheet.append_row(expected_headers)
                    print("✅ Headers created successfully!")
                else:
                    print("✅ Headers already exist and match expected format!")

            except gspread.exceptions.APIError as e:
                print(f"Error checking headers: {e}")
                raise

            print("✅ Google Sheets setup completed successfully!")
            
        except FileNotFoundError as e:
            print(f"❌ Credentials file error: {e}")
            raise
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Spreadsheet not found. Check your spreadsheet ID: {target_spreadsheet_id}")
            raise
        except gspread.exceptions.APIError as e:
            print(f"❌ Google Sheets API error: {e}")
            print("This might be due to:")
            print("1. API not enabled in Google Cloud Console")
            print("2. Service account doesn't have access to the spreadsheet")
            print("3. Invalid credentials")
            raise
        except Exception as e:
            print(f"❌ Unexpected error setting up Google Sheets: {e}")
            print(f"Error type: {type(e).__name__}")
            raise
                

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = (
            "🤖 Welcome to the Google Sheets Bot!\n\n"
            "Send me any message and I'll save it to Google Sheets.\n\n"
            "Available commands:\n"
            "/start - Show this welcome message\n"
            "/help - Show help information\n"
            "/status - Check bot status\n"
            "/checkid - Get your Telegram ID and username\n\n"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = (
            "📋 How to use this bot:\n\n"
            "1. Simply send any text message\n"
            "2. The bot will automatically save it to Google Sheets\n"
            "3. Each entry includes timestamp, your user info, and message\n\n"
            "Commands:\n"
            "/start - Welcome message\n"
            "/help - This help message\n"
            "/status - Check if bot is working\n"
            "/checkid - Get your Telegram ID and username\n\n"
        )
        await update.message.reply_text(help_message)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            # Test Google Sheets connection
            row_count = len(self.sheet.get_all_records())
            status_message = f"✅ Bot is working!\n📊 Total records in sheet: {row_count}"
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
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages and save to Google Sheets"""
        try:
            # Extract message data
            user = update.effective_user
            message_text = update.message.text
            unix_timestamp = int(time.time())  # Unix timestamp for filename

            # Determine the spreadsheet ID to use and generate the URL
            user_spreadsheet_id = self.IDS_SPREADSHEETS.get(str(user.id))
            if user_spreadsheet_id:
                target_spreadsheet_id = user_spreadsheet_id
                print(f"Using custom spreadsheet ID for user {user.id}: {user_spreadsheet_id}")
                spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{target_spreadsheet_id}"
            else:
                target_spreadsheet_id = self.default_spreadsheet_id
                print(f"Using default spreadsheet ID for user {user.id}: {self.default_spreadsheet_id}")
                spreadsheet_url = 'https://bit.ly/invoice-to-gsheets'
            
            # Setup Google Sheets client with the determined spreadsheet ID
            self.setup_google_sheets(GOOGLE_CREDENTIALS_FILE, target_spreadsheet_id)

            # Process text to extract invoice data
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
                        str(user.id),
                        unix_timestamp
                    ]

                    # Append to Google Sheets
                    self.sheet.append_row(row_data)
                    items_processed += 1

                # Send confirmation with summary of all processed items and the correct spreadsheet URL
                await update.message.reply_text(
                    f"✅ Data extracted and saved successfully!\n\n"
                    f"📊 Summary:\n"
                    f"📝 Items processed: {items_processed}\n"
                    f"🏪 Seller: {invoice_data[0].get('penjual', 'N/A')}\n"
                    f"💰 Total (all items): {sum(inv.get('subtotal', 0) for inv in invoice_data):,.2f}\n"
                    f"⏰ Date: {invoice_data[0].get('waktu', 'N/A')}\n"
                    f"See the full data in Google Sheets: {spreadsheet_url}\n\n"
                )

            else:
                # If no invoice data found, send the original message
                await update.message.reply_text(
                    f"Hi, please upload a photo or document containing your invoice/receipt.\n"
                    f"The data will be extracted and saved to Google Sheets https://bit.ly/invoice-to-gsheets.\n\n"
                )

            logger.info(f"Processed message from {user.username}: {message_text}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text(
                "❌ Sorry, there was an error processing your message. Please try again."
            )

    async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photos and documents"""
        try:
            user = update.effective_user
            unix_timestamp = int(time.time())

            spreadsheet_url = 'https://bit.ly/invoice-to-gsheets'
            # Determine the spreadsheet ID to use and generate the URL
            user_spreadsheet_id = self.IDS_SPREADSHEETS.get(str(user.id))
            if user_spreadsheet_id:
                target_spreadsheet_id = user_spreadsheet_id
                print(f"Using custom spreadsheet ID for user {user.id}: {user_spreadsheet_id}")
                spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{target_spreadsheet_id}"
            else:
                target_spreadsheet_id = self.default_spreadsheet_id
                print(f"Using default spreadsheet ID for user {user.id}: {self.default_spreadsheet_id}")

            # Setup Google Sheets client with the determined spreadsheet ID
            self.setup_google_sheets(GOOGLE_CREDENTIALS_FILE, target_spreadsheet_id)

            # Process images and PDFs
            if update.message.photo:
                file = update.message.photo[-1]
                file_type = "photo"
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

            # Process image or PDF
            await update.message.reply_text("🔄 Processing document, please wait...")
            
            if file_type == "pdf":
                # Process PDF - convert each page to image and extract data
                invoice_data = await self.convert_pdf_to_data(temp_path)
            else:
                # Process regular image
                invoice_data = await self.convert_image_to_data(temp_path, mime_type)

            # Clean up temp file
            os.remove(temp_path)

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
                        str(user.id),
                        unix_timestamp
                    ]

                    # Append to Google Sheets
                    self.sheet.append_row(row_data)
                    items_processed += 1

                # Send confirmation with summary of all processed items and the correct spreadsheet URL
                await update.message.reply_text(
                    f"✅ Data extracted and saved successfully!\n\n"
                    f"📊 Summary:\n"
                    f"📝 Items processed: {items_processed}\n"
                    f"🏪 Seller: {invoice_data[0].get('penjual', 'N/A')}\n"
                    f"💰 Total (all items): {sum(inv.get('subtotal', 0) for inv in invoice_data):,.2f}\n"
                    f"⏰ Date: {invoice_data[0].get('waktu', 'N/A')}\n"
                    f"See the full data in Google Sheets: {spreadsheet_url}\n\n"
                )

            else:
                await update.message.reply_text(
                    "❌ Could not extract data from the image.\n"
                    "Please make sure the image is clear and contains a valid receipt/invoice."
                )

        except Exception as e:
            logger.error(f"Error processing image: {e}")
            await update.message.reply_text(
                "❌ Sorry, there was an error processing your image. Please try again."
            )
            
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")

    def run(self):
        """Start the bot"""
        # Create application
        application = Application.builder().token(self.telegram_token).build()

        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("checkid", self.checkid_command))
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
        logger.info("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    # Validate configuration
    if not all([TELEGRAM_BOT_TOKEN, GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID]):
        logger.error("Missing required configuration. Please set all required variables.")
        return

    # Create and run bot
    try:
        bot = TelegramGoogleSheetsBot(
            telegram_token=TELEGRAM_BOT_TOKEN,
            google_credentials_file=GOOGLE_CREDENTIALS_FILE,
            spreadsheet_id=SPREADSHEET_ID
        )
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()