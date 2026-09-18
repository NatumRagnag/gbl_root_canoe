"""Run on Linux: python3 tests/test_arb.py build/arb_inspect.

Exercises the actual CLI and Android shell wrapper without writing a partition.
"""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

BINARY = Path(sys.argv.pop(1)).resolve()
ROOT = Path(__file__).resolve().parents[3]


def fixture(version=7, arb=3, qti=None, elf64=False, metadata_version=3):
    def metadata(value):
        return struct.pack('<4I', metadata_version, 0, value, 0) + bytes(208)
    q = metadata(qti) if qti is not None else b''
    o = metadata(arb) if arb is not None else b''
    segment = (struct.pack('<10I', 0, version, 24, len(q), len(o), 0, 0, 0, 0, 0)
               + struct.pack('<6I', 0, 0, 28, 0, 3, 0) + q + o)
    ident = b'\x7fELF' + bytes([2 if elf64 else 1, 1, 1]) + bytes(9)
    if elf64:
        header = struct.pack('<16sHHIQQQIHHHHHH', ident, 2, 183, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
        ph = struct.pack('<IIQQQQQQ', 1, 0x02000000, 0x1000, 0, 0, len(segment), len(segment), 4096)
    else:
        header = struct.pack('<16sHHIIIIIHHHHHH', ident, 2, 40, 1, 0, 52, 0, 0, 52, 32, 1, 0, 0, 0)
        ph = struct.pack('<8I', 1, 0x1000, 0, 0, len(segment), len(segment), 0x02000000, 4096)
    return (header + ph).ljust(4096, b'\0') + segment


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def run_image(self, data, ok=True):
        image = self.dir / "image with ' quote.img"
        image.write_bytes(data)
        p = subprocess.run([str(BINARY), str(image)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0 if ok else 1, p.stdout + p.stderr)
        fields = dict(line.split('=', 1) for line in p.stdout.splitlines())
        self.assertEqual(fields['STATUS'], 'ok' if ok else 'error')
        if not ok:
            self.assertNotIn('OEM_ARB', fields)
        return fields

    def test_elf32_64_authorities_and_uint32(self):
        for is64 in (False, True):
            for major in (2, 3):
                with self.subTest(elf64=is64, major=major):
                    fields = self.run_image(fixture(arb=0xffffffff, qti=7, elf64=is64, metadata_version=major))
                    self.assertEqual(fields['OEM_ARB'], '4294967295')
                    self.assertEqual(fields['QTI_ARB'], '7')
                    self.assertEqual(fields['SW_ID'], '28')

    def test_absent_is_not_zero(self):
        fields = self.run_image(fixture(arb=0))
        self.assertEqual(fields['OEM_ARB'], '0')
        self.assertEqual(fields['QTI_ARB'], 'absent')
        fields = self.run_image(fixture(arb=None, qti=0))
        self.assertEqual(fields['OEM_ARB'], 'absent')
        self.assertEqual(self.run_image(fixture(arb=None), False)['ERROR'], 'NO_ARB_METADATA')

    def test_unsupported_and_truncated(self):
        for version in (3, 5, 6, 8):
            self.assertEqual(self.run_image(fixture(version=version), False)['ERROR'], 'UNSUPPORTED_MBN_VERSION')
        for length in (0, 15, 32, 70, 4095, 4120, len(fixture()) - 1):
            self.run_image(fixture()[:length], False)
        self.run_image(b'MZ' + bytes(4096), False)
        self.run_image(fixture(metadata_version=99), False)

    def test_bad_offsets_sizes_and_duplicate_segments(self):
        data = bytearray(fixture(elf64=True))
        struct.pack_into('<Q', data, 32, (1 << 64) - 1)
        self.run_image(data, False)
        data = bytearray(fixture(elf64=True))
        struct.pack_into('<Q', data, 64 + 32, (1 << 64) - 1)
        self.run_image(data, False)
        data = bytearray(fixture())
        struct.pack_into('<I', data, 4096 + 12, 0xffffffff)
        self.run_image(data, False)
        data = bytearray(fixture())
        struct.pack_into('<H', data, 44, 2)
        data[84:116] = data[52:84]
        self.assertEqual(self.run_image(data, False)['ERROR'], 'MISSING_OR_AMBIGUOUS_HASH_SEGMENT')

    def test_real_repository_images(self):
        images = list((ROOT / 'ablrepo').glob('*/abl.img'))
        self.assertEqual(len(images), 11)
        for image in images:
            fields = self.run_image(image.read_bytes())
            self.assertEqual(fields['SW_ID'], '28')
            expected = '1' if image.parent.name in ('myron', 'nezha', 'nezha_global', 'pandora', 'popsicle', 'pudding') else '0'
            self.assertEqual(fields['OEM_ARB'], expected, str(image))

    def test_shell_wrapper_paths_slots_and_no_writes(self):
        module = self.dir / "module's files"
        (module / 'bin').mkdir(parents=True)
        shutil.copy2(BINARY, module / 'bin/arb_inspect')
        mock = self.dir / 'mock'
        mock.mkdir()
        getprop = mock / 'getprop'
        getprop.write_text('#!/bin/sh\n[ "$1" = ro.boot.slot_suffix ] && printf "%s" "$TEST_SLOT"\n')
        getprop.chmod(0o755)
        parts = self.dir / 'partitions'
        parts.mkdir()
        (parts / 'abl_a').write_bytes(fixture(arb=0))
        (parts / 'abl_b').write_bytes(fixture(arb=1))
        path = self.dir / "target's $(touch INJECTED).img"
        path.write_bytes(fixture(arb=2))
        before = {p: p.read_bytes() for p in parts.iterdir()}
        env = dict(os.environ, MODDIR=str(module), BY_NAME_DIR=str(parts), TEST_SLOT='_b', PATH=f'{mock}:{os.environ["PATH"]}')
        wrapper = ROOT / 'targets/magisk_module/module/bin/arb_check.sh'
        def run(*args):
            p = subprocess.run(['sh', str(wrapper), *args], env=env, capture_output=True, text=True)
            return p, dict(line.split('=', 1) for line in p.stdout.splitlines())
        p, values = run('slots', 'abl')
        self.assertEqual(p.returncode, 0)
        self.assertEqual(values['CURRENT_SLOT'], '_b')
        self.assertEqual(values['A_OEM_ARB'], '0')
        self.assertEqual(values['B_OEM_ARB'], '1')
        p, values = run('image', 'abl', str(path))
        self.assertEqual(values['CURRENT_OEM_ARB'], '1')
        self.assertEqual(values['FILE_OEM_ARB'], '2')
        env['TEST_SLOT'] = ''
        p, values = run('image', 'abl', str(path))
        self.assertEqual(values['CURRENT_ERROR'], 'UNKNOWN_SLOT')
        self.assertEqual(values['FILE_OEM_ARB'], '2')
        for part in ('../abl', 'abl_a', 'abl; touch INJECTED'):
            p, values = run('slots', part)
            self.assertNotEqual(p.returncode, 0)
        p, values = run('image', 'abl', str(path) + '.missing')
        self.assertEqual(values['FILE_STATUS'], 'error')
        self.assertFalse((self.dir / 'INJECTED').exists())
        self.assertEqual(before, {p: p.read_bytes() for p in parts.iterdir()})


if __name__ == '__main__':
    unittest.main()
