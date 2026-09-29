"""Configurazione generale del motore Knowflix."""
import os
import json

# Versione del motore (usata per invalidare la cache quando cambia il prompt o lo schema)
ENGINE_VERSION = "1.0"

# Prezzi per 1M token (input, output) in USD
DEFAULT_PRICING = {
    "gemini/gemini-3.6-flash": {"input": 0.35, "output": 1.05},
    "gemini/gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "openai/gpt-4o": {"input": 5.00, "output": 15.00},
}

def get_pricing_table():
    pricing = DEFAULT_PRICING.copy()
    env_pricing = os.getenv("MODEL_PRICING")
    if env_pricing:
        try:
            pricing.update(json.loads(env_pricing))
        except Exception:
            pass
    return pricing
