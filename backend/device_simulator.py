"""Opt-in MQTT device protocol simulator. Never drives physical hardware."""
import argparse, json, time, math, ssl, os
import paho.mqtt.client as mqtt
p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=1883);p.add_argument('--device',default='HY-001');p.add_argument('--tls',action='store_true');args=p.parse_args()
c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='simulator-'+args.device)
if os.getenv('MQTT_USERNAME'):c.username_pw_set(os.getenv('MQTT_USERNAME'),os.getenv('MQTT_PASSWORD',''))
if args.tls:c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
seen=set()
def connected(client,*_):client.subscribe(f'hydroponics/{args.device}/command',qos=1)
def received(client,userdata,msg):
 d=json.loads(msg.payload);id=d.get('command_id')
 if d.get('device_id')!=args.device or d.get('expires_at',0)<time.time() or id in seen:return
 if d.get('actuator') not in ['pump','light','fan','mist'] or type(d.get('state')) is not bool:return
 seen.add(id);print('SIMULATED (not physical):',d)
 client.publish(f'hydroponics/{args.device}/ack',json.dumps({'device_id':args.device,'command_id':id,'status':'executed','state':d['state']}),qos=1)
c.on_connect=connected;c.on_message=received;c.connect(args.host,args.port,60);c.loop_start()
try:
 while True:
  c.publish(f'hydroponics/{args.device}/telemetry',json.dumps({'device_id':args.device,'values':{'air_temp':round(25.6+math.sin(time.time()/30),2),'humidity':68,'light':12500,'ec':1.8,'ph':6.1,'level':72,'water_temp':22.4}}),qos=1);time.sleep(2)
except KeyboardInterrupt:pass
finally:c.disconnect();c.loop_stop()
