"""Backfill the completion vocabulary after importing older textbook records."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="rebuild existing source terms")
    options = parser.parse_args()
    db.init_db()
    with db.connect() as connection:
        sources = connection.execute("SELECT id,title FROM sources ORDER BY id").fetchall()
    for index, source in enumerate(sources, 1):
        with db.connect() as connection:
            if not options.force and connection.execute("SELECT 1 FROM search_terms WHERE source_id=? LIMIT 1", (source["id"],)).fetchone():
                continue
            chunks = [(row["page"], row["section"], row["text"]) for row in connection.execute(
                "SELECT page,section,text FROM chunks WHERE source_id=? ORDER BY id", (source["id"],))]
            db.index_source_terms(connection, source["id"], chunks)
        print(f"{index}/{len(sources)} {source['title']}", flush=True)


if __name__ == "__main__":
    main()
