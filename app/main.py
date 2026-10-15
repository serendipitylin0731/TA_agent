import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .deepseek import ModelError, answer, configured
from .ingest import pdf_chunks, plain_chunks

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web"
WIKI_API = "https://zh.wikipedia.org/w/api.php"
WIKI_LICENSE = "CC BY-SA 4.0 · https://creativecommons.org/licenses/by-sa/4.0/"


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


class WikiImportRequest(BaseModel):
    pageid: int = Field(gt=0)
    subject: str = "通用"


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
    return {"results": db.search(request.query, request.stage, request.subject, request.limit)}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    matches = db.search(request.query, request.stage, request.subject, 6, group=False) if request.mode == "grounded" else []
    if request.mode == "grounded" and not matches:
        return {"answer": "当前知识库没有足够证据回答这个问题。可先在‘联网资料’中检索并导入开放资料，或导入有使用权限的教材 PDF；我不会猜测教材页码。", "citations": [], "mode": request.mode, "model_used": False}
    evidence = db.get_chunks([item["id"] for item in matches])
    try:
        content = await answer(request.query, evidence, request.mode, request.history)
    except ModelError as exc:
        raise HTTPException(503, str(exc)) from exc
    citations = [{"number": i + 1, "chunk_id": item["id"], "source_id": item["source_id"],
                  "title": item["title"], "kind": item["kind"], "page": item["page"],
                  "url": item["url"], "edition": item["edition"], "volume": item["volume"]}
                 for i, item in enumerate(evidence)]
    return {"answer": content, "citations": citations, "mode": request.mode, "model_used": True}


@app.get("/api/web/search")
async def web_search(q: str = Query(min_length=2, max_length=100)):
    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "TA-agent/0.1 (educational research; source-linked)"}) as client:
            response = await client.get(WIKI_API, params={"action": "query", "list": "search", "srsearch": q, "srlimit": 8, "srnamespace": 0, "format": "json", "formatversion": 2})
            response.raise_for_status()
        hits = response.json().get("query", {}).get("search", [])
        return {"provider": "中文维基百科", "license": WIKI_LICENSE, "results": [
            {"pageid": item["pageid"], "title": item["title"],
             "snippet": BeautifulSoup(item.get("snippet", ""), "html.parser").get_text(" ", strip=True),
             "url": f"https://zh.wikipedia.org/?curid={item['pageid']}"} for item in hits
        ]}
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise HTTPException(502, f"开放网络资料检索失败：{type(exc).__name__}") from exc


@app.post("/api/web/import")
async def import_wikipedia(request: WikiImportRequest):
    try:
        async with httpx.AsyncClient(timeout=18, headers={"User-Agent": "TA-agent/0.1 (educational research; source-linked)"}) as client:
            response = await client.get(WIKI_API, params={"action": "query", "prop": "extracts|info", "pageids": request.pageid, "explaintext": 1, "inprop": "url", "format": "json", "formatversion": 2})
            response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", [])
        if not pages or "missing" in pages[0]:
            raise HTTPException(404, "网页条目不存在")
        page = pages[0]
        text = page.get("extract", "")[:50000]
        if len(text.strip()) < 80:
            raise HTTPException(422, "该条目没有足够的可提取正文")
        meta = {"title": page["title"], "kind": "open_web", "stage": "通用", "subject": request.subject,
                "edition": "", "publisher": "维基百科贡献者", "volume": "", "url": page.get("canonicalurl", f"https://zh.wikipedia.org/?curid={request.pageid}"),
                "license": WIKI_LICENSE, "file_path": "", "catalog_id": None}
        source_id = db.add_source(meta, plain_chunks(text))
        return {"source_id": source_id, "title": page["title"], "chunks": len(plain_chunks(text)), "license": WIKI_LICENSE}
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, KeyError) as exc:
        raise HTTPException(502, f"导入开放资料失败：{type(exc).__name__}") from exc


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), catalog_id: str = Form(...), volume: str = Form(...), authorized: bool = Form(False)):
    if not authorized:
        raise HTTPException(400, "请确认你有权在本地项目中处理此文件")
    catalog_item = next((item for item in db.list_catalog() if item["id"] == catalog_id), None)
    if not catalog_item:
        raise HTTPException(400, "请选择有效的教材目录项")
    if not volume.strip() or len(volume) > 70:
        raise HTTPException(400, "请填写具体册次，最多 70 字")
    content = await file.read(35 * 1024 * 1024 + 1)
    if len(content) > 35 * 1024 * 1024:
        raise HTTPException(413, "单份文件不能超过 35 MB")
    name = file.filename or "document"
    extension = Path(name).suffix.lower()
    if extension not in (".pdf", ".txt", ".md"):
        raise HTTPException(400, "仅支持 PDF、TXT、Markdown")
    if extension == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(400, "PDF 文件格式无效")
    upload_dir = db.data_dir() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}{extension}"
    path.write_bytes(content)
    try:
        chunks = pdf_chunks(path) if extension == ".pdf" else plain_chunks(content.decode("utf-8-sig"))
        if not chunks:
            raise ValueError("文件没有可检索文字")
        source_id = db.add_source({"title": name[:180], "kind": "textbook", "stage": catalog_item["stage"],
            "subject": catalog_item["subject"], "edition": catalog_item["edition"],
            "publisher": catalog_item["publisher"], "volume": volume.strip(), "url": "",
            "license": "用户自行提供并确认本地使用权限", "file_path": str(path), "catalog_id": catalog_id}, chunks)
        source = db.get_source(source_id)
        if source["file_path"] != str(path):
            path.unlink(missing_ok=True)
        return {"source_id": source_id, "title": name, "chunks": len(chunks), "pages": max((page or 0 for page, _, _ in chunks), default=0)}
    except (ValueError, UnicodeDecodeError, RuntimeError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/sources/{source_id}/file")
def source_file(source_id: int):
    source = db.get_source(source_id)
    if not source or not source["file_path"] or not Path(source["file_path"]).is_file():
        raise HTTPException(404, "本地文件不存在")
    return FileResponse(source["file_path"], media_type="application/pdf" if source["file_path"].endswith(".pdf") else "text/plain")


@app.delete("/api/sources/{source_id}")
def remove_source(source_id: int):
    if not db.delete_source(source_id):
        raise HTTPException(404, "资料不存在")
    return {"deleted": True}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
