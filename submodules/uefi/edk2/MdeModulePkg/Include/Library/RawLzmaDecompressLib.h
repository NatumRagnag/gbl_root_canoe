/** @file
  Standalone LZMA decoding without guided-section registration or constructors.
  The caller validates the LZMA header and bounds all allocations before use.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#ifndef RAW_LZMA_DECOMPRESS_LIB_H_
#define RAW_LZMA_DECOMPRESS_LIB_H_
#include <Base.h>

RETURN_STATUS EFIAPI
LzmaUefiDecompressGetInfo (
  IN CONST VOID *Source,
  IN UINT32 SourceSize,
  OUT UINT32 *DestinationSize,
  OUT UINT32 *ScratchSize
  );

RETURN_STATUS EFIAPI
LzmaUefiDecompress (
  IN CONST VOID *Source,
  IN UINTN SourceSize,
  IN OUT VOID *Destination,
  IN OUT VOID *Scratch
  );
#endif
