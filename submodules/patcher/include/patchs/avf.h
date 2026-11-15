#ifndef PATCHS_AVF_H
#define PATCHS_AVF_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* This experimental branch intentionally accepts only reviewed image profiles. */
typedef enum {
    AVF_IMAGE_UNKNOWN = 0,
    AVF_IMAGE_STOCK,
    AVF_IMAGE_TEE_PATCHED,
    AVF_IMAGE_PATCHED
} AvfImageKind;

AvfImageKind ClassifyAvfImage(const char *data, int32_t size);
bool PatchAvfBuffer(char *data, int32_t size);

#ifdef AVF_TESTING
void AvfTestSha256(const void *data, size_t size, char hex[65]);
#endif

#endif
