"""Integration tests isolate the native Python graph and business data."""
import os
os.environ["HYDRO_REAL_ONLY"]="0"
import pytest
import tempfile
from pathlib import Path
import yaml

_config=yaml.safe_load((Path(__file__).resolve().parents[1]/"backend/config/mqtt.yaml").read_text(encoding="utf-8"))
_config["mqtt"].update(protocol="legacy",username="",password="",autoconnect=False,telemetry_topic="hydroponics/+/telemetry",command_topic="hydroponics/{device_id}/command",ack_topic="hydroponics/+/ack")
_config_path=Path(tempfile.mkdtemp(prefix="hydro-mqtt-yaml-"))/"mqtt.yaml"
_config_path.write_text(yaml.safe_dump(_config,allow_unicode=True))
os.environ["HYDRO_MQTT_CONFIG"]=str(_config_path)
_data_path=Path(tempfile.mkdtemp(prefix="hydro-test-data-"))
os.environ["HYDRO_DATA_DIR"]=str(_data_path)
os.environ["HYDRO_KNOWLEDGE_FILE"]=str(_data_path/"knowledge_graph.json")


@pytest.fixture(scope='session', autouse=True)
def local_graph():
    from backend.knowledge_graph import kg
    from backend import store
    store.init()
    store.seed()
    kg.initialize()
    yield kg
