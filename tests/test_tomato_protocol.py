import pytest
from backend import mqtt_config, store as s
from backend.mqtt_service import service
from backend.tomato_protocol import validate_command


def test_yaml_protocol_definitions_and_validation():
    spec=mqtt_config.read()['protocol']
    assert spec['version']=='1.1' and spec['telemetry_interval_seconds']==15
    assert set(spec['commands'])=={f'{i:02}' for i in range(1,10)}
    assert spec['fill_light_modes'][3]['red']==80
    assert spec['subscriptions']['telemetry']['qos']==0
    assert all(item['qos']==0 for item in spec['subscriptions'].values())
    assert spec['publish']['set']=={'config_key':'command_topic','qos':0,'retain':False}
    validate_command('09',{'start_hour':20,'start_minute':12,'end_hour':7,'end_minute':22})
    for cmd,data in [('01',{'value':101}),('03',{'value':True}),('05',{'value':0}),('10',{'value':1}),('09',{'start_hour':24,'start_minute':0,'end_hour':7,'end_minute':0})]:
        with pytest.raises(ValueError):validate_command(cmd,data)


def test_tomato_result_identity_availability_and_yaml_persistence():
    old=service.config();device=s.get('devices','HY-001')
    try:
        service.save_config({**old,'protocol':'tomato_v1_1','device_id':'HY-001',
            'telemetry_topic':'tomato_hnsw0001/telemetry','command_topic':'tomato_hnsw0001/set','ack_topic':'tomato_hnsw0001/result'})
        assert mqtt_config.read()['mqtt']['command_topic']=='tomato_hnsw0001/set'
        service.ingest('tomato_hnsw0001/availability',{'status':'offline'})
        assert s.get('devices','HY-001')['mqtt_available'] is False
        cmd=s.put('commands',{'device':'HY-001','cmd':'05','status':'sent_unconfirmed'})
        with pytest.raises(ValueError):service.ingest('tomato_hnsw0001/result',{'request_id':cmd['id'],'cmd':'03','success':True,'applied':True})
        assert s.get('commands',cmd['id'])['status']=='sent_unconfirmed'
        service.ingest('tomato_hnsw0001/result',{'request_id':cmd['id'],'cmd':'05','success':False,'applied':False,'message':'error'})
        assert s.get('commands',cmd['id'])['status']=='failed'
        with pytest.raises(ValueError):service.command('HY-001','fan',True)
    finally:
        service.save_config(old);s.put('devices',device)


def test_secret_reference_is_not_replaced_with_a_password(monkeypatch):
    import yaml
    old=mqtt_config.path().read_text()
    try:
        config=yaml.safe_load(old);config['mqtt']['password']='${MQTT_TEST_SECRET}'
        mqtt_config.path().write_text(yaml.safe_dump(config))
        monkeypatch.setenv('MQTT_TEST_SECRET','isolated-secret-value')
        assert service.config()['password']=='isolated-secret-value'
        assert service.config(True)['password']==''
        service.save_config(service.config())
        assert yaml.safe_load(mqtt_config.path().read_text())['mqtt']['password']=='${MQTT_TEST_SECRET}'
    finally:mqtt_config.path().write_text(old)


def test_retained_telemetry_cannot_make_device_appear_live():
    old=service.config();device=s.get('devices','HY-001');before=s.telemetry('HY-001',1)
    try:
        service.save_config({**old,'protocol':'tomato_v1_1','device_id':'HY-001',
            'telemetry_topic':'tomato_hnsw0001/telemetry','command_topic':'tomato_hnsw0001/set','ack_topic':'tomato_hnsw0001/result'})
        payload={'air_temperature':28,'air_humidity':54,'light_intensity':238,'hydroponic_temperature':23.7,'water_tank_level':10.4,'ph':6.3,'ec':110.47}
        with pytest.raises(ValueError,match='保留的 telemetry'):
            service.ingest('tomato_hnsw0001/telemetry',payload,retained=True)
        assert s.telemetry('HY-001',1)==before
        assert not service.device_online(device)
    finally:service.save_config(old);s.put('devices',device)
