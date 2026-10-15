"""Import a small, attributed open reference set for the first local run."""

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db  # noqa: E402
from app.ingest import plain_chunks  # noqa: E402

API = "https://zh.wikipedia.org/w/api.php"
LICENSE = "CC BY-SA 4.0 · https://creativecommons.org/licenses/by-sa/4.0/"
ARTICLES = [
    ("修辞", "语文"),
    ("函数", "数学"),
    ("英语语法", "英语"),
    ("欧姆定律", "物理"),
    ("化学元素周期表", "化学"),
    ("光合作用", "生物学"),
    ("公民", "道德与法治"),
    ("政治学", "思想政治"),
    ("中国近代史", "历史"),
    ("板块构造论", "地理"),
    ("信息系统", "信息技术"),
    ("工业设计", "通用技术"),
]


async def main() -> None:
    db.init_db()
    covered = {item["subject"] for item in db.list_sources() if item["kind"] == "open_web"}
    async with httpx.AsyncClient(timeout=25, headers={"User-Agent": "TA-agent/0.1 (educational research; source-linked)"}) as client:
        for title, subject in ARTICLES:
            if subject in covered:
                print(f"EXISTS {subject}")
                continue
            try:
                response = await client.get(API, params={"action": "query", "prop": "extracts|info", "titles": title,
                    "redirects": 1, "explaintext": 1, "inprop": "url", "format": "json", "formatversion": 2})
                response.raise_for_status()
                page = response.json().get("query", {}).get("pages", [{}])[0]
                body = page.get("extract", "")[:50000]
                if len(body.strip()) < 80:
                    print(f"SKIP {title}: no extract")
                    continue
                chunks = plain_chunks(body)
                meta = {"title": page["title"], "kind": "open_web", "stage": "通用", "subject": subject,
                    "edition": "", "publisher": "维基百科贡献者", "volume": "",
                    "url": page.get("canonicalurl", f"https://zh.wikipedia.org/?curid={page['pageid']}"),
                    "license": LICENSE, "file_path": "", "catalog_id": None}
                source_id = db.add_source(meta, chunks)
                print(f"OK {subject}: {page['title']} ({len(chunks)} chunks, id={source_id})")
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                print(f"ERROR {title}: {type(exc).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
