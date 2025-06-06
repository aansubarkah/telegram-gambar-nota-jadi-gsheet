import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
from typing import Optional
from google import genai
from google.genai import types

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class QuestionAnswerBot:
    def __init__(self, telegram_token: str, gemini_api_key: Optional[str] = None):
        self.telegram_token = telegram_token
        self.gemini_api_key = gemini_api_key
        self.model = None
        
        # Initialize Gemini if API key is provided
        if gemini_api_key:
            try:
                client = genai.Client(api_key=gemini_api_key)
                self.model = client
                #self.model = genai.GenerativeModel('gemini-pro')
                logger.info("Gemini API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini API: {e}")
                self.model = None

    def escape_markdown(self, text: str) -> str:
        """Escape special characters for MarkdownV2"""
        special_chars = ['[', ']', '(', ')', '+', '-', '=', '|', '{', '}', '.', '!']
        #special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text
            
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "Hello! I'm a Q&A bot powered by Google Gemini. Ask me any question and I'll try to help!\n"
            "You can use me in groups or private chats."
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
Available commands:
/start - Start the bot
/help - Show this help message

Just ask me any question and I'll try to answer it!
Examples:
- "What is Python?"
- "How does photosynthesis work?"
- "Explain quantum computing"
- "Write a short poem about nature"

In groups, mention me (@botname) to get my attention!
        """
        await update.message.reply_text(help_text)
    
    async def answer_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle questions from users"""
        user_question = update.message.text
        user_name = update.effective_user.first_name
        
        # Skip if message is a command
        if user_question.startswith('/'):
            return
        
        # Check if bot is mentioned in groups
        if update.effective_chat.type in ['group', 'supergroup']:
            bot_username = context.bot.username
            if f"@{bot_username}" not in user_question:
                return  # Only respond when mentioned in groups
            # Remove bot mention from question
            user_question = user_question.replace(f"@{bot_username}", "").strip()
        
        try:
            # Show typing indicator
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action="typing"
            )
            
            # Generate answer
            answer = await self.generate_answer(user_question)
            logger.info(f"User {user_name} asked: {user_question}\nAnswer: {answer}")

            escaped_answer = self.escape_markdown(answer)
            #escaped_answer = answer
            
            # Split long messages if needed
            if len(escaped_answer) > 4096:  # Telegram message limit
                chunks = [escaped_answer[i:i+4096] for i in range(0, len(escaped_answer), 4096)]
                for chunk in chunks:
                    await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(f"{escaped_answer}", parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error while processing your question. Please try again!"
            )
    
    async def generate_answer(self, question: str) -> str:
        """Generate answer to the question using Gemini"""
        
        # If Gemini API is available, use it
        if self.model:
            try:
                prompt = f"""Anda adalah asisten AI yang membantu pengguna di Telegram.
                Jawab pertanyaan dengan jelas dan singkat. Berikan jawaban informatif.
                
                Format teks menggunakan sintaks berikut:
                - Teks tebal: *teks*
                - Teks miring: _teks_
                - Garis bawah: __teks__
                - Kode: `kode`
                - Blok kode: ```kode```
                
                Pertanyaan: {question}
                """
                
                response = self.model.models.generate_content(
                    model='gemini-2.5-flash-preview-05-20',
                    config=types.GenerateContentConfig(
                        system_instruction='''
                        Anda adalah asisten Excel dan Google Sheets.
                        Jawab pertanyaan dengan jelas dan singkat.
                        Selalu jawab dalam Bahasa Indonesia.
                        Gunakan format teks berikut:
                        - Teks penting dalam *teks tebal*
                        - Istilah teknis dalam _teks miring_
                        - Rumus atau kode dalam `kode`
                        - Contoh kode panjang dalam blok ```kode```
                        - Buat poin-poin dengan •
                        ''',
                        max_output_tokens=4096,
                    ),
                    contents=prompt)

                if response.text:
                    return response.text.strip()
                else:
                    logger.warning("Gemini returned empty response")
                    return self.fallback_answer(question)
                    
            except Exception as e:
                logger.error(f"Gemini API error: {e}")
                return self.fallback_answer(question)
        else:
            return self.fallback_answer(question)
    
    def fallback_answer(self, question: str) -> str:
        """Provide fallback answers when AI API is not available"""
        question_lower = question.lower()
        
        # Simple keyword-based responses
        if any(word in question_lower for word in ['hello', 'hi', 'hey', 'greetings']):
            return "Hello! How can I help you today? 😊"
        
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
    
    def run(self):
        """Start the bot"""
        # Create application
        application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.answer_question))
        
        # Add error handler
        application.add_error_handler(self.error_handler)
        
        # Start the bot
        logger.info("Starting Gemini-powered Telegram bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    # Configuration
    TELEGRAM_BOT_TOKEN = '7268324383:AAEB7hYkWCB-TxYGwFhuZ4_Eqo5WjlDuDN0'
    GEMINI_API_KEY = 'AIzaSyDBhCAMcISchXzLzkyWN3uI_ZvNKBDEP6Q'
    
    if TELEGRAM_BOT_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN_HERE':
        print("❌ Please set your Telegram bot token!")
        print("1. Create a bot with @BotFather on Telegram")
        print("2. Set TELEGRAM_BOT_TOKEN environment variable or replace in code")
        return
    
    if not GEMINI_API_KEY:
        print("⚠️  No Gemini API key found. Bot will use fallback responses.")
        print("To get full AI capabilities:")
        print("1. Go to https://makersuite.google.com/app/apikey")
        print("2. Create an API key")
        print("3. Set GEMINI_API_KEY environment variable")
    
    # Create and run bot
    bot = QuestionAnswerBot(TELEGRAM_BOT_TOKEN, GEMINI_API_KEY)
    bot.run()

if __name__ == '__main__':
    main()