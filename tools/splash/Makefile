.PHONY: test
SDK = ../../submodules/uefi/edk2/MdeModulePkg/Library/LzmaCustomDecompressLib/Sdk/C
LOADER = ../../submodules/uefi/edk2/QcomModulePkg/Application/LinuxLoader
test:
	mkdir -p build
	$(CC) -O2 -g -fsanitize=undefined -fno-sanitize-recover=all -I$(SDK) -I$(LOADER) test_decode.c $(SDK)/LzmaDec.c -o build/test_decode
	python3 test_assets.py
	python3 test_boot_flow.py
	python3 test_boot_keys.py
	python3 test_fastboot_commands.py
