"""Isolated regression coverage for the r19 sensor-unavailable wire format."""
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend import mqtt_config, store as s
from backend.main import app
from backend.mqtt_service import MQTTService


@pytest.fixture
def controller(monkeypatch):
    from backend import main
    original = mqtt_config.path().read_text()
    device_id = 'TEST-NULL-R19'
    service = MQTTService()
    service.save_config({**service.config(), 'protocol': 'tomato_v1_1', 'device_id': device_id,
                         'qos': 0, 'telemetry_topic': 'tomato_hnsw0001/telemetry',
                         'command_topic': 'tomato_hnsw0001/set', 'ack_topic': 'tomato_hnsw0001/result'})
    s.put('devices', {'id': device_id, 'name': 'isolated r19 fixture', 'source': 'mqtt',
                     'batch': 'test', 'mode': 'manual', 'actuators': {'pump': False, 'light': False},
                     'thresholds': {'ph_min': 5.8, 'ph_max': 6.5, 'temp_max': 32, 'level_min_cm': 5}})
    service.connected = service.subscribed = True
    service.client = Mock()
    service.client.publish.return_value = SimpleNamespace(rc=0)
    monkeypatch.setattr(main, 'service', service)
    client = TestClient(app)
    assert client.post('/api/session', json={'role': 'teacher'}).status_code == 200
    payload = {wire: None for wire in mqtt_config.read()['protocol']['telemetry_fields']}
    yield service, client, device_id, payload
    mqtt_config.path().write_text(original)
    with s.db() as connection:
        connection.execute('DELETE FROM telemetry WHERE device=?', (device_id,))
        connection.execute("DELETE FROM objects WHERE id=? OR json_extract(data,'$.device')=?", (device_id, device_id))


def test_null_frame_proves_communication_without_fabricating_readings(controller, monkeypatch):
    service, client, device, payload = controller
    service.on_message(None, None, SimpleNamespace(topic='tomato_hnsw0001/telemetry',
                        payload=json.dumps(payload).encode(), retain=False))
    assert service.received_at
    reported = next(d for d in client.get('/api/devices').json() if d['id'] == device)
    assert reported['online'] and reported['hardware_mode']
    assert len(reported['unavailable_metrics']) == 7
    assert reported['raw_telemetry'] == payload
    assert set(reported['latest']['values'].values()) == {None}
    assert reported['latest']['source'] == 'mqtt'
    trend = client.get(f'/api/telemetry/{device}').json()
    assert set(trend['points'][-1]['values'].values()) == {None}
    assert not any(a['device'] == device for a in client.get('/api/alerts').json())
    snapshot = client.post(f'/api/devices/{device}/snapshot', json={}).json()
    assert snapshot['values'] == reported['latest']['values']
    assert snapshot['source'] == 'mqtt' and '暂无读数' in snapshot['content']
    assert snapshot['telemetry_at'] == reported['latest']['ts']
    for kind in ('telemetry', 'records'):
        response = client.get(f'/api/export/{kind}?format=pdf&device={device}')
        assert response.status_code == 200 and response.content.startswith(b'%PDF')

    # Real commands must still wait for an authoritative manual state.
    with pytest.raises(ValueError, match='手动模式'):
        service.protocol_command(device, '03', {'value': 0})
    s.patch('devices', device, {'device_state': {'control_mode': 0}})
    command = service.protocol_command(device, '03', {'value': 0})
    assert command['status'] == 'sent_unconfirmed'
    assert s.get('devices', device)['actuators']['pump'] is False
    assert service.client.publish.call_args.kwargs == {'qos': 0, 'retain': False}
    service.client.publish.reset_mock()
    for changes in ({'connected': False}, {'subscribed': False}):
        with monkeypatch.context() as patch:
            for key, value in changes.items(): patch.setattr(service, key, value)
            assert not service.device_online(s.get('devices', device))
    service.ingest('tomato_hnsw0001/availability', {'status': 'offline'})
    with pytest.raises(ValueError, match='离线'):
        service.protocol_command(device, '03', {'value': 0})
    service.ingest('tomato_hnsw0001/availability', {'status': 'online'})
    future = time.time() + 46
    monkeypatch.setattr('backend.mqtt_service.time.time', lambda: future)
    with pytest.raises(ValueError, match='离线'):
        service.protocol_command(device, '03', {'value': 0})
    service.client.publish.assert_not_called()


def test_partial_readings_keep_units_and_average_only_available_values(controller, monkeypatch):
    service, client, device, payload = controller
    hour = int(time.time() // 3600) * 3600
    for index, reading in enumerate(({'ec': 1000, 'ph': 4}, {}, {'ec': 2000, 'ph': 6, 'water_tank_level': 125})):
        timestamp = datetime.fromtimestamp(hour - (2 - index) * 3600, timezone.utc).isoformat()
        with monkeypatch.context() as patch:
            patch.setattr(s, 'now', lambda: timestamp)
            service.ingest('tomato_hnsw0001/telemetry', {**payload, **reading})
    latest = s.telemetry(device, 1)[0]
    assert latest['values']['level'] == 125  # cm, not percent.
    assert latest['values']['ec'] == 2
    assert latest['values']['air_temp'] is None
    assert latest['units'] == {'ec': 'mS/cm', 'level': 'cm'}
    daily = s.aggregate(device, 86400, 2**40)[-1]
    assert daily['values']['ec'] == 1.5 and daily['values']['ph'] == 5
    assert daily['values']['air_temp'] is None
    points = client.get(f'/api/telemetry/{device}').json()['points']
    assert [point['values']['ec'] for point in points] == [1, None, 2]
    from reportlab.graphics.charts.lineplots import LinePlot
    original_draw = LinePlot.draw
    plotted = []
    def capture(chart):
        plotted.append(chart.data)
        return original_draw(chart)
    monkeypatch.setattr(LinePlot, 'draw', capture)
    response = client.get(f'/api/export/telemetry?format=pdf&device={device}')
    assert response.status_code == 200 and response.content.startswith(b'%PDF')
    assert [[(0, 1.0)], [(2, 2.0)]] in plotted  # No line across the null interval.
    service.ingest('tomato_hnsw0001/telemetry', {**payload, 'ph': 4})
    assert [a['title'] for a in client.get('/api/alerts').json() if a['device'] == device] == ['pH 偏低']


def test_missing_invalid_or_retained_frames_still_rejected(controller):
    service, client, device, payload = controller
    invalid = [{k: v for k, v in payload.items() if k != 'ph'}]
    invalid += [{**payload, 'ph': value} for value in (True, '6.2', float('nan'), float('inf'), -1, 15)]
    invalid += [{**payload, 'water_tank_level': -1}, {**payload, 'ec': 100001}]
    for frame in invalid:
        with pytest.raises(ValueError): service.ingest('tomato_hnsw0001/telemetry', frame)
    with pytest.raises(ValueError, match='保留'):
        service.ingest('tomato_hnsw0001/telemetry', payload, retained=True)
    assert not s.telemetry(device)
    assert not service.device_online(s.get('devices', device))
    service.client.publish.assert_not_called()
