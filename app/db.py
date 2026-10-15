import hashlib
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
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
          kind TEXT NOT NULL CHECK(kind='textbook'),
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
        CREATE TABLE IF NOT EXISTS search_terms (
          source_id INTEGER NOT NULL, term TEXT NOT NULL, frequency INTEGER NOT NULL,
          PRIMARY KEY (source_id,term),
          FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_search_terms_term ON search_terms(term);
        """)
        db.executemany("""INSERT OR REPLACE INTO catalog
          (id,stage,subject,edition,publisher,title,catalog_url,note)
          VALUES (:id,:stage,:subject,:edition,:publisher,:title,:catalog_url,:note)""", catalog_entries())
        # Older installations may still contain imported web pages. Remove their
        # search rows as well as their source records during the schema upgrade.
        obsolete = [row["id"] for row in db.execute("SELECT id FROM sources WHERE kind!='textbook'")]
        for source_id in obsolete:
            db.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE source_id=?)", (source_id,))
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))


def add_source(meta: dict, page_chunks: list[tuple[int | None, str, str]]) -> int:
    if meta.get("kind") != "textbook":
        raise ValueError("知识库仅接受教材原件")
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
        index_source_terms(db, source_id, page_chunks)
        return source_id


def source_terms(page_chunks: list[tuple[int | None, str, str]]) -> Counter:
    """Create a small, source-backed vocabulary for completion and typo proposals."""
    terms: Counter = Counter()
    for _, _, body in page_chunks:
        terms.update(token.lower() for token in jieba.lcut(body)
                     if 2 <= len(token) <= 14 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", token))
        for line in body.splitlines():
            if len(line) > 60:
                continue
            for phrase in re.findall(r"[\u4e00-\u9fff]{3,20}", line):
                terms[phrase] += 2
    return terms


def index_source_terms(connection: sqlite3.Connection, source_id: int,
                       page_chunks: list[tuple[int | None, str, str]]) -> None:
    connection.execute("DELETE FROM search_terms WHERE source_id=?", (source_id,))
    terms = source_terms(page_chunks)
    connection.executemany("INSERT INTO search_terms (source_id,term,frequency) VALUES (?,?,?)",
                           ((source_id, term, freq) for term, freq in terms.items()))


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
        return [dict(row) for row in db.execute("SELECT id,title,kind,stage,subject,edition,publisher,volume,url,license,catalog_id,created_at,(SELECT COUNT(*) FROM chunks WHERE source_id=sources.id) AS chunk_count FROM sources WHERE kind='textbook' ORDER BY id DESC")]


def get_source(source_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM sources WHERE id=? AND kind='textbook'", (source_id,)).fetchone()
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


def suggest(query: str, stage: str = "", subject: str = "", limit: int = 6) -> dict:
    """Return completions and close spellings that actually occur in local sources."""
    value = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", unicodedata.normalize("NFKC", query)).lower()[:30]
    if len(value) < 2:
        return {"completions": [], "corrections": []}
    scope = "s.kind='textbook' AND (?='' OR s.stage=?) AND (?='' OR s.subject=?)"
    filters = (stage, stage, subject, subject)
    with connect() as db:
        completions = db.execute(f"""SELECT t.term, SUM(t.frequency) AS popularity FROM search_terms t
            JOIN sources s ON s.id=t.source_id WHERE t.term LIKE ? AND LENGTH(t.term)<=14 AND {scope}
            GROUP BY t.term ORDER BY popularity DESC LIMIT 50""", (value + "%", *filters)).fetchall()
        anchors = [value[:2]]
        if len(value) >= 5:
            anchors.append(value[-2:])
        fuzzy = db.execute(f"""SELECT t.term, SUM(t.frequency) AS popularity FROM search_terms t
            JOIN sources s ON s.id=t.source_id WHERE (t.term LIKE ? OR t.term LIKE ?)
            AND LENGTH(t.term) BETWEEN ? AND ? AND {scope}
            GROUP BY t.term ORDER BY popularity DESC LIMIT 350""",
            (f"%{anchors[0]}%", f"%{anchors[-1]}%", max(2, len(value)-3), len(value)+4, *filters)).fetchall()
    comp = [row["term"] for row in completions if row["term"] != value][:limit]
    scored = []
    for row in fuzzy:
        term = row["term"]
        if term == value or term.startswith(value) or value.startswith(term):
            continue
        ratio = SequenceMatcher(None, value, term, autojunk=False).ratio()
        if ratio >= (0.78 if len(value) >= 4 else 0.6):
            scored.append((ratio, min(row["popularity"], 100), term))
    scored.sort(key=lambda row: (-row[0], -row[1], len(row[2])))
    return {"completions": comp, "corrections": [row[2] for row in scored[:limit]]}


def search(query: str, stage: str = "", subject: str = "", limit: int = 8, group: bool = True) -> list[dict]:
    named = re.search(r"《([^》]{2,40})》", query)
    definition = re.search(r"(?:什么是|请解释)?([\u4e00-\u9fffA-Za-z0-9]{2,20})的定义", query)
    focus = named.group(1) if named else definition.group(1) if definition else query
    wants_definition = bool(definition or re.search(r"什么是|怎么定义|如何定义", query))
    likely_subject = next((name for markers, name in (
        (("函数", "勾股", "方程"), "数学"),
        (("光合作用", "细胞", "生态系统"), "生物学"),
        (("电流", "电压", "牛顿定律"), "物理"),
        (("中和反应", "酸碱", "化学反应"), "化学"),
    ) if any(marker in query for marker in markers)), "")
    terms = _terms(focus)
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
        rows = db.execute(f"SELECT c.id FROM chunks c JOIN sources s ON s.id=c.source_id WHERE s.kind='textbook' AND ({clauses}) AND (?='' OR s.stage=?) AND (?='' OR s.subject=?)", (*[f"%{term}%" for term in terms[:5]], stage, stage, subject, subject)).fetchall()
        ids.update(row["id"] for row in rows)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        candidates = db.execute(f"""SELECT c.id,c.page,c.section,c.text,
          s.id AS source_id,s.title,s.kind,s.stage,s.subject,s.edition,s.publisher,s.volume,s.url,s.license,s.catalog_id
          FROM chunks c JOIN sources s ON s.id=c.source_id
          WHERE c.id IN ({placeholders}) AND s.kind='textbook' AND (?='' OR s.stage=?)
          AND (?='' OR s.subject=?)""", (*ids, stage, stage, subject, subject)).fetchall()
    result = []
    for row in candidates:
        item = dict(row)
        body = item["text"].lower()
        title = item["title"].lower()
        item["score"] = round(sum((3 if term in body else 0) + (2 if term in title else 0) for term in terms)
                              + (7 if len(focus) >= 3 and focus.lower() in body else 0)
                              + (4 if len(focus) >= 3 and focus.lower() in body[:110] else 0)
                              + (1.5 if item["kind"] == "textbook" else 0)
                              + (6 if likely_subject and item["subject"] == likely_subject else 0)
                              + (9 if wants_definition and "一般地" in body and any(cue in body for cue in ("叫做", "称为", "就说")) else 0)
                              + (5 if wants_definition and "唯一确定" in body else 0)
                              + (7 if wants_definition and "那么我们就说" in body else 0), 2)
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
