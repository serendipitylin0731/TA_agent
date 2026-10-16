import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .deepseek import ModelError, answer, configured

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="TA Agent API", version="0.1.0", lifespan=lifespan)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    stage: str = ""
    subject: str = ""
    limit: int = Field(default=8, ge=1, le=20)


class ChatRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1500)
    mode: str = Field(default="grounded", pattern="^(grounded|general)$")
    stage: str = ""
    subject: str = ""
    history: list[dict] = Field(default_factory=list)


@app.get("/api/status")
def status():
    sources = db.list_sources()
    catalog = db.list_catalog()
    return {"deepseek_configured": configured(), "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            "source_count": len(sources), "textbook_count": sum(source["kind"] == "textbook" for source in sources),
            "catalog_slots": len(catalog), "filled_slots": sum(item["textbook_count"] > 0 for item in catalog)}


@app.get("/api/catalog")
def catalog():
    return db.list_catalog()


@app.get("/api/sources")
def sources():
    return db.list_sources()


@app.get("/api/sources/{source_id}/content")
def source_content(source_id: int):
    source = db.get_source(source_id)
    if not source:
        raise HTTPException(404, "资料不存在")
    public = {key: value for key, value in source.items() if key not in {"file_path", "content_hash"}}
    public["file_type"] = Path(source["file_path"]).suffix.lower() if source["file_path"] else ""
    return {"source": public, "text": db.get_source_text(source_id) if public["file_type"] != ".pdf" else ""}


@app.post("/api/search")
def search(request: SearchRequest):
    results = [item for item in db.search(request.query, request.stage, request.subject, request.limit * 12)
               if item["relevance"] == "strong"]
    proposals = db.suggest(request.query, request.stage, request.subject)
    corrected_query = ""
    if not results and proposals["corrections"]:
        candidate = proposals["corrections"][0]
        if candidate != request.query:
            results = [item for item in db.search(candidate, request.stage, request.subject, request.limit * 12)
                       if item["relevance"] == "strong"]
            if results:
                corrected_query = candidate
    if not results:
        plan = db._query_plan(request.query)
        term_suggestions = db.suggest(plan["core"], request.stage, request.subject)["corrections"]
        for term in term_suggestions[:3]:
            candidate = term + ("的" + plan["facet"] if plan["facet"] else "")
            results = [item for item in db.search(candidate, request.stage, request.subject, request.limit * 12)
                       if item["relevance"] == "strong"]
            if results:
                corrected_query = candidate
                proposals["corrections"] = list(dict.fromkeys([candidate] + proposals["corrections"]))[:6]
                break
    grouped = {}
    for item in results:
        source = grouped.setdefault(item["source_id"], {**item, "key_pages": []})
        if item["page"] and len(source["key_pages"]) < 8:
            source["key_pages"].append({"page": item["page"], "snippet": item["snippet"], "score": item["score"]})
    return {"results": list(grouped.values())[:request.limit],
            "corrected_query": corrected_query, "suggestions": proposals}


@app.get("/api/suggest")
def suggestions(q: str = Query(min_length=2, max_length=60), stage: str = "", subject: str = ""):
    return db.suggest(q, stage, subject)


@app.post("/api/chat")
async def chat(request: ChatRequest):
    broad = bool(re.search(r"发展|演变|历程|变化|沿革", request.query))
    candidates = db.search(request.query, request.stage, request.subject, 90) if request.mode == "grounded" else []
    if broad:
        topic = db._query_plan(request.query)["core"]
        topic = re.sub(r"^(中国古代|中国近代|我国古代|我国)", "", topic)
        if len(topic) >= 2:
            more = db.search(topic, request.stage, request.subject, 90)
            candidates = list({(item["source_id"], item["page"]): item for item in candidates + more}.values())
            candidates.sort(key=lambda item: -item["score"])
    matches = [item for item in candidates if item["relevance"] == "strong"]
    if broad and matches:
        focus = matches[0]["subject"]
        matches = [item for item in matches if item["subject"] == focus]
        selected = []
        used_sources = {}
        for item in matches:
            source_pages = used_sources.setdefault(item["source_id"], [])
            if len(source_pages) >= 3 or any(abs((item["page"] or 0) - page) < 2 for page in source_pages):
                continue
            selected.append(item)
            source_pages.append(item["page"] or 0)
            if len(selected) >= 8:
                break
        matches = selected
    elif matches:
        top_score = matches[0]["score"]
        matches = [item for item in matches if item["score"] >= top_score - 7][:6]
        if re.search(r"定义|什么是", request.query) and top_score >= (matches[1]["score"] + 6 if len(matches) > 1 else 0):
            matches = matches[:1]
    interpreted_query = ""
    if request.mode == "grounded" and not matches:
        plan = db._query_plan(request.query)
        corrections = db.suggest(request.query, request.stage, request.subject)["corrections"]
        if not corrections:
            corrections = [term + ("的" + plan["facet"] if plan["facet"] else "")
                           for term in db.suggest(plan["core"], request.stage, request.subject)["corrections"]]
        if corrections:
            candidate = corrections[0]
            matches = [item for item in db.search(candidate, request.stage, request.subject, 6) if item["relevance"] == "strong"]
            if matches:
                interpreted_query = candidate
            else:
                matches = []
    evidence = db.get_page_evidence([item["id"] for item in matches]) if matches else []
    response_mode = "grounded" if evidence and request.mode == "grounded" else "general"
    try:
        content = await answer(request.query, evidence, response_mode, request.history)
        if response_mode == "grounded":
            cited = {int(number) for number in re.findall(r"\[(\d+)\]", content)}
            insufficient = re.search(
                r"(?:不能|无法|不足以).{0,24}(?:列出|回答|确定|确认|说明)|"
                r"(?:片段|资料|教材).{0,24}(?:没有|未|不足以|无法).{0,28}(?:给出|列出|回答|说明|涉及|明确)|"
                r"(?:没有|未).{0,24}(?:对.+?作出|给出|列出).{0,20}(?:说明|列举|特征|定义|内容)",
                content,
            )
            if not cited or insufficient:
                content = await answer(request.query, [], "general", request.history)
                response_mode = "general"
                evidence = []
    except ModelError as exc:
        raise HTTPException(503, str(exc)) from exc
    citations = [{"number": i + 1, "chunk_id": item["id"], "source_id": item["source_id"],
                  "title": item["title"], "kind": item["kind"], "page": item["page"],
                  "stage": item["stage"], "subject": item["subject"], "section": item["section"],
                  "url": item["url"], "edition": item["edition"], "volume": item["volume"]}
                 for i, item in enumerate(evidence)]
    cited_numbers = {int(number) for number in re.findall(r"\[(\d+)\]", content)}
    if cited_numbers:
        citations = [citation for citation in citations if citation["number"] in cited_numbers]
    return {"answer": content, "citations": citations, "mode": response_mode,
            "model_used": True, "interpreted_query": interpreted_query,
            "evidence_status": "found" if evidence else "not_found"}


@app.get("/api/sources/{source_id}/file")
def source_file(source_id: int):
    source = db.get_source(source_id)
    if not source or not source["file_path"] or not Path(source["file_path"]).is_file():
        raise HTTPException(404, "本地文件不存在")
    return FileResponse(source["file_path"], media_type="application/pdf" if source["file_path"].endswith(".pdf") else "text/plain")


@app.get("/api/sources/{source_id}/pages")
def source_pages(source_id: int, q: str = Query(min_length=2, max_length=300)):
    if not db.get_source(source_id):
        raise HTTPException(404, "教材不存在")
    return {"pages": db.matching_pages(source_id, q)}


@app.get("/api/sources/{source_id}/cover")
def source_cover(source_id: int):
    source = db.get_source(source_id)
    if not source or not source["file_path"] or Path(source["file_path"]).suffix.lower() != ".pdf":
        raise HTTPException(404, "教材封面不存在")
    path = Path(source["file_path"])
    if not path.is_file():
        raise HTTPException(404, "本地文件不存在")
    cover_dir = db.data_dir() / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover = cover_dir / f"{source_id}-{path.stat().st_mtime_ns}.png"
    if not cover.exists():
        with pymupdf.open(path) as document:
            pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(.42, .42), alpha=False)
            cover.write_bytes(pixmap.tobytes("png"))
    return FileResponse(cover, media_type="image/png")


@app.get("/api/sources/{source_id}/markdown")
def source_markdown(source_id: int):
    if not db.get_source(source_id):
        raise HTTPException(404, "教材不存在")
    path = db.data_dir() / "markdown" / f"{source_id}.md"
    if not path.is_file():
        raise HTTPException(404, "Markdown 版本尚未生成")
    return FileResponse(path, media_type="text/markdown; charset=utf-8")


@app.get("/api/sources/{source_id}/markdown-images/{filename}")
def source_markdown_image(source_id: int, filename: str):
    if not db.get_source(source_id) or not re.fullmatch(r"p\d{4}-[a-f0-9]{12}\.(?:png|jpg|jpeg|webp)", filename):
        raise HTTPException(404, "教材插图不存在")
    path = db.data_dir() / "markdown" / "images" / str(source_id) / filename
    if not path.is_file():
        raise HTTPException(404, "教材插图不存在")
    return FileResponse(path)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
