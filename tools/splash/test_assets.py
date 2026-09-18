"""Exercise the real firmware SDK/scaler on every asset and damaged samples."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
binary = Path(__file__).resolve().parent / 'build/test_decode'
assets = root / 'targets/magisk_module/module/efisp/splash'
preview = Path(__file__).resolve().parent / 'build'
for i in range(1, 8):
    subprocess.run([str(binary), str(assets / f'{i}.sfb'), str(preview / f'{i}.bgrx')], check=True)
original = (assets / '1.sfb').read_bytes()
with tempfile.TemporaryDirectory() as tmp:
    damaged = Path(tmp) / 'damaged.sfb'
    samples = [original[:12], original[:-20]]
    for pos in (0, 8, 12, 16, 20, 24, 28, 32, 37, 41, len(original)//2):
        data = bytearray(original)
        data[pos] ^= 0xff
        samples.append(data)
    for data in samples:
        damaged.write_bytes(data)
        result = subprocess.run([str(binary), str(damaged)])
        assert result.returncode == 1, result.returncode
print(f'PASS {len(samples)} corrupt/truncated cases')
