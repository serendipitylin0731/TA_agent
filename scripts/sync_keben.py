"""Download selected keben.app books for local study; files never enter Git."""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db  # noqa: E402
from app.ingest import pdf_chunks  # noqa: E402

SITE = "https://keben.app"
ALLOWED_MEDIA_HOSTS = {"media.keben.app", "dl2.keben.app"}
MAX_PDF_BYTES = 350 * 1024 * 1024


def selected_version(edition: str) -> str:
    for name in ("统编版", "人教版", "浙教版", "苏教版"):
        if edition.startswith(name):
            return name
    raise ValueError(f"Unknown edition: {edition}")


def get_json(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    for attempt in range(3):
        response = client.get(SITE + path, params=params)
        if response.status_code == 429 and attempt < 2:
            delay = min(30, max(3, int(response.headers.get("Retry-After", "8"))))
            print(f"RATE LIMIT: wait {delay}s", flush=True)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("rate limit")


def book_list(client: httpx.Client, stage: str, subject: str, version: str) -> list[dict]:
    page = 1
    matches = []
    while True:
        data = get_json(client, "/api/search", {"q": subject, "stage": stage, "version": version,
                                                "limit": 100, "page": page})
        for item in data.get("items", []):
            if item.get("stage") != stage or item.get("subject") != subject or item.get("version") != version:
                continue
            if not item.get("title", "").startswith(subject):
                continue
            if stage == "初中" and item.get("system") != "六三制":
                continue
            if item.get("isCurrent") is False:
                continue
            if item.get("revision") and int(item["revision"]) > date.today().year:
                continue
            if stage == "高中" and subject == "数学" and item.get("variant") not in (None, "A"):
                continue
            matches.append(item)
        if page >= data.get("totalPages", 1):
            return matches
        page += 1
        time.sleep(0.5)


def download_pdf(client: httpx.Client, book_id: str, output: Path) -> None:
    if output.is_file() and output.stat().st_size > 1000:
        with output.open("rb") as handle:
            if handle.read(4) == b"%PDF":
                return
    data = get_json(client, f"/api/download/{book_id}")
    url = data.get("downloadUrl", "")
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in ALLOWED_MEDIA_HOSTS or not url.endswith(".pdf"):
        raise ValueError("untrusted download URL")
    temp = output.with_suffix(".part")
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            if response.url.host not in ALLOWED_MEDIA_HOSTS:
                raise ValueError("untrusted redirect")
            total = 0
            with temp.open("wb") as handle:
                for piece in response.iter_bytes(1024 * 1024):
                    total += len(piece)
                    if total > MAX_PDF_BYTES:
                        raise ValueError("PDF exceeds local size limit")
                    handle.write(piece)
        with temp.open("rb") as handle:
            if handle.read(4) != b"%PDF":
                raise ValueError("download is not a PDF")
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)


def import_book(client: httpx.Client, item: dict, catalog: dict) -> tuple[int, int, int]:
    book_id = item["id"]
    root = db.data_dir() / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"keben-{book_id}.pdf"
    download_pdf(client, book_id, path)
    with pymupdf.open(path) as document:
        pages = document.page_count
    try:
        chunks = pdf_chunks(path)
    except ValueError as exc:
        if "无法提取文字" not in str(exc):
            raise
        chunks = []
    title = item["title"]
    version = selected_version(catalog["edition"])
    marker = version + " "
    volume = title.split(marker, 1)[1] if marker in title else " ".join(
        filter(None, [item.get("grade"), item.get("variant"), item.get("semester")]))
    volume = re.sub(r"\s+(\d{4}版)$", r"（\1）", volume).strip()
    meta = {"title": item["title"], "kind": "textbook", "stage": catalog["stage"],
            "subject": catalog["subject"], "edition": selected_version(catalog["edition"]),
            "publisher": ", ".join(item.get("publishers") or [catalog["publisher"]]),
            "volume": volume, "url": f"{SITE}/book/{book_id}",
            "license": "课本网提供个人学习与研究下载；教材版权归出版社，文件仅在本地保存",
            "file_path": str(path), "catalog_id": catalog["id"]}
    return db.add_source(meta, chunks), pages, len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="show matching books without downloading")
    parser.add_argument("--limit", type=int, default=0, help="maximum new books to import; 0 means all")
    args = parser.parse_args()
    db.init_db()
    existing_urls = {item["url"] for item in db.list_sources()}
    pending = []
    with httpx.Client(timeout=70, follow_redirects=True, headers={"User-Agent": "TA-Agent/0.1 (local educational study)"}) as client:
        for catalog in db.list_catalog():
            version = selected_version(catalog["edition"])
            try:
                matches = book_list(client, catalog["stage"], catalog["subject"], version)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                print(f"SEARCH ERROR {catalog['id']}: {type(exc).__name__}", flush=True)
                continue
            print(f"CATALOG {catalog['id']}: {len(matches)} matched", flush=True)
            for item in matches:
                book_url = f"{SITE}/book/{item['id']}"
                if book_url in existing_urls:
                    continue
                if args.dry_run:
                    print(f"  WOULD IMPORT {item['id']} {item['title']}", flush=True)
                    continue
                pending.append((item, catalog))
            time.sleep(0.4)
        if args.dry_run:
            return
        if args.limit:
            pending = pending[:args.limit]
        print(f"DOWNLOAD QUEUE: {len(pending)} books", flush=True)
        root = db.data_dir() / "uploads"
        root.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(download_pdf, client, item["id"], root / f"keben-{item['id']}.pdf"): (item, catalog)
                       for item, catalog in pending}
            for future in as_completed(futures):
                item, catalog = futures[future]
                try:
                    future.result()
                    source_id, pages, chunks = import_book(client, item, catalog)
                    print(f"OK {item['id']} source={source_id} pages={pages} chunks={chunks} {item['title']}", flush=True)
                except (httpx.HTTPError, ValueError, OSError, RuntimeError) as exc:
                    print(f"ERROR {item['id']}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
