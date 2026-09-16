"""Explicit, idempotent import of traceable project documentation, never demo seeds.

Run: python -m backend.import_project_knowledge --root /path/to/project
Existing IDs are preserved, including edits made through the knowledge editor.
"""
import argparse
from hashlib import sha256
from pathlib import Path

from .knowledge_graph import kg
from .store import now


SOURCES = [
    ('MQTT-TOPICS', 'docs/mqtt-protocol.md', '## 主题',
     'MQTT 主题与消息方向', 'MQTT 主题配置', '收发方向或 QoS 与固件要求不一致',
     '按资料核对 set、result、state、telemetry、availability 五个主题与 QoS 0',
     ['MQTT', '主题', 'QoS', '订阅', '发布'], []),
    ('MQTT-PROTOCOL', 'docs/mqtt-protocol.md', '## 消息适配',
     'r19 遥测、控制回执与设备 AI 模式', '遥测与控制协议核对', '协议字段、命令能力与状态确认有不同职责',
     '核对原始遥测、request_id、result 与 state；不把回执当作物理动作的独立确认',
     ['CMD', '命令', '雾化泵', '水位', '液位', 'EC', '遥测', '回执', 'AI模式'], ['EC', '液位']),
    ('MQTT-CONNECTION', 'docs/mqtt-protocol.md', '## 本机连接',
     '本机 Python 后端与 EMQX 连接', 'MQTT 连接配置', 'MQTT 地址、端口与 Client ID 需要符合现场配置',
     '核对后端与硬件是否到达同一本机 Broker，避免 Client ID 冲突',
     ['EMQX', 'Python', '连接', 'Client ID', 'Broker'], []),
    ('MQTT-NETWORK', 'docs/local-emqx.md', '## 验证边界',
     '硬件网络与在线状态核对', '设备没有上报数据', '平台连接成功并不证明硬件已经联网并发送遥测',
     '核对 NANANA 网络、服务器实际地址与真实 telemetry、state',
     ['NANANA', '网络', '离线', '在线', '没有数据', '上报'], []),
]


def import_sources(root):
    kg.initialize()
    existing = {k['id'] for k in kg.all()}
    added = []
    for key, relative, heading, title, problem, cause, measure, tags, environments in SOURCES:
        source_id = 'KB-PROJECT-' + key
        if source_id in existing:
            continue
        raw = (root / relative).read_bytes()
        text = raw.decode('utf-8-sig')
        start = text.index(heading)
        end = text.find('\n## ', start + len(heading))
        excerpt = text[start:end if end >= 0 else len(text)].strip()
        kg.upsert(dict(id=source_id, title=title, crop='番茄', problem=problem,
                       cause=cause, measure=measure, tags=tags, environments=environments,
                       content=excerpt, source=f'项目资料 · {relative} · {heading[3:]}（待核验）',
                       source_path=relative, source_sha256=sha256(raw).hexdigest(),
                       source_kind='project_document', verified=False,
                       created_at=now(), owner='teacher'))
        added.append(source_id)
    return added


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print({'imported': import_sources(args.root), 'status': kg.status()})
