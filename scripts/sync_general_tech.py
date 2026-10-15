"""Fill Zhejiang-used Sujiao general technology books from keben's upstream catalog."""

import sys
import time
from pathlib import Path

import httpx
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db  # noqa: E402
from app.ingest import pdf_chunks  # noqa: E402

API = "https://api.github.com/repos/TapXWorld/ChinaTextbook/contents/高中/通用技术/苏教版-江苏凤凰教育出版社"
MAX_PDF_BYTES = 350 * 1024 * 1024


def download(client: httpx.Client, url: str, blob_url: str, path: Path) -> None:
    temp = path.with_suffix(".part")
    if not blob_url.startswith("https://api.github.com/repos/TapXWorld/ChinaTextbook/git/blobs/"):
        raise ValueError("untrusted blob URL")
    for target, headers in ((url, {}), (blob_url, {"Accept": "application/vnd.github.raw+json"})):
        try:
            with client.stream("GET", target, headers=headers) as source:
                if source.status_code == 429:
                    print("RATE LIMIT: trying alternate GitHub endpoint", flush=True)
                    continue
                source.raise_for_status()
                total = 0
                with temp.open("wb") as output:
                    for piece in source.iter_bytes(1024 * 1024):
                        total += len(piece)
                        if total > MAX_PDF_BYTES:
                            raise ValueError("PDF exceeds local size limit")
                        output.write(piece)
            with temp.open("rb") as handle:
                if handle.read(4) != b"%PDF":
                    raise ValueError("not a PDF")
            temp.replace(path)
            return
        finally:
            temp.unlink(missing_ok=True)
    raise RuntimeError("download rate limited on both GitHub endpoints")


def main() -> None:
    db.init_db()
    existing = {item["url"] for item in db.list_sources()}
    root = db.data_dir() / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=90, follow_redirects=True, headers={"User-Agent": "TA-Agent/0.1 (local educational study)"}) as client:
        response = client.get(API)
        response.raise_for_status()
        for item in response.json():
            if item.get("type") != "file" or not item["name"].endswith(".pdf"):
                continue
            source_url = item["html_url"]
            if source_url in existing:
                continue
            raw_url = item.get("download_url", "")
            if not raw_url.startswith("https://raw.githubusercontent.com/TapXWorld/ChinaTextbook/"):
                print(f"SKIP untrusted URL: {item['name']}", flush=True)
                continue
            path = root / f"general-tech-{item['sha'][:12]}.pdf"
            try:
                if not path.is_file():
                    download(client, raw_url, item.get("git_url", ""), path)
                with pymupdf.open(path) as document:
                    pages = document.page_count
                try:
                    chunks = pdf_chunks(path)
                except ValueError as exc:
                    if "无法提取文字" not in str(exc):
                        raise
                    chunks = []
                name = item["name"].removesuffix(".pdf")
                volume = name.split("通用技术", 1)[-1].strip()
                meta = {"title": name, "kind": "textbook", "stage": "高中", "subject": "通用技术",
                        "edition": "苏教版", "publisher": "江苏凤凰教育出版社", "volume": volume,
                        "url": source_url, "license": "上游开源索引提供下载；教材版权归出版社，文件仅在本地保存",
                        "file_path": str(path), "catalog_id": "高中-通用技术"}
                source_id = db.add_source(meta, chunks)
                print(f"OK source={source_id} pages={pages} chunks={len(chunks)} {name}", flush=True)
                existing.add(source_url)
            except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
                print(f"ERROR {item['name']}: {type(exc).__name__}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
