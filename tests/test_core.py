from fastapi.testclient import TestClient

from app import db
from app.main import app


def textbook_meta(subject='数学', catalog='初中-数学'):
    return {'title': f'{subject} 八年级下册', 'kind': 'textbook', 'stage': '初中',
            'subject': subject, 'edition': '人教版', 'publisher': '人民教育出版社',
            'volume': '八年级下册', 'url': '', 'license': '本地研究', 'file_path': '',
            'catalog_id': catalog}


def test_textbook_search_and_read_only_api(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    assert len(db.list_catalog()) == 20
    source_id = db.add_source(textbook_meta(), [(80, '函数',
        '一般地，在一个变化过程中，如果有两个变量 x 与 y，并且对于 x 的每一个确定的值，y 都有唯一确定的值与其对应，那么我们就说 y 是 x 的函数。')])
    results = db.search('函数的定义是什么？', stage='初中', subject='数学')
    assert results[0]['source_id'] == source_id
    assert results[0]['page'] == 80
    with TestClient(app) as client:
        assert client.get(f'/api/sources/{source_id}/content').status_code == 200
        assert client.post('/api/upload').status_code in (404, 405)
        assert client.delete(f'/api/sources/{source_id}').status_code == 405
        assert client.post('/api/web/import', json={'pageid': 1}).status_code in (404, 405)
        assert client.get('/api/sources').json()[0]['kind'] == 'textbook'


def test_chat_falls_back_to_model_with_separate_status(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    async def fake_answer(question, evidence, mode, history):
        assert question == '欧姆定律是什么？'
        assert evidence == []
        assert mode == 'general'
        return '欧姆定律表明，在温度不变时，导体中的电流与两端电压成正比。'
    monkeypatch.setattr('app.main.answer', fake_answer)
    with TestClient(app) as client:
        response = client.post('/api/chat', json={'query': '欧姆定律是什么？'})
    assert response.status_code == 200
    data = response.json()
    assert data['answer'].startswith('欧姆定律表明')
    assert data['citations'] == []
    assert data['evidence_status'] == 'not_found'
    assert data['model_used'] is True


def test_only_textbooks_enter_index_and_suggestions(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    db.add_source(textbook_meta('语文', '初中-语文') | {'title': '语文 七年级上册'},
                  [(13, '济南的冬天', '济南的冬天\n济南的冬天是一篇散文。')])
    assert '济南的冬天' in db.suggest('济南的', '初中', '语文')['completions']
    assert '济南的冬天' in db.suggest('济南的东天', '初中', '语文')['corrections']
    try:
        db.add_source(textbook_meta() | {'kind': 'open_web'}, [(1, '', '非教材内容')])
        assert False, 'Non-textbook sources must be rejected'
    except ValueError:
        pass
