#!/usr/bin/env python3
"""Host tests. Set AVF_TEST_IMAGE_DIR for private on-device-image regression tests.

Firmware images are intentionally not distributed in this repository.
"""
import ctypes
import hashlib
import importlib.util
import os
import struct
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


def mode_block(u=9, flags=8, tmp=10, one=11, ctx=19, unlock=0xddd, mode=0xa68):
    """Small synthetic ARM64 mode-selection block, never used for booting."""
    mov = lambda reg, value: 0x52800000 | (value << 5) | reg
    words = [
        0xb0000580 | u,
        0x39400000 | (3 << 10) | (ctx << 5) | flags,
        0x39400000 | (2 << 10) | (ctx << 5) | tmp,
        mov(one, 1), 0x2a1f03e1, mov(2, 0x28),
        0x39400000 | (unlock << 10) | (u << 5) | u,
        0x2a000000 | (tmp << 16) | (flags << 5) | flags,
        0x91000000 | (0x1b8 << 10) | (31 << 5) | tmp,
        0x91001000 | (tmp << 5),
        0x7100001f | (u << 5),
        0x1a800400 | (one << 16) | (one << 5) | u,
        0x7100001f | (flags << 5), mov(flags, 3),
        0x1a800000 | (flags << 16) | (u << 5) | flags,
        0xf0000700 | u,
        0xb9000000 | ((mode // 4) << 10) | (u << 5) | flags,
    ]
    return struct.pack('<17I', *words)


def pe_image(block=None, offset=0x440, executable=True):
    data = bytearray(0x1000)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, 0xaa64, 2)
    struct.pack_into('<H', data, 0x94, 0xf0)
    struct.pack_into('<H', data, 0x98, 0x20b)
    for hdr, name, rva, raw, attrs in [
        (0x188, b'.text', 0x5000, 0x400, 0x60000020 if executable else 0x40000040),
        (0x1b0, b'.data', 0x6000, 0x800, 0xc0000040),
    ]:
        data[hdr:hdr + len(name)] = name
        struct.pack_into('<IIII', data, hdr + 8, 0x400, rva, 0x400, raw)
        struct.pack_into('<I', data, hdr + 36, attrs)
    block = mode_block() if block is None else block
    data[offset:offset + len(block)] = block
    return bytes(data)


class AvfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        lib = cls.work / "avf.so"
        subprocess.run([
            os.environ.get("CC", "gcc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-shared", "-fPIC", "-DAVF_TESTING", "-I" + str(ROOT / "include"),
            str(ROOT / "src/patchs/avf.c"),
            str(ROOT / "src/arm64_inst/arm64_inst_decoder.c"), "-o", str(lib),
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

    def test_pattern_tracks_offsets_registers_and_address_fields(self):
        for offset, regs, unlock, mode in [
            (0x440, (9, 8, 10, 11, 19), 0xddd, 0xa68),
            (0x580, (13, 14, 15, 16, 20), 0x2f, 0x7a0),
        ]:
            with self.subTest(offset=offset):
                block = bytearray(mode_block(*regs, unlock=unlock, mode=mode))
                # Independent ADRP relocations and a different stack frame size.
                struct.pack_into('<I', block, 0, 0x90000000 | regs[0])
                struct.pack_into('<I', block, 60, 0xb0001ac0 | regs[0])
                struct.pack_into('<I', block, 32, 0x91000000 | (0x2c0 << 10) | (31 << 5) | regs[2])
                original = pe_image(block, offset)
                buf = ctypes.create_string_buffer(original)
                self.assertTrue(self.lib.PatchAvfBuffer(buf, len(original)))
                expected = bytearray(original)
                struct.pack_into('<I', expected, offset + 24, 0x52800000 | regs[0])
                self.assertEqual(buf.raw[:len(original)], expected)
                self.assertTrue(self.lib.PatchAvfBuffer(buf, len(original)))
                self.assertEqual(buf.raw[:len(original)], expected)

    def test_ambiguous_and_non_executable_patterns_are_rejected(self):
        duplicate = bytearray(pe_image())
        duplicate[0x580:0x580 + 68] = mode_block()
        for original in (bytes(duplicate), pe_image(executable=False), pe_image(offset=0x840)):
            buf = ctypes.create_string_buffer(original)
            self.assertFalse(self.lib.PatchAvfBuffer(buf, len(original)))
            self.assertEqual(buf.raw[:len(original)], original)

    def test_changed_mode_logic_and_broken_register_links_are_rejected(self):
        changes = [(3, 0x60), (6, 0x20), (7, 0x10000), (10, 0x400),
                   (11, 0x1000), (12, 0x20), (13, 0x20), (14, 0x1000), (16, 1)]
        for index, mask in changes:
            with self.subTest(instruction=index):
                block = bytearray(mode_block())
                word = struct.unpack_from('<I', block, index * 4)[0]
                struct.pack_into('<I', block, index * 4, word ^ mask)
                original = pe_image(block)
                buf = ctypes.create_string_buffer(original)
                self.assertFalse(self.lib.PatchAvfBuffer(buf, len(original)))
                self.assertEqual(buf.raw[:len(original)], original)

    def test_bad_pe_headers_and_truncated_sections_are_rejected(self):
        inputs = [pe_image()[:0x500], b'MZ' + bytes(30)]
        for offset, value in [(0x3c, 0xfffffff0), (0x84, 0x00028664),
                              (0x94, 0xffff), (0x98, 0x10b), (0x19c, 0xfffffff0)]:
            data = bytearray(pe_image())
            struct.pack_into('<I', data, offset, value)
            inputs.append(bytes(data))
        for original in inputs:
            buf = ctypes.create_string_buffer(original)
            self.assertFalse(self.lib.PatchAvfBuffer(buf, len(original)))
            self.assertEqual(buf.raw[:len(original)], original)

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
    def test_unrelated_image_changes_do_not_gate_the_avf_match(self):
        data = bytearray((Path(PRIVATE) / "boot_current_original.efi").read_bytes())
        data[0x30000] ^= 1
        buf = ctypes.create_string_buffer(bytes(data))
        self.assertTrue(self.lib.PatchAvfBuffer(buf, len(data)))
        data[helper.OFFSET:helper.OFFSET + 4] = helper.REPLACEMENT
        self.assertEqual(buf.raw[:len(data)], bytes(data))

    @unittest.skipUnless(PRIVATE, "private reviewed firmware fixtures not provided")
    def test_ota_pipeline_accepts_new_hash_size_and_relocated_avf_block(self):
        fixtures = Path(PRIVATE)
        stock = (fixtures / "LinuxLoader_stock.efi").read_bytes()
        current = (fixtures / "boot_current_original.efi").read_bytes()
        old, new = helper.OFFSET - 24, 0x25000
        # These are synthetic offline mutations, not bootable OTA fixtures.
        def mutate(source, relocate):
            data = bytearray(source + bytes(128))
            data[0x30000] ^= 1
            if relocate:
                block = bytearray(data[old:old + 68])
                for i in (0, 15):
                    word = struct.unpack_from('<I', block, i * 4)[0]
                    pages = ((word >> 5) & 0x7ffff) * 4 + ((word >> 29) & 3)
                    if pages & (1 << 20): pages -= 1 << 21
                    target = ((old + i * 4) & ~0xfff) + pages * 4096
                    pages = ((target - ((new + i * 4) & ~0xfff)) // 4096) & 0x1fffff
                    word = (word & 0x9f00001f) | ((pages & 3) << 29) | ((pages >> 2) << 5)
                    struct.pack_into('<I', block, i * 4, word)
                data[old:old + 68] = bytes(68)
                data[new:new + 68] = block
            return data
        for relocate in (False, True):
            with self.subTest(relocate=relocate):
                src, out = self.work / f'ota_{relocate}.efi', self.work / f'ota_{relocate}_out.efi'
                src.write_bytes(mutate(stock, relocate))
                result = subprocess.run([str(self.cli), str(src), str(out)], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))
                expected = mutate(current, relocate)
                off = new + 24 if relocate else helper.OFFSET
                expected[off:off + 4] = helper.REPLACEMENT
                self.assertEqual(out.read_bytes(), expected)

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
