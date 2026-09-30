import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.run_trend_scheduler import run_collector


class TrendSchedulerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trend launcher ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_windowless_child_has_explicit_streams_and_no_shell(self):
        def launch(command, **options):
            self.assertEqual(command, [str(self.root / "Python install" / "python.exe"),
                                      "-B", "-X", "utf8",
                                      str(self.root / "scripts" / "collect_trend_snapshots.py")])
            self.assertEqual(options["cwd"], self.root)
            self.assertFalse(options["shell"])
            self.assertEqual(options["stdin"], subprocess.DEVNULL)
            self.assertEqual(options["creationflags"], 0x08000000)
            options["stdout"].write("collector output\n")
            options["stderr"].write("collector diagnostic\n")
            return Mock(returncode=0)

        with patch("scripts.run_trend_scheduler.subprocess.CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch("scripts.run_trend_scheduler.subprocess.run", side_effect=launch):
            self.assertEqual(run_collector(root=self.root,
                             executable=str(self.root / "Python install" / "pythonw.exe")), 0)
        self.assertEqual((self.root / "artifacts" / "trend-scheduler.stdout.log").read_text(),
                         "collector output\n")
        self.assertEqual((self.root / "artifacts" / "trend-scheduler.stderr.log").read_text(),
                         "collector diagnostic\n")

    def test_status_mode_is_forwarded_without_configuring_schedule(self):
        with patch("scripts.run_trend_scheduler.subprocess.run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(run_collector(root=self.root, executable=sys.executable, status_only=True), 0)
        self.assertEqual(run.call_args.args[0][-1], "--status")
        self.assertNotIn("--configure-daily", run.call_args.args[0])

    def test_collector_failure_exit_code_is_preserved(self):
        with patch("scripts.run_trend_scheduler.subprocess.run", return_value=Mock(returncode=7)):
            self.assertEqual(run_collector(root=self.root, executable=sys.executable), 7)

    def test_missing_interpreter_reports_failure_without_leaking_exception_detail(self):
        with patch("scripts.run_trend_scheduler.subprocess.run",
                   side_effect=FileNotFoundError("sensitive exception detail")):
            self.assertEqual(run_collector(root=self.root), 1)
        error = (self.root / "artifacts" / "trend-scheduler.stderr.log").read_text()
        self.assertIn("FileNotFoundError", error)
        self.assertNotIn("sensitive", error)

    def test_unwritable_logs_do_not_silently_report_success(self):
        with patch("scripts.run_trend_scheduler.Path.mkdir", side_effect=PermissionError), \
                patch("scripts.run_trend_scheduler.subprocess.run") as run:
            self.assertEqual(run_collector(root=self.root), 1)
        run.assert_not_called()

    def test_each_check_replaces_diagnostic_logs(self):
        logs = self.root / "artifacts"
        logs.mkdir()
        for name in ("stdout", "stderr"):
            (logs / f"trend-scheduler.{name}.log").write_text("previous invocation")
        with patch("scripts.run_trend_scheduler.subprocess.run", return_value=Mock(returncode=0)):
            self.assertEqual(run_collector(root=self.root), 0)
        for name in ("stdout", "stderr"):
            self.assertEqual((logs / f"trend-scheduler.{name}.log").read_text(), "")

    @unittest.skipUnless(sys.platform == "win32", "Requires the Windows GUI Python launcher")
    def test_real_pythonw_launch_creates_no_collector_console_and_returns_failure(self):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.is_file():
            self.skipTest("pythonw.exe is not installed")
        scripts = self.root / "scripts"
        scripts.mkdir()
        launcher = scripts / "run_trend_scheduler.py"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts" / launcher.name, launcher)
        (scripts / "collect_trend_snapshots.py").write_text(
            "import ctypes, json, sys\n"
            "ctypes.windll.kernel32.GetConsoleWindow.restype = ctypes.c_void_p\n"
            "print(json.dumps({'console': ctypes.windll.kernel32.GetConsoleWindow(), "
            "'args': sys.argv[1:], 'stdin': sys.stdin.read()}))\n"
            "print('diagnostic from collector', file=sys.stderr)\n"
            "raise SystemExit(7)\n", encoding="utf-8")
        result = subprocess.run([str(pythonw), "-B", "-X", "utf8", str(launcher), "--status"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 7)
        output = json.loads((self.root / "artifacts" / "trend-scheduler.stdout.log").read_text())
        self.assertIsNone(output["console"])
        self.assertEqual(output["args"], ["--status"])
        self.assertEqual(output["stdin"], "")
        self.assertIn("diagnostic from collector",
                      (self.root / "artifacts" / "trend-scheduler.stderr.log").read_text())


if __name__ == "__main__":
    unittest.main()
