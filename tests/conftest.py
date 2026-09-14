"""Integration tests use a unique namespace in the real Neo4j server."""
import os
os.environ["HYDRO_REAL_ONLY"]="0"
import uuid
import pytest
import tempfile
from pathlib import Path
import yaml

_config=yaml.safe_load((Path(__file__).resolve().parents[1]/"backend/config/mqtt.yaml").read_text())
_config["mqtt"].update(protocol="legacy",telemetry_topic="hydroponics/+/telemetry",command_topic="hydroponics/{device_id}/command",ack_topic="hydroponics/+/ack")
_config_path=Path(tempfile.mkdtemp(prefix="hydro-mqtt-yaml-"))/"mqtt.yaml"
_config_path.write_text(yaml.safe_dump(_config,allow_unicode=True))
os.environ["HYDRO_MQTT_CONFIG"]=str(_config_path)

os.environ['NEO4J_SCOPE'] = 'hydro-test-' + uuid.uuid4().hex


@pytest.fixture(scope='session', autouse=True)
def real_graph():
    from backend.knowledge_graph import kg
    from backend import store
    store.init()
    store.seed()
    kg.initialize()
    for item in store.allof('knowledge'):
        kg.upsert(item)
    yield kg
    kg.query('MATCH (n:HydroNode {scope:$scope}) DETACH DELETE n')
    kg.driver.close()
