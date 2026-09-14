from fastapi.testclient import TestClient
from backend.main import app
from backend.knowledge_graph import kg, KnowledgeGraph


def test_write_read_and_traverse_real_database(real_graph):
    c=TestClient(app)
    c.post('/api/session',json={'role':'teacher'})
    status=c.get('/api/knowledge/status').json()
    assert status['connected'] and status['backend']=='neo4j'
    item=c.post('/api/knowledge',json={
        'title':'独立图数据库测试知识','crop':'测试生菜','problem':'测试叶缘卷曲',
        'cause':'测试气流不足','measure':'检查测试风机','content':'仅用于集成测试。',
        'tags':['测试叶缘卷曲'],'source':'自动化集成测试','environments':['空气湿度'],
    }).json()
    # A separate Bolt driver verifies actual server persistence, not Python state.
    separate=KnowledgeGraph()
    try:
        found=separate.query('MATCH (k:HydroKnowledge {scope:$scope,id:$id}) RETURN k.doc AS doc',id=item['id'])
        assert len(found)==1 and '独立图数据库测试知识' in found[0]['doc']
    finally:
        separate.driver.close()
    result=c.post('/api/ask',json={'question':'测试叶缘卷曲'}).json()
    assert result['mode']=='neo4j_graph' and result['items'][0]['id']==item['id']
    graph=result['graph']
    assert graph['backend']=='neo4j'
    assert any(n['name']=='测试生菜' for n in graph['nodes'])
    assert {e['type'] for e in graph['edges']}=={'AFFECTS','HAS_PROBLEM','HAS_CAUSE','ADDRESSED_BY','SUPPORTED_BY'}
    # Change a stored relationship directly; the next API graph must reflect it.
    kg.query('MATCH (:Cause)-[r:SUPPORTED_BY]->(k:HydroKnowledge {scope:$scope,id:$id}) SET r.label=$label',id=item['id'],label='数据库直接更新的引用')
    changed=c.post('/api/ask',json={'question':'测试叶缘卷曲'}).json()
    assert any(e['label']=='数据库直接更新的引用' for e in changed['graph']['edges'])
    kg.query('MATCH (c:Cause)-[:SUPPORTED_BY]->(k:HydroKnowledge {scope:$scope,id:$id}) SET c.name=$name',id=item['id'],name='Neo4j 内修改后的原因')
    updated=c.post('/api/ask',json={'question':'测试叶缘卷曲'}).json()
    assert updated['items'][0]['cause']=='Neo4j 内修改后的原因'
    assert any(n['name']=='Neo4j 内修改后的原因' for n in updated['graph']['nodes'])
    fav=c.post('/api/favorites',json={'question':'测试叶缘卷曲'}).json()
    assert fav['graph']['backend']=='neo4j' and fav['sources']==[item['id']]
    assert not c.post('/api/ask',json={'question':'没有资料的独立问题'}).json()['graph']['nodes']
