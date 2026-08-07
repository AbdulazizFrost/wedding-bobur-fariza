import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")

# Convert comma-separated string of IDs to a list of integers
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip().isdigit()]

# Allowed origins for CORS
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "*")
if ALLOWED_ORIGINS_STR == "*":
    ALLOWED_ORIGINS = "*"
else:
    ALLOWED_ORIGINS = [x.strip() for x in ALLOWED_ORIGINS_STR.split(",") if x.strip()]

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'rsvp.db')
