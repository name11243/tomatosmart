"""Contract checks use isolated Neo4j and HTTP transports, never production telemetry."""
import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from backend import main, store as s
from backend.knowledge_graph import kg
from backend.local_ai import LocalAI, AIUnavailable


def client(role='teacher'):
    c = TestClient(main.app)
    assert c.post('/api/session', json={'role': role}).status_code == 200
    return c


def test_ai_citations_and_request_constraints(monkeypatch):
    ai = LocalAI()
    original = httpx.Client
    calls = []
    def respond(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': ai.model}]})
        payload = json.loads(request.content)
        calls.append(payload)
        return httpx.Response(200, json={'message': {'content': json.dumps({
            'statements': [{'text': '待核验资料指出应核对液位。', 'source_ids': ['K-TEST']}],
            'follow_up': ['请补充人工核对结果。']})}})
    monkeypatch.setattr('backend.local_ai.httpx.Client', lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    result = ai.generate('液位问题', [{'id': 'K-TEST', 'content': '核对液位', 'verified': False}])
    assert result['model'] == ai.model
    assert result['statements'][0]['source_ids'] == ['K-TEST']
    assert calls[0]['stream'] is False and calls[0]['think'] is False
    assert 'tools' not in calls[0] and calls[0]['format'] == 'json'


@pytest.mark.parametrize('response', ['not json', '{"statements":[]}', json.dumps({
    'statements': [{'text': '编造引用', 'source_ids': ['NOT-IN-CONTEXT']}]})])
def test_model_invalid_output_is_not_used(monkeypatch, response):
    ai = LocalAI()
    monkeypatch.setattr(ai, 'status', lambda: {'connected': True, 'models': [ai.model]})
    original = httpx.Client
    monkeypatch.setattr('backend.local_ai.httpx.Client', lambda **kw: original(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'message': {'content': response}}))))
    with pytest.raises(AIUnavailable):
        ai.generate('问题', [{'id': 'K-TEST'}])
    assert not ai.lock.locked()


def test_offline_and_busy_models(monkeypatch):
    ai = LocalAI()
    monkeypatch.setattr(ai, 'status', lambda: {'connected': False, 'message': 'offline'})
    with pytest.raises(AIUnavailable, match='offline'):
        ai.generate('问题', [])
    monkeypatch.setattr(ai, 'status', lambda: {'connected': True, 'models': [ai.model]})
    ai.lock.acquire()
    try:
        with pytest.raises(AIUnavailable, match='正在处理'):
            ai.generate('问题', [])
    finally:
        ai.lock.release()


def test_real_graph_edits_rewire_and_preserve_snapshots(monkeypatch):
    c = client()
    data = dict(title='隔离来源 A', crop='隔离作物', problem='独有卷曲故障', cause='隔离原因',
                measure='检查样本', content='真实数据库集成测试文本', source='自动化测试',
                tags=['独有卷曲故障'], environments=['隔离环境'])
    created = c.post('/api/knowledge', json=data).json()
    fake_generation = {'model': 'isolated-http-contract', 'statements': [
        {'text': '回答快照', 'source_ids': [created['id']]}], 'follow_up': []}
    monkeypatch.setattr(main.local_ai, 'generate', lambda *args: fake_generation)
    result = c.post('/api/ask', json={'question': '独有卷曲故障', 'mode': 'local_ai'}).json()
    assert result['generation'] == fake_generation and result['mode'] == 'local_ai'
    edited = c.put('/api/knowledge/' + created['id'], json={**data, 'problem': '另外一个故障',
        'cause': '更新原因', 'content': '更新后的文本', 'tags': ['另外一个故障'], 'environments': []}).json()
    assert edited['verified'] is False and edited['revisions'][0]['content'] == data['content']
    assert not kg.retrieve('独有卷曲故障')
    assert kg.retrieve('另外一个故障')[0]['cause'] == '更新原因'
    updated_graph = kg.graph([edited])
    assert not any(n['category'] == 1 for n in updated_graph['nodes'])
    favorite = c.post('/api/favorites', json={'question': result['question'], 'answer_id': result['id']}).json()
    assert favorite['answer']['generation'] == fake_generation
    assert favorite['answer']['items'][0]['content'] == data['content']
    inquiry = c.post('/api/inquiries', json={'title': 'ignored', 'answer_id': result['id']}).json()
    assert inquiry['title'] == result['question'] and '回答快照' in inquiry['content']
    assert client('student').post('/api/favorites', json={
        'question': result['question'], 'answer_id': result['id']}).status_code == 403
    assert client('student').put('/api/knowledge/' + created['id'], json=data).status_code == 403


def test_no_sources_offline_graph_and_offline_ai(monkeypatch):
    c = client()
    generate = Mock(side_effect=AIUnavailable('本地模型离线'))
    monkeypatch.setattr(main.local_ai, 'generate', generate)
    response = c.post('/api/ask', json={'question': 'zxq-unrelated-987654', 'mode': 'local_ai'})
    assert response.status_code == 200 and response.json()['generation'] is None
    generate.assert_not_called()
    assert c.post('/api/ask', json={'question': '叶片发黄', 'mode': 'local_ai'}).status_code == 503
    assert c.post('/api/ask', json={'question': '叶片发黄', 'mode': 'neo4j_graph'}).status_code == 200
    monkeypatch.setattr(kg, 'query', Mock(side_effect=ServiceUnavailable('offline')))
    assert c.get('/api/knowledge/graph').status_code == 503
    assert c.post('/api/ask', json={'question': '叶片发黄'}).status_code == 503


def test_query_without_device_and_no_cross_batch_environment():
    c = client()
    assert c.post('/api/ask', json={'question': '   '}).status_code == 422
    result = c.post('/api/ask', json={'question': '叶片发黄'}).json()
    assert result['environment'] is None and result['device'] == ''
    s.put('devices', dict(id='QA-BATCH-AI', name='isolated', batch='new', source='mqtt', thresholds={'ph_min':5.8,'ph_max':6.5,'level_min':20,'temp_max':32}))
    s.add_telemetry('QA-BATCH-AI', 'old', {'ph': 6.1}, source='mqtt')
    result = c.post('/api/ask', json={'question': '叶片发黄', 'device': 'QA-BATCH-AI'}).json()
    assert result['environment'] is None
    d = next(d for d in c.get('/api/devices').json() if d['id'] == 'QA-BATCH-AI')
    assert d['latest'] is None
    s.add_telemetry('QA-BATCH-AI', 'new', {'ph': None}, source='mqtt', ts='2020-01-01T00:00:00+00:00')
    # A separate device avoids newer old-batch samples obscuring this historical check.
    s.put('devices', dict(id='QA-STALE-AI', name='isolated', batch='new', source='mqtt', thresholds={'ph_min':5.8,'ph_max':6.5,'level_min':20,'temp_max':32}))
    s.add_telemetry('QA-STALE-AI', 'new', {'ph': None}, source='mqtt', ts='2020-01-01T00:00:00+00:00')
    result = c.post('/api/ask', json={'question': '叶片发黄', 'device': 'QA-STALE-AI'}).json()
    assert result['environment']['is_stale'] and result['environment']['values']['ph'] is None


def test_overview_filters_and_rejects_implicit_environment():
    c = client()
    source = c.post('/api/knowledge', json=dict(title='无环境假设资料', problem='独特标签',
        cause='记录原因', measure='核对原文', content='未提及环境因素', source='隔离测试')).json()
    response = c.get('/api/knowledge/graph', params={'q': source['id'], 'limit': 1}).json()
    assert response['total'] == 1 and len(response['items']) == 1
    assert not any(n['category'] == 1 for n in response['graph']['nodes'])
