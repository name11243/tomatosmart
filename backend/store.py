import os, sqlite3, json, uuid, threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
REAL_ONLY=os.getenv('HYDRO_REAL_ONLY','1')=='1'
ROOT=Path(os.getenv('HYDRO_DATA_DIR',Path(__file__).parent/('real-data' if REAL_ONLY else 'data')))
ROOT.mkdir(parents=True,exist_ok=True)
(ROOT/'photos').mkdir(exist_ok=True)
DB=ROOT/'hydro.db'
LOCK=threading.RLock()
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex[:16]
def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; c.execute('PRAGMA journal_mode=WAL'); return c
def init():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS objects(kind TEXT,id TEXT,data TEXT,created TEXT,PRIMARY KEY(kind,id)); CREATE TABLE IF NOT EXISTS telemetry(id INTEGER PRIMARY KEY,device TEXT,batch TEXT,ts TEXT,source TEXT,data TEXT); CREATE INDEX IF NOT EXISTS idx_telemetry ON telemetry(device,ts);''')
  if 'units' not in [row[1] for row in c.execute('PRAGMA table_info(telemetry)')]:c.execute("ALTER TABLE telemetry ADD COLUMN units TEXT NOT NULL DEFAULT '{}'")
def put(kind,data,id=None):
 id=id or data.get('id') or uid(); data={**data,'id':id}; data.setdefault('created_at',now())
 with db() as c: c.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?,?)',(kind,id,json.dumps(data,ensure_ascii=False),data['created_at']))
 return data
def get(kind,id):
 with db() as c:r=c.execute('SELECT data FROM objects WHERE kind=? AND id=?',(kind,id)).fetchone()
 return json.loads(r['data']) if r else None
def allof(kind):
 with db() as c:r=c.execute('SELECT data FROM objects WHERE kind=? ORDER BY created DESC',(kind,)).fetchall()
 return [json.loads(x['data']) for x in r]
def patch(kind,id,updates):
 with LOCK:
  old=get(kind,id)
  if old is None: return None
  return put(kind,{**old,**updates},id)
def add_telemetry(device,batch,values,source='demo',ts=None,units=None):
 if REAL_ONLY and source!='mqtt':raise ValueError('真实数据模式拒绝模拟遥测')
 t=ts or now()
 with db() as c:c.execute('INSERT INTO telemetry(device,batch,ts,source,data,units) VALUES(?,?,?,?,?,?)',(device,batch,t,source,json.dumps(values),json.dumps(units or {},sort_keys=True)))
 return dict(device=device,batch=batch,ts=t,source=source,values=values,units=units or {})
def telemetry(device,limit=1800):
 with db() as c:r=c.execute('SELECT * FROM telemetry WHERE device=? ORDER BY ts DESC LIMIT ?',(device,limit)).fetchall()
 return [{**dict(x),'values':json.loads(x['data']),'units':json.loads(x['units'])} for x in reversed(r)]
def log(title,detail,level='info',device=None,sources=None,recognition=None,command=None,knowledge_records=None):
 evidence={'knowledge':knowledge_records if knowledge_records is not None else [k for id in (sources or []) if (k:=get('knowledge',id))]}
 d=get('devices',device) if device else None
 if d:
  samples=telemetry(device,1)
  sample=samples[-1] if samples else None
  if sample and sample['source']==d['source'] and sample['batch']==d['batch']:evidence['environment']=sample
  evidence['batch']=d['batch']
 if recognition:evidence['recognition']=recognition
 if command:evidence['command']=command
 return put('logs',dict(title=title,detail=detail,level=level,device=device,sources=sources or [],evidence=evidence,flagged=False))
METRICS=[('air_temp','空气温度','°C',25.6),('humidity','空气湿度','%',68),('light','光照','lx',12500),('ec','EC','mS/cm',1.8),('ph','pH','',5.6),('level','液位','%',72),('water_temp','水温','°C',22.4)]
COURSES=['认识水培与劳动安全','环境传感器校准','营养液 EC 与 pH 测定','水泵与循环系统实训','补光对生长的影响','番茄定植与观察','AI 图像采集与标注','AI 模型训练与评价','成熟度识别与采摘','生长档案数据分析','知识图谱探究','水培成果展示与复盘']
def seed():
 if REAL_ONLY:return
 if get('settings','seed'):return
 for i in range(1,4):
  put('devices',dict(id=f'HY-00{i}',name=f'水培设备 0{i}',group='七年级一班' if i<3 else '研学温室',batch='2026-A',planted='2026-08-12',mode='manual',source='demo',actuators=dict(pump=False,light=False,fan=False,mist=False),thresholds={'ph_min':5.8,'ph_max':6.5,'temp_max':32,'level_min':20}))
 for i,title in enumerate(COURSES):
  put('tasks',dict(id=f'TASK-{i+1:02}',title=title,description='记录实训过程、环境数据与观察结果，形成有依据的探究报告。',hours=2,deadline='2026-10-01',status='published',teacher='王老师'))
 knowledge=[dict(id='KB-001',title='番茄营养失衡与叶片发黄',problem='叶片发黄',cause='营养失衡',measure='检查营养液 EC 与 pH',content='番茄叶片发黄常与营养元素供应不均衡有关。氮、镁、铁等元素不足，或 pH、EC 偏离适宜范围，都可能影响叶绿素合成。请先核对传感器与实际植株情况，再判断是否调整营养液。',source='示例资料 · 营养管理课堂',tags=['番茄','叶片','发黄','营养','EC','pH'],verified=False),dict(id='KB-002',title='根系缺氧与循环系统',problem='叶片发黄',cause='根系缺氧',measure='检查水泵运行',content='在水培系统中，若水泵运行异常、溶氧不足或根系过密，容易导致根系缺氧，影响养分吸收，进而出现叶片发黄。需检查水泵运行状态及根系健康情况。',source='示例资料 · 根系观察实训',tags=['番茄','根系','水泵','叶片','发黄','缺氧'],verified=False),dict(id='KB-003',title='液位不足的排查',problem='液位不足',cause='水分消耗或管路泄漏',measure='核对液位传感器并检查管路',content='先人工核对液位，再检查容器和管路是否漏水。低液位时避免水泵空转，补水后复测 EC 与 pH。',source='示例资料 · 设备维护',tags=['液位','漏水','水泵','补水'],verified=False),dict(id='KB-004',title='高温环境管理',problem='温度过高',cause='通风不足或补光积热',measure='检查通风与补光设置',content='对照实测温度与设备设定阈值，检查通风和补光。调整后持续观察水温、空气温度和植株变化。',source='示例资料 · 环境监测',tags=['温度','高温','通风','水温','补光'],verified=False)]
 for k in knowledge:put('knowledge',k)
 for d in allof('devices'):
  for i in range(145):
   import math
   t=datetime.now(timezone.utc)-timedelta(minutes=(144-i)*10)
   v={k:round(base+math.sin(i/12)*base*.03,2) for k,_,_,base in METRICS}
   add_telemetry(d['id'],d['batch'],v,ts=t.isoformat())
  put('records',dict(title='番茄定植观察',content='记录定植时间，检查根系与循环供水。',type='定植',device=d['id'],batch=d['batch'],photos=[],owner='teacher',values={k:v for k,_,_,v in METRICS}))
 log('知识库初始化','已载入 4 条示例知识，回答保留来源编号。',sources=['KB-001','KB-002'])
 put('settings',{'id':'seed','version':1})

def aggregate(device,seconds,bucket,batch=''):
 cutoff=datetime.now(timezone.utc)-timedelta(seconds=seconds)
 cols=', '.join(f'AVG(json_extract(data,\'$.{k}\')) AS {k}' for k,_,_,_ in METRICS)
 where='device=? AND ts>=?';params=[device,cutoff.isoformat()]
 d=get('devices',device)
 if d:
  where+=' AND source=? AND units=?';params.extend([d['source'],json.dumps(d.get('metric_units',{}) if d['source']=='mqtt' else {},sort_keys=True)])
 if batch:where+=' AND batch=?';params.append(batch)
 with db() as c:
  rows=c.execute(f"SELECT CAST(strftime('%s',ts) AS INTEGER)/{int(bucket)}*{int(bucket)} AS t,COUNT(*) AS samples,{cols} FROM telemetry WHERE {where} GROUP BY t ORDER BY t",params).fetchall()
 return [{'ts':datetime.fromtimestamp(r['t'],timezone.utc).isoformat(),'samples':r['samples'],'values':{k:round(r[k],2) for k,_,_,_ in METRICS}} for r in rows]
