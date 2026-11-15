#!/usr/bin/env python3
"""Host tests. Set AVF_TEST_IMAGE_DIR for private on-device-image regression tests.

Firmware images are intentionally not distributed in this repository.
"""
import ctypes
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
spec = importlib.util.spec_from_file_location("patch_avf", REPO / "tools/patch_avf_nezha.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
PRIVATE = os.environ.get("AVF_TEST_IMAGE_DIR")


class AvfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        lib = cls.work / "avf.so"
        subprocess.run([
            os.environ.get("CC", "gcc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-shared", "-fPIC", "-DAVF_TESTING", "-I" + str(ROOT / "include"),
            str(ROOT / "src/patchs/avf.c"), "-o", str(lib),
        ], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        cls.lib.AvfTestSha256.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        cls.lib.ClassifyAvfImage.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        cls.lib.ClassifyAvfImage.restype = ctypes.c_int
        cls.lib.PatchAvfBuffer.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        cls.lib.PatchAvfBuffer.restype = ctypes.c_bool
        cls.cli = ROOT / "build/patch_abl"
        if not cls.cli.is_file():
            raise RuntimeError("Run make build before these tests")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_sha256_padding_boundaries_and_long_input(self):
        samples = [b"", b"abc", b"a" * 1000000]
        samples += [bytes(range(n)) for n in (1, 55, 56, 63, 64, 65, 119, 120, 127, 128, 129)]
        for data in samples:
            with self.subTest(size=len(data)):
                result = ctypes.create_string_buffer(65)
                self.lib.AvfTestSha256(data, len(data), result)
                self.assertEqual(result.value.decode(), hashlib.sha256(data).hexdigest())

    def test_invalid_sizes_and_null_do_not_read_memory(self):
        for size in (-2147483648, -1, 0, 1, helper.SIZE - 1, helper.SIZE + 1, 2147483647):
            self.assertEqual(self.lib.ClassifyAvfImage(None, size), 0)
        self.assertEqual(self.lib.ClassifyAvfImage(None, helper.SIZE), 0)

    def test_instruction_match_alone_is_rejected_without_mutation(self):
        data = bytearray(helper.SIZE)
        data[:2] = b"MZ"
        data[helper.OFFSET:helper.OFFSET + 4] = helper.ORIGINAL
        original = bytes(data)
        buf = ctypes.create_string_buffer(original)
        self.assertFalse(self.lib.PatchAvfBuffer(buf, len(original)))
        self.assertEqual(buf.raw[:len(original)], original)
        with self.assertRaises(ValueError):
            helper.patch(original)

    def test_cli_unknown_input_does_not_create_output(self):
        src, dst = self.work / "unknown.efi", self.work / "unknown_output.efi"
        src.write_bytes(b"MZ" + bytes(4094))
        result = subprocess.run([str(self.cli), str(src), str(dst)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(dst.exists())
        self.assertEqual(src.read_bytes(), b"MZ" + bytes(4094))

    @unittest.skipUnless(PRIVATE, "private reviewed firmware fixtures not provided")
    def test_real_images_classify_and_c_matches_python(self):
        current = (Path(PRIVATE) / "boot_current_original.efi").read_bytes()
        stock = (Path(PRIVATE) / "LinuxLoader_stock.efi").read_bytes()
        expected = helper.patch(current)
        self.assertEqual(self.lib.ClassifyAvfImage(stock, len(stock)), 1)
        self.assertEqual(self.lib.ClassifyAvfImage(current, len(current)), 2)
        self.assertEqual(self.lib.ClassifyAvfImage(expected, len(expected)), 3)
        buf = ctypes.create_string_buffer(current)
        self.assertTrue(self.lib.PatchAvfBuffer(buf, len(current)))
        self.assertEqual(buf.raw[:len(current)], expected)
        self.assertTrue(self.lib.PatchAvfBuffer(buf, len(current)))
        self.assertEqual(buf.raw[:len(current)], expected)
        self.assertEqual(helper.patch(expected), expected)
        self.assertEqual([i for i, (a, b) in enumerate(zip(current, expected)) if a != b],
                         list(range(helper.OFFSET, helper.OFFSET + 4)))

    @unittest.skipUnless(PRIVATE, "private reviewed firmware fixtures not provided")
    def test_full_cli_stock_current_and_reapplication_are_identical(self):
        fixtures = Path(PRIVATE)
        current = (fixtures / "boot_current_original.efi").read_bytes()
        expected = helper.patch(current)
        for name in ("LinuxLoader_stock.efi", "boot_current_original.efi"):
            out = self.work / (name + ".patched")
            result = subprocess.run([str(self.cli), str(fixtures / name), str(out)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))
            self.assertEqual(out.read_bytes(), expected)
        out2 = self.work / "reapplied.efi"
        subprocess.run([str(self.cli), str(out), str(out2)], check=True, capture_output=True)
        self.assertEqual(out2.read_bytes(), expected)

    @unittest.skipUnless(PRIVATE, "private reviewed firmware fixtures not provided")
    def test_other_firmware_change_rejected_even_with_same_patch_instruction(self):
        data = bytearray((Path(PRIVATE) / "boot_current_original.efi").read_bytes())
        data[0x30000] ^= 1
        buf = ctypes.create_string_buffer(bytes(data))
        self.assertFalse(self.lib.PatchAvfBuffer(buf, len(data)))
        self.assertEqual(buf.raw[:len(data)], bytes(data))
        src, out = self.work / "changed.efi", self.work / "changed_out.efi"
        src.write_bytes(data)
        result = subprocess.run([str(self.cli), str(src), str(out)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(out.exists())

    @unittest.skipUnless(PRIVATE, "private reviewed firmware fixtures not provided")
    def test_portable_helper_preserves_input_and_existing_output(self):
        data = (Path(PRIVATE) / "boot_current_original.efi").read_bytes()
        src, dst = self.work / "helper_input.efi", self.work / "helper_output.efi"
        src.write_bytes(data)
        command = [os.environ.get("PYTHON", "python3"), str(REPO / "tools/patch_avf_nezha.py")]
        self.assertNotEqual(subprocess.run(command + [str(src), str(src)], capture_output=True).returncode, 0)
        self.assertEqual(src.read_bytes(), data)
        dst.write_bytes(b"existing file")
        self.assertNotEqual(subprocess.run(command + [str(src), str(dst)], capture_output=True).returncode, 0)
        self.assertEqual(dst.read_bytes(), b"existing file")


if __name__ == "__main__":
    unittest.main(verbosity=2)
