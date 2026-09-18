/* Early boot selection. No storage, graphics, protocol hooks or constructors. */
#include <Uefi.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/ShutdownServices.h>
#include <Protocol/EFIResetReason.h>
#include <Protocol/SimpleTextIn.h>
#include "SuperFbBootKeys.h"

STATIC EFI_STATUS __attribute__ ((no_sanitize ("safe-stack")))
SfbReadResetReason (UINT32 *Reason)
{
  EFI_RESETREASON_PROTOCOL *Protocol = NULL;
  EFI_STATUS Status;

  *Reason = 0;
  Status = gBS->LocateProtocol (&gEfiResetReasonProtocolGuid, NULL,
                                (VOID **)&Protocol);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (Protocol == NULL || Protocol->GetResetReason == NULL) {
    return EFI_UNSUPPORTED;
  }
  /* Never ClearResetReason: the parent ABL still needs this request. */
  return Protocol->GetResetReason (Protocol, Reason, NULL, NULL);
}

BOOLEAN __attribute__ ((no_sanitize ("safe-stack")))
SfbNativeFastbootPending (VOID)
{
  UINT32 Reason;
  return !EFI_ERROR (SfbReadResetReason (&Reason)) && Reason == FASTBOOT_MODE;
}

EFI_STATUS
SfbRequestNativeFastboot (VOID)
{
  UINT32 Reason;
  EFI_STATUS Status;
  ResetDataType ResetData = { STR_RESET_PARAM, FASTBOOT_MODE };

  /* Do not request another boot if we cannot read its reason on re-entry. */
  Status = SfbReadResetReason (&Reason);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (Reason == FASTBOOT_MODE) {
    return EFI_ALREADY_STARTED;
  }
  /* Same payload as the original RebootDevice(FASTBOOT_MODE), without its
   * USB-flash wait or display teardown: neither is initialized on this path. */
  gRT->ResetSystem (EfiResetCold, EFI_INVALID_PARAMETER,
                    sizeof (ResetData), &ResetData);
  return EFI_DEVICE_ERROR; /* ResetSystem must not return on success. */
}

UINT8
SfbWaitForBootKey (UINT32 TimeoutMs)
{
  EFI_STATUS Status;
  EFI_EVENT TimerEvent;
  EFI_EVENT WaitList[2];
  UINTN EventIndex;
  EFI_INPUT_KEY Key;
  UINT8 Selection = SFB_BOOT_DEFAULT;

  if (gST->ConIn == NULL) {
    return Selection;
  }
  /* Do not discard the volume press that got us here. Unrelated keys are
   * skipped within one bounded timer window. */
  Status = gBS->CreateEvent (EVT_TIMER, TPL_CALLBACK, NULL, NULL, &TimerEvent);
  if (EFI_ERROR (Status)) {
    return SFB_BOOT_MENU;
  }
  Status = gBS->SetTimer (TimerEvent, TimerRelative, (UINT64)TimeoutMs * 10000);
  if (EFI_ERROR (Status)) {
    gBS->CloseEvent (TimerEvent);
    return SFB_BOOT_MENU;
  }
  WaitList[0] = TimerEvent; /* Expired timer wins even with a busy key queue. */
  WaitList[1] = gST->ConIn->WaitForKey;
  while (TRUE) {
    Status = gBS->WaitForEvent (2, WaitList, &EventIndex);
    if (EFI_ERROR (Status)) {
      Selection = SFB_BOOT_MENU;
      break;
    }
    if (EventIndex == 0) {
      break;
    }
    Status = gST->ConIn->ReadKeyStroke (gST->ConIn, &Key);
    if (!EFI_ERROR (Status)) {
      if (Key.ScanCode == SCAN_DOWN) {
        Selection = SFB_BOOT_NATIVE_FASTBOOT;
        break;
      }
      if (Key.ScanCode == SCAN_UP) {
        Selection = SFB_BOOT_MENU;
        break;
      }
    } else if (Status != EFI_NOT_READY) {
      Selection = SFB_BOOT_MENU;
      break;
    }
  }
  gBS->CloseEvent (TimerEvent);
  return Selection;
}
