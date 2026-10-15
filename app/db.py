import hashlib
import os
import re
import sqlite3
from pathlib import Path

import jieba

from .catalog import catalog_entries

STOPWORDS = {"什么", "怎么", "如何", "为什么", "可以", "哪些", "关于", "是否", "解释", "一下", "这个", "那个", "相关", "教材", "课本", "知识", "内容", "在哪", "哪里", "什么是"}


def data_dir() -> Path:
    return Path(os.getenv("TA_DATA_DIR", "storage")).resolve()


def connect() -> sqlite3.Connection:
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "ta.db", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS catalog (
          id TEXT PRIMARY KEY, stage TEXT NOT NULL, subject TEXT NOT NULL,
          edition TEXT NOT NULL, publisher TEXT NOT NULL, title TEXT NOT NULL,
          catalog_url TEXT NOT NULL, note TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('textbook','open_web','official')),
          stage TEXT NOT NULL, subject TEXT NOT NULL, edition TEXT NOT NULL DEFAULT '',
          publisher TEXT NOT NULL DEFAULT '', volume TEXT NOT NULL DEFAULT '',
          url TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '',
          file_path TEXT NOT NULL DEFAULT '', content_hash TEXT NOT NULL UNIQUE,
          catalog_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(catalog_id) REFERENCES catalog(id)
        );
        CREATE TABLE IF NOT EXISTS chunks (
          id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL,
          page INTEGER, section TEXT NOT NULL DEFAULT '', text TEXT NOT NULL,
          FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='trigram');
        CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id);
        CREATE INDEX IF NOT EXISTS idx_sources_filter ON sources(stage,subject,kind);
        """)
        db.executemany("""INSERT OR REPLACE INTO catalog
          (id,stage,subject,edition,publisher,title,catalog_url,note)
          VALUES (:id,:stage,:subject,:edition,:publisher,:title,:catalog_url,:note)""", catalog_entries())


def add_source(meta: dict, page_chunks: list[tuple[int | None, str, str]]) -> int:
    digest = hashlib.sha256((meta["url"] + meta["title"] + "".join(x[2] for x in page_chunks)).encode()).hexdigest()
    with connect() as db:
        existing = db.execute("SELECT id FROM sources WHERE content_hash=?", (digest,)).fetchone()
        if existing:
            return existing["id"]
        columns = ("title", "kind", "stage", "subject", "edition", "publisher", "volume", "url", "license", "file_path", "catalog_id")
        values = [meta.get(column, "") or None if column == "catalog_id" else meta.get(column, "") for column in columns]
        cursor = db.execute(f"INSERT INTO sources ({','.join(columns)},content_hash) VALUES ({','.join('?' for _ in columns)},?)", (*values, digest))
        source_id = cursor.lastrowid
        for page, section, body in page_chunks:
            cursor = db.execute("INSERT INTO chunks (source_id,page,section,text) VALUES (?,?,?,?)", (source_id, page, section, body))
            db.execute("INSERT INTO chunks_fts (rowid,text) VALUES (?,?)", (cursor.lastrowid, body))
        return source_id


def delete_source(source_id: int) -> bool:
    with connect() as db:
        source = db.execute("SELECT file_path FROM sources WHERE id=?", (source_id,)).fetchone()
        if not source:
            return False
        ids = [row["id"] for row in db.execute("SELECT id FROM chunks WHERE source_id=?", (source_id,))]
        db.executemany("DELETE FROM chunks_fts WHERE rowid=?", [(i,) for i in ids])
        db.execute("DELETE FROM sources WHERE id=?", (source_id,))
        if source["file_path"]:
            Path(source["file_path"]).unlink(missing_ok=True)
        return True


def list_catalog():
    with connect() as db:
        rows = db.execute("""SELECT c.*, COUNT(s.id) AS source_count,
          SUM(CASE WHEN s.kind='textbook' THEN 1 ELSE 0 END) AS textbook_count
          FROM catalog c LEFT JOIN sources s ON s.catalog_id=c.id
          GROUP BY c.id ORDER BY c.stage,c.subject""").fetchall()
        return [dict(row) for row in rows]


def list_sources():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT id,title,kind,stage,subject,edition,publisher,volume,url,license,catalog_id,created_at,(SELECT COUNT(*) FROM chunks WHERE source_id=sources.id) AS chunk_count FROM sources ORDER BY id DESC")]


def get_source(source_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None


def get_source_text(source_id: int) -> str:
    with connect() as db:
        pieces = [row["text"] for row in db.execute(
            "SELECT text FROM chunks WHERE source_id=? ORDER BY id LIMIT 120", (source_id,)
        )]
    body = ""
    for piece in pieces:
        if not body:
            body = piece
            continue
        overlap = next((size for size in range(min(80, len(piece), len(body)), 0, -1)
                        if body.endswith(piece[:size])), 0)
        body += piece[overlap:] if overlap else "\n\n" + piece
    return body[:80000]


def _terms(query: str) -> list[str]:
    raw = [x.strip().lower() for x in jieba.lcut(query) if x.strip()]
    return list(dict.fromkeys(x for x in raw if (len(x) >= 2 or re.fullmatch(r"[a-z0-9]+", x)) and x not in STOPWORDS))[:10]


def search(query: str, stage: str = "", subject: str = "", limit: int = 8, group: bool = True) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    ids: set[int] = set()
    with connect() as db:
        long_terms = [term for term in terms if len(term) >= 3]
        if long_terms:
            expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in long_terms)
            try:
                rows = db.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 160", (expression,)).fetchall()
                ids.update(row["rowid"] for row in rows)
            except sqlite3.OperationalError:
                pass
        clauses = " OR ".join("c.text LIKE ?" for _ in terms[:5])
        rows = db.execute(f"SELECT c.id FROM chunks c JOIN sources s ON s.id=c.source_id WHERE ({clauses}) AND (?='' OR s.stage=? OR s.stage='通用') AND (?='' OR s.subject=? OR s.subject='通用') LIMIT 200", (*[f"%{term}%" for term in terms[:5]], stage, stage, subject, subject)).fetchall()
        ids.update(row["id"] for row in rows)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        candidates = db.execute(f"""SELECT c.id,c.page,c.section,c.text,
          s.id AS source_id,s.title,s.kind,s.stage,s.subject,s.edition,s.publisher,s.volume,s.url,s.license,s.catalog_id
          FROM chunks c JOIN sources s ON s.id=c.source_id
          WHERE c.id IN ({placeholders}) AND (?='' OR s.stage=? OR s.stage='通用')
          AND (?='' OR s.subject=? OR s.subject='通用')""", (*ids, stage, stage, subject, subject)).fetchall()
    result = []
    for row in candidates:
        item = dict(row)
        body = item["text"].lower()
        title = item["title"].lower()
        item["score"] = round(sum((3 if term in body else 0) + (2 if term in title else 0) for term in terms) + (1.5 if item["kind"] == "textbook" else .8 if item["kind"] == "official" else 0), 2)
        if item["score"] <= 0:
            continue
        first = min((body.find(term) for term in terms if term in body), default=0)
        start = max(0, first - 55)
        item["snippet"] = ("…" if start else "") + item["text"][start:start + 220] + ("…" if start + 220 < len(item["text"]) else "")
        item.pop("text")
        result.append(item)
    result.sort(key=lambda x: (-x["score"], x["source_id"], x["page"] or 0))
    if not group:
        return result[:limit]
    grouped = []
    seen = set()
    for item in result:
        key = (item["source_id"], item["page"] if item["kind"] == "textbook" else None)
        if key not in seen:
            grouped.append(item)
            seen.add(key)
    return grouped[:limit]


def get_chunks(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    with connect() as db:
        rows = db.execute(f"SELECT c.*,s.title,s.kind,s.stage,s.subject,s.edition,s.volume,s.url FROM chunks c JOIN sources s ON s.id=c.source_id WHERE c.id IN ({','.join('?' for _ in ids)})", ids).fetchall()
        by_id = {r["id"]: dict(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]
