import os

# Get from https://my.telegram.org
API_ID = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "your_api_hash")

# Get from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")

# File size limit
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

# Download directory
DOWNLOAD_DIR = "./downloads"
