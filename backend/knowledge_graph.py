"""Neo4j is the authoritative knowledge and relationship store (no fallback)."""
import json
import os
import re
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)


class KnowledgeGraph:
    def __init__(self):
        self.scope = os.getenv('NEO4J_REAL_SCOPE', 'hydroponic-real') if os.getenv('HYDRO_REAL_ONLY','1')=='1' else os.getenv('NEO4J_SCOPE', 'hydroponic')
        self.database = os.getenv('NEO4J_DATABASE', 'neo4j')
        self.uri = os.getenv('NEO4J_URI', 'bolt://127.0.0.1:7689')
        self.driver = GraphDatabase.driver(
            self.uri, auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', '')),
            connection_timeout=3, connection_acquisition_timeout=5,
            max_transaction_retry_time=3,
        )

    def query(self, cypher, **params):
        with self.driver.session(database=self.database) as session:
            return session.run(cypher, scope=self.scope, **params).data()

    def initialize(self):
        self.driver.verify_connectivity()
        self.query('CREATE CONSTRAINT hydro_node_uid IF NOT EXISTS FOR (n:HydroNode) REQUIRE n.uid IS UNIQUE')

    def key(self, kind, value):
        return self.scope + ':' + kind + ':' + sha256(value.encode()).hexdigest()[:20]

    def all(self, q=''):
        rows = self.query('''MATCH (k:HydroKnowledge {scope:$scope})
            WHERE $q='' OR toLower(k.doc) CONTAINS toLower($q)
            RETURN k.doc AS doc ORDER BY k.id''', q=q)
        return [json.loads(r['doc']) for r in rows]

    def upsert(self, item):
        crop = item.get('crop') or '番茄'
        k = {**item, 'crop':crop}
        envs = k.get('environments') or []
        entities = [dict(uid=self.key('environment', e), name=e) for e in envs]
        self.query('''
            MERGE (k:HydroNode:HydroKnowledge {uid:$source_id})
            SET k.scope=$scope, k.id=$id, k.name=$id, k.category=5,
                k.doc=$doc, k.tags=$tags, k.problem=$problem, k.verified=$verified,
                k.environment_ids=$environment_ids, k.title=$title
            WITH k
            OPTIONAL MATCH (old:Cause)-[:SUPPORTED_BY]->(k)
            OPTIONAL MATCH (:Problem)-[old_link:HAS_CAUSE]->(old)
            DELETE old_link
            WITH DISTINCT k
            MERGE (crop:HydroNode:Crop {uid:$crop_id})
            SET crop.scope=$scope, crop.name=$crop, crop.category=0
            MERGE (p:HydroNode:Problem {uid:$problem_id})
            SET p.scope=$scope, p.name=$problem, p.category=2
            MERGE (c:HydroNode:Cause {uid:$cause_id})
            SET c.scope=$scope, c.name=$cause, c.category=3
            MERGE (m:HydroNode:Measure {uid:$measure_id})
            SET m.scope=$scope, m.name=$measure, m.category=4
            MERGE (crop)-[r1:HAS_PROBLEM]->(p) SET r1.label='出现问题'
            MERGE (p)-[r2:HAS_CAUSE]->(c) SET r2.label='可能原因'
            MERGE (c)-[r3:ADDRESSED_BY]->(m) SET r3.label='建议措施'
            MERGE (c)-[r4:SUPPORTED_BY]->(k) SET r4.label='来源支持'
            WITH crop
            UNWIND $environments AS env
            MERGE (e:HydroNode:Environment {uid:env.uid})
            SET e.scope=$scope, e.name=env.name, e.category=1
            MERGE (e)-[r:AFFECTS]->(crop) SET r.label='影响生长'
            ''', source_id=self.key('source', k['id']), id=k['id'], doc=json.dumps(k, ensure_ascii=False),
            tags=k.get('tags', []), problem=k['problem'], verified=bool(k.get('verified')),
            environment_ids=[e['uid'] for e in entities], title=k['title'],
            crop_id=self.key('crop', crop), crop=crop,
            problem_id=self.key('problem', crop+':'+k['problem']),
            cause_id=self.key('cause', k['id']), cause=k['cause'],
            measure_id=self.key('measure', k['id']), measure=k['measure'], environments=entities)
        return k

    def retrieve(self, question):
        # Parameters only: model/user text never becomes executable Cypher.
        normalized = question.lower()
        for alias, term in {'黄叶':'发黄', '叶子黄':'叶片发黄', '水位':'液位', '酸碱度':'ph',
                            '电导率':'ec', '消息主题':'主题', '拍照':'摄像头'}.items():
            normalized = normalized.replace(alias, term)
        grams = list(dict.fromkeys(re.findall(r'[a-z0-9_]+', normalized) +
                     [part[i:i+2] for part in re.findall(r'[\u4e00-\u9fff]+', normalized)
                      for i in range(len(part)-1)]))[:100]
        rows = self.query('''MATCH (crop:Crop {scope:$scope})-[:HAS_PROBLEM]->(p:Problem)
            -[:HAS_CAUSE]->(c:Cause)-[:SUPPORTED_BY]->(k:HydroKnowledge {scope:$scope})
            MATCH (c)-[:ADDRESSED_BY]->(m:Measure)
            WITH k,crop,p,c,m, reduce(score=0, tag IN k.tags |
                score + CASE WHEN tag<>crop.name AND tag<>'' AND toLower($q) CONTAINS toLower(tag) THEN 4 ELSE 0 END)
                + CASE WHEN $q CONTAINS toLower(p.name) THEN 10 ELSE 0 END
                + CASE WHEN toLower(coalesce(k.title,'')) CONTAINS $q OR toLower(k.id)=$q THEN 10 ELSE 0 END
                AS exact, size([g IN $grams WHERE toLower(p.name+' '+coalesce(k.title,'')+' '+c.name) CONTAINS g]) AS overlap
            WITH k,crop,p,c,m,exact,overlap WHERE exact>0 OR overlap>=2
            RETURN k.doc AS doc, crop.name AS crop, p.name AS problem,
                c.name AS cause, m.name AS measure, exact*10+overlap AS score
            ORDER BY score DESC, k.id LIMIT 6''', q=normalized, grams=grams)
        if not rows:
            return []
        items = [{**json.loads(r['doc']), **{key:r[key] for key in ('crop','problem','cause','measure')}} for r in rows]
        return list({k['id']:k for k in items}.values())

    def graph(self, items):
        if not items:
            return {'nodes':[], 'edges':[], 'backend':'neo4j'}
        rows = self.query('''
            MATCH path=(crop:Crop {scope:$scope})-[:HAS_PROBLEM]->(p:Problem)
                -[:HAS_CAUSE]->(c:Cause)-[:SUPPORTED_BY]->(k:HydroKnowledge)
            WHERE k.id IN $ids AND k.scope=$scope
            MATCH action=(c)-[:ADDRESSED_BY]->(m:Measure)
            OPTIONAL MATCH env=(e:Environment)-[:AFFECTS]->(crop)
            WHERE e.uid IN coalesce(k.environment_ids,[])
            RETURN [n IN nodes(path)+nodes(action)+coalesce(nodes(env),[]) | properties(n)] AS nodes,
                [r IN relationships(path)+relationships(action)+coalesce(relationships(env),[]) |
                {source:startNode(r).uid, target:endNode(r).uid, label:r.label, type:type(r)}] AS edges
            ''', ids=[k['id'] for k in items])
        nodes, edges = {}, {}
        for row in rows:
            for n in row['nodes']:
                nodes[n['uid']] = n
            for e in row['edges']:
                edges[(e['source'], e['target'], e['type'])] = e
        source_keys={e['source']:nodes[e['target']]['id'] for e in edges.values() if e['type']=='SUPPORTED_BY'}
        measure_keys={e['target']:source_keys.get(e['source'],'') for e in edges.values() if e['type']=='ADDRESSED_BY'}
        output=[]
        icons={0:'seedling-fill', 1:'drop-fill', 2:'', 3:'leaf-fill', 4:'settings-3-fill', 5:'file-text-line'}
        xs={0:220,1:70,2:390,3:560,4:735,5:935}
        ids={uid:n.get('id',uid) for uid,n in nodes.items()}
        for category in range(6):
            group=sorted((n for n in nodes.values() if n['category']==category), key=lambda n:source_keys.get(n['uid'],measure_keys.get(n['uid'],n.get('id',n['name']))))
            for i,n in enumerate(group):
                y=230 if len(group)==1 else (40+i*410/(len(group)-1) if category==5 else 100+i*260/(len(group)-1))
                if category in (3,4) and len(group)==2:y=145+i*175
                name=n['name']
                if category==4:name=name.replace('营养液 ','').replace('检查','检查\n')
                if category==5:name+='\n'+('已核验资料' if n.get('verified') else '待核验资料')
                output.append({'id':ids[n['uid']], 'name':name, 'category':category,
                    'x':xs[category], 'y':y, 'full_name':n.get('title') or n['name'], 'icon':({'EC':'pulse-line','水温':'temp-cold-line'}.get(n['name'],icons[category])), 'neo4j_uid':n['uid']})
        return {'nodes':output, 'edges':[{**e,'source':ids[e['source']],'target':ids[e['target']]} for e in edges.values()], 'backend':'neo4j'}

    def status(self):
        counts=self.query('''MATCH (n:HydroNode {scope:$scope})
            OPTIONAL MATCH (n)-[r]->(:HydroNode {scope:$scope})
            RETURN count(DISTINCT n) AS nodes, count(r) AS relationships''')[0]
        sources=self.query('MATCH (k:HydroKnowledge {scope:$scope}) RETURN count(k) AS sources')[0]['sources']
        return {'backend':'neo4j','connected':True,'database':self.database,'sources':sources,**counts}


kg=KnowledgeGraph()
