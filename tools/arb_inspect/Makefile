.PHONY: build build_android test
build:
	mkdir -p build
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror arb_inspect.c -o build/arb_inspect
build_android:
	mkdir -p build
	@test -n "$(NDK_PATH)" || (echo 'Set NDK_PATH to your Android NDK'; exit 1)
	"$(NDK_PATH)/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android31-clang" -std=c11 -O2 -Wall -Wextra -Werror -static arb_inspect.c -o build/arb_inspect_android
test: build
	python3 tests/test_arb.py build/arb_inspect
