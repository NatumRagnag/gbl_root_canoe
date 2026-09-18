#ifndef SUPER_FB_BOOT_KEYS_H
#define SUPER_FB_BOOT_KEYS_H

#define SFB_BOOT_DEFAULT 0
#define SFB_BOOT_MENU 1
#define SFB_BOOT_NATIVE_FASTBOOT 2

BOOLEAN SfbNativeFastbootPending (VOID);
EFI_STATUS SfbRequestNativeFastboot (VOID);
UINT8 SfbWaitForBootKey (UINT32 TimeoutMs);

#endif
