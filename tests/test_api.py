import os, tempfile, io, shutil
from pathlib import Path
TEST_ROOT=Path(tempfile.mkdtemp(prefix='hydro-tests-'))
os.environ['HYDRO_DATA_DIR']=str(TEST_ROOT/'data')
os.environ['HYDRO_ENV_FILE']=str(TEST_ROOT/'.env')
os.environ['HYDRO_MQTT_CONFIG']=str(TEST_ROOT/'mqtt.yaml')
shutil.copy2(Path(__file__).parents[1]/'backend/config/mqtt.yaml',os.environ['HYDRO_MQTT_CONFIG'])
os.environ['HYDRO_DEMO']='1'
from fastapi.testclient import TestClient
from PIL import Image
from backend.main import app
from backend import store as s
from backend.mqtt_service import service

def client(role='teacher'):
 c=TestClient(app);assert c.post('/api/session',json={'role':role}).status_code==200;return c

def test_auth_and_role_boundaries():
 c=TestClient(app);assert c.get('/api/devices').status_code==401
 student=client('student');assert student.post('/api/devices',json={'id':'DENIED','name':'no'}).status_code==403
 assert student.post('/api/mqtt/disconnect',json={}).status_code==200
 parent=client('parent');assert parent.post('/api/devices/HY-001/snapshot',json={}).status_code==403

def test_knowledge_changes_with_question_and_no_fake_answer():
 c=client();a=c.post('/api/ask',json={'question':'番茄叶片发黄怎么办？'}).json()
 assert [x['id'] for x in a['items']]==['KB-001','KB-002'];assert len(a['graph']['nodes'])==8  # No inferred environment nodes.
 b=c.post('/api/ask',json={'question':'液位不足怎么办'}).json();assert b['items'][0]['id']=='KB-003'
 assert not c.post('/api/ask',json={'question':'火星宇航服'}).json()['items']
 assert c.post('/api/ask',json={'question':''}).status_code==422
 assert c.post('/api/favorites',json={'question':'叶片发黄'}).status_code==200
 assert c.get('/api/favorites').json()[0]['graph']['edges']

def test_persistence_snapshot_and_device_isolation():
 c=client();r=c.post('/api/devices/HY-001/snapshot',json={}).json();assert len(r['values'])==7
 fresh=client();assert any(x['id']==r['id'] for x in fresh.get('/api/records?device=HY-001').json())
 assert not any(x['id']==r['id'] for x in fresh.get('/api/records?device=HY-002').json())
 student=client('student');assert not any(x['id']==r['id'] for x in student.get('/api/records').json())
 assert c.post('/api/records',json={'title':'','content':'x'}).status_code==422

def test_courses_submission_review_and_photos():
 student=client('student');teacher=client();task='TASK-01'
 a=student.post(f'/api/tasks/{task}/claim',json={}).json();b=student.post(f'/api/tasks/{task}/claim',json={}).json();assert a['id']==b['id']
 assert teacher.post(f'/api/submissions/{a["id"]}/evaluate',json={'evaluation':'good','score':90}).status_code==409
 sub=student.post(f'/api/tasks/{task}/submit',json={'content':'比较校准前后读数，记录误差与操作过程。','photos':[],'records':[]}).json();assert sub['status']=='submitted'
 assert student.post(f'/api/submissions/{a["id"]}/evaluate',json={'evaluation':'x','score':90}).status_code==403
 result=teacher.post(f'/api/submissions/{a["id"]}/evaluate',json={'evaluation':'数据记录完整，请补充误差分析。','score':92});assert result.json()['status']=='evaluated'
 assert client('parent').get('/api/submissions').json()[0]['evaluation']

def test_mqtt_config_validation_secret_redaction_and_disconnect():
 c=client('teacher');config=service.config(True);config.update(host='127.0.0.1',port=18884,client_id='test-platform-client',username='test-platform-user',tls=False,qos=0,keepalive=90,password='test-only-secret')
 saved=c.put('/api/mqtt',json=config);assert saved.status_code==200
 for role in ['student','admin','parent']:
  same={**config,'password':''};assert client(role).put('/api/mqtt',json=same).status_code==200
 assert saved.json()['username']=='test-platform-user' and saved.json()['client_id']=='test-platform-client' and saved.json()['keepalive']==90
 returned=c.get('/api/mqtt').json()['config'];assert returned['password']=='' and returned['password_set']
 assert 'test-only-secret' not in c.get('/api/mqtt').text
 assert 'test-only-secret' not in Path(os.environ['HYDRO_MQTT_CONFIG']).read_text(encoding='utf-8')
 assert 'TOMATO_MQTT_PASSWORD=test-only-secret' in Path(os.environ['HYDRO_ENV_FILE']).read_text(encoding='utf-8')
 config['password']='';c.put('/api/mqtt',json=config);assert service.config()['password']=='test-only-secret'
 config['command_topic']='hydroponics/+/command';assert c.put('/api/mqtt',json=config).status_code==422
 config['command_topic']='hydroponics/{device_id}/command';config['host']='mqtt://bad';assert c.put('/api/mqtt',json=config).status_code==422

def test_control_never_claims_physical_execution_without_ack():
 c=client();assert c.post('/api/devices/HY-001/commands',json={'actuator':'pump','state':True}).status_code==422
 r=c.post('/api/devices/HY-001/commands',json={'actuator':'pump','state':True,'confirmed':True}).json();assert r['status']=='simulated'
 d=s.get('devices','HY-002');s.patch('devices','HY-002',{'source':'mqtt'})
 r=c.post('/api/devices/HY-002/commands',json={'actuator':'pump','state':True,'confirmed':True});assert r.status_code==409
 s.patch('devices','HY-002',{'source':d['source']})

def test_telemetry_and_ack_reject_wrong_identity_and_invalid_numbers(monkeypatch):
 import pytest
 config={**service.config(),'protocol':'legacy','telemetry_topic':'hydroponics/+/telemetry','ack_topic':'hydroponics/+/ack'}
 monkeypatch.setattr(service,'config',lambda:config)
 good={k:v for k,_,_,v in s.METRICS}
 service.ingest('hydroponics/HY-001/telemetry',{'device_id':'HY-001','values':good})
 with pytest.raises(ValueError):service.ingest('hydroponics/HY-002/telemetry',{'device_id':'HY-001','values':good})
 with pytest.raises(ValueError):service.ingest('hydroponics/HY-001/telemetry',{'device_id':'HY-001','values':{**good,'ph':99}})
 cmd=s.put('commands',{'device':'HY-001','actuator':'pump','state':True,'status':'sent_unconfirmed'})
 with pytest.raises(ValueError):service.ingest('hydroponics/HY-002/ack',{'command_id':cmd['id'],'device_id':'HY-002','status':'executed','state':True})
 assert s.get('commands',cmd['id'])['status']=='sent_unconfirmed'
 service.ingest('hydroponics/HY-001/ack',{'command_id':cmd['id'],'device_id':'HY-001','status':'executed','state':True})
 assert s.get('commands',cmd['id'])['status']=='acknowledged'

def test_photo_recognition_exports_and_no_fake_model():
 c=client();buf=io.BytesIO();Image.new('RGB',(200,180),'green').save(buf,format='JPEG');data=buf.getvalue()
 r=c.post('/api/photos',data={'device':'HY-001','batch':'2026-A'},files={'file':('test.jpg',data,'image/jpeg')});assert r.status_code==200;p=r.json()
 assert c.get(p['url']).headers['content-type']=='image/jpeg'
 assert c.post('/api/recognitions',json={'photo_id':p['id'],'demo':False}).status_code==409
 r=c.post('/api/recognitions',json={'photo_id':p['id'],'demo':True}).json();assert r['mode']=='demo';assert len(r['detections'])==2
 assert c.get(r['annotated']).status_code==200
 assert r['summary']=={'fruit_count':2,'maturity_distribution':{'未成熟':0,'半成熟':1,'成熟':1},'average_confidence':.9}
 saved=next(x for x in c.get('/api/recognitions').json() if x['id']==r['id'])
 exported=next(x for x in c.get('/api/export/recognitions?format=json').json() if x['id']==r['id'])
 archived=next(x for x in c.get('/api/records').json() if x.get('recognition')==r['id'])
 assert saved['summary']==exported['summary']==archived['summary']==r['summary']
 from backend.main import recognition_summary
 assert recognition_summary([])['average_confidence'] is None
 assert recognition_summary([{'label':'未知类别','confidence':.3}])['maturity_distribution']['未知类别']==1

 for fmt,magic in [('csv',b'\xef\xbb\xbf'),('pdf',b'%PDF'),('xlsx',b'PK'),('zip',b'PK')]:
  r=c.get('/api/export/records?format='+fmt);assert r.status_code==200;assert r.content.startswith(magic)
 assert c.post('/api/photos',files={'file':('bad.jpg',b'garbage','image/jpeg')}).status_code==422

def test_aggregation_and_device_crud():
 c=client();r=c.get('/api/telemetry/HY-001?period=day').json();assert r['aggregation']=='hour';assert r['points']
 d={'id':'TEST-DEVICE','name':'测试水培设备','group':'测试班级','batch':'B','source':'mqtt','planted':'2026-09-01'}
 assert c.post('/api/devices',json=d).status_code==200;assert c.post('/api/devices',json=d).status_code==409
 assert c.put('/api/devices/TEST-DEVICE',json={**d,'name':'改名设备'}).json()['name']=='改名设备'
 assert c.post('/api/devices/TEST-DEVICE/snapshot',json={}).status_code==409

def test_automatic_policy_has_interlock_hysteresis_and_confirmation():
 from backend.control import desired_states
 values={k:v for k,_,_,v in s.METRICS};current=dict(pump=True,light=False,fan=False,mist=False)
 assert desired_states({**values,'level':5,'light':8000,'air_temp':31,'humidity':45},current)==dict(pump=False,light=True,fan=True,mist=True)
 mid={**values,'level':50,'light':9000,'air_temp':28,'humidity':55}
 assert desired_states(mid,dict(pump=False,light=True,fan=True,mist=True))==dict(pump=True,light=True,fan=True,mist=True)
 c=client();assert c.post('/api/devices/HY-001/mode',json={'mode':'auto'}).status_code==422

def test_switch_to_mqtt_does_not_relabel_demo_readings_as_real():
 c=client();d=s.get('devices','HY-002');s.patch('devices','HY-002',{'source':'mqtt'})
 result=next(x for x in c.get('/api/devices').json() if x['id']=='HY-002');assert result['latest'] is None and not result['online']
 assert c.post('/api/devices/HY-002/snapshot',json={}).status_code==409
 s.put('devices',d)


def test_log_evidence_uses_selected_device_and_retains_snapshot():
 c=client();sample=s.add_telemetry('HY-002','2026-A',{'ph':6.2},'demo')
 assert c.post('/api/ask',json={'question':'叶片发黄','device':'HY-002'}).status_code==200
 log=next(x for x in c.get('/api/logs').json() if x['title']=='知识检索与图谱关联' and x['device']=='HY-002')
 assert log['evidence']['environment']['ts']==sample['ts']
 assert log['evidence']['environment']['values']['ph']==6.2
 assert log['evidence']['knowledge'][0]['id']=='KB-001'
 s.add_telemetry('HY-002','2026-A',{'ph':7.1},'demo')
 assert s.get('logs',log['id'])['evidence']['environment']['values']['ph']==6.2
 assert c.post('/api/ask',json={'question':'叶片发黄','device':'DOES-NOT-EXIST'}).status_code==404
 global_log=s.log('测试系统事件','无设备关联')
 assert global_log['device'] is None and 'environment' not in global_log['evidence']
 s.patch('devices','HY-002',{'source':'mqtt'})
 assert 'environment' not in s.log('来源切换测试','旧演示采样不可冒充实机',device='HY-002')['evidence']
 s.patch('devices','HY-002',{'source':'demo'})
