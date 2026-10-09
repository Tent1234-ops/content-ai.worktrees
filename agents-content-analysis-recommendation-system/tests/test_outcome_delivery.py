import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = ROOT / "scripts/build_outcome_delivery.py"
    spec = importlib.util.spec_from_file_location("build_outcome_delivery", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OutcomeDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_script()

    def test_source_manifest_excludes_secrets_runtime_and_private_data(self):
        records = self.delivery.source_records()
        paths = {item["path"] for item in records}
        self.assertIn(".env.example", paths)
        self.assertNotIn(".env", paths)
        self.assertFalse(any(path.startswith("artifacts/") for path in paths))
        self.assertFalse(any(path.startswith("videos/") for path in paths))
        self.assertFalse(any("models_cache" in path for path in paths))
        self.assertTrue(all("__pycache__" not in path for path in paths))

    def test_schema_contract_is_metadata_only_and_contains_outcome_registry(self):
        result = self.delivery.schema_contract()
        names = {item["name"] for item in result["tables"]}
        self.assertIn("outcome_models", names)
        self.assertIn("outcome_training_runs", names)
        self.assertIn("outcome_model_metrics", names)
        self.assertNotIn("rows", result)
        self.assertEqual(len(result["schema_sha256"]), 64)

    def test_package_allowlist_has_no_private_file_types(self):
        self.assertNotIn(".env", self.delivery.PACKAGE_FILES)
        for name in self.delivery.PACKAGE_FILES:
            self.assertNotIn(Path(name).suffix.lower(), self.delivery.FORBIDDEN_PACKAGE_SUFFIXES)

    def test_json_loader_accepts_windows_utf8_bom(self):
        with TemporaryDirectory() as raw:
            path = Path(raw) / "version.json"
            path.write_text('{"version":"3.41.9"}', encoding="utf-8-sig")
            self.assertEqual(self.delivery.load_json(path), {"version": "3.41.9"})

    def test_private_backup_checksum_and_restore_identity_are_verified(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            backup = root / "backup"
            backup.mkdir()
            manifest = {
                "schema_version": "content-ai-private-delivery-backup-v1",
                "privacy": "private",
                "database_tables": [],
                "database_row_total": 0,
                "environment": {"private_env_included": False},
            }
            manifest_path = backup / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            (backup / "manifest.sha256").write_text(
                f"{digest}  manifest.json\n", encoding="ascii"
            )
            checked = self.delivery.verify_private_backup(backup)
            report_path = root / "restore.json"
            report_path.write_text(json.dumps({
                "passed": True,
                "backup_manifest_sha256": digest,
                "source_database_was_not_modified": True,
                "tables": [],
                "row_total": 0,
            }), encoding="utf-8")
            restored = self.delivery.verify_restore_report(report_path, checked)
            self.assertFalse(checked["shareable"])
            self.assertTrue(restored["passed"])
            self.assertTrue(restored["source_database_was_not_modified"])

    def test_phase6_integrity_rejects_modified_file(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            payload = root / "release-decision.json"
            payload.write_text(json.dumps({"decision": "NO_GO"}), encoding="utf-8")
            integrity = {
                "files": {"release-decision.json": hashlib.sha256(payload.read_bytes()).hexdigest()},
                "bundle_sha256": "fixture",
            }
            (root / "integrity.json").write_text(json.dumps(integrity), encoding="utf-8")
            self.delivery.verify_phase6_bundle(root)
            payload.write_text(json.dumps({"decision": "PASS"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "integrity mismatch"):
                self.delivery.verify_phase6_bundle(root)


if __name__ == "__main__":
    unittest.main()
