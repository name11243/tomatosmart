"""Exercise the Windows launcher against temporary configs, never live services."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'change-ip.ps1'
POWERSHELL = shutil.which('powershell.exe')
MQTT = (b'mqtt:\r\n  host: 10.0.0.8 # broker\r\n  port: 1883\r\n'
        b'  password: ${TOMATO_MQTT_PASSWORD}\r\n  qos: 0\r\n'
        b'  telemetry_topic: tomato_hnsw0001/telemetry\r\n'
        b'protocol:\r\n  host: do-not-change\r\n')
CAMERA = (b'camera:\r\n  url: "http://10.0.0.8:8081/photo.jpg?x=1&scale=2" # camera\r\n'
          b'  refresh_seconds: 20\r\n')


@unittest.skipUnless(POWERSHELL, 'Windows PowerShell 5.1 is required')
class ChangeIPChecks(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='tomato-ip-script-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name) / 'project with spaces'
        self.config = self.root / 'backend' / 'config'
        self.config.mkdir(parents=True)
        (self.config / 'mqtt.yaml').write_bytes(MQTT)
        (self.config / 'camera.yaml').write_bytes(CAMERA)
        (self.root / '.env').write_text('TOMATO_MQTT_PASSWORD=local-only-fixture', encoding='utf-8')
        (self.root / 'history.txt').write_text('Original address 10.0.0.8', encoding='utf-8')

    def run_script(self, ip='192.168.31.217', *flags):
        return subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                               '-File', str(SCRIPT), '-ProjectRoot', str(self.root),
                               '-NewIP', ip, '-SkipRestart', *flags],
                              capture_output=True, timeout=15)

    def unchanged(self):
        self.assertEqual((self.config / 'mqtt.yaml').read_bytes(), MQTT)
        self.assertEqual((self.config / 'camera.yaml').read_bytes(), CAMERA)

    def test_updates_only_hosts_and_keeps_original_bytes_in_backup(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mqtt = (self.config / 'mqtt.yaml').read_bytes()
        camera = (self.config / 'camera.yaml').read_bytes()
        self.assertEqual(mqtt, MQTT.replace(b'10.0.0.8', b'192.168.31.217'))
        self.assertIn(b"'http://192.168.31.217:8081/photo.jpg?x=1&scale=2' # camera", camera)
        self.assertIn(b'\r\n  refresh_seconds: 20\r\n', camera)
        backup, = (self.root / 'data' / 'ip-backups').iterdir()
        self.assertEqual((backup / 'mqtt.yaml').read_bytes(), MQTT)
        self.assertEqual((backup / 'camera.yaml').read_bytes(), CAMERA)
        self.assertEqual(json.loads((backup / 'change.json').read_text())['new_ip'], '192.168.31.217')
        self.assertEqual((self.root / 'history.txt').read_text(), 'Original address 10.0.0.8')
        self.assertEqual((self.root / '.env').read_text(), 'TOMATO_MQTT_PASSWORD=local-only-fixture')
        self.assertNotIn(b'local-only-fixture', result.stdout + result.stderr)

    def test_repeated_run_does_not_rewrite_or_create_another_backup(self):
        self.assertEqual(self.run_script().returncode, 0)
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in self.config.iterdir()]
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in self.config.iterdir()])
        self.assertEqual(len(list((self.root / 'data' / 'ip-backups').iterdir())), 1)

    def test_preview_writes_nothing(self):
        result = self.run_script('192.168.31.217', '-Preview')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.unchanged()
        self.assertFalse((self.root / 'data').exists())

    def test_invalid_ips_never_change_either_config(self):
        for ip in ['192.168.31.999', '192.168.31.217:1883', '127.1', '01.2.3.4',
                   '224.0.0.1', '0.0.0.0', '$(whoami)', 'http://192.168.31.217']:
            with self.subTest(ip=ip):
                self.assertEqual(self.run_script(ip).returncode, 1)
                self.unchanged()
                self.assertFalse((self.root / 'data').exists())

    def test_ambiguous_or_malformed_config_stops_before_any_write(self):
        for invalid in [CAMERA + CAMERA, CAMERA + b'  url: http://10.0.0.9/image\n',
                        b'camera: {url: http://10.0.0.8/image}\n',
                        b'camera:\n  url: ftp://10.0.0.8/image\n']:
            with self.subTest(invalid=invalid):
                (self.config / 'camera.yaml').write_bytes(invalid)
                self.assertEqual(self.run_script().returncode, 1)
                self.assertEqual((self.config / 'mqtt.yaml').read_bytes(), MQTT)
                self.assertEqual((self.config / 'camera.yaml').read_bytes(), invalid)
                self.assertFalse((self.root / 'data').exists())

    def test_https_path_query_and_utf8_bom_are_preserved(self):
        original = b'\xef\xbb\xbfcamera:\n  url: https://10.0.0.8:8443/a%20b/image?key=a%23b\n'
        (self.config / 'camera.yaml').write_bytes(original)
        result = self.run_script('10.5.6.7')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.config / 'camera.yaml').read_bytes(),
                         b"\xef\xbb\xbfcamera:\n  url: 'https://10.5.6.7:8443/a%20b/image?key=a%23b'\n")

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing contract')
    def test_second_write_failure_restores_first_config(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                       ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(self.config / 'camera.yaml'), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        mqtt_before_time = (self.config / 'mqtt.yaml').stat().st_mtime_ns
        try:
            result = self.run_script()
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.unchanged()
        self.assertNotEqual((self.config / 'mqtt.yaml').stat().st_mtime_ns, mqtt_before_time)
        self.assertEqual(len(list((self.root / 'data' / 'ip-backups').iterdir())), 1)
        self.assertFalse(list(self.config.glob('.ip-update-*.tmp')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
