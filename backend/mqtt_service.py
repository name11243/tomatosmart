import asyncio, json, time, threading, ssl
from datetime import datetime
import paho.mqtt.client as mqtt
from . import store as s
from . import mqtt_config
DEFAULT={'protocol':'legacy','host':'','port':8883,'client_id':'hydroponic-server','username':'','password':'','tls':True,'qos':1,'keepalive':60,'telemetry_topic':'hydroponics/+/telemetry','command_topic':'hydroponics/{device_id}/command','ack_topic':'hydroponics/+/ack'}
class MQTTService:
 def __init__(self):
  self.client=None;self.connected=False;self.subscribed=False;self.error=''
  self.event=threading.Event();self.lock=threading.RLock();self.want_connection=False
  self.subscriptions=[];self.received_at=None
 def config(self,redact=False):
  from .schemas import MQTTConfig
  c=MQTTConfig(**mqtt_config.read()['mqtt']).model_dump()
  c['password']=mqtt_config.password(c['password'])
  if redact:c['password_set']=bool(c['password']);c['password']=''
  return c
 def save_config(self,values):mqtt_config.save(values)
 def status(self):
  c=self.config();spec=mqtt_config.read()['protocol']
  return {'connected':self.connected,'subscribed':self.subscribed,'error':self.error,
   'broker':f"{c['host']}:{c['port']}",'device_id':c['device_id'],'protocol':c['protocol'],
   'firmware':spec.get('firmware'),'publish_topic':c['command_topic'],'publish_qos':c['qos'],
   'subscriptions':self.subscriptions,'received_at':self.received_at,
   'telemetry_interval_seconds':spec['telemetry_interval_seconds']}
 def device_online(self,device):
  if not self.connected or not self.subscribed or not device.get('mqtt_available'):return False
  latest=s.telemetry(device['id'],1)
  return bool(latest and latest[-1]['source']=='mqtt' and
   time.time()-datetime.fromisoformat(latest[-1]['ts']).timestamp()<mqtt_config.read()['protocol']['telemetry_stale_seconds'])
 def disconnect(self,stop_retry=True):
  with self.lock:
   if stop_retry:self.want_connection=False
   client=self.client;self.client=None
   if client:client.disconnect();client.loop_stop()
   self.connected=False;self.subscribed=False
 def start(self):
  with self.lock:self._start()
 def _start(self):
  self.disconnect(False);self.want_connection=True;c=self.config()
  if not c['host']:raise ValueError('请填写 Broker 地址')
  if c['username'] and not c['password']:
   self.error='MQTT 账号密码尚未配置，请检查后端 YAML 的密码引用'
   raise ValueError(self.error)
  self.error='';self.event.clear()
  client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=c['client_id'],protocol=mqtt.MQTTv311)
  if c['username']:client.username_pw_set(c['username'],c['password'])
  if c['tls']:client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
  topics=[(c[x['config_key']],x['qos']) for x in mqtt_config.read()['protocol']['subscriptions'].values()] if c['protocol']=='tomato_v1_1' else [(c['telemetry_topic'],c['qos']),(c['ack_topic'],c['qos'])]
  self.subscriptions=[{'topic':topic,'qos':qos} for topic,qos in topics]
  def on_connect(client,userdata,flags,reason,properties):
   if client is not self.client:return
   self.connected=not reason.is_failure
   self.subscribed=False
   if self.connected:
    result,_=client.subscribe(topics)
    if result!=mqtt.MQTT_ERR_SUCCESS:self.error='MQTT 订阅请求发送失败';self.event.set()
   else:self.error=f'Broker 拒绝连接：{reason}';self.event.set()
  def on_subscribe(client,userdata,mid,reasons,properties):
   if client is not self.client:return
   self.subscribed=len(reasons)==len(topics) and not any(reason.is_failure for reason in reasons)
   self.error='' if self.subscribed else 'Broker 拒绝订阅，请检查 EMQX 主题授权'
   self.event.set()
  def on_disconnect(client,userdata,flags,reason,properties):
   if client is self.client:
    self.connected=False;self.subscribed=False
    if reason.is_failure:self.error='MQTT 连接中断，正在自动重连'
  client.on_connect=on_connect;client.on_subscribe=on_subscribe;client.on_disconnect=on_disconnect;client.on_message=self.on_message
  client.reconnect_delay_set(min_delay=2,max_delay=15)
  self.client=client
  try:
   client.connect_timeout=4;client.connect_async(c['host'],c['port'],c['keepalive']);client.loop_start()
   if not self.event.wait(6) or not self.connected or not self.subscribed:raise ValueError(self.error or '连接或订阅确认超时')
   s.log('MQTT 已连接','Broker 已确认遥测、状态、在线状态与结果主题订阅。')
  except Exception as e:self.disconnect(False);self.error=str(e);raise ValueError('连接失败，请检查地址、端口、认证和主题授权') from e
 async def maintain(self):
  self.want_connection=self.config()['autoconnect']
  while True:
   if self.want_connection and self.client is None:
    try:await asyncio.to_thread(self.start)
    except ValueError:pass
   await asyncio.sleep(5)
 def on_message(self,client,userdata,msg):
  try:
   self.ingest(msg.topic,json.loads(msg.payload.decode('utf8')),retained=msg.retain)
   self.received_at=s.now()
  except Exception as e:s.log('MQTT 消息被拒绝',str(e),'error')
 def ingest(self,topic,data,retained=False):
  c=self.config()
  if c['protocol']=='tomato_v1_1':
   from .tomato_protocol import ingest
   return ingest(self,topic,data,retained)
  if mqtt.topic_matches_sub(c['telemetry_topic'],topic):
   device=data.get('device_id');d=s.get('devices',device)
   if not d:raise ValueError('未知设备')
   # Bind payload identity to the configured single device topic wildcard.
   parts=c['telemetry_topic'].split('/');actual=topic.split('/')
   if '+' in parts and actual[parts.index('+')]!=device:raise ValueError('遥测主题与设备编号不匹配')
   values=data.get('values',{})
   from .schemas import TelemetryValues
   values=TelemetryValues(**values).model_dump()
   s.add_telemetry(device,d['batch'],values,'mqtt')
   s.patch('devices',device,{'source':'mqtt','last_seen':s.now()})
  elif mqtt.topic_matches_sub(c['ack_topic'],topic):
   command=s.get('commands',data.get('command_id'))
   if not command:raise ValueError('未知指令回执')
   device=data.get('device_id');parts=c['ack_topic'].split('/');actual=topic.split('/')
   if device!=command['device'] or ('+' in parts and actual[parts.index('+')]!=device):raise ValueError('回执设备与指令不匹配')
   if command['status']!='sent_unconfirmed':return
   if data.get('status') not in ('executed','failed'):raise ValueError('无效回执状态')
   if data['status']=='executed' and data.get('state') is not command['state']:raise ValueError('执行状态与请求不一致')
   status='acknowledged' if data['status']=='executed' else 'failed'
   s.patch('commands',command['id'],{'status':status,'ack_at':s.now()})
   if status=='acknowledged':
    d=s.get('devices',device);a=d['actuators'];a[command['actuator']]=command['state'];s.patch('devices',device,{'actuators':a})
   s.log('设备控制回执',f'{command["actuator"]}：{status}',device=device,command=s.get('commands',command['id']))
 def protocol_command(self,device,cmd,data):
  from .tomato_protocol import validate_command
  c=self.config();spec=validate_command(cmd,data)
  if c['protocol']!='tomato_v1_1' or device!=c['device_id']:raise ValueError('设备未绑定番茄架协议主题')
  if not self.connected or not self.client:raise ValueError('MQTT 未连接')
  d=s.get('devices',device)
  if not d or d.get('source')!='mqtt':raise ValueError('设备不是已登记的真实 MQTT 设备')
  if not self.device_online(d):raise ValueError('设备离线或遥测已过期，等待设备真实数据后再控制')
  if spec.get('manual_only') and (d or {}).get('device_state',{}).get('control_mode')!=0:raise ValueError('需先收到设备手动模式 state，才能发送灯光或水泵命令')
  record=s.put('commands',{'device':device,'cmd':cmd,'data':data,'actuator':next((name for name,code in mqtt_config.read()['protocol']['actuator_commands'].items() if code==cmd),spec['name']),'state':data.get('value'),'status':'sent_unconfirmed','protocol':'tomato_v1_1'})
  payload={'request_id':record['id'],'cmd':cmd,'data':data}
  info=self.client.publish(c['command_topic'],json.dumps(payload),qos=c['qos'],retain=False)
  if info.rc!=mqtt.MQTT_ERR_SUCCESS:s.patch('commands',record['id'],{'status':'failed'});raise ValueError('发送失败')
  s.log('番茄架控制请求已发送',cmd,device=device,command=record)
  return record
 def command(self,device,actuator,state):
  if self.config()['protocol']=='tomato_v1_1':
   cmd=mqtt_config.read()['protocol']['actuator_commands'].get(actuator)
   if not cmd:raise ValueError('番茄架 V1.1 未定义此执行器命令')
   return self.protocol_command(device,cmd,{'value':int(state)})
  if not self.connected or not self.client:raise ValueError('MQTT 未连接，不能下发设备指令')
  c=self.config();cmd=s.put('commands',{'device':device,'actuator':actuator,'state':state,'status':'sent_unconfirmed'})
  payload={'command_id':cmd['id'],'device_id':device,'actuator':actuator,'state':state,'expires_at':time.time()+30}
  info=self.client.publish(c['command_topic'].replace('{device_id}',device),json.dumps(payload),qos=c['qos'],retain=False)
  if info.rc!=mqtt.MQTT_ERR_SUCCESS:s.patch('commands',cmd['id'],{'status':'failed'});raise ValueError('发送失败')
  s.log('控制指令已发送',f'{actuator} → {state}；等待设备回执',device=device,command=cmd)
  return cmd
service=MQTTService()
