"""Exercise actual default/menu control flow with mocked firmware services.

This does not emulate UEFI hardware. --check-build also audits the generated
constructor list and linked image for the fixed-address registration regression.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
loader = root / 'submodules/uefi/edk2/QcomModulePkg/Application/LinuxLoader'
main = (loader / 'LinuxLoader.c').read_text()
entries = (loader / 'SuperFbEntries.c').read_text()


def block(text, opening):
    depth = 0
    for i in range(opening, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if not depth:
                return text[opening:i + 1]
    raise AssertionError('Unclosed C block')


# Compile the actual relevant source bodies, not a reimplementation of them.
entry = main.index('LinuxLoaderEntry (')
dispatch = block(main, main.index('{', entry))
default_start = entries.index('SfbLaunchDefaultEntry (VOID)')
default_body = block(entries, entries.index('{', default_start))
assert 'SfbSplashBegin (' not in main and 'SfbSplashLoad (' not in main
assert main.count('SfbLaunchDefaultEntry ();') == 1

prefix = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
typedef unsigned char UINT8;
typedef int BOOLEAN;
typedef int EFI_STATUS;
#define VOID void
#define TRUE 1
#define FALSE 0
#define EFI_SUCCESS 0
#define EFI_ALREADY_STARTED 2
#define SFB_BOOT_NATIVE_FASTBOOT 2
#define DEFAULT_STACK_CHK_GUARD 0xc0c0c0c0
#define EFI_ERROR(x) ((x) != 0)
#define DEBUG(x) ((void)0)
#define SFB_NO_INDEX ((size_t)-1)
typedef struct { int unused; } SFB_BOOT_ENTRY;
typedef struct {
  BOOLEAN DefaultIsPersisted;
  size_t DefaultIndex;
  SFB_BOOT_ENTRY Entry[1];
} SFB_MENU_STATE;
static int key, persisted, found, handoff, filesystem_error, pending, reset_works, reset_status;
static unsigned __stack_chk_guard;
static char events[64];
static jmp_buf launched;
static void event(char c) { size_t n=strlen(events); assert(n+1<sizeof(events)); events[n]=c; events[n+1]=0; }
static int SfbNativeFastbootPending(void) { event('N'); return pending; }
static EFI_STATUS InitThreadUnsafeStack(void) { event('I'); return 0; }
static void DeInitThreadUnsafeStack(void) { event('D'); }
static UINT8 SfbWaitForBootKey(unsigned timeout) { assert(timeout==3000); event('K'); return key; }
static EFI_STATUS SfbRequestNativeFastboot(void) { event('Q'); if(reset_works) longjmp(launched,1); return reset_status; }
static EFI_STATUS EnumeratePartitions(void) { event('P'); return 0; }
static void UpdatePartitionEntries(void) { }
static void Print(const void *s) { (void)s; }
static EFI_STATUS FastbootInitialize(void) { event('T'); return 0; }
static EFI_STATUS SfbStartFatStack(void) { event('F'); return filesystem_error; }
static void SfbBuildMenu(SFB_MENU_STATE *m) { event('B'); m->DefaultIsPersisted=persisted; m->DefaultIndex=found?0:SFB_NO_INDEX; }
static void SfbFreeMenu(SFB_MENU_STATE *m) { (void)m; event('R'); }
static void SfbSplashBegin(void) { event('G'); }
static void SfbSplashLoad(void) { event('L'); }
static EFI_STATUS SfbLaunchEntry(SFB_BOOT_ENTRY *e, int temporary, int clear) {
  (void)e; assert(!temporary && !clear); event('A');
  if(handoff) longjmp(launched,1);
  return 1; /* default loader returned or failed */
}
static void SfbShowEnteringMenu(void) { event('E'); }
static BOOLEAN SfbRunBootMenu(void) { event('M'); return TRUE; }
static void SfbShowFastbootMode(void) { event('V'); }
'''
suffix = r'''
static void check(int k, int p, int f, int h, int fs, const char *expected) {
  key=k; persisted=p; found=f; handoff=h; filesystem_error=fs; events[0]=0;
  if(setjmp(launched)==0) run_dispatch();
  if(strcmp(events,expected)) {
    fprintf(stderr,"flow mismatch: got %s expected %s\n",events,expected);
    assert(0);
  }
}
int main(void) {
  check(1,1,1,0,0,"NIKPFEMVTD");
  check(0,0,1,0,0,"NIKPFBREMVTD");
  check(0,1,0,0,0,"NIKPFBREMVTD");
  check(0,0,0,0,1,"NIKPFBREMVTD");
  check(0,1,1,1,0,"NIKPFBGLA");
  check(0,1,1,0,0,"NIKPFBGLAREMVTD");
  pending=1; check(2,1,1,0,0,"N"); /* no stack/input/storage/gfx initialization */
  pending=0; reset_works=1; check(2,1,1,0,0,"NIKQ"); /* request before storage */
  reset_works=0; reset_status=1; check(2,1,1,0,0,"NIKQPTD"); /* BDS fallback */
  reset_status=2; check(2,1,1,0,0,"NIKQD"); /* preserve newly pending request */
  puts("PASS 10 source-derived boot-flow scenarios");
}
'''
source = (prefix + '\nBOOLEAN SfbLaunchDefaultEntry(VOID)\n' + default_body +
          '\nstatic EFI_STATUS run_dispatch(void)\n' + dispatch + '\n' + suffix)
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'flow.c'
    binary = Path(tmp) / 'flow'
    c.write_text(source)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=undefined', '-fno-sanitize-recover=all', str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

parser = argparse.ArgumentParser()
parser.add_argument('--check-build', action='store_true')
args = parser.parse_args()
if args.check_build:
    debug = root / 'submodules/uefi/edk2/Build/RELEASE_CLANG35/AARCH64/QcomModulePkg/Application/LinuxLoader/LinuxLoader/DEBUG'
    autogen = (debug / 'AutoGen.c').read_text()
    link_map = (debug / 'LinuxLoader.map').read_text()
    image = (root / 'submodules/uefi/build/BDS.efi').read_bytes()
    for forbidden in ('LzmaDecompressLibConstructor', 'GetExtractGuidedSectionHandlerInfo',
                      'PcdGuidedExtractHandlerTableAddress', 'ExtractGuidedSectionRegisterHandlers'):
        assert forbidden not in autogen, forbidden
        assert forbidden not in link_map, forbidden
    assert 'LzmaUefiDecompress' in link_map
    assert 'RawLzmaDecompressLib' in link_map
    assert b'BaseExtractGuidedSectionLib.c' not in image
    assert b'SFBSPL03' in image
    print('PASS built-image audit: raw decoder present; no guided registration constructor/fixed-address table')
