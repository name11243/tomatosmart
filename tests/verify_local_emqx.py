"""Read-only checks against local EMQX: authentication and subscriptions only.

Never publishes control, state, availability, result, or telemetry messages.
The firmware is parsed as data; none of its code is executed.
"""
import argparse
import ast
import json
import os
import threading
import uuid
from pathlib import Path
import paho.mqtt.client as mqtt


def check(username,password,topics=(),rejected=False,expected_qos=None):
    connected=threading.Event();subscribed=threading.Event();result={}
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='tomatosmart-check-'+uuid.uuid4().hex[:12],protocol=mqtt.MQTTv311)
    client.username_pw_set(username,password)
    def on_connect(c,u,f,reason,p):
        result['connected']=not reason.is_failure;connected.set()
        if not reason.is_failure and topics:c.subscribe([(topic,0) for topic in topics])
    def on_subscribe(c,u,mid,reasons,p):
        result['qos']=[reason.value for reason in reasons];subscribed.set()
    client.on_connect=on_connect;client.on_subscribe=on_subscribe
    try:
        client.connect_timeout=4;client.connect('127.0.0.1',1883,30);client.loop_start()
        assert connected.wait(8),'No CONNACK received'
        assert result['connected'] is not rejected,'Unexpected authentication result'
        if topics:
            assert subscribed.wait(8),'No SUBACK received'
            assert result['qos']==(expected_qos if expected_qos is not None else [0]*len(topics)),'Unexpected subscription authorization or QoS'
        return result
    finally:client.disconnect();client.loop_stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('firmware');args=parser.parse_args()
    tree=ast.parse(Path(args.firmware).read_text(encoding='utf-8-sig'))
    credentials={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('mqtt_user','mqtt_password'):
            credentials[node.targets[0].id]=ast.literal_eval(node.value.args[1])
    root='tomato_hnsw0001'
    result={
        'hardware_account':check(credentials['mqtt_user'],credentials['mqtt_password'],[root+'/set']),
        'platform_account':check('tomatosmart-platform',os.environ['TOMATO_MQTT_PASSWORD'],[root+'/'+part for part in ['telemetry','state','availability','result']]),
        'platform_control_subscription_denied':check('tomatosmart-platform',os.environ['TOMATO_MQTT_PASSWORD'],[root+'/set'],expected_qos=[128]),
        'hardware_result_subscription_denied':check(credentials['mqtt_user'],credentials['mqtt_password'],[root+'/result'],expected_qos=[128]),
        'incorrect_password':check('tomatosmart-platform','invalid-'+uuid.uuid4().hex,rejected=True),
        'published_messages':0,
    }
    print(json.dumps(result))
