import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(override=True)

# Runtime
APP_ENV = os.getenv("APP_ENV", "local")
ENABLE_CRAWLERS = os.getenv("ENABLE_CRAWLERS", "true").lower() == "true"

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
SAGEMAKER_ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT_NAME", "")
SAGEMAKER_RUNTIME_MODE = os.getenv("SAGEMAKER_RUNTIME_MODE", "tgi").strip().lower()
AWS_REGION              = os.getenv("AWS_REGION", "ap-northeast-2")
LLM_TIMEOUT_SECONDS     = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# Oracle
ORACLE_DSN      = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")
ORACLE_USER     = os.getenv("ORACLE_USER", "mockstock")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")

# MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "mockstock")

SPRING_BASE_URL = os.getenv("SPRING_BASE_URL", "http://localhost:8080")
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "3"))


class Settings(BaseSettings):
    MONGO_URI: str
    MONGO_DB: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
