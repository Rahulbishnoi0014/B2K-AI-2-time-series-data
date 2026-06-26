"""
Data loader shim
================
The AI task files used to call json.load(open("output/<name>.json")).
Now they call load_collection("<name>") instead, which reads the same
documents from MongoDB. Each Mongo collection has the SAME name as the
old JSON file (users, consultations, patient_details, ...), so the data
shape is identical and the task logic never changes.

Set USE_MONGO=false to fall back to reading the local output/*.json files
(handy for offline testing without a Mongo instance).
"""

import os
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

USE_MONGO = os.environ.get("USE_MONGO", "false").lower() == "true"
DATA_DIR = os.environ.get("DATA_DIR", "output")

_db = None
if USE_MONGO:
    from pymongo import MongoClient
    _client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))
    _db = _client[os.environ.get("MONGO_DB", "teleconsult_dummy")]


def load_collection(name: str) -> list:
    """
    Drop-in replacement for json.load(open(f'{name}.json')).
    Returns a list of dicts. Mongo's own '_id' field is left intact because
    the generator stores it as a 24-char hex STRING (not an ObjectId), which
    is exactly what the task code expects.
    """
    if USE_MONGO:
        # projection {} returns all fields including _id (string) as-is
        return list(_db[name].find({}))
    with open(Path(DATA_DIR) / f"{name}.json") as f:
        return json.load(f)
