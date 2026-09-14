"""Backend YAML owns MQTT settings; secret references resolve only on the server."""
import os
import re
import tempfile
import threading
from pathlib import Path
import yaml

LOCK=threading.RLock()
DEFAULT_PATH=Path(__file__).parent/'config'/'mqtt.yaml'

def path():
    return Path(os.getenv('HYDRO_MQTT_CONFIG',str(DEFAULT_PATH)))

def read():
    with LOCK:
        data=yaml.safe_load(path().read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('mqtt'),dict):
            raise ValueError('MQTT YAML 必须包含 mqtt 配置对象')
        return data

def password(value):
    match=re.fullmatch(r'\$\{([A-Z][A-Z0-9_]*)\}',value)
    return os.environ.get(match[1],'') if match else value

def save(values):
    from .schemas import MQTTConfig
    values=MQTTConfig(**values).model_dump()
    with LOCK:
        data=read()
        previous=data['mqtt'].get('password','')
        if previous.startswith('${') and values['password']==password(previous):
            values['password']=previous
        data['mqtt']=values
        target=path()
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False) as out:
            yaml.safe_dump(data,out,allow_unicode=True,sort_keys=False)
            temp=Path(out.name)
        temp.chmod(0o600)
        os.replace(temp,target)
