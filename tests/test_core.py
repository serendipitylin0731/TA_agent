from fastapi.testclient import TestClient

from app import db
from app.ingest import plain_chunks
from app.main import app


def test_catalog_search_and_in_page_source(monkeypatch, tmp_path):
    monkeypatch.setenv("TA_DATA_DIR", str(tmp_path))
    db.init_db()
    catalog = db.list_catalog()
    assert len(catalog) == 20
    assert next(x for x in catalog if x["id"] == "高中-通用技术")["publisher"] == "江苏凤凰教育出版社"
    text = "光合作用让绿色植物把光能转为化学能。" * 80
    source_id = db.add_source({"title": "开放条目", "kind": "open_web", "stage": "通用", "subject": "生物学",
        "edition": "", "publisher": "测试贡献者", "volume": "", "url": "https://example.org/test",
        "license": "CC BY-SA 4.0", "file_path": "", "catalog_id": None}, plain_chunks(text))
    results = db.search("光合作用", subject="生物学")
    assert len(results) == 1
    assert results[0]["source_id"] == source_id
    assert len(db.search("光合作用", subject="生物学", group=False)) > 1
    assert db.get_source_text(source_id) == text
    with TestClient(app) as client:
        content = client.get(f"/api/sources/{source_id}/content")
        assert content.status_code == 200
        assert content.json()["text"] == text
        assert "file_path" not in content.json()["source"]
        assert client.post("/api/chat", json={"query": "欧姆定律是什么？", "mode": "grounded", "subject": "物理"}).json()["model_used"] is False


def test_upload_requires_rights_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("TA_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/upload", data={"catalog_id": "初中-语文", "volume": "七年级上册"},
                               files={"file": ("sample.txt", "测试文本".encode())})
        assert response.status_code == 400
        assert db.list_sources() == []


def test_source_backed_completion_and_typo_suggestion(monkeypatch, tmp_path):
    monkeypatch.setenv("TA_DATA_DIR", str(tmp_path))
    db.init_db()
    db.add_source({"title": "语文 七年级上册", "kind": "textbook", "stage": "初中", "subject": "语文",
        "edition": "统编版", "publisher": "人民教育出版社", "volume": "七年级上册", "url": "https://example.org/book",
        "license": "test", "file_path": "", "catalog_id": "初中-语文"},
        [(13, "济南的冬天", "济南的冬天\n济南的冬天是一篇散文。")])
    assert "济南的冬天" in db.suggest("济南的", "初中", "语文")["completions"]
    assert "济南的冬天" in db.suggest("济南的东天", "初中", "语文")["corrections"]
    assert db.suggest("济南的东天", "高中", "语文")["corrections"] == []
