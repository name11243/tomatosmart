"""ESP32-S3 r19 / protocol 1.1 wire adapter driven by mqtt.yaml."""
import math
from . import store as s
from .mqtt_config import read

def validate_command(cmd,data):
    spec=read()['protocol']['commands'].get(cmd)
    if not spec:raise ValueError('UNKNOWN_COMMAND：协议未定义命令')
    if not isinstance(data,dict):raise ValueError('data 必须为对象')
    bounds=spec.get('fields') or {'value':spec}
    if set(data)!=set(bounds):raise ValueError('MISSING_FIELD：命令参数不匹配')
    for key,rule in bounds.items():
        value=data[key]
        if type(value) is not int or not rule['min']<=value<=rule['max']:
            raise ValueError('VALUE_OUT_OF_RANGE：'+key)
    return spec

def ingest(service,topic,data,retained=False):
    c=service.config();device=c['device_id'];d=s.get('devices',device)
    if not isinstance(data,dict):raise ValueError('INVALID_JSON：消息必须为 JSON 对象')
    if not d:raise ValueError('YAML 绑定的系统设备不存在')
    spec=read()['protocol']
    if topic==c['telemetry_topic']:
        if retained:raise ValueError('拒绝保留的 telemetry 消息，等待设备实时采样')
        values={}
        for wire,field in spec['telemetry_fields'].items():
            if wire not in data:raise ValueError('遥测字段缺失：'+wire)
            value=data[wire]
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
                raise ValueError('遥测字段无效：'+wire)
            values[field['target']]=None if value is None else value*field['scale']
        from .schemas import TomatoTelemetryValues
        values=TomatoTelemetryValues(**values).model_dump()
        sample=s.add_telemetry(device,d['batch'],values,'mqtt',units={'level':'cm','ec':'mS/cm'})
        s.patch('devices',device,{'source':'mqtt','protocol':'tomato_v1_1','last_seen':sample['ts'],
            'metric_units':{'level':'cm','ec':'mS/cm'},'mqtt_available':True,
            'raw_telemetry':data})
    elif topic==c['availability_topic']:
        if data.get('status') not in ('online','offline'):raise ValueError('无效 availability 状态')
        s.patch('devices',device,{'mqtt_available':data['status']=='online','availability_at':s.now()})
    elif topic==c['state_topic']:
        for field,cmd in [('control_mode','08'),('red_brightness','01'),('blue_brightness','02'),('pump_state','03'),('light_master_state','04'),('fill_light_mode','05'),('pump_interval_min','06'),('pump_duration_sec','07')]:
            validate_command(cmd,{'value':data.get(field)})
        rest=data.get('rest_schedule',{})
        validate_command('09',{k:rest.get(k) for k in spec['commands']['09']['fields']})
        s.patch('devices',device,{'protocol':'tomato_v1_1','device_state':data,'state_received_at':s.now(),'state_retained':retained,
            'mode':'auto' if data['control_mode']==1 else 'manual',
            'actuators':{**d['actuators'],'pump':bool(data['pump_state']),'light':bool(data['light_master_state'])}})
    elif topic==c['ack_topic']:
        if retained:raise ValueError('拒绝保留的 result 消息')
        command=s.get('commands',data.get('request_id'))
        if not command or command.get('device')!=device or command.get('cmd')!=data.get('cmd'):
            raise ValueError('result 的 request_id / cmd 与请求不匹配')
        if type(data.get('success')) is not bool or type(data.get('applied')) is not bool:
            raise ValueError('result 缺少 success / applied 布尔值')
        if command['status']!='sent_unconfirmed':return
        status='acknowledged' if data['success'] and data['applied'] else 'failed'
        s.patch('commands',command['id'],{'status':status,'ack_at':s.now(),'result':data})
        # Authoritative actuator state comes from /state, not an assumed local toggle.
        s.log('番茄架控制结果',data.get('message',status),device=device,command=s.get('commands',command['id']))
    else:
        raise ValueError('消息主题不在 YAML 配置中')
