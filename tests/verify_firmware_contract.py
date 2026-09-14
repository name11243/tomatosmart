"""Compare the supplied firmware AST with backend YAML without executing it."""
import ast
import hashlib
import json
import sys
from pathlib import Path
import yaml

source=Path(sys.argv[1]).read_bytes()
tree=ast.parse(source.decode('utf-8-sig'))
assignments={node.targets[0].id:node.value for node in tree.body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)}
functions={node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
config=yaml.safe_load(Path('backend/config/mqtt.yaml').read_text())
spec=config['protocol'];connection=config['mqtt']
root=ast.literal_eval(assignments['MQTT_TOPIC_ROOT']).decode()
assert root==spec['root']
for wire,key in [('SET','command_topic'),('RESULT','ack_topic'),('STATE','state_topic'),('TELEMETRY','telemetry_topic'),('AVAILABILITY','availability_topic')]:
    expression=assignments['TOPIC_'+wire]
    assert isinstance(expression,ast.BinOp) and isinstance(expression.op,ast.Add)
    assert connection[key]==root+ast.literal_eval(expression.right).decode()
assert ast.literal_eval(assignments['MQTT_PUBLISH_QOS'])==0
assert ast.literal_eval(assignments['MQTT_COMMAND_SUBSCRIBE_QOS'])==connection['qos']==0
assert all(value['qos']==0 for value in spec['subscriptions'].values())
assert spec['telemetry_interval_seconds']*1000==ast.literal_eval(assignments['MQTT_TELEMETRY_INTERVAL_MS'])
assert spec['firmware']==ast.literal_eval(assignments['APP_BUILD'])
payload=next(node.value for node in functions['_mqtt_telemetry_payload'].body if isinstance(node,ast.Return))
assert {ast.literal_eval(key) for key in payload.keys}==set(spec['telemetry_fields'])
limits=next(ast.literal_eval(node.value) for node in ast.walk(functions['_mqtt_apply_command']) if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='limits')
for cmd,(minimum,maximum) in limits.items():
    assert (spec['commands'][cmd]['min'],spec['commands'][cmd]['max'])==(minimum,maximum)
assert set(spec['commands'])==set(limits)|{'09'}
print(json.dumps({'firmware_sha256':hashlib.sha256(source).hexdigest(),'root':root,'qos':0,'telemetry_fields':len(spec['telemetry_fields']),'commands':len(spec['commands']),'firmware_code_executed':False}))
