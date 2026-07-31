import os
from dotenv import load_dotenv

# Loads variables from a .env file at the project root (if present) into the
# process environment. Safe to call even if the file doesn't exist, and
# never overwrites variables that are already set (e.g. real env vars in
# a deployed environment take priority over .env).
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "db")

DB_PATHS = {
    "primary": os.path.join(DB_DIR, "primary.db"),
    "secondary_east": os.path.join(DB_DIR, "secondary_east.db"),
    "secondary_west": os.path.join(DB_DIR, "secondary_west.db"),
}

# Which store owns which region's authoritative "live" copy (for query routing).
REGION_TO_STORE = {
    "SOUTH": "primary",          # Hyderabad DC is the primary store itself
    "WEST": "secondary_west",
    "EAST": "secondary_east",
    "CENTRAL": "primary",
}

# ---- LLM (Azure OpenAI) config. Wire your real keys via env vars. ----
# If AZURE_OPENAI_API_KEY is not set, the agents fall back to deterministic
# rule-based logic so the demo works fully offline.
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

USE_LLM = bool(AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT)

CACHE_SIMILARITY_THRESHOLD = 0.82
MAX_SATISFACTION_RETRIES = 2
JWT_SECRET = os.getenv("APP_JWT_SECRET", "hackathon-demo-secret-change-me")
