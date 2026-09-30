"""Shared DB access + execution-accuracy comparison, used identically by
all three stages so the eval protocol never drifts between them."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "arc.db"


def connect(db_path=None):
    return sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)


def schema_text(db_path=None) -> str:
    """CREATE TABLE text in the same compact format the off-the-shelf
    fine-tuned checkpoint (cssupport/t5-small-awesome-text-to-sql) expects,
    per its model card -- so stage 0's baseline gets a fair shot."""
    conn = connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    parts = []
    for t in tables:
        cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
        col_str = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        parts.append(f"CREATE TABLE {t} ({col_str})")
    conn.close()
    return "; ".join(parts)


def tables_and_columns(db_path=None) -> dict[str, list[str]]:
    conn = connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    out = {}
    for t in tables:
        cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
        out[t] = [c[1] for c in cols]
    conn.close()
    return out


def foreign_keys(db_path=None) -> list[tuple[str, str, str, str]]:
    """(from_table, from_col, to_table, to_col) for every FK in the schema."""
    conn = connect(db_path)
    tables = list(tables_and_columns(db_path).keys())
    out = []
    for t in tables:
        for fk in conn.execute(f"PRAGMA foreign_key_list({t})").fetchall():
            # fk row: (id, seq, table, from, to, ...)
            out.append((t, fk[3], fk[2], fk[4]))
    conn.close()
    return out


def value_lookup_for(db_path):
    """A link_engine-shaped value_lookup fn scoped to one DB file."""
    def lookup(table: str, col: str) -> dict[str, str]:
        try:
            conn = connect(db_path)
            conn.text_factory = lambda b: b.decode(errors="ignore")
            rows = conn.execute(f'SELECT DISTINCT "{col}" FROM "{table}"').fetchall()
            conn.close()
            return {str(r[0]).lower(): str(r[0]) for r in rows if isinstance(r[0], str)}
        except Exception:
            return {}
    return lookup


def run_sql_at(db_path, sql: str) -> tuple[list[tuple] | None, str | None]:
    """Same as run_sql, against an arbitrary DB file -- WikiSQL and Spider
    each have their own per-question/per-database SQLite files, unlike the
    toy schema's single fixed arc.db."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA busy_timeout = 5000")
        rows = conn.execute(sql).fetchall()
        conn.close()
        return rows, None
    except Exception as e:
        return None, str(e)


def run_sql(sql: str) -> tuple[list[tuple] | None, str | None]:
    """Runs read-only, 5s busy timeout. Returns (rows, None) or (None, error)."""
    return run_sql_at(DB_PATH, sql)


def results_match(gold_sql: str, gold_rows: list[tuple], pred_rows: list[tuple] | None) -> bool:
    """Execution accuracy: compare result *sets*, not query strings, since
    syntactically different SQL can be semantically identical. Ordered
    comparison only when the gold query itself has ORDER BY -- otherwise
    row order is not part of the query's meaning."""
    if pred_rows is None:
        return False
    if "order by" in gold_sql.lower():
        return gold_rows == pred_rows
    return sorted(map(str, gold_rows)) == sorted(map(str, pred_rows))
