"""Isolated browser QA server. Never run against the deployed broker or database."""
import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path
import yaml
import paho.mqtt.client as mqtt
from amqtt.broker import Broker

assert os.environ.get('TOMATO_ISOLATED_QA')=='1'
os.environ.update(HYDRO_DATA_DIR='/tmp/tomato-mqtt-preview-'+uuid.uuid4().hex,HYDRO_REAL_ONLY='1',HYDRO_DEMO='1',YOLO_MODEL_PATH='')
config=yaml.safe_load(Path('backend/config/mqtt.yaml').read_text())
config['mqtt'].update(host='127.0.0.1',port=18889,username='',password='',device_id='MQTT-QA',autoconnect=True)
Path('/tmp/mqtt-preview.yaml').write_text(yaml.safe_dump(config,allow_unicode=True))
os.environ['HYDRO_MQTT_CONFIG']='/tmp/mqtt-preview.yaml'
from backend.main import app
from backend import store as s
from backend.tomato_protocol import validate_command
s.put('devices',{'id':'MQTT-QA','name':'协议联调（隔离测试）','group':'QA','batch':'QA','source':'mqtt','planted':'2026-09-14','mode':'manual','actuators':dict(pump=False,light=False,fan=False,mist=False),'thresholds':{'ph_min':5.8,'ph_max':6.5,'temp_max':32,'level_min':20}})
loop=asyncio.new_event_loop();broker_ready=threading.Event()
async def start_broker():
    broker=Broker({'listeners':{'default':{'type':'tcp','bind':'127.0.0.1:18889'}},'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
    await broker.start();broker_ready.set()
def broker_worker():
    asyncio.set_event_loop(loop);loop.run_until_complete(start_broker());loop.run_forever()
threading.Thread(target=broker_worker,daemon=True).start();assert broker_ready.wait(8)
root='tomato_hnsw0001';received=[];online=True
state={'control_mode':0,'red_brightness':0,'blue_brightness':0,'pump_state':0,'light_master_state':0,'fill_light_mode':1,'pump_interval_min':0,'pump_duration_sec':0,'rest_schedule':{'start_hour':0,'start_minute':0,'end_hour':0,'end_minute':0,'crosses_midnight':False}}
wire={'air_temperature':28,'air_humidity':54,'light_intensity':238,'hydroponic_temperature':23.7,'water_tank_level':10.4,'ph':6.3,'ec':110.47}
endpoint=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='isolated-r19-fixture')
def publish(part,data,retain=False):endpoint.publish(root+'/'+part,json.dumps(data),qos=0,retain=retain)
def on_message(client,userdata,message):
    payload=json.loads(message.payload);cmd=payload['cmd'];data=payload['data'];spec=validate_command(cmd,data)
    received.append({'payload':payload,'topic':message.topic,'qos':message.qos,'retain':message.retain})
    if cmd=='09':state['rest_schedule']={**data,'crosses_midnight':(data['end_hour'],data['end_minute'])<(data['start_hour'],data['start_minute'])}
    else:
        state[spec['name']]=data['value']
        if cmd=='04':state.update(red_brightness=100*data['value'],blue_brightness=100*data['value'])
        if cmd in ('01','02'):state['light_master_state']=int(bool(state['red_brightness'] or state['blue_brightness']))
        if cmd=='05':
            profile=config['protocol']['fill_light_modes'][data['value']]
            state.update(red_brightness=profile['red'],blue_brightness=profile['blue'],light_master_state=1)
    publish('result',{'request_id':payload['request_id'],'cmd':cmd,'success':True,'applied':True,'data':data,'message':'Isolated fixture acknowledged'})
    publish('state',state,True)
endpoint.on_message=on_message;endpoint.connect('127.0.0.1',18889);endpoint.subscribe(root+'/set',qos=0);endpoint.loop_start()
publish('availability',{'status':'online'},True);publish('state',state,True)
def telemetry_worker():
    while True:
        if online:publish('telemetry',wire)
        time.sleep(1)
threading.Thread(target=telemetry_worker,daemon=True).start()
@app.get('/__qa/stats')
def stats():return {'received':received,'state':state,'online':online}
@app.post('/__qa/offline')
def offline():
    global online
    online=False;publish('availability',{'status':'offline'},True)
    return {'online':False}
import uvicorn
uvicorn.run(app,host='0.0.0.0',port=8016,access_log=False)
