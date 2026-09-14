from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Literal
import math
class TelemetryValues(BaseModel):
 model_config=ConfigDict(extra='forbid')
 air_temp:float=Field(ge=-50,le=100);humidity:float=Field(ge=0,le=100);light:float=Field(ge=0,le=300000);ec:float=Field(ge=0,le=100);ph:float=Field(ge=0,le=14);level:float=Field(ge=0,le=100);water_temp:float=Field(ge=-10,le=100)
 @field_validator('*')
 @classmethod
 def finite(cls,v):
  if not math.isfinite(v):raise ValueError('参数必须是有限数值')
  return v
class MQTTConfig(BaseModel):
 protocol:Literal['legacy','tomato_v1_1']='legacy'
 host:str=Field(max_length=253);port:int=Field(ge=1,le=65535);client_id:str=Field(min_length=1,max_length=100);username:str='';password:str='';tls:bool=True;qos:Literal[0,1,2]=1;keepalive:int=Field(default=120,ge=10,le=3600)
 device_id:str='HY-001'
 autoconnect:bool=False
 telemetry_topic:str;command_topic:str;ack_topic:str
 state_topic:str='tomato_hnsw0001/state';availability_topic:str='tomato_hnsw0001/availability'
 @field_validator('host')
 @classmethod
 def hostonly(cls,v):
  if '://' in v or '/' in v or ' ' in v:raise ValueError('填写主机名或 IP，不包含协议和路径')
  return v
 @model_validator(mode='after')
 def topics(self):
  topics=[self.telemetry_topic,self.command_topic,self.ack_topic]
  if self.protocol=='tomato_v1_1':topics += [self.state_topic,self.availability_topic]
  for topic in topics:
   if not topic or len(topic)>240 or '\x00' in topic:raise ValueError('主题为空或长度无效')
   if self.protocol=='tomato_v1_1' and any(x in topic for x in ['+','#','{','}']):raise ValueError('番茄架协议使用固定主题，不使用通配符')
  if len(set(topics))!=len(topics):raise ValueError('各消息主题不能相同')
  if self.protocol=='legacy':
   for topic in [self.telemetry_topic,self.ack_topic]:
    if topic.split('/').count('+')!=1 or '#' in topic:raise ValueError('旧协议订阅主题必须含一个独立 +')
   if self.command_topic.split('/').count('{device_id}')!=1 or '+' in self.command_topic or '#' in self.command_topic:raise ValueError('旧协议控制主题必须含独立的 {device_id}')
  return self
class Command(BaseModel):
 actuator:Literal['pump','light','fan','mist'];state:bool;confirmed:bool=False
class Question(BaseModel):
 device:str='HY-001'
 question:str=Field(min_length=1,max_length=1000)
class Record(BaseModel):
 units:dict={}
 title:str=Field(min_length=1,max_length=200);content:str=Field(default='',max_length=20000);type:str='观察';device:str='HY-001';batch:str='2026-A';photos:list[str]=[];values:dict={};sources:list[str]=[];task_id:str|None=None
class Device(BaseModel):
 id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,40}$');name:str=Field(min_length=1,max_length=100);group:str='未分组';batch:str='2026-A';planted:str='2026-09-13';source:Literal['demo','mqtt']='mqtt'
