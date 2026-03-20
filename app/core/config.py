import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings


load_dotenv()

# LLM
# OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# LS증권 API
# LS_API_BASE_URL  = os.getenv("LS_API_BASE_URL", "https://openapi.ls-sec.co.kr:8080")
# LS_APP_KEY       = os.getenv("LS_APP_KEY", "")
# LS_APP_SECRET    = os.getenv("LS_APP_SECRET", "")

# Oracle
# ORACLE_DSN      = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")
# ORACLE_USER     = os.getenv("ORACLE_USER", "mockstock")
# ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")

# MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "mockstock")

# Redis
# REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
# REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
# REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

class Settings(BaseSettings):
    MONGO_URI: str
    MONGO_DB: str

    class Config:
        env_file = ".env"


settings = Settings()