/* Optional read-only boot artwork, scoped to the display owned by this BDS.
 * File format is produced by tools/splash/build_splash.py. The decoder accepts
 * only the bounded 1200x2608 BGRX format used by this device's artwork bundle.
 */
#include "SuperFbMenu.h"
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/RawLzmaDecompressLib.h>
#include <Library/PrintLib.h>
#include <Library/TimerLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Protocol/GraphicsOutput.h>
#include <Protocol/EFIRng.h>
#include <Guid/FileInfo.h>
#include "SuperFbSplashPixels.h"

#define SFB_SPLASH_WIDTH  1200U
#define SFB_SPLASH_HEIGHT 2608U
#define SFB_SPLASH_BYTES  (SFB_SPLASH_WIDTH * SFB_SPLASH_HEIGHT * 4U)
#define SFB_SPLASH_COUNT  7U
#define SFB_SPLASH_MAX_FILE (3U * 1024U * 1024U)

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL *mSplashGop;
STATIC EFI_GRAPHICS_OUTPUT_BLT_PIXEL *mSplashPixels;
STATIC UINT32 mSplashIndex;

STATIC BOOLEAN
SfbSplashHasMode (VOID)
{
  return mSplashGop != NULL && mSplashGop->Mode != NULL &&
         mSplashGop->Mode->Info != NULL &&
         mSplashGop->Mode->Info->HorizontalResolution == SFB_SPLASH_WIDTH &&
         mSplashGop->Mode->Info->VerticalResolution == SFB_SPLASH_HEIGHT;
}

/* Optional display preparation, only after key handling and default selection. */
VOID
SfbSplashBegin (VOID)
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Black = { 0, 0, 0, 0 };
  EFI_STATUS Status;
  Status = gBS->HandleProtocol (gST->ConsoleOutHandle,
                                 &gEfiGraphicsOutputProtocolGuid,
                                 (VOID **)&mSplashGop);
  if (EFI_ERROR (Status)) {
    Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL,
                                   (VOID **)&mSplashGop);
  }
  if (EFI_ERROR (Status) || !SfbSplashHasMode ()) {
    mSplashGop = NULL;
    DEBUG ((EFI_D_INFO, "SFB: splash skipped, no matching 1200x2608 GOP\n"));
    return;
  }
  if (gST->ConOut != NULL) {
    gST->ConOut->EnableCursor (gST->ConOut, FALSE);
  }
  mSplashGop->Blt (mSplashGop, &Black, EfiBltVideoFill, 0, 0, 0, 0,
                    SFB_SPLASH_WIDTH, SFB_SPLASH_HEIGHT, 0);
}

STATIC UINT32
SfbSplashRandom (VOID)
{
  EFI_QCOM_RNG_PROTOCOL *Rng = NULL;
  UINT32 Value;
  EFI_TIME Time;
  if (!EFI_ERROR (gBS->LocateProtocol (&gQcomRngProtocolGuid, NULL, (VOID **)&Rng)) &&
      Rng != NULL && !EFI_ERROR (Rng->GetRNG (Rng, NULL, sizeof (Value), (UINT8 *)&Value))) {
    return Value;
  }
  /* Aesthetic randomness only. No persistent counter/partition writes. */
  Value = (UINT32)GetPerformanceCounter ();
  if (gRT != NULL && !EFI_ERROR (gRT->GetTime (&Time, NULL))) {
    Value ^= Time.Nanosecond ^ ((UINT32)Time.Second << 24) ^
             ((UINT32)Time.Minute << 16) ^ ((UINT32)Time.Hour << 8);
  }
  Value ^= Value << 13; Value ^= Value >> 17; Value ^= Value << 5;
  return Value;
}

STATIC EFI_STATUS
SfbSplashRead (IN EFI_FILE_PROTOCOL *Root, IN CONST CHAR16 *Path)
{
  EFI_FILE_PROTOCOL *File = NULL;
  EFI_FILE_INFO *Info = NULL;
  UINT8 *Packed = NULL;
  VOID *Scratch = NULL;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Pixels = NULL;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Screen = NULL;
  UINTN InfoSize = 0, FileSize, ReadSize;
  UINT32 RawSize, ScratchSize, Crc;
  EFI_STATUS Status;

  Status = Root->Open (Root, &File, (CHAR16 *)Path, EFI_FILE_MODE_READ, 0);
  if (EFI_ERROR (Status) || File == NULL) return EFI_NOT_FOUND;
  Status = File->GetInfo (File, &gEfiFileInfoGuid, &InfoSize, NULL);
  if (Status != EFI_BUFFER_TOO_SMALL || InfoSize > 4096 || InfoSize < sizeof (EFI_FILE_INFO)) {
    Status = EFI_UNSUPPORTED; goto Done;
  }
  Info = AllocateZeroPool (InfoSize);
  if (Info == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Done; }
  Status = File->GetInfo (File, &gEfiFileInfoGuid, &InfoSize, Info);
  if (EFI_ERROR (Status)) goto Done;
  if ((Info->Attribute & EFI_FILE_DIRECTORY) != 0 || Info->FileSize < 45 ||
      Info->FileSize > SFB_SPLASH_MAX_FILE) { Status = EFI_UNSUPPORTED; goto Done; }
  FileSize = (UINTN)Info->FileSize;
  Packed = AllocatePool (FileSize);
  if (Packed == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Done; }
  ReadSize = FileSize;
  Status = File->Read (File, &ReadSize, Packed);
  if (EFI_ERROR (Status) || ReadSize != FileSize) { Status = EFI_DEVICE_ERROR; goto Done; }
  /* Validate before calling the SDK: restrict properties/sizes so malformed
   * files cannot trigger huge allocations or its scratch-allocation ASSERT. */
  if (CompareMem (Packed, "SFBSPL03", 8) != 0 ||
      ReadUnaligned32 ((UINT32 *)(Packed + 8)) != SFB_ART_WIDTH ||
      ReadUnaligned32 ((UINT32 *)(Packed + 12)) != SFB_ART_HEIGHT ||
      ReadUnaligned32 ((UINT32 *)(Packed + 16)) != FileSize - 32 ||
      ReadUnaligned32 ((UINT32 *)(Packed + 20)) != SFB_ART_BYTES ||
      ReadUnaligned32 ((UINT32 *)(Packed + 28)) != 0 || Packed[32] != 0x5d ||
      ReadUnaligned32 ((UINT32 *)(Packed + 33)) > 16U * 1024U * 1024U ||
      ReadUnaligned64 ((UINT64 *)(Packed + 37)) != SFB_ART_BYTES) {
    Status = EFI_UNSUPPORTED; goto Done;
  }
  Status = LzmaUefiDecompressGetInfo (Packed + 32, (UINT32)FileSize - 32, &RawSize, &ScratchSize);
  if (EFI_ERROR (Status) || RawSize != SFB_ART_BYTES || ScratchSize > 65536) {
    Status = EFI_UNSUPPORTED; goto Done;
  }
  Pixels = AllocateZeroPool (RawSize);
  Scratch = AllocatePool (ScratchSize);
  if (Pixels == NULL || Scratch == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Done; }
  Status = LzmaUefiDecompress (Packed + 32, FileSize - 32, Pixels, Scratch);
  if (EFI_ERROR (Status)) goto Done;
  Status = gBS->CalculateCrc32 (Pixels, RawSize, &Crc);
  if (EFI_ERROR (Status) || Crc != ReadUnaligned32 ((UINT32 *)(Packed + 24))) {
    Status = EFI_CRC_ERROR; goto Done;
  }
  Screen = AllocateZeroPool (SFB_SPLASH_BYTES);
  if (Screen == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Done; }
  SfbScaleSplash ((UINT8 *)Pixels, (UINT8 *)Screen);
  mSplashPixels = Screen;
Done:
  if (Pixels != NULL) FreePool (Pixels);
  if (Scratch != NULL) FreePool (Scratch);
  if (Packed != NULL) FreePool (Packed);
  if (Info != NULL) FreePool (Info);
  File->Close (File);
  return Status;
}

BOOLEAN
SfbSplashRestore (VOID)
{
  EFI_STATUS Status;
  if (!SfbSplashHasMode () || mSplashPixels == NULL) return FALSE;
  Status = mSplashGop->Blt (mSplashGop, mSplashPixels, EfiBltBufferToVideo,
                             0, 0, 0, 0, SFB_SPLASH_WIDTH, SFB_SPLASH_HEIGHT, 0);
  return !EFI_ERROR (Status);
}

VOID
SfbSplashLoad (VOID)
{
  EFI_HANDLE *Volumes = NULL;
  EFI_FILE_PROTOCOL *Root = NULL;
  UINTN Count = 0, Index, Try;
  UINT32 First;
  CHAR16 Path[64];
  EFI_STATUS Status;
  if (!SfbSplashHasMode () || mSplashPixels != NULL) return;
  First = SfbSplashRandom () % SFB_SPLASH_COUNT;
  if (EFI_ERROR (SfbLocateVolumes (&Volumes, &Count))) return;
  for (Index = 0; Index < Count && mSplashPixels == NULL; Index++) {
    /* Only the persist boot root, never arbitrary artwork on an attached USB. */
    if (StrCmp (SfbVolumeRootPrefix (Volumes[Index]), L"\\efisp") != 0) continue;
    if (EFI_ERROR (SfbOpenVolumeRoot (Volumes[Index], &Root)) || Root == NULL) continue;
    for (Try = 0; Try < SFB_SPLASH_COUNT; Try++) {
      mSplashIndex = (First + (UINT32)Try) % SFB_SPLASH_COUNT + 1;
      UnicodeSPrint (Path, sizeof (Path), L"\\efisp\\splash\\%u.sfb", mSplashIndex);
      Status = SfbSplashRead (Root, Path);
      DEBUG ((EFI_D_INFO, "SFB: splash %u decode: %r\n", mSplashIndex, Status));
      if (!EFI_ERROR (Status)) break;
    }
    Root->Close (Root); Root = NULL;
  }
  FreePool (Volumes);
  if (SfbSplashRestore ()) {
    DEBUG ((EFI_D_INFO, "SFB: splash %u drawn at 1200x2608\n", mSplashIndex));
  }
}
