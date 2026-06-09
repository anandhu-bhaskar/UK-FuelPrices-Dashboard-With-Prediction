"""Blob Storage model versioning: save latest/backup, fallback on failure."""

from __future__ import annotations

import io
import json
import logging
import os
import pickle

from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)

CONTAINER = "models"


def _client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(os.environ["AZURE_STORAGE_CONNECTION_STRING"])


def _blob(name: str):
    return _client().get_blob_client(container=CONTAINER, blob=name)


def save_model(name: str, obj: object) -> None:
    """
    Save a model with backup versioning:
      - current 'name/latest' is copied to 'name/backup'
      - new model is uploaded as 'name/latest'
    If upload fails the backup is untouched, so dashboard keeps working.
    """
    data = pickle.dumps(obj)
    latest = f"{name}/latest.pkl"
    backup = f"{name}/backup.pkl"

    # Promote existing latest → backup before overwriting
    try:
        src = _blob(latest)
        existing = src.download_blob().readall()
        _blob(backup).upload_blob(existing, overwrite=True)
        logger.info("Backed up existing %s model.", name)
    except Exception:
        pass  # No existing model yet — first run

    _blob(latest).upload_blob(data, overwrite=True)
    logger.info("Saved %s model (%.1f KB).", name, len(data) / 1024)


def save_json(name: str, obj: dict) -> None:
    data = json.dumps(obj).encode()
    latest = f"{name}/latest.json"
    backup = f"{name}/backup.json"
    try:
        existing = _blob(latest).download_blob().readall()
        _blob(backup).upload_blob(existing, overwrite=True)
    except Exception:
        pass
    _blob(latest).upload_blob(data, overwrite=True)
    logger.info("Saved %s thresholds.", name)


def load_model(name: str) -> object:
    """Load latest, fall back to backup if latest is missing."""
    for suffix in ("latest", "backup"):
        try:
            data = _blob(f"{name}/{suffix}.pkl").download_blob().readall()
            logger.info("Loaded %s/%s model.", name, suffix)
            return pickle.loads(data)
        except Exception:
            continue
    raise FileNotFoundError(f"No model found for {name}")


def load_json(name: str) -> dict:
    for suffix in ("latest", "backup"):
        try:
            data = _blob(f"{name}/{suffix}.json").download_blob().readall()
            return json.loads(data)
        except Exception:
            continue
    raise FileNotFoundError(f"No JSON found for {name}")
