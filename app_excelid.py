import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import base64
import requests
from typing import Optional, Dict, List, Tuple
from excelid_credentials import NANOGPT_API_KEY, TELEGRAM_BOT_TOKEN
import io
from PIL import Image
from datetime import datetime, timedelta
from dataclasses import dataclass, field

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============== SESSION MANAGER ==============
# Handles image buffering and conversation history for multi-image Q&A

@dataclass
class BufferedImage:
    """Represents a buffered image waiting to be processed"""
    file_id: str
    message_id: int
    timestamp: datetime
    base64_data: Optional[str] = None  # Cached base64 data

@dataclass
class ConversationSession:
    """User session with buffered images and conversation history"""
    images: List[BufferedImage] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.now)
    is_processing_started: bool = False  # True after first question asked
    conversation_history: List[dict] = field(default_factory=list)

# Global session store: {(user_id, chat_id): ConversationSession}
sessions: Dict[Tuple[int, int], ConversationSession] = {}

# Configuration
SESSION_TIMEOUT_MINUTES = 30
MAX_IMAGES_PER_SESSION = 10
MAX_HISTORY_PAIRS = 10


def get_session(user_id: int, chat_id: int) -> ConversationSession:
    """Get or create a session for a user in a specific chat"""
    key = (user_id, chat_id)
    if key not in sessions:
        sessions[key] = ConversationSession()
    return sessions[key]


def is_session_expired(session: ConversationSession) -> bool:
    """Check if session has expired due to inactivity"""
    return datetime.now() - session.last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES)


def add_image_to_session(user_id: int, chat_id: int, file_id: str, message_id: int) -> Tuple[bool, int]:
    """
    Add image to session buffer.
    Returns: (is_new_session, total_image_count)
    """
    session = get_session(user_id, chat_id)
    is_new_session = False
    
    # New image after questions started OR expired = fresh session
    if is_session_expired(session) or session.is_processing_started:
        session.images = []
        session.conversation_history = []
        session.is_processing_started = False
        is_new_session = True
    
    # Limit buffer size (remove oldest if full)
    if len(session.images) >= MAX_IMAGES_PER_SESSION:
        session.images.pop(0)
    
    session.images.append(BufferedImage(
        file_id=file_id,
        message_id=message_id,
        timestamp=datetime.now()
    ))
    session.last_activity = datetime.now()
    
    return is_new_session, len(session.images)


def get_session_for_question(user_id: int, chat_id: int) -> Tuple[List[BufferedImage], List[dict]]:
    """
    Get images and history for processing a question.
    Marks session as started (for follow-up tracking).
    Returns: (images, conversation_history)
    """
    session = get_session(user_id, chat_id)
    
    if is_session_expired(session) or not session.images:
        return [], []
    
    session.is_processing_started = True
    session.last_activity = datetime.now()
    
    return session.images.copy(), session.conversation_history.copy()


def add_to_history(user_id: int, chat_id: int, question: str, answer: str):
    """Add Q&A pair to conversation history for follow-up context"""
    session = get_session(user_id, chat_id)
    
    session.conversation_history.append({"role": "user", "content": question})
    session.conversation_history.append({"role": "assistant", "content": answer})
    
    # Trim if too long
    max_messages = MAX_HISTORY_PAIRS * 2
    if len(session.conversation_history) > max_messages:
        session.conversation_history = session.conversation_history[-max_messages:]


def clear_session(user_id: int, chat_id: int):
    """Manually clear a session"""
    key = (user_id, chat_id)
    if key in sessions:
        del sessions[key]


def get_session_info(user_id: int, chat_id: int) -> dict:
    """Get session stats for /status command"""
    session = get_session(user_id, chat_id)
    
    if is_session_expired(session):
        return {"images": 0, "history": 0, "active": False, "expired": True}
    
    return {
        "images": len(session.images),
        "history": len(session.conversation_history) // 2,
        "active": session.is_processing_started,
        "expired": False
    }

# ============== END SESSION MANAGER ==============


class QuestionAnswerBot:
    def __init__(self, telegram_token: str, nanogpt_api_key: Optional[str] = None):
        self.telegram_token = telegram_token
        self.nanogpt_api_key = nanogpt_api_key
        self.base_url = "https://nano-gpt.com/api/v1"
        self.model = "qwen3-vl-235b-a22b-instruct-original"
        self.api_available = bool(nanogpt_api_key)
        
        if self.api_available:
            logger.info(f"NanoGPT API initialized with model: {self.model}")
        else:
            logger.warning("NanoGPT API key not provided, using fallback responses")

    def escape_markdown(self, text: str) -> str:
        """Escape special characters for MarkdownV2"""
        special_chars = ['>', '#', '[', ']', '(', ')', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text

    def compress_image(self, image_base64: str, max_size: int = 1024, quality: int = 75) -> str:
        """Compress image to reduce processing time"""
        try:
            # Decode base64
            image_data = base64.b64decode(image_base64)
            
            # Open with PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary (for PNG with transparency)
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            
            # Resize if too large
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.LANCZOS)
            
            # Compress
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=quality, optimize=True)
            
            # Re-encode to base64
            return base64.b64encode(output.getvalue()).decode('utf-8')
        except Exception as e:
            logger.warning(f"Image compression failed: {e}, using original")
            return image_base64

    def get_current_time(self) -> str:
        """Get current time in Indonesia format"""
        from datetime import datetime
        from pytz import timezone
    
        # Set timezone to Indonesia/Jakarta
        jakarta_tz = timezone('Asia/Jakarta')
        current_time = datetime.now(jakarta_tz)
        
        # Format time in Indonesian style
        weekdays = {
            0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis',
            4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'
        }
        
        day_name = weekdays[current_time.weekday()]
        formatted_time = current_time.strftime(f"{day_name}, %d-%m-%Y %H:%M:%S WIB")
        
        return formatted_time 
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "Hello! I'm a Q&A bot powered by NanoGPT with Qwen Vision AI.\n\n"
            "🔹 Ask me any question about Excel or Google Sheets\n"
            "🔹 Send me an image and I'll analyze it for you\n"
            "🔹 Works in groups and private chats\n\n"
            "Model: Qwen/Qwen3-VL-235B-A22B-Instruct (Vision-capable)"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🤖 *NanoGPT Excel & Sheets Assistant*
Model: Qwen/Qwen3-VL-235B-A22B-Instruct

*Available commands:*
/start - Start the bot
/help - Show this help message
/status - Check your current session (buffered images)
/clear - Clear your buffered images

*Multi-Image Q&A Flow:*
1. Send one or more images
2. Then ask your question
3. Ask follow-up questions about the same images!
4. Sending a NEW image starts a fresh session

*Text Questions:*
Just send me any question and I'll answer!
Examples:
- "Bagaimana cara membuat VLOOKUP?"
- "Rumus untuk menghitung rata-rata?"
- "Cara menggunakan pivot table?"

*Image Analysis:*
📷 Send me images and then ask:
- "What's the total from these invoices?"
- "Compare these two screenshots"
- "Explain what's wrong here"

In groups, @mention me to get my attention!
        """
        await update.message.reply_text(help_text)
    
    async def answer_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle questions from users - processes buffered images if available"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_question = update.message.text
        user_name = update.effective_user.first_name
        is_group = update.effective_chat.type in ['group', 'supergroup']
        
        # Skip if message is a command
        if user_question.startswith('/'):
            return
        
        # Check if bot is mentioned in groups
        if is_group:
            bot_username = context.bot.username
            if f"@{bot_username}" not in user_question:
                return  # Only respond when mentioned in groups
            # Remove bot mention from question
            user_question = user_question.replace(f"@{bot_username}", "").strip()
        
        if not user_question:
            return  # Empty question after removing mention
        
        try:
            # Get buffered images and conversation history
            buffered_images, history = get_session_for_question(user_id, chat_id)
            
            # Check if user is replying to an image (especially useful in groups)
            reply_to_image = None
            if update.message.reply_to_message and update.message.reply_to_message.photo:
                reply_to_image = update.message.reply_to_message.photo[-1]  # Best quality
                logger.info(f"User {user_name} replied to an image with question")
            
            # Show typing indicator
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action="typing"
            )
            
            # Determine which images to use: buffered > reply_to > none
            if buffered_images:
                # Process with buffered images!
                is_followup = len(history) > 0
                
                if is_followup:
                    await update.message.reply_text(
                        f"🔄 Processing follow-up question..."
                    )
                else:
                    await update.message.reply_text(
                        f"🔄 Processing {len(buffered_images)} image(s) with your question..."
                    )
                
                # Download and convert all buffered images
                images_base64 = []
                for img in buffered_images:
                    try:
                        photo_file = await context.bot.get_file(img.file_id)
                        photo_bytes = await photo_file.download_as_bytearray()
                        image_b64 = base64.b64encode(photo_bytes).decode('utf-8')
                        image_b64 = self.compress_image(image_b64, max_size=1024, quality=75)
                        images_base64.append(image_b64)
                    except Exception as e:
                        logger.warning(f"Failed to download buffered image: {e}")
                
                if not images_base64:
                    await update.message.reply_text(
                        "⚠️ Could not retrieve buffered images. Please send them again."
                    )
                    return
                
                # Generate answer with images and history
                answer = await self.generate_answer(
                    user_question, 
                    images_base64=images_base64,
                    conversation_history=history
                )
                
                # Save to history for follow-up questions
                add_to_history(user_id, chat_id, user_question, answer)
                
                logger.info(f"User {user_name} asked about {len(images_base64)} images: {user_question}")
            
            elif reply_to_image:
                # No buffered images, but user replied to an image - use that!
                await update.message.reply_text("🔄 Processing the image you replied to...")
                
                try:
                    photo_file = await context.bot.get_file(reply_to_image.file_id)
                    photo_bytes = await photo_file.download_as_bytearray()
                    image_b64 = base64.b64encode(photo_bytes).decode('utf-8')
                    image_b64 = self.compress_image(image_b64, max_size=1024, quality=75)
                    
                    # Also add this image to the session for follow-ups
                    add_image_to_session(user_id, chat_id, reply_to_image.file_id, 
                                        update.message.reply_to_message.message_id)
                    # Mark session as started
                    get_session_for_question(user_id, chat_id)
                    
                    answer = await self.generate_answer(
                        user_question,
                        images_base64=[image_b64]
                    )
                    
                    # Save to history for follow-up questions
                    add_to_history(user_id, chat_id, user_question, answer)
                    
                    logger.info(f"User {user_name} replied to image with question: {user_question}")
                    
                except Exception as e:
                    logger.error(f"Failed to process reply-to image: {e}")
                    await update.message.reply_text(
                        "⚠️ Could not retrieve the image you replied to. Please send it directly."
                    )
                    return
            else:
                # No images - regular text question
                answer = await self.generate_answer(user_question)
                logger.info(f"User {user_name} asked (no images): {user_question}")
            
            await self._send_response(update, answer)
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error while processing your question. Please try again!"
            )
    
    async def _send_response(self, update: Update, answer: str):
        """Send response with proper formatting and chunking"""
        try:
            escaped_answer = self.escape_markdown(answer)
            
            # Split long messages if needed
            if len(escaped_answer) > 4096:
                chunks = [escaped_answer[i:i+4096] for i in range(0, len(escaped_answer), 4096)]
                for chunk in chunks:
                    await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(escaped_answer, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            # Fallback to plain text if markdown fails
            logger.warning(f"Markdown formatting failed: {e}, sending plain text")
            if len(answer) > 4096:
                chunks = [answer[i:i+4096] for i in range(0, len(answer), 4096)]
                for chunk in chunks:
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(answer)
    
    async def generate_answer(
        self, 
        question: str, 
        images_base64: Optional[List[str]] = None,
        conversation_history: Optional[List[dict]] = None
    ) -> str:
        """Generate answer to the question using NanoGPT with Qwen VL model
        
        Args:
            question: The user's question
            images_base64: List of base64 encoded images
            conversation_history: Previous Q&A pairs for context
        """
        
        # If NanoGPT API is available, use it
        if self.api_available:
            try:
                headers = {
                    "Authorization": f"Bearer {self.nanogpt_api_key}",
                    "Content-Type": "application/json"
                }
                
                system_prompt = '''Anda adalah asisten Excel dan Google Sheets.
Jawab pertanyaan dengan jelas dan singkat.
Selalu jawab dalam Bahasa Indonesia.
Gunakan format teks berikut:
- Teks penting dalam *teks tebal*
- Istilah teknis dalam _teks miring_
- Rumus atau kode dalam `kode`
- Contoh kode panjang dalam blok ```kode```
- Buat poin-poin dengan •'''
                
                # Build messages array
                messages = [{"role": "system", "content": system_prompt}]
                
                # Add conversation history if available (for follow-up questions)
                if conversation_history:
                    messages.extend(conversation_history)
                
                # Build user message content
                if images_base64:
                    # Multi-image support
                    user_content = []
                    
                    # Add text first
                    user_content.append({
                        "type": "text", 
                        "text": question if question else "Jelaskan gambar-gambar ini."
                    })
                    
                    # Add all images
                    for img_b64 in images_base64:
                        user_content.append({
                            "type": "image_url", 
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}", 
                                "detail": "high"
                            }
                        })
                    
                    messages.append({"role": "user", "content": user_content})
                else:
                    messages.append({"role": "user", "content": question})
                
                data = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 4096
                }
                
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=600  # Increased to 10 minutes for large VL models
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("choices") and len(result["choices"]) > 0:
                        content = result["choices"][0].get("message", {}).get("content", "")
                        if content:
                            return content.strip()
                    logger.warning("NanoGPT returned empty response")
                    return self.fallback_answer(question)
                else:
                    logger.error(f"NanoGPT API error: {response.status_code} - {response.text}")
                    return self.fallback_answer(question)
                    
            except Exception as e:
                logger.error(f"NanoGPT API error: {e}")
                return self.fallback_answer(question)
        else:
            return self.fallback_answer(question)
    
    def fallback_answer(self, question: str) -> str:
        """Provide fallback answers when AI API is not available"""
        question_lower = question.lower()
        
        # Simple keyword-based responses
        if any(word in question_lower for word in ['hello', 'hi', 'hey', 'greetings']):
            return "Hello! How can I help you today? 😊"
        
        elif any(word in question_lower for word in ['time', 'date', 'today', 'waktu', 'jam', 'sekarang', 'tanggal', 'hari ini']):
            current_time = self.get_current_time()
            return f"🕐 Waktu saat ini: {current_time}"

        elif any(word in question_lower for word in ['python', 'programming', 'code']):
            return """🐍 Python is a high-level programming language known for its simplicity and readability. 
It's widely used for:
• Web development
• Data science & AI
• Automation & scripting
• Desktop applications

Great for beginners and professionals alike!"""
        
        elif any(word in question_lower for word in ['weather', 'temperature', 'climate']):
            return "🌤️ I don't have access to real-time weather data, but you can check weather apps or websites for current conditions!"
        
        elif any(word in question_lower for word in ['time', 'date', 'today']):
            from datetime import datetime
            now = datetime.now()
            return f"🕐 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        
        elif any(word in question_lower for word in ['joke', 'funny', 'humor']):
            return "😄 Why don't scientists trust atoms? Because they make up everything!"
        
        elif any(word in question_lower for word in ['help', 'support', 'assistance']):
            return """🤖 I'm here to help! You can ask me about:
• General knowledge questions
• Programming and technology
• Explanations of concepts
• Creative writing
• And much more!

Just type your question and I'll do my best to answer!"""
        
        else:
            return """🤔 I'm a Q&A bot powered by AI! While I don't have access to advanced AI right now, 
I can help with basic questions. For complex queries, you might want to search online or consult specific resources.

Try asking me something specific, and I'll do my best to help!"""
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")
    
    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Buffer images for later processing with questions"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        is_group = update.effective_chat.type in ['group', 'supergroup']
        caption = update.message.caption or ""
        
        # In groups: if image has caption with @mention, process immediately (old behavior)
        # Otherwise, buffer the image for later question
        if is_group:
            bot_username = context.bot.username
            if caption and f"@{bot_username}" in caption:
                # Immediate processing with caption as question
                await self._process_single_image_immediately(update, context, caption)
                return
            # No mention = silent buffer (don't spam the group)
        
        try:
            # Get the photo file_id
            photo = update.message.photo[-1]
            
            # Add to session buffer
            is_new_session, image_count = add_image_to_session(
                user_id, chat_id, photo.file_id, update.message.message_id
            )
            
            logger.info(f"User {user_name} sent image (buffered: {image_count}, new_session: {is_new_session})")
            
            if is_group:
                # Only notify on new session start in groups
                if is_new_session:
                    await update.message.reply_text(
                        f"📸 New session started!\n"
                        f"Send more images, then @{context.bot.username} your question."
                    )
                # Otherwise silent
            else:
                # Direct chat: always acknowledge
                if is_new_session:
                    await update.message.reply_text(
                        f"📸 New session! ({image_count} image)\n"
                        f"Send more images or type your question."
                    )
                else:
                    await update.message.reply_text(
                        f"📸 Image added ({image_count} buffered)"
                    )
                
        except Exception as e:
            logger.error(f"Error buffering image: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error. Please try again!"
            )
    
    async def _process_single_image_immediately(self, update: Update, context: ContextTypes.DEFAULT_TYPE, caption: str):
        """Process a single image immediately (for backwards compatibility with caption mentions)"""
        user_name = update.effective_user.first_name
        bot_username = context.bot.username
        
        # Remove mention from caption
        question = caption.replace(f"@{bot_username}", "").strip()
        
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            # Get the photo
            photo = update.message.photo[-1]
            photo_file = await context.bot.get_file(photo.file_id)
            photo_bytes = await photo_file.download_as_bytearray()
            
            # Convert and compress
            image_base64 = base64.b64encode(photo_bytes).decode('utf-8')
            image_base64 = self.compress_image(image_base64, max_size=1024, quality=75)
            
            # Process
            question = question if question else "Jelaskan gambar ini dalam Bahasa Indonesia."
            answer = await self.generate_answer(question, images_base64=[image_base64])
            
            logger.info(f"User {user_name} sent image with immediate caption: {question}")
            
            await self._send_response(update, answer)
                
        except Exception as e:
            logger.error(f"Error processing image immediately: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error while processing your image. Please try again!"
            )
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command - clears the user's image buffer"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Get info before clearing
        info = get_session_info(user_id, chat_id)
        
        clear_session(user_id, chat_id)
        
        if info["images"] > 0:
            await update.message.reply_text(
                f"🧹 Session cleared!\n"
                f"Removed {info['images']} buffered image(s) and {info['history']} Q&A pair(s).\n"
                f"Send new images to start fresh."
            )
        else:
            await update.message.reply_text(
                "🧹 Session was already empty. Send images to start!"
            )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - shows current session info"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_group = update.effective_chat.type in ['group', 'supergroup']
        
        info = get_session_info(user_id, chat_id)
        
        if info["expired"]:
            await update.message.reply_text(
                "📊 *Session Status*\n\n"
                "No active session (expired or empty).\n"
                "Send images to start a new session!"
            )
            return
        
        status_emoji = "🟢" if info["active"] else "🟡"
        status_text = "Active (questions asked)" if info["active"] else "Waiting for question"
        
        if is_group:
            mention_hint = f"Type @{context.bot.username} followed by your question."
        else:
            mention_hint = "Just type your question!"
        
        await update.message.reply_text(
            f"📊 *Session Status*\n\n"
            f"{status_emoji} Status: {status_text}\n"
            f"🖼️ Buffered images: {info['images']}\n"
            f"💬 Conversation history: {info['history']} Q&A pairs\n\n"
            f"💡 {mention_hint}\n"
            f"Use /clear to start fresh."
        )

    def run(self):
        """Start the bot"""
        # Create application
        application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("clear", self.clear_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.answer_question))
        application.add_handler(MessageHandler(filters.PHOTO, self.handle_image))
        
        # Add error handler
        application.add_error_handler(self.error_handler)
        
        # Start the bot
        logger.info(f"Starting NanoGPT-powered Telegram bot with model: {self.model}...")
        logger.info(f"Session timeout: {SESSION_TIMEOUT_MINUTES} minutes, Max images: {MAX_IMAGES_PER_SESSION}")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    # Configuration
    
    if TELEGRAM_BOT_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN_HERE':
        print("❌ Please set your Telegram bot token!")
        print("1. Create a bot with @BotFather on Telegram")
        print("2. Set TELEGRAM_BOT_TOKEN environment variable or replace in code")
        return
    
    if not NANOGPT_API_KEY:
        print("⚠️  No NanoGPT API key found. Bot will use fallback responses.")
        print("To get full AI capabilities:")
        print("1. Go to https://nano-gpt.com/api")
        print("2. Create an API key")
        print("3. Set NANOGPT_API_KEY in excelid_credentials.py")
    else:
        print("✅ NanoGPT API key found. Using Qwen/Qwen3-VL-235B-A22B-Instruct model with vision capabilities.")
    
    # Create and run bot
    bot = QuestionAnswerBot(TELEGRAM_BOT_TOKEN, NANOGPT_API_KEY)
    bot.run()

if __name__ == '__main__':
    main()