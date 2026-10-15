import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

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
    results = db.search(request.query, request.stage, request.subject, request.limit)
    proposals = db.suggest(request.query, request.stage, request.subject)
    corrected_query = ""
    if not results and proposals["corrections"]:
        candidate = proposals["corrections"][0]
        if candidate != request.query:
            results = db.search(candidate, request.stage, request.subject, request.limit)
            if results:
                corrected_query = candidate
    return {"results": results, "corrected_query": corrected_query, "suggestions": proposals}


@app.get("/api/suggest")
def suggestions(q: str = Query(min_length=2, max_length=60), stage: str = "", subject: str = ""):
    return db.suggest(q, stage, subject)


@app.post("/api/chat")
async def chat(request: ChatRequest):
    matches = db.search(request.query, request.stage, request.subject, 6) if request.mode == "grounded" else []
    if matches and matches[0]["score"] < 7.5:
        matches = []
    if matches and re.search(r"定义|什么是", request.query) and len(matches) > 1 and matches[0]["score"] >= matches[1]["score"] + 5:
        matches = matches[:1]
    interpreted_query = ""
    if request.mode == "grounded" and not matches:
        corrections = db.suggest(request.query, request.stage, request.subject)["corrections"]
        if corrections:
            candidate = corrections[0]
            matches = db.search(candidate, request.stage, request.subject, 6)
            if matches and matches[0]["score"] >= 7.5:
                interpreted_query = candidate
            else:
                matches = []
    evidence = db.get_chunks([item["id"] for item in matches]) if matches else []
    response_mode = "grounded" if evidence and request.mode == "grounded" else "general"
    try:
        content = await answer(request.query, evidence, response_mode, request.history)
    except ModelError as exc:
        raise HTTPException(503, str(exc)) from exc
    citations = [{"number": i + 1, "chunk_id": item["id"], "source_id": item["source_id"],
                  "title": item["title"], "kind": item["kind"], "page": item["page"],
                  "stage": item["stage"], "subject": item["subject"],
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


app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
