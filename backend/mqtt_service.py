import json, time, threading, ssl
import paho.mqtt.client as mqtt
from . import store as s
from . import mqtt_config
DEFAULT={'protocol':'legacy','host':'','port':8883,'client_id':'hydroponic-server','username':'','password':'','tls':True,'qos':1,'keepalive':60,'telemetry_topic':'hydroponics/+/telemetry','command_topic':'hydroponics/{device_id}/command','ack_topic':'hydroponics/+/ack'}
class MQTTService:
 def __init__(self):self.client=None;self.connected=False;self.error='';self.event=threading.Event();self.lock=threading.RLock()
 def config(self,redact=False):
  from .schemas import MQTTConfig
  c=MQTTConfig(**mqtt_config.read()['mqtt']).model_dump()
  if redact:c['password_set']=bool(c['password']);c['password']=''
  return c
 def save_config(self,values):mqtt_config.save(values)
 def disconnect(self):
  if self.client:
   self.client.disconnect();self.client.loop_stop();self.client=None
  self.connected=False
 def start(self):
  self.disconnect();c=self.config()
  if not c['host']:raise ValueError('请填写 Broker 地址')
  self.error='';self.event.clear()
  client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=c['client_id'])
  if c['username']:client.username_pw_set(c['username'],c['password'])
  if c['tls']:client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
  def on_connect(client,userdata,flags,reason,properties):
   self.connected=not reason.is_failure
   if self.connected:
    subscriptions=[(c[x['config_key']],x['qos']) for x in mqtt_config.read()['protocol']['subscriptions'].values()] if c['protocol']=='tomato_v1_1' else [(c['telemetry_topic'],c['qos']),(c['ack_topic'],c['qos'])]
    client.subscribe(subscriptions)
   else:self.error=f'Broker 拒绝连接：{reason}'
   self.event.set()
  def on_disconnect(client,userdata,flags,reason,properties):self.connected=False
  client.on_connect=on_connect;client.on_disconnect=on_disconnect;client.on_message=self.on_message
  self.client=client
  try:
   client.connect_timeout=4;client.connect(c['host'],c['port'],c['keepalive']);client.loop_start()
   if not self.event.wait(5) or not self.connected:raise ValueError(self.error or '连接超时')
   s.log('MQTT 已连接','已建立 Broker 连接并订阅遥测与回执主题。')
  except Exception as e:self.disconnect();self.error=str(e);raise ValueError('连接失败，请检查地址、端口、认证和 TLS 设置')
 def on_message(self,client,userdata,msg):
  try:self.ingest(msg.topic,json.loads(msg.payload.decode('utf8')),retained=msg.retain)
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
