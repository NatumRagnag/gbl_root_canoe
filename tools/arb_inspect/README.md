# Read-only anti-rollback inspector

`arb_inspect IMAGE_OR_PARTITION` reads Qualcomm ELF32/ELF64 little-endian images
with an MBN v7 hash segment, common metadata 0.0 and authority metadata 2.0/3.0.
It prints decimal OEM/QTI anti-rollback versions and software IDs. Missing
metadata is `absent`, not zero. Unsupported formats, ambiguous hash segments and
truncation produce `STATUS=error`, never a guessed version. MBN v3/v5/v6/v8,
Android AVB images, sparse images, and extracted/patched PE files (`boot.efi`,
`BDS.efi`) are not supported.

This inspects metadata, **not signatures, hardware fuse values, RPMB, or the AVB
DeviceInfo rollback array**. Equality is not evidence that an image is authentic,
compatible with the device, or safe to flash. Even matching SW IDs do not establish
matching hardware. A slot's on-disk image can have changed since the last boot.

Format references:

- [Qualcomm secure boot overview](https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/secure-boot-and-image-authentication.pdf)
- [coreboot MBN layout](https://github.com/coreboot/coreboot/blob/main/util/qualcomm/mbn_tools.py)

## Module usage

The WebUI has a read-only check panel. Choose a partition base name (`abl` by
default, or another supported Qualcomm image such as `xbl_config`), then check
both slots or enter an absolute path **on the phone**. Image comparisons use the
selected partition in the current slot. OEM and QTI are separate authorities;
software IDs and presence of authority metadata must match before comparing.
Both higher and lower versions are differences. Mixed OEM/QTI changes and missing
or unreadable baselines are explicitly reported. Results are snapshots, cleared
when a running flash task is detected; recheck after OTA/partition changes.

CLI (run in a root shell; outputs key/value records):

```sh
sh /data/adb/modules/gbl_uefi/bin/arb_check.sh slots abl
sh /data/adb/modules/gbl_uefi/bin/arb_check.sh image abl '/sdcard/Download/abl.img'
```

The wrapper and inspector only read their inputs. They do not modify flash state,
set block devices writable, flash a partition, or reset anti-rollback counters.

## Build and validation

```sh
make -C tools/arb_inspect test
node tools/arb_inspect/tests/test_ui.cjs
NDK_PATH=/path/to/android-ndk make -C tools/arb_inspect build_android
```

The Magisk module Makefile builds and bundles the static Android arm64 inspector.
On Windows, the same source can be built with the NDK's
`aarch64-linux-android31-clang.cmd -std=c11 -O2 -Wall -Wextra -Werror -static`.
Tests include ELF32/64 fixtures, OEM/QTI, uint32 limits, unsupported/corrupt inputs,
all 11 checked-in ABL images, and shell integration with fake read-only partition
files. They do not require or write to a connected phone.
