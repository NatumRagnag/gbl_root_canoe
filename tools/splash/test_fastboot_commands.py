"""Check actual registration, prefix dispatch and reboot handlers together."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'submodules/uefi/edk2/QcomModulePkg/Library/FastbootLib/FastbootCmds.c').read_text()
def body(name):
    a=s.index(name+' ('); start=s.index('{',a);depth=0
    for i in range(start,len(s)):
        depth+=(s[i]=='{')-(s[i]=='}')
        if not depth:return s[start:i+1]
table=s[s.index('struct FastbootCmdDesc cmd_list[]'):]
commands=re.findall(r'\{"(reboot[^\"]*)", (\w+)\}',table.split('};')[0])
assert commands==[('reboot','CmdReboot'),('reboot-bootloader','CmdRebootBootloader')]
a=s.index('  for (cmd = cmdlist; cmd; cmd = cmd->next)');b=s.index('  DEBUG',a)
dispatch=s[a:b]
source=r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef char CHAR8;
typedef unsigned int UINT32;
typedef void VOID;
#define IN
#define CONST const
#define STATIC static
#define DEBUG(x) ((void)0)
#define NORMAL_MODE 0
#define FASTBOOT_MODE 2
#define AllocateZeroPool(n) calloc(1,n)
#define AsciiStrLen strlen
#define AsciiStrnCmp strncmp
typedef struct FASTBOOT_CMD FASTBOOT_CMD;
struct FASTBOOT_CMD { const char *prefix; size_t prefix_len; void (*handle)(const char*,void*,unsigned); FASTBOOT_CMD *next; };
static FASTBOOT_CMD *cmdlist;
static void *mUsbDataBuffer;
static unsigned mBytesReceivedSoFar;
static int reason=-1,ok;
static void FastbootOkay(const char *s) {(void)s;ok++;}
static void FastbootFail(const char *s) {(void)s;}
static void RebootDevice(int r) {reason=r;}
'''
source+='\nvoid FastbootRegister(const char *prefix,void (*handle)(const char*,void*,unsigned))'+body('FastbootRegister')
for name in ['CmdReboot','CmdRebootBootloader']:
    source+=f'\nstatic void {name}(const char *arg,void *data,unsigned sz)'+body(name)
source+='\nstatic void dispatch(const char *Data){ FASTBOOT_CMD *cmd;'+dispatch+'}\nint main(void){\n'
source+='\n'.join(f'FastbootRegister("{cmd}",{fn});' for cmd,fn in commands)
source+='''
dispatch("reboot-bootloader"); assert(reason==2 && ok==1);
dispatch("reboot"); assert(reason==0 && ok==2);
while(cmdlist){FASTBOOT_CMD *next=cmdlist->next;free(cmdlist);cmdlist=next;}
puts("PASS source-derived Fastboot prefix dispatch: reboot-bootloader=2, reboot=0");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    c=Path(tmp)/'commands.c';out=Path(tmp)/'commands';c.write_text(source)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    '-fsanitize=undefined',str(c),'-o',str(out)],check=True)
    subprocess.run([str(out)],check=True)
