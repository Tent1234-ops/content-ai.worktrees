import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DeliveryToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backup = load_script("create_delivery_backup.py")
        cls.restore = load_script("restore_delivery_backup.py")

    def test_backup_values_round_trip_without_string_guessing(self):
        values = [
            None,
            "ข้อความ",
            42,
            3.5,
            True,
            datetime(2026, 10, 2, 18, 0, 1),
            date(2026, 10, 2),
            time(18, 0, 1),
            Decimal("12.340"),
            b"\x00\x01content-ai",
        ]
        for value in values:
            encoded = self.backup.encode_value(value)
            decoded = self.restore.decode_value(encoded)
            self.assertEqual(value, decoded)

    def test_private_env_is_never_a_backup_asset(self):
        self.assertNotIn(".env", self.backup.VERSION_FILES)
        self.assertIn(".env.example", self.backup.VERSION_FILES)

    def test_restore_refuses_source_database_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            manifest = {
                "source_database": {"dialect": "sqlite", "database": "same.sqlite3"},
                "database_tables": [],
            }
            manifest_path = folder / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            (folder / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, "source database"):
                self.restore.restore(folder, "sqlite:///same.sqlite3")

    def test_launcher_is_hidden_and_refuses_occupied_ports(self):
        script = (ROOT / "scripts" / "start_demo.ps1").read_text(encoding="utf-8")
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("Port $port is already in use", script)
        self.assertIn("No process was stopped", script)
        self.assertNotIn("Stop-Process -Name", script)


if __name__ == "__main__":
    unittest.main()
