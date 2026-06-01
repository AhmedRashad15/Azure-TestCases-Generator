"""Server-side AI configuration (Anthropic + env loading)."""
import os
from dotenv import load_dotenv

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"


def load_env():
    """Load .env then .env.local (Next.js-style) so local overrides win."""
    load_dotenv()
    load_dotenv(".env.local", override=True)


def get_anthropic_api_key():
    """Same variable names as the QC Next.js app, with legacy CLAUDE_API_KEY fallback."""
    return (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or "").strip()


def get_claude_model():
    return (os.getenv("CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL).strip()


def get_claude_models():
    primary = get_claude_model()
    models = [primary]
    fallbacks = os.getenv("CLAUDE_MODEL_FALLBACKS", "")
    for name in fallbacks.split(","):
        name = name.strip()
        if name and name not in models:
            models.append(name)
    return models


def is_claude_configured():
    return bool(get_anthropic_api_key())


def is_claude_billing_error(error_str):
    s = error_str.lower()
    return "credit balance" in s or "credit_balance" in s or "insufficient" in s and "credit" in s
