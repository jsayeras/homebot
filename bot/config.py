import os
from dotenv import load_dotenv

load_dotenv(".env")


class Config:
    ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", "0"))
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    DUCKDNS_TOKEN = os.getenv("DUCKDNS_TOKEN", "")
    DUCKDNS_DOMAIN = "saydu"
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    SERVICES_YAML = os.getenv("SERVICES_YAML", "services.yaml")
