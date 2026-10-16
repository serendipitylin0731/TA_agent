from fastapi.testclient import TestClient
import pymupdf

from app import db
from app.markdown_ingest import convert_book, update_section
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


def test_chat_retries_without_irrelevant_textbook_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    db.add_source(textbook_meta(), [(18, '', '动量守恒定律是自然界中的一条重要规律。')])
    calls = []
    async def fake_answer(question, evidence, mode, history):
        calls.append(mode)
        return ('这些片段没有给出定律的具体内容。' if mode == 'grounded'
                else '系统不受外力时总动量保持不变。')
    monkeypatch.setattr('app.main.answer', fake_answer)
    with TestClient(app) as client:
        data = client.post('/api/chat', json={'query': '动量守恒定律是什么？'}).json()
    assert calls == ['grounded', 'general']
    assert data['answer'] == '系统不受外力时总动量保持不变。'
    assert data['citations'] == []
    assert data['evidence_status'] == 'not_found'


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


def test_normalized_pages_grouping_and_cover(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    pdf_path = tmp_path / 'biology.pdf'
    document = pymupdf.open()
    for label in ('封面', '光合作用'):
        page = document.new_page()
        page.insert_text((40, 40), label, fontname='china-s')
    document.save(pdf_path)
    document.close()
    source_id = db.add_source(textbook_meta('生物学', '初中-生物学') | {'file_path': str(pdf_path)}, [
        (1, '', '封面'),
        (2, '', '光 合 作 用：植物吸收光能。光合作用可以制造有机物。'),
    ])
    with TestClient(app) as client:
        data = client.post('/api/search', json={'query': '光合作用'}).json()
        assert len(data['results']) == 1
        assert data['results'][0]['key_pages'][0]['page'] == 2
        assert client.get(f'/api/sources/{source_id}/pages?q=光合作用').json()['pages'] == [2]
        cover = client.get(f'/api/sources/{source_id}/cover')
        assert cover.status_code == 200 and cover.headers['content-type'].startswith('image/png')


def test_broad_question_combines_textbook_pages(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    db.add_source(textbook_meta('历史', '初中-历史') | {'title': '历史 七年级下册'}, [
        (11, '', '中国古代科举制度的形成：隋炀帝时开设进士科，科举制度形成。'),
        (51, '', '科举制度在宋朝扩大取士名额，殿试成为常制。'),
        (89, '', '明清科举制度实行八股取士，清末废除科举制度。'),
    ])
    async def fake_answer(question, evidence, mode, history):
        assert mode == 'grounded'
        assert {item['page'] for item in evidence} == {11, 51, 89}
        return '隋朝形成[1]，宋朝发展[2]，明清以后废除[3]。'
    monkeypatch.setattr('app.main.answer', fake_answer)
    with TestClient(app) as client:
        data = client.post('/api/chat', json={'query': '中国古代科举制度如何发展？'}).json()
    assert data['evidence_status'] == 'found'
    assert {item['page'] for item in data['citations']} == {11, 51, 89}


def test_typo_rewrites_topic_before_model_answer(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    db.add_source(textbook_meta('生物学', '初中-生物学'), [
        (38, '', '光合作用在叶绿体中进行，光反应把光能转成化学能，碳反应固定二氧化碳。'),
    ])
    async def fake_answer(question, evidence, mode, history):
        assert mode == 'grounded' and evidence[0]['page'] == 38
        return '光合作用分为光反应和碳反应[1]。'
    monkeypatch.setattr('app.main.answer', fake_answer)
    with TestClient(app) as client:
        data = client.post('/api/chat', json={'query': '光合做用的过程是什么？'}).json()
    assert data['interpreted_query'] == '光合作用的过程'
    assert data['citations'][0]['page'] == 38


def test_false_exercise_statement_is_not_answer_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    db.add_source(textbook_meta(), [
        (18, '', '三角形的内角和等于180°。我们可以通过平行线证明这个结论。'),
        (135, '', '下列哪些是随机事件？任意画一个三角形，其内角和是360°；投篮一次未投中。'),
    ])
    strong = [item for item in db.search('三角形内角和是多少？') if item['relevance'] == 'strong']
    assert [item['page'] for item in strong] == [18]


def test_design_principles_retrieves_enumeration_not_evaluation(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    source_id = db.add_source(textbook_meta('通用技术', '高中-通用技术') | {'stage': '高中'}, [
        (39, '', '设计的一般原则。在长期实践中，人们逐渐总结出实用、创新、经济、道德、美观、技术规范、可持续发展等设计的一般原则。'),
        (173, '', '设计的评价是指依据设计的一般原则和要求，对设计结果进行事实判断和价值认定的活动。'),
    ])
    db.reindex_source(source_id, [
        (39, '§ 第二章 / 设计的一般原则', '设计的一般原则。在长期实践中，人们逐渐总结出实用、创新、经济、道德、美观、技术规范、可持续发展等设计的一般原则。'),
        (173, '§ 第七章 / 设计评价', '设计的评价是指依据设计的一般原则和要求，对设计结果进行事实判断和价值认定的活动。'),
    ])
    for question in ('什么是设计的一般原则？', '设计的一般原则有哪些？', '设计的一般原则包括什么？'):
        result = db.search(question, subject='通用技术')[0]
        assert result['page'] == 39
        assert '可持续发展' in db.get_chunks([result['id']])[0]['text']


def test_answer_evidence_restores_all_passages_on_hit_page(monkeypatch, tmp_path):
    monkeypatch.setenv('TA_DATA_DIR', str(tmp_path))
    db.init_db()
    source_id = db.add_source(textbook_meta('信息技术', '高中-信息技术') | {'stage': '高中'}, [
        (49, '', '算法的特征：①有穷性。②可行性。③确定性。④可以没有输入。'),
        (49, '', '⑤算法必须有输出。'),
    ])
    with db.connect() as connection:
        first_id = connection.execute('SELECT id FROM chunks WHERE source_id=? ORDER BY id LIMIT 1',
                                      (source_id,)).fetchone()['id']
    evidence = db.get_page_evidence([first_id])[0]
    assert '①有穷性' in evidence['text']
    assert '⑤算法必须有输出' in evidence['text']
    assert evidence['page'] == 49


def test_markdown_preserves_pdf_page_and_section(tmp_path):
    pdf_path = tmp_path / 'textbook.pdf'
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((40, 40), 'Chapter one', fontname='helv')
    document.save(pdf_path)
    document.close()
    source = textbook_meta() | {'id': 42, 'file_path': str(pdf_path)}
    path, chunks, _ = convert_book(source, tmp_path / 'markdown', with_images=False)
    assert '## PDF 第 1 页' in path.read_text(encoding='utf-8')
    assert chunks[0][0] == 1
    assert update_section('第二章 技术世界中的设计\n二、设计的一般原则', '', '')[1] == '设计的一般原则'
