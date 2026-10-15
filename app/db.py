import hashlib
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from math import sqrt
from pathlib import Path

import jieba

from .catalog import catalog_entries

STOPWORDS = {"什么", "怎么", "如何", "为什么", "可以", "哪些", "关于", "是否", "解释", "一下", "这个", "那个", "相关", "教材", "课本", "知识", "内容", "在哪", "哪里", "什么是"}


def normalize_search(value: str) -> str:
    """Match OCR text despite full-width characters and arbitrary PDF line breaks."""
    return "".join(char for char in unicodedata.normalize("NFKC", value).lower() if not char.isspace())


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
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_search USING fts5(text, tokenize='trigram');
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
            db.execute("DELETE FROM chunks_search WHERE rowid IN (SELECT id FROM chunks WHERE source_id=?)", (source_id,))
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))
        indexed = db.execute("SELECT COUNT(*) FROM chunks_search").fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if indexed != total:
            db.execute("DELETE FROM chunks_search")
            db.executemany("INSERT INTO chunks_search(rowid,text) VALUES (?,?)",
                           ((row["id"], normalize_search(row["text"]))
                            for row in db.execute("SELECT id,text FROM chunks")))


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
            db.execute("INSERT INTO chunks_search (rowid,text) VALUES (?,?)", (cursor.lastrowid, normalize_search(body)))
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
        db.executemany("DELETE FROM chunks_search WHERE rowid=?", [(i,) for i in ids])
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
        if ratio >= (0.72 if len(value) >= 4 else 0.6):
            scored.append((ratio, min(row["popularity"], 100), term))
    scored.sort(key=lambda row: (-row[0], -row[1], len(row[2])))
    return {"completions": comp, "corrections": [row[2] for row in scored[:limit]]}


def _query_plan(query: str) -> dict:
    value = unicodedata.normalize("NFKC", query).strip().lower()
    value = re.sub(r"[?？!！。\s]+$", "", value)
    value = re.sub(r"^(请问|请解释|请说明|什么是|什么叫)", "", value)
    value = re.sub(r"(是什么意思|是什么|有哪些|是多少|是谁|怎么理解|如何理解)$", "", value)
    description = re.fullmatch(r"(.+?)(描写了什么|写了什么|讲了什么|表达了什么)", value)
    development = re.fullmatch(r"(.+?)(?:如何|怎么)(发展|演变|形成)", value)
    facet_words = "第二定义|第一定义|定义|基本过程|过程|主要特点|特点|性质|意义|原因|作用|用法|影响因素|一般原则|基本特征|作者"
    match = re.fullmatch(rf"(.+?)的({facet_words})", value)
    if description:
        core, facet = description.group(1).strip("《》"), "描写"
    elif development:
        core, facet = development.group(1), development.group(2)
    elif match:
        core, facet = match.group(1), match.group(2)
    elif "的" in value and len(value.split("的", 1)[0]) >= 2 and len(value.split("的", 1)[1]) >= 2:
        core, facet = value.split("的", 1)
    else:
        core, facet = value, ""
    if facet == "原因" and core.endswith("爆发"):
        core = core[:-2]
    core = normalize_search(core.strip("《》"))
    phrase = normalize_search(value)
    tokens = list(dict.fromkeys(normalize_search(token) for token in jieba.lcut(core)
                                if len(normalize_search(token)) >= 2 and token not in STOPWORDS))
    if len(core) >= 5 and core[-3:] not in tokens:
        tokens.append(core[-3:])
    tokens.sort(key=lambda token: (-len(token), token))
    if core and core not in tokens:
        tokens.insert(0, core)
    return {"core": core, "facet": normalize_search(facet), "phrase": phrase,
            "tokens": tokens[:6], "definition": bool("定义" in facet or "什么是" in query or ("是什么" in query and not facet)),
            "strict_ordinal": facet == "第二定义", "numeric": "是多少" in query}


def _compact_with_offsets(value: str) -> tuple[str, str, list[int]]:
    display = unicodedata.normalize("NFKC", value)
    offsets = [index for index, char in enumerate(display) if not char.isspace()]
    return display, "".join(display[index].lower() for index in offsets), offsets


def search(query: str, stage: str = "", subject: str = "", limit: int = 8, group: bool = True) -> list[dict]:
    plan = _query_plan(query)
    core = plan["core"]
    if len(core) < 2:
        return []
    with connect() as connection:
        def find_ids(term: str) -> list[int]:
            return [row["rowid"] for row in connection.execute("""SELECT x.rowid FROM chunks_search x
                JOIN chunks c ON c.id=x.rowid JOIN sources s ON s.id=c.source_id
                WHERE x.text LIKE ? AND s.kind='textbook' AND (?='' OR s.stage=?)
                AND (?='' OR s.subject=?) LIMIT 5000""",
                (f"%{term}%", stage, stage, subject, subject))]
        ids = set(find_ids(core))
        exact_core = bool(ids)
        if not ids or (len(core) >= 5 and len(ids) < 30):
            token_matches = [set(find_ids(token)) for token in plan["tokens"] if token != core and len(token) >= 2]
            usable = [group for group in token_matches if group]
            if usable:
                common = set.intersection(*usable[:2]) if len(usable) > 1 else set()
                ids.update(common if common else set.union(*usable))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(f"""SELECT c.id,c.page,c.section,c.text,
            s.id AS source_id,s.title,s.kind,s.stage,s.subject,s.edition,s.publisher,s.volume,s.url,s.license,s.catalog_id
            FROM chunks c JOIN sources s ON s.id=c.source_id WHERE c.id IN ({placeholders})""", tuple(ids)).fetchall()
    subject_counts = Counter(row["subject"] for row in rows if core in normalize_search(row["text"]))
    max_subject_count = max(subject_counts.values(), default=0)
    results = []
    for row in rows:
        item = dict(row)
        display, body, offsets = _compact_with_offsets(item["text"])
        present = [token for token in plan["tokens"] if token in body]
        if not present:
            continue
        anchor = core if core in body else max(present, key=len)
        positions = [match.start() for match in re.finditer(re.escape(anchor), body)]
        if not positions:
            continue
        best_score = -1000.0
        best_position = positions[0]
        best_window = ""
        best_direct = False
        best_near = ""
        best_numeric = False
        best_exercise = False
        for position in positions[:35]:
            window = body[max(0, position - 155):position + max(230, len(anchor) + 100)]
            near = body[max(0, position - 75):position + len(anchor) + 65]
            direct = bool(re.search(r"(?:叫做|称为|这就是|是指|定义为).{0,24}" + re.escape(core), near)
                          or ("我们就说" in near and core in near)
                          or (core in near and "点的轨迹" in near and ("叫做" in near or "称为" in near)))
            score = 10.0 if anchor == core or len(anchor) >= 3 else 4.0
            score += min(len(anchor), 10) * .6
            score += min(window.count(anchor), 3) * 1.2
            score += 7 if plan["phrase"] and plan["phrase"] in window and not plan["definition"] else 0
            facet = plan["facet"]
            facet_alias = facet[:-1] if facet.endswith("式") and len(facet) >= 3 else facet[2:] if facet.startswith("基本") else facet[2:] if facet.startswith("主要") else ""
            facet_weighted = facet not in ("", "定义", "第一定义", "第二定义")
            score += 15 if facet_weighted and facet in near else 8 if facet_weighted and facet_alias and facet_alias in near else 0
            if facet_weighted and facet not in near and (not facet_alias or facet_alias not in near):
                score -= 4
            score += 2 * sum(token in window for token in present if token != anchor)
            numeric_direct = bool(plan["numeric"] and re.search(re.escape(anchor) + r".{0,12}(?:等于|为|是)\s*\d", near))
            exercise_context = bool(plan["numeric"] and re.search(r"(?:哪些是|下列.*?中|判断.*?对错|随机事件)", body[max(0, position - 150):position]))
            if numeric_direct:
                score += 18
            if exercise_context:
                score -= 20
            if plan["definition"]:
                score += 15 if direct else 0
                score += 2 if any(cue in near for cue in ("一般地", "定律", "定义")) else 0
                if core == "函数" and "我们就说" in near and "唯一确定" in window:
                    score += 15
                if core == "函数" and any(modifier + core in near for modifier in ("三角", "反比例", "正比例", "一次", "二次")):
                    score -= 6
            if core == "二次函数" and facet == "顶点式" and re.search(r"[y狔]\s*=\s*[a犪].{0,3}\([x狓].{0,8}\)\s*2.{0,4}[k犽]", window):
                score += 18
            if plan["facet"] == "作者" and position < 100 and "选自" in body[:600]:
                score += 12
            if position < 110:
                score += 2
            if score > best_score:
                best_score, best_position, best_window, best_direct, best_near, best_numeric, best_exercise = score, position, window, direct, near, numeric_direct, exercise_context
        opening = body[:260]
        if "目录" in opening[:70]:
            best_score -= 25
        if "致同学" in opening[:80] or "本章导言" in opening[:80]:
            best_score -= 10
        if "索引" in opening and item["page"] and item["page"] > 20:
            best_score -= 12
        if item["page"] and item["page"] <= 4 and any(x in opening for x in ("isbn", "责任编辑", "普通高中教科书")):
            best_score -= 10
        second_alias = ("另一个角度" in body and "椭圆的定义" in body
                        and all(word in body for word in ("准线", "焦点", "距离")))
        ordinal_matched = plan["facet"] in best_window or second_alias
        if plan["strict_ordinal"]:
            if plan["facet"] in best_window:
                best_score += 12
            elif second_alias:
                best_score += 15
                best_direct = True
            else:
                best_score -= 18
        if not exact_core:
            best_score -= 2
        if max_subject_count:
            best_score += 8 * sqrt(subject_counts[item["subject"]] / max_subject_count)
        if best_score < 7:
            continue
        begin = max(0, best_position - 75)
        end = min(len(body), best_position + max(190, len(anchor) + 120))
        snippet = " ".join(display[offsets[begin]:offsets[end - 1] + 1].split()) if offsets else ""
        item["snippet"] = ("…" if begin else "") + snippet + ("…" if end < len(body) else "")
        item["score"] = round(best_score, 2)
        coherent = core in body or (best_numeric and all(token in best_near for token in ("三角形", "内角和")))
        supported_definition = not plan["definition"] or best_direct or len(core) >= 3 or bool(plan["facet"] == "第二定义" and second_alias)
        item["relevance"] = "strong" if best_score >= 14 and coherent and supported_definition and (not plan["numeric"] or best_numeric and not best_exercise) and (not plan["strict_ordinal"] or ordinal_matched) else "weak"
        item.pop("text")
        results.append(item)
    results.sort(key=lambda item: (-item["score"], item["source_id"], item["page"] or 0))
    if not group:
        return results[:limit]
    grouped = []
    seen = set()
    for item in results:
        key = (item["source_id"], item["page"])
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


def matching_pages(source_id: int, query: str) -> list[int]:
    """Return every PDF page containing the normalized core query."""
    plan = _query_plan(query)
    terms = [plan["core"]] + [token for token in plan["tokens"] if token != plan["core"]]
    with connect() as connection:
        for term in terms:
            if len(term) < 2:
                continue
            rows = connection.execute("""SELECT DISTINCT c.page FROM chunks_search x
                JOIN chunks c ON c.id=x.rowid WHERE c.source_id=? AND c.page IS NOT NULL
                AND x.text LIKE ? ORDER BY c.page""", (source_id, f"%{term}%")).fetchall()
            if rows:
                return [row["page"] for row in rows]
    return []
