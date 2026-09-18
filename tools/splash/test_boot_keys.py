"""Compile the actual early-boot implementation against mock UEFI protocols."""
from pathlib import Path
import os, subprocess, tempfile
root = Path(__file__).resolve().parents[2]
loader = root / 'submodules/uefi/edk2/QcomModulePkg/Application/LinuxLoader'
code = (loader / 'SuperFbBootKeys.c').read_text()
code = '\n'.join(line for line in code.splitlines() if not line.startswith('#include'))
assert '->ClearResetReason' not in code and 'ConIn->Reset' not in code
# The guard runs before the unsafe-stack allocator.
assert code.count('no_sanitize ("safe-stack")') == 2
prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <uchar.h>
#include <string.h>
typedef uint8_t UINT8;
typedef uint16_t CHAR16;
typedef uint32_t UINT32;
typedef uint64_t UINT64;
typedef size_t UINTN;
typedef void *EFI_EVENT;
typedef int EFI_STATUS;
typedef int BOOLEAN;
#define VOID void
#define STATIC static
#define TRUE 1
#define EFI_SUCCESS 0
#define EFI_UNSUPPORTED 1
#define EFI_ALREADY_STARTED 2
#define EFI_DEVICE_ERROR 3
#define EFI_NOT_READY 4
#define EFI_INVALID_PARAMETER 5
#define EFI_ERROR(s) ((s)!=0)
#define EVT_TIMER 1
#define TPL_CALLBACK 8
#define TimerRelative 2
#define EfiResetCold 0
#define FASTBOOT_MODE 2
#define STR_RESET_PARAM u"RESET_PARAM"
#define SFB_BOOT_DEFAULT 0
#define SFB_BOOT_MENU 1
#define SFB_BOOT_NATIVE_FASTBOOT 2
#define SCAN_UP 1
#define SCAN_DOWN 2
typedef struct { CHAR16 DataBuffer[12]; UINT8 Bdata; } __attribute__((packed,aligned(2))) ResetDataType;
typedef struct { unsigned ScanCode; } EFI_INPUT_KEY;
typedef struct EFI_RESETREASON_PROTOCOL EFI_RESETREASON_PROTOCOL;
struct EFI_RESETREASON_PROTOCOL { EFI_STATUS (*GetResetReason)(EFI_RESETREASON_PROTOCOL*,UINT32*,CHAR16*,UINT32*); };
static int locate_error, read_error, null_protocol, null_method, create_error, timer_error;
static int wait_error, key_error, key_count, key_pos, closed, requests, clears, reads;
static UINT32 reason;
static unsigned keys[8];
static int gEfiResetReasonProtocolGuid;
static EFI_STATUS read_reason(EFI_RESETREASON_PROTOCOL *p,UINT32 *r,CHAR16 *s,UINT32 *n) {
 (void)p; assert(!s && !n); reads++; *r=reason; return read_error;
}
static EFI_RESETREASON_PROTOCOL protocol={read_reason};
static EFI_STATUS locate(void *g,void *r,void **p) {
 assert(g==&gEfiResetReasonProtocolGuid && !r);
 protocol.GetResetReason=null_method?NULL:read_reason;
 *p=null_protocol?NULL:&protocol; return locate_error;
}
static EFI_STATUS create(unsigned t,unsigned tpl,void *a,void *b,EFI_EVENT *e) {
 assert(t==EVT_TIMER && tpl==TPL_CALLBACK && !a && !b); *e=(void*)1; return create_error;
}
static EFI_STATUS timer(EFI_EVENT e,unsigned t,UINT64 n) { assert(e==(void*)1 && t==TimerRelative && n==30000000); return timer_error; }
static EFI_STATUS close_event(EFI_EVENT e) { assert(e==(void*)1); closed++; return 0; }
static EFI_STATUS wait_event(UINTN n,EFI_EVENT *events,UINTN *i) {
 assert(n==2 && events[0]==(void*)1 && events[1]==(void*)2);
 *i=key_pos<key_count?1:0; return wait_error;
}
typedef struct INPUT INPUT;
struct INPUT { EFI_EVENT WaitForKey; EFI_STATUS (*ReadKeyStroke)(INPUT*,EFI_INPUT_KEY*); };
static EFI_STATUS read_key(INPUT *p,EFI_INPUT_KEY *k) { (void)p; k->ScanCode=keys[key_pos++]; return key_error; }
static INPUT input={(void*)2,read_key};
static struct { INPUT *ConIn; } system_table={&input}, *gST=&system_table;
static struct {
 EFI_STATUS (*LocateProtocol)(void*,void*,void**);
 EFI_STATUS (*CreateEvent)(unsigned,unsigned,void*,void*,EFI_EVENT*);
 EFI_STATUS (*SetTimer)(EFI_EVENT,unsigned,UINT64);
 EFI_STATUS (*CloseEvent)(EFI_EVENT);
 EFI_STATUS (*WaitForEvent)(UINTN,EFI_EVENT*,UINTN*);
} services={locate,create,timer,close_event,wait_event}, *gBS=&services;
static void reset_system(unsigned type,EFI_STATUS status,UINTN size,void *data) {
 ResetDataType *d=data;
 assert(type==EfiResetCold && status==EFI_INVALID_PARAMETER && size==26);
 assert(d->Bdata==2 && memcmp(d->DataBuffer,u"RESET_PARAM",24)==0); requests++;
}
static struct { void (*ResetSystem)(unsigned,EFI_STATUS,UINTN,void*); } runtime={reset_system}, *gRT=&runtime;
'''
suffix = r'''
int main(void) {
 reason=2; assert(SfbNativeFastbootPending()); assert(reason==2 && reads==1 && clears==0);
 reason=0; assert(!SfbNativeFastbootPending());
 locate_error=1; assert(!SfbNativeFastbootPending()); assert(SfbRequestNativeFastboot()==1 && requests==0);
 locate_error=0; read_error=1; assert(!SfbNativeFastbootPending()); assert(SfbRequestNativeFastboot()==1 && requests==0);
 read_error=0; null_protocol=1; assert(!SfbNativeFastbootPending()); null_protocol=0;
 null_method=1; assert(!SfbNativeFastbootPending()); null_method=0;
 reason=2; assert(SfbRequestNativeFastboot()==EFI_ALREADY_STARTED && requests==0);
 reason=0; assert(SfbRequestNativeFastboot()==EFI_DEVICE_ERROR && requests==1);
 assert(SfbWaitForBootKey(3000)==SFB_BOOT_DEFAULT && closed==1);
 keys[0]=SCAN_DOWN; key_count=1; assert(SfbWaitForBootKey(3000)==SFB_BOOT_NATIVE_FASTBOOT && closed==2);
 key_pos=0; keys[0]=SCAN_UP; assert(SfbWaitForBootKey(3000)==SFB_BOOT_MENU && closed==3);
 key_pos=0; keys[0]=99; keys[1]=SCAN_DOWN; key_count=2;
 assert(SfbWaitForBootKey(3000)==SFB_BOOT_NATIVE_FASTBOOT && key_pos==2 && closed==4);
 create_error=1; assert(SfbWaitForBootKey(3000)==SFB_BOOT_MENU && closed==4); create_error=0;
 timer_error=1; assert(SfbWaitForBootKey(3000)==SFB_BOOT_MENU && closed==5); timer_error=0;
 wait_error=1; assert(SfbWaitForBootKey(3000)==SFB_BOOT_MENU && closed==6); wait_error=0;
 key_pos=0; key_error=EFI_DEVICE_ERROR; assert(SfbWaitForBootKey(3000)==SFB_BOOT_MENU && closed==7);
 key_error=EFI_NOT_READY; key_pos=0; key_count=1; assert(SfbWaitForBootKey(3000)==SFB_BOOT_DEFAULT && closed==8);
 gST->ConIn=NULL; assert(SfbWaitForBootKey(3000)==SFB_BOOT_DEFAULT && closed==8);
 puts("PASS actual early-key/reset code: retained reason, reset payload, missing protocols, queued keys, timer and input errors");
}
'''
with tempfile.TemporaryDirectory() as temp:
    c=Path(temp)/'boot_keys.c'; binary=Path(temp)/'boot_keys'
    c.write_text(prefix+code+suffix)
    subprocess.run([os.environ.get('CC','clang'),'-std=c11','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined','-fno-sanitize-recover=all',str(c),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
