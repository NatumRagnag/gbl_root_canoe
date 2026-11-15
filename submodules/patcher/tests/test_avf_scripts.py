#!/usr/bin/env python3
"""Exercise module failure paths with all device writes replaced by shell mocks."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "targets/magisk_module/module/bin/bl_flasher.sh"
FUNCTIONS = SCRIPT.read_text().rsplit('\ncase "$1" in\n', 1)[0]
MOCKS = r'''
write_state() { printf 'state:%s\n' "$1" >> "$TRACE"; }
write_log() { :; }
detect_current_slot() { echo _a; }
persist_mounted() { return 0; }
place_efisp_tree_to() { echo write:tree >> "$TRACE"; }
cp() { echo write:cp >> "$TRACE"; }
mv() { echo write:mv >> "$TRACE"; }
dd() { echo write:dd >> "$TRACE"; }
blockdev() { echo write:blockdev >> "$TRACE"; }
sync() { :; }
ensure_runtime
'''


class FlashScriptTests(unittest.TestCase):
    def run_mock(self, command, extract_exit=0, patch_exit=0):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bins = root / "bin"
            bins.mkdir()
            for name, body in {
                "extractfv": 'echo extract >> "$TRACE"\n'
                             '[ "$EXTRACT_EXIT" -ne 0 ] || : > "$2/LinuxLoader.efi"\n'
                             'exit "$EXTRACT_EXIT"\n',
                "patch_abl": 'echo patch >> "$TRACE"\n'
                             'printf partial > "$2"\n'
                             'exit "$PATCH_EXIT"\n',
            }.items():
                executable = bins / name
                executable.write_text("#!/bin/sh\n" + body)
                executable.chmod(0o755)
            trace = root / "trace"
            env = dict(os.environ, MODDIR=str(root), TRACE=str(trace),
                       EXTRACT_EXIT=str(extract_exit), PATCH_EXIT=str(patch_exit))
            result = subprocess.run(["/bin/sh"], input=FUNCTIONS + MOCKS + command,
                                    text=True, capture_output=True, env=env)
            return result, trace.read_text().splitlines() if trace.exists() else []

    def test_extractor_failure_stops_before_patch_or_writes(self):
        for function in ("update_efisp", "detect_gbl_vulnerability"):
            with self.subTest(function=function):
                result, trace = self.run_mock(f"{function} unused.img no\n", extract_exit=1)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(trace, ["extract"])

    def test_failed_patcher_output_is_never_used(self):
        for function in ("update_efisp", "detect_gbl_vulnerability"):
            with self.subTest(function=function):
                result, trace = self.run_mock(f"{function} unused.img no\n", patch_exit=1)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(trace, ["extract", "patch"])

    def test_update_failure_stops_before_abl_copy(self):
        result, trace = self.run_mock("update_efisp() { return 1; }\nrun_flash update-efisp\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("state:error", trace)
        self.assertFalse(any(line.startswith("write:") for line in trace), trace)

    def test_detection_failure_stops_before_abl_copy(self):
        result, trace = self.run_mock("detect_gbl_vulnerability() { return 1; }\nrun_flash copy-abl\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("state:error", trace)
        self.assertFalse(any(line.startswith("write:") for line in trace), trace)

    def test_successful_detection_keeps_existing_decision(self):
        for detected in (0, 2):
            with self.subTest(detected=detected):
                result, trace = self.run_mock(
                    f"detect_gbl_vulnerability() {{ return {detected}; }}\nrun_flash copy-abl\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("state:success", trace)
                self.assertEqual("write:dd" in trace, detected == 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
