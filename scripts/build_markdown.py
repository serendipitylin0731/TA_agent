"""Convert every installed PDF to page-aware Markdown with selected embedded figures.

Usage: PYTHONPATH=. .venv/bin/python scripts/build_markdown.py
"""

import argparse
from pathlib import Path

import pymupdf

from app import db
from app.markdown_ingest import convert_book


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-id", type=int, help="only rebuild one textbook")
    parser.add_argument("--limit", type=int, default=0, help="maximum textbooks this run")
    parser.add_argument("--no-images", action="store_true", help="omit extracted figures")
    parser.add_argument("--force", action="store_true", help="rebuild already converted books")
    args = parser.parse_args()
    db.init_db()
    sources = db.list_sources()
    if args.book_id:
        sources = [item for item in sources if item["id"] == args.book_id]
    if args.limit:
        sources = sources[:args.limit]
    output_root = db.data_dir() / "markdown"
    errors = []
    for index, source in enumerate(sources, 1):
        try:
            full = db.get_source(source["id"])
            if not full or not Path(full["file_path"]).is_file():
                raise FileNotFoundError("教材 PDF 不存在")
            marker = output_root / f"{source['id']}.indexed"
            if (output_root / f"{source['id']}.md").is_file() and marker.is_file() and not args.force:
                print(f"{index}/{len(sources)} SKIP id={source['id']} already converted", flush=True)
                continue
            marker.unlink(missing_ok=True)
            path, chunks, images = convert_book(full, output_root, not args.no_images)
            db.reindex_source(source["id"], chunks)
            marker.write_text("indexed\n", encoding="utf-8")
            with pymupdf.open(full["file_path"]) as pdf:
                page_count = len(pdf)
            print(f"{index}/{len(sources)} OK id={source['id']} pages={page_count} "
                  f"passages={len(chunks)} figures={images} {path.name} {source['title']}", flush=True)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append((source["id"], str(exc)))
            print(f"{index}/{len(sources)} ERROR id={source['id']} {type(exc).__name__}: {exc}", flush=True)
    print(f"Finished {len(sources)-len(errors)}/{len(sources)} books; errors={errors}", flush=True)


if __name__ == "__main__":
    main()
