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

def env_path():
    return Path(os.getenv('HYDRO_ENV_FILE',str(Path(__file__).parents[1]/'.env')))

def _env_value(name):
    target=env_path()
    if not target.exists():return ''
    for line in target.read_text(encoding='utf-8').splitlines():
        if line.startswith(name+'='):return line.split('=',1)[1]
    return ''

def _save_env_value(name,value):
    target=env_path();target.parent.mkdir(parents=True,exist_ok=True)
    lines=target.read_text(encoding='utf-8').splitlines() if target.exists() else []
    replacement=f'{name}={value}';found=False
    for index,line in enumerate(lines):
        if line.startswith(name+'='):lines[index]=replacement;found=True;break
    if not found:lines.append(replacement)
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    os.environ[name]=value

def read():
    with LOCK:
        data=yaml.safe_load(path().read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('mqtt'),dict):
            raise ValueError('MQTT YAML 必须包含 mqtt 配置对象')
        return data

def password(value):
    match=re.fullmatch(r'\$\{([A-Z][A-Z0-9_]*)\}',value)
    return (os.environ.get(match[1]) or _env_value(match[1])) if match else value

def save(values):
    from .schemas import MQTTConfig
    values=MQTTConfig(**values).model_dump()
    with LOCK:
        data=read()
        previous=data['mqtt'].get('password','')
        reference=re.fullmatch(r'\$\{([A-Z][A-Z0-9_]*)\}',previous)
        if reference:
            if values['password'] and values['password']!=password(previous):_save_env_value(reference[1],values['password'])
            values['password']=previous
        elif not values['password']:
            values['password']=previous
        data['mqtt']=values
        target=path()
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False) as out:
            yaml.safe_dump(data,out,allow_unicode=True,sort_keys=False)
            temp=Path(out.name)
        temp.chmod(0o600)
        os.replace(temp,target)
