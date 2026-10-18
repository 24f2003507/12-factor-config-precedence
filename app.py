
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS: dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

INTEGER_KEYS = {"port", "workers"}
BOOLEAN_TRUE = {"true", "1", "yes", "on"}

# Permit browser-based cross-origin checks.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def coerce(key: str, value: Any) -> Any:
    if key in INTEGER_KEYS:
        return int(value)
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in BOOLEAN_TRUE
    return str(value)


def load_config(set_overrides: list[str]) -> dict[str, Any]:
    config = DEFAULTS.copy()

    # Layer 2: environment-specific YAML configuration.
    environment = os.getenv("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{environment}.yaml"

    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as file:
            yaml_config = yaml.safe_load(file) or {}
        if isinstance(yaml_config, dict):
            config.update(yaml_config)

    # Layer 3: .env file. NUM_WORKERS aliases to workers.
    env_file = dotenv_values(BASE_DIR / ".env")
    for key, value in env_file.items():
        if value is None:
            continue
        normalized_key = "workers" if key == "NUM_WORKERS" else key.lower()
        if normalized_key in config:
            config[normalized_key] = value

    # Layer 4: actual OS environment variables with APP_ prefix.
    for key, value in os.environ.items():
        if key.startswith("APP_"):
            normalized_key = key[4:].lower()
            if normalized_key in config:
                config[normalized_key] = value

    # Layer 5: repeated CLI-style query overrides.
    for item in set_overrides:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip().lower()
        if key in config:
            config[key] = value

    # Coerce values after merging all layers.
    result = {
        key: coerce(key, value)
        for key, value in config.items()
    }

    # Never expose the real API key.
    result["api_key"] = "****"

    return result


@app.get("/")
async def home():
    return {"message": "Effective Config API is running"}


@app.get("/effective-config")
async def effective_config(
    set: list[str] = Query(default=[]),
):
    try:
        return load_config(set)
    except (ValueError, yaml.YAMLError):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid configuration value"},
        )
