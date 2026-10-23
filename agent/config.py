import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()


class Settings:
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    BEDROCK_MODEL_ID: str = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-v1:0")

    CRM_BASE_URL: str = os.getenv("CRM_BASE_URL", "http://localhost:8000")
    LEDGER_BASE_URL: str = os.getenv("LEDGER_BASE_URL", "http://localhost:8081")

    DECIDER_BASE_URL: str = os.getenv("DECIDER_BASE_URL", "http://localhost:8001")
    DECIDER_MODE: str = os.getenv("DECIDER_MODE", "mock").lower()
    DECIDER_CONFIDENCE_THRESHOLD: float = float(os.getenv("DECIDER_CONFIDENCE_THRESHOLD", "0.65"))
    FAIL_CLOSED_IF_DECIDER_UNAVAILABLE: bool = os.getenv("FAIL_CLOSED_IF_DECIDER_UNAVAILABLE", "true").lower() in ("true", "1", "yes")

    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "15"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
