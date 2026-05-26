import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise ValueError(f"Missing required env var: {key}. Check your .env file.")
    return val

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NVIDIA_API_KEY    = os.getenv("NVIDIA_API_KEY", "")

EMAIL_ADDRESS  = _require("EMAIL_ADDRESS")
EMAIL_PASSWORD = _require("EMAIL_PASSWORD")

JOB_KEYWORDS  = [k.strip() for k in os.getenv("JOB_KEYWORDS", "Senior Project Manager").split(",") if k.strip()]
JOB_LOCATIONS = [l.strip() for l in os.getenv("JOB_LOCATIONS", "Remote").split(",") if l.strip()]
JOB_DAYS_BACK = int(os.getenv("JOB_DAYS_BACK", "7"))

EMAIL_DAYS_BACK = int(os.getenv("EMAIL_DAYS_BACK", "5"))

DIGEST_TO_EMAIL = os.getenv("DIGEST_TO_EMAIL", "")

# LLM provider: "anthropic" or "nvidia"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

_MODEL_DEFAULTS = {
    "anthropic": "claude-opus-4-7",
    "nvidia":    "meta-llama/llama-3.3-70b-instruct:free",
}
MODEL = os.getenv("LLM_MODEL", _MODEL_DEFAULTS.get(LLM_PROVIDER, "claude-opus-4-7"))

# Base URL for the LLM endpoint (only used when LLM_PROVIDER=nvidia)
# OpenRouter: https://openrouter.ai/api/v1
# NVIDIA NIM: https://integrate.api.nvidia.com/v1
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")

# Validate that the selected provider has an API key
if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
    raise ValueError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
if LLM_PROVIDER == "nvidia" and not NVIDIA_API_KEY:
    raise ValueError("LLM_PROVIDER=nvidia but NVIDIA_API_KEY is not set.")

# SMTP (for sending digest only)
SMTP_SERVER = "smtp-mail.outlook.com"
SMTP_PORT   = 587
