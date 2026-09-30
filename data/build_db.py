"""Build arc.db from schema.sql. Rerun anytime to reset to a clean state."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "arc.db"


def build():
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript((ROOT / "schema.sql").read_text())
    conn.commit()
    conn.close()
    print(f"built {DB_PATH}")


if __name__ == "__main__":
    build()
