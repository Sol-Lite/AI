import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

#JWT
 
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError(".env에 JWT_SECRET_KEY가 설정되지 않았습니다.")
 
JWT_ALGORITHM = "HS384"  # HS256 → HS384

# LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# Oracle
ORACLE_DSN      = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")
ORACLE_USER     = os.getenv("ORACLE_USER", "mockstock")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")

# MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "mockstock")

SPRING_BASE_URL = os.getenv("SPRING_BASE_URL", "http://localhost:8080")

USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

class Settings(BaseSettings):
    MONGO_URI: str
    MONGO_DB: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()