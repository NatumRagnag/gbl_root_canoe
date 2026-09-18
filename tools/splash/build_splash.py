"""Convert supplied artwork to fixed-screen, lossless compressed GOP pixels.

No artwork regeneration: composite alpha on black, fit proportionally, then
store BGRX pixels in LZMA-alone with explicit output size for EDK2.
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct
import zlib
from PIL import Image, ImageOps

WIDTH, HEIGHT = 1200, 2608
MAGIC = b'SFBSPL03'


def render(source):
    artwork = ImageOps.exif_transpose(Image.open(source)).convert('RGBA')
    # Keep hair/feet clear of the edges and the camera cutout.
    artwork = ImageOps.contain(artwork, (WIDTH - 96, HEIGHT - 96), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 255))
    canvas.alpha_composite(artwork, ((WIDTH - artwork.width) // 2, (HEIGHT - artwork.height) // 2))
    rgb = canvas.convert('RGB')
    return rgb


def build(source, output, preview):
    rgb = render(source)
    # Store original-resolution pixels losslessly; BDS scales to 1200x2608.
    original = Image.open(source).convert('RGBA')
    assert original.size == (890, 1920)
    black = Image.new('RGBA', original.size, (0, 0, 0, 255))
    black.alpha_composite(original)
    pixels = black.convert('RGB').tobytes('raw', 'BGRX')
    packed = bytearray(lzma.compress(pixels, format=lzma.FORMAT_ALONE, preset=6))
    packed[5:13] = struct.pack('<Q', len(pixels))
    assert packed[0] == 0x5d
    assert lzma.decompress(packed, format=lzma.FORMAT_ALONE) == pixels
    checksum = zlib.crc32(pixels)
    header = struct.pack('<8s6I', MAGIC, 890, 1920, len(packed), len(pixels), checksum, 0)
    output.write_bytes(header + packed)
    rgb.save(preview)
    return {'file': output.name, 'source': source.name, 'width': WIDTH, 'height': HEIGHT,
            'bytes': output.stat().st_size, 'source_width': 890, 'source_height': 1920, 'crc32': f'{checksum:08x}',
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('preview', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.preview.mkdir(parents=True, exist_ok=True)
    sources = sorted(args.source.glob('*.png'))
    if len(sources) != 7:
        parser.error('Expected exactly seven PNG inputs')
    entries = [build(p, args.output / f'{i}.sfb', args.preview / f'{i}.png') for i, p in enumerate(sources, 1)]
    (args.output / 'manifest.json').write_text(json.dumps(entries, indent=2) + '\n')
    print(json.dumps({'count': len(entries), 'bytes': sum(e['bytes'] for e in entries), 'entries': entries}, indent=2))


if __name__ == '__main__':
    main()
