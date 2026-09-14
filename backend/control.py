"""Explainable threshold policy; MQTT ACK remains authoritative for physical state."""
import time
from datetime import datetime
from . import store as s
from .mqtt_service import service

def desired_states(values,current):
 # Hysteresis prevents oscillation near thresholds. Low level interlock wins.
 out=dict(current)
 out['pump']=values['level']>=20
 if values['light']<8500:out['light']=True
 elif values['light']>10000:out['light']=False
 if values['air_temp']>29:out['fan']=True
 elif values['air_temp']<27:out['fan']=False
 if values['humidity']<50:out['mist']=True
 elif values['humidity']>60:out['mist']=False
 return out

def evaluate_device(d):
 if d['source']=='mqtt' and service.config()['protocol']=='tomato_v1_1':return  # AI mode is owned by ESP32
 if d.get('mode')!='auto':return
 readings=s.telemetry(d['id'],1)
 if not readings or readings[-1]['source']!=d['source'] or time.time()-datetime.fromisoformat(readings[-1]['ts']).timestamp()>15:
  s.patch('devices',d['id'],{'mode':'manual'});s.log('自动模式已暂停','遥测缺失或过期，切换手动模式。','warning',device=d['id']);return
 if d['source']=='mqtt' and not service.connected:
  s.patch('devices',d['id'],{'mode':'manual'});s.log('自动模式已暂停','MQTT 未连接，切换手动模式。','warning',device=d['id']);return
 desired=desired_states(readings[-1]['values'],d['actuators'])
 for key,value in desired.items():
  if value==d['actuators'].get(key):continue
  outstanding=[c for c in s.allof('commands') if c['device']==d['id'] and c['actuator']==key and c['status']=='sent_unconfirmed']
  if outstanding:continue
  if d['source']=='demo':
   s.put('commands',{'device':d['id'],'actuator':key,'state':value,'status':'simulated','origin':'threshold_policy'})
   a=s.get('devices',d['id'])['actuators'];a[key]=value;s.patch('devices',d['id'],{'actuators':a})
  else:
   try:service.command(d['id'],key,value)
   except ValueError:s.patch('devices',d['id'],{'mode':'manual'});return
  s.log('阈值自动策略',f'{key} → {value}；依据：'+str(readings[-1]['values']),device=d['id'],sources=['KB-003' if key=='pump' else 'KB-004'])
