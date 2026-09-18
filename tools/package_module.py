"""Package the current module source and verified build outputs, no stale tree."""
from pathlib import Path
import hashlib
import struct
import zipfile

root = Path(__file__).resolve().parents[1]
debug = root / 'submodules/uefi/edk2/Build/RELEASE_CLANG35/AARCH64/QcomModulePkg/Application/LinuxLoader/LinuxLoader/DEBUG'
autogen = (debug / 'AutoGen.c').read_text(encoding='utf8')
link_map = (debug / 'LinuxLoader.map').read_text(encoding='utf8')
for forbidden in ('LzmaDecompressLibConstructor', 'GetExtractGuidedSectionHandlerInfo',
                  'PcdGuidedExtractHandlerTableAddress', 'ExtractGuidedSectionRegisterHandlers'):
    assert forbidden not in autogen and forbidden not in link_map, forbidden
for required in ('RawLzmaDecompressLib', 'SfbNativeFastbootPending', 'SfbRequestNativeFastboot', 'CmdRebootBootloader'):
    assert required in link_map, required
module = root / 'targets/magisk_module/module'
files = {p.relative_to(module).as_posix(): p for p in module.rglob('*') if p.is_file()}
for name in ('BDS.efi', 'ArbTools.efi', 'BLTools.efi', 'RebootTools.efi'):
    source = root / 'submodules/uefi/build' / name
    data = source.read_bytes()
    pe = struct.unpack_from('<I', data, 60)[0]
    assert data[:2] == b'MZ' and struct.unpack_from('<H', data, pe + 4)[0] == 0xaa64
    files[name if name == 'BDS.efi' else f'efisp/tools/{name}'] = source
for source, name in (
    ('submodules/patcher/build/patch_abl_android', 'patch_abl'),
    ('submodules/ablfvextractor/build/extractfv_android', 'extractfv'),
    ('tools/arb_inspect/build/arb_inspect_android', 'arb_inspect'),
):
    source = root / source
    data = source.read_bytes()
    assert data[:4] == b'\x7fELF' and struct.unpack_from('<H', data, 18)[0] == 183
    files[f'bin/{name}'] = source
for i in range(1, 8):
    assert files[f'efisp/splash/{i}.sfb'].read_bytes()[:8] == b'SFBSPL03'

output = root / 'targets/magisk_module/build/gbl_uefi.zip'
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, source in sorted(files.items()):
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (0o100755 if name.startswith('bin/') or name.endswith('.sh') else 0o100644) << 16
        archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    bds = archive.read('BDS.efi')
    assert bds == (root / 'submodules/uefi/build/BDS.efi').read_bytes()
    assert len(bds) <= 3 * 1024 * 1024
    for name, source in files.items():
        assert archive.read(name) == source.read_bytes(), name

efisp = output.parent / 'efisp.img'
efisp.write_bytes(bds)
efisp.with_suffix('.img.sha256').write_text(f'{hashlib.sha256(bds).hexdigest()}  efisp.img\n')
digest = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n')
print(f'{output}\n{output.stat().st_size} bytes\nSHA-256 {digest}')
print(f'{efisp}\n{len(bds)} bytes\nSHA-256 {hashlib.sha256(bds).hexdigest()}')
