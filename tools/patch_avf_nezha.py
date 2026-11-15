#!/usr/bin/env python3
"""Add only the reviewed AVF instruction to an existing TEE-patched EFI.

This does not flash, reboot, modify boot entries, or accept arbitrary firmware.
The C patcher handles stock/OTA inputs through instruction-pattern matching;
this helper remains restricted to the reviewed current image.
"""
import argparse
import hashlib
from pathlib import Path

SIZE = 1089536
OFFSET = 0x24588
ORIGINAL = bytes.fromhex("29757739")
REPLACEMENT = bytes.fromhex("09008052")
INPUT_SHA256 = "39cfb80eb6cb3ce73c43b347cb9e63bf36694f24d733d79808df71d248d1ef52"
OUTPUT_SHA256 = "14058f4e11282bcbcc57eedac5f438bc73ab73cc24f4bec42d2dd812f2a29b68"


def patch(data: bytes) -> bytes:
    digest = hashlib.sha256(data).hexdigest()
    if len(data) == SIZE and digest == OUTPUT_SHA256:
        return data
    if len(data) != SIZE or digest != INPUT_SHA256:
        raise ValueError(f"Unsupported input SHA-256: {digest}; source left unchanged")
    if data[OFFSET:OFFSET + 4] != ORIGINAL:
        raise ValueError("Instruction mismatch")
    result = data[:OFFSET] + REPLACEMENT + data[OFFSET + 4:]
    if hashlib.sha256(result).hexdigest() != OUTPUT_SHA256:
        raise ValueError("Output SHA-256 mismatch")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Use a separate output file; the input is your recovery copy")
    try:
        original = args.input.read_bytes()
        result = patch(original)
        # Exclusive creation also rejects an existing alias/hardlink to the input.
        with args.output.open("xb") as out:
            out.write(result)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"AVF patch failed: {exc}\n")
    print(f"Saved {args.output} ({len(result)} bytes)")
    print(f"SHA-256: {hashlib.sha256(result).hexdigest()}")
    print("Experimental image created; boot and fresh CSR validation still required.")


if __name__ == "__main__":
    main()
