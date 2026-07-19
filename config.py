import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# =====================================================
# Cesty
# =====================================================

ROOT_DIR = Path(__file__).parent

DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# =====================================================
# Discord
# =====================================================

BOT_NAME = "Piticko Bot"

# Pro vývoj můžeš vložit ID serveru.
# 0 = globální synchronizace slash příkazů
GUILD_ID = 0

# =====================================================
# YouTube
# =====================================================

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

CHECK_INTERVAL = 300  # sekund

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id="


# =====================================================
# Databáze
# =====================================================

DATABASE = DATA_DIR / "bot.db"

# =====================================================
# Logování
# =====================================================

LOG_FILE = LOG_DIR / "bot.log"

LOG_LEVEL = "INFO"

# =====================================================
# Embedy
# =====================================================

EMBED_COLOR = 0x367C2B

EMBED_FOOTER = "Piticko Bot • Vše, co tvůj server potřebuje"

# =====================================================
# Vývoj
# =====================================================

DEBUG = False

VERSION = "2.0.0"
