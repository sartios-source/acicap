from pathlib import Path
import os
from secrets import token_hex


class Config:
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    FABRICS_DIR = BASE_DIR / "fabrics"
    OUTPUT_DIR = BASE_DIR / "output"
    UPLINKS_PER_LEAF_DEFAULT = int(os.environ.get("UPLINKS_PER_LEAF_DEFAULT", "2"))
    SECRET_KEY = os.environ.get("SECRET_KEY") or token_hex(16)
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1GB uploads
    ALLOWED_EXTENSIONS = {"json", "csv", "xml", "txt", "cfg", "conf", "zip"}
    API_RATE_LIMIT = "60 per minute"
    LOG_FILE = BASE_DIR / "acicap.log"
    LOG_MAX_BYTES = 2 * 1024 * 1024
    LOG_BACKUP_COUNT = 3

    @staticmethod
    def init_app(app):
        for path in (Config.DATA_DIR, Config.FABRICS_DIR, Config.OUTPUT_DIR):
            path.mkdir(parents=True, exist_ok=True)


def get_config(_name: str):
    return Config
