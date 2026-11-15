#ifndef PATCHS_AVF_H
#define PATCHS_AVF_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Exact known-image identities are compatibility shortcuts, not OTA gates. */
typedef enum {
    AVF_IMAGE_UNKNOWN = 0,
    AVF_IMAGE_STOCK,
    AVF_IMAGE_TEE_PATCHED,
    AVF_IMAGE_PATCHED
} AvfImageKind;

AvfImageKind ClassifyAvfImage(const char *data, int32_t size);
int32_t FindAvfPatch(const char *data, int32_t size, uint8_t *reg, bool *patched);
bool PatchAvfBuffer(char *data, int32_t size);

#ifdef AVF_TESTING
void AvfTestSha256(const void *data, size_t size, char hex[65]);
#endif

#endif
