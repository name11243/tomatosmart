"""Real TCP MQTT test with an isolated local AMQTT broker and a simulated device.
No external broker or physical actuator is contacted.
"""
import asyncio, threading, time, socket, json, os, tempfile
import pytest
os.environ.setdefault("HYDRO_DATA_DIR",tempfile.mkdtemp(prefix="hydro-mqtt-test-"))
from amqtt.broker import Broker
import paho.mqtt.client as mqtt
from backend import store as s
s.init();s.seed()
from backend.mqtt_service import service, DEFAULT

@pytest.mark.parametrize('protocol',['legacy','tomato_v1_1'])
def test_real_mqtt_roundtrip(protocol):
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
 loop=asyncio.new_event_loop();ready=threading.Event();holder={}
 async def start():
  broker=Broker({'listeners':{'default':{'type':'tcp','bind':f'127.0.0.1:{port}'}},'sys_interval':0,'auth':{'allow-anonymous':True},'topic-check':{'enabled':False}})
  holder['broker']=broker;await broker.start();ready.set()
 def worker():asyncio.set_event_loop(loop);loop.run_until_complete(start());loop.run_forever()
 th=threading.Thread(target=worker,daemon=True);th.start();assert ready.wait(8)
 old=service.config();device=s.get('devices','HY-003');s.patch('devices','HY-003',{'source':'mqtt'})
 config={**DEFAULT,'host':'127.0.0.1','port':port,'tls':False,'client_id':'test-server'}
 if protocol=='tomato_v1_1':
  config.update(protocol=protocol,device_id='HY-003',telemetry_topic='tomato_hnsw0001/telemetry',command_topic='tomato_hnsw0001/set',ack_topic='tomato_hnsw0001/result')
 service.save_config(config)
 endpoint=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='test-device');received=[];ack_now=threading.Event()
 def on_message(c,u,m):
  payload=json.loads(m.payload);received.append(payload)
 endpoint.on_message=on_message
 try:
  endpoint.connect('127.0.0.1',port);endpoint.subscribe('tomato_hnsw0001/set' if protocol=='tomato_v1_1' else 'hydroponics/HY-003/command',qos=1);endpoint.loop_start()
  service.start();assert service.connected
  previous_ts=s.telemetry('HY-003',1)[-1]['ts']
  vals={k:v for k,_,_,v in s.METRICS};vals['ph']=6.3
  if protocol=='tomato_v1_1':
   state={'control_mode':0,'red_brightness':80,'blue_brightness':60,'pump_state':0,'light_master_state':1,'fill_light_mode':3,'pump_interval_min':30,'pump_duration_sec':20,'rest_schedule':{'start_hour':20,'start_minute':12,'end_hour':7,'end_minute':22,'crosses_midnight':True}}
   endpoint.publish('tomato_hnsw0001/state',json.dumps(state),qos=1,retain=True).wait_for_publish()
   payload={'air_temperature':28.0,'air_humidity':53.6,'light_intensity':238,'hydroponic_temperature':23.7,'water_tank_level':10.4,'ph':6.3,'ec':110.47}
   endpoint.publish('tomato_hnsw0001/telemetry',json.dumps(payload),qos=0).wait_for_publish()
  else:endpoint.publish('hydroponics/HY-003/telemetry',json.dumps({'device_id':'HY-003','values':vals}),qos=1).wait_for_publish()
  for _ in range(50):
   if s.telemetry('HY-003',1)[-1]['ts']!=previous_ts and s.telemetry('HY-003',1)[-1]['values']['ph']==6.3:break
   time.sleep(.05)
  assert s.telemetry('HY-003',1)[-1]['ts']!=previous_ts
  assert s.telemetry('HY-003',1)[-1]['source']=='mqtt';assert s.telemetry('HY-003',1)[-1]['values']['ph']==6.3
  if protocol=='tomato_v1_1':
   assert s.telemetry('HY-003',1)[-1]['values']['ec']==pytest.approx(.11047)
   assert s.telemetry('HY-003',1)[-1]['units']['level']=='cm'
  cmd=service.command('HY-003','pump' if protocol=='tomato_v1_1' else 'fan',True)
  assert s.get('commands',cmd['id'])['status']=='sent_unconfirmed'
  assert not s.get('devices','HY-003')['actuators']['fan']
  for _ in range(50):
   if received:break
   time.sleep(.05)
  assert received and received[0]['request_id' if protocol=='tomato_v1_1' else 'command_id']==cmd['id']
  if protocol=='tomato_v1_1':
   assert received[0]=={'request_id':cmd['id'],'cmd':'03','data':{'value':1}}
   endpoint.publish('tomato_hnsw0001/result',json.dumps({'request_id':cmd['id'],'cmd':'03','success':True,'applied':True,'data':{'value':1},'message':'pump updated'}),qos=1).wait_for_publish()
  else:endpoint.publish('hydroponics/HY-003/ack',json.dumps({'device_id':'HY-003','command_id':cmd['id'],'status':'executed','state':True}),qos=1).wait_for_publish()
  for _ in range(50):
   if s.get('commands',cmd['id'])['status']=='acknowledged':break
   time.sleep(.05)
  assert s.get('commands',cmd['id'])['status']=='acknowledged';assert s.get('devices','HY-003')['actuators']['fan'] if protocol=='legacy' else not s.get('devices','HY-003')['actuators']['pump']
 finally:
  endpoint.disconnect();endpoint.loop_stop();service.disconnect();service.save_config(old);s.put('devices',device)
  asyncio.run_coroutine_threadsafe(holder['broker'].shutdown(),loop).result(5);loop.call_soon_threadsafe(loop.stop);th.join(3)
