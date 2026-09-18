.PHONY: clean copy_resources submodule_uefi submodule_patcher submodule_ablfvextractor tool_arb_inspect build
clean:
	rm -rf build || true
copy_resources:
	mkdir -p build/module
	cp -r module/* build/module/
submodule_uefi: copy_resources
	cd ../../submodules/uefi && make build && make tools
	cp ../../submodules/uefi/build/BDS.efi ./build/module/BDS.efi
	cp ../../submodules/uefi/build/ArbTools.efi ./build/module/efisp/tools/ArbTools.efi
	cp ../../submodules/uefi/build/BLTools.efi ./build/module/efisp/tools/BLTools.efi
	cp ../../submodules/uefi/build/RebootTools.efi ./build/module/efisp/tools/RebootTools.efi
submodule_patcher: copy_resources
	cd ../../submodules/patcher && make build_android
	cp ../../submodules/patcher/build/patch_abl_android ./build/module/bin/patch_abl
submodule_ablfvextractor: copy_resources
	cd ../../submodules/ablfvextractor && make build_android
	cp ../../submodules/ablfvextractor/build/extractfv_android ./build/module/bin/extractfv
tool_arb_inspect: copy_resources
	$(MAKE) -C ../../tools/arb_inspect build_android
	cp ../../tools/arb_inspect/build/arb_inspect_android ./build/module/bin/arb_inspect
build: submodule_uefi submodule_patcher submodule_ablfvextractor tool_arb_inspect
	# zip
	python3 ../../tools/package_module.py
