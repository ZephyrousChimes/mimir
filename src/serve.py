"""A tiny local server: upload any SQLite database, ask it a question in
plain English, get back the generated SQL and its results -- using
encoder.ground() + decoder.build(), the same engine this project evaluated
against the toy schema, WikiSQL, and Spider. Nothing here is a demo
reimplementation; it's the real generation code with a page in front of it.

Single active database at a time, on purpose -- this is a local tool for
one person trying one database, not a multi-tenant service.
"""
import shutil
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db_utils
import decoder
import enc_rule
import enc_ngram
import enc_embed

ROOT = Path(__file__).parent.parent
UPLOAD_DIR = ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_DB = UPLOAD_DIR / "current.db"

ENCODERS = {"rule": enc_rule, "ngram": enc_ngram, "embed": enc_embed}

app = FastAPI(title="nl2sql-arc")


class Question(BaseModel):
    question: str
    encoder: str = "rule"


@app.post("/upload")
async def upload(file: UploadFile):
    if not file.filename.endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(400, "expected a .db/.sqlite/.sqlite3 file")
    with open(CURRENT_DB, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        schema = db_utils.tables_and_columns(CURRENT_DB)
    except Exception as e:
        CURRENT_DB.unlink(missing_ok=True)
        raise HTTPException(400, f"not a readable SQLite database: {e}")
    if not schema:
        CURRENT_DB.unlink(missing_ok=True)
        raise HTTPException(400, "database has no tables")
    return {"tables": schema, "foreign_keys": db_utils.foreign_keys(CURRENT_DB)}


@app.get("/schema")
def schema():
    if not CURRENT_DB.exists():
        raise HTTPException(404, "no database uploaded yet")
    return {"tables": db_utils.tables_and_columns(CURRENT_DB),
            "foreign_keys": db_utils.foreign_keys(CURRENT_DB)}


@app.get("/encoders")
def encoders():
    return {"encoders": list(ENCODERS.keys())}


def _grounding_json(g):
    return {
        "tables": sorted(g.tables),
        "target": g.target,
        "filters": g.filters,
        "aggregation": list(g.aggregation) if g.aggregation else None,
    }


@app.post("/query")
def query(q: Question):
    if not CURRENT_DB.exists():
        raise HTTPException(404, "no database uploaded yet")
    if q.encoder not in ENCODERS:
        raise HTTPException(400, f"unknown encoder '{q.encoder}', choose from {list(ENCODERS)}")

    schema_ = db_utils.tables_and_columns(CURRENT_DB)
    fks = db_utils.foreign_keys(CURRENT_DB)
    lookup = db_utils.value_lookup_for(CURRENT_DB)

    grounding = ENCODERS[q.encoder].ground(q.question, schema_, lookup)
    if grounding is None:
        return {"sql": None, "grounding": None,
                "error": "couldn't link this question to any table in the schema",
                "columns": [], "rows": []}

    sql = decoder.build(grounding, schema_, fks)
    grounding_json = _grounding_json(grounding)

    try:
        conn = sqlite3.connect(f"file:{CURRENT_DB}?mode=ro", uri=True)
        conn.execute("PRAGMA busy_timeout = 5000")
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        conn.close()
        return {"sql": sql, "grounding": grounding_json, "error": None,
                "columns": columns, "rows": rows}
    except Exception as e:
        return {"sql": sql, "grounding": grounding_json, "error": str(e),
                "columns": [], "rows": []}


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
