"""YAML is the sole source of MQTT configuration; UI writes the same file."""
import os
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

def save(values):
    from .schemas import MQTTConfig
    values=MQTTConfig(**values).model_dump()
    with LOCK:
        data=read();data['mqtt']=values
        target=path()
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False) as out:
            yaml.safe_dump(data,out,allow_unicode=True,sort_keys=False)
            temp=Path(out.name)
        temp.chmod(0o600)
        os.replace(temp,target)
