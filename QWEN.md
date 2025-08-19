# Telegram Gambar Nota Jadi GSheet Project Context

## Project Overview

This project is a Telegram bot that integrates with Google Sheets and Google's Gemini AI. Its primary function is to allow users to send images of receipts or invoices to a Telegram bot. The bot then uses the Gemini API to extract structured data (like date, seller, items, prices) from the image and automatically saves this information to a Google Spreadsheet.

### Key Technologies

* **Python**: The core programming language.
* **python-telegram-bot**: For building and running the Telegram bot.
* **gspread**: For interacting with Google Sheets.
* **google-generativeai (Google Gen AI SDK)**: For calling the Gemini API to analyze images.
* **Pydantic**: For defining data models and parsing the AI's JSON response.
* **pandas**: For handling data processing (though usage appears limited in the current code).
* **Google Cloud Service Account**: For authenticating with Google Sheets and Gemini APIs.

### Architecture

1.  A Telegram bot listens for incoming messages (text, photos, documents).
2.  When a user sends an image or PDF, it's downloaded temporarily.
3.  The image/PDF is sent to the Gemini `gemini-2.0-flash-lite` model with a specific prompt (`DEFAULT_PROMPT` in `prompts.py`) asking it to extract receipt data in a structured JSON format.
4.  The AI's JSON response is parsed into a list of `Invoice` objects (defined using Pydantic).
5.  The extracted data is formatted and appended as new rows to a predefined Google Sheet.
6.  The user receives a confirmation message in Telegram with a summary of the extracted data.

## Development Environment & Running

### Prerequisites

1.  **Python**: Ensure Python 3.9+ is installed.
2.  **Virtual Environment (Recommended)**: Use a virtual environment to manage dependencies.
3.  **Dependencies**: Install required packages from `requirements.txt` (though this file seems to contain a very large list, possibly from an Anaconda environment, rather than just project-specific deps).
4.  **Credentials**:
    *   A Telegram Bot Token (obtained via BotFather).
    *   A Google Cloud Project with:
        *   The Google Sheets API and Google Drive API enabled.
        *   A Service Account with a JSON key file (`credentials.json`).
        *   The Service Account granted "Editor" access to the target Google Spreadsheet.
    *   A Google AI (Gemini) API key.

### Configuration

Configuration is handled via `credentials.py`. You must set the following variables:

*   `TELEGRAM_BOT_TOKEN`: Your Telegram bot's API token.
*   `GOOGLE_CREDENTIALS_FILE`: Path to your Google Service Account JSON key file (e.g., `"credentials.json"`).
*   `SPREADSHEET_ID`: The unique ID of the Google Spreadsheet where data will be saved (found in the spreadsheet's URL).
*   `GEMINI_API_KEY`: Your Google AI (Gemini) API key.

Example `credentials.py`:
```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
GOOGLE_CREDENTIALS_FILE = "path/to/your/credentials.json"
SPREADSHEET_ID = "your_google_spreadsheet_id_here"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
```

### Running the Bot

1.  Ensure your `credentials.py` is configured correctly.
2.  Install dependencies (you might want to create a minimal `requirements.txt` first, or use the existing one if appropriate):
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: The current `requirements.txt` is very large. A minimal list would likely include `python-telegram-bot`, `gspread`, `google-generativeai`, `pandas`, `pydantic`)*
3.  Run the main application script:
    ```bash
    python app.py
    ```
    The bot should start and begin listening for messages on Telegram.

### Key Files

*   `app.py`: The main application file containing the bot logic, Google Sheets setup, and message handlers.
*   `prompts.py`: Contains the `DEFAULT_PROMPT` used to instruct the Gemini AI on how to extract data from the image.
*   `credentials.py`: Stores sensitive configuration like API keys and file paths (ensure this is kept secret and not committed if public).
*   `requirements.txt`: Lists project dependencies (though currently very extensive).
*   `uploads/`: A directory created at runtime to temporarily store downloaded images/documents.

## Development Conventions

*   **Logging**: Uses Python's standard `logging` module for tracking events and errors.
*   **Error Handling**: Includes `try...except` blocks around critical operations like API calls and file processing to catch and log errors gracefully.
*   **Asynchronous Programming**: Leverages `async`/`await` for Telegram bot handlers to handle multiple users concurrently.
*   **Object-Oriented Design**: Core bot functionality is encapsulated within the `TelegramGoogleSheetsBot` class.
*   **Data Modeling**: Uses Pydantic `BaseModel` (`Invoice`) to define the expected structure of data returned by the AI.
*   **Hardcoded Model**: The AI model `gemini-2.0-flash-lite` is hardcoded in `app.py`.
