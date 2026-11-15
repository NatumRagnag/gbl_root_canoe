#include "patchs/avf.h"

#include <stdio.h>
#include <string.h>

/* Xiaomi 17 Ultra (nezha), OS4.0.2.0.XPACNXM. File offsets equal RVAs
 * in this reviewed PE image. Do not reuse the offset on another image.
 * The full-image allowlist is deliberate: pattern-only matching is not yet
 * validated across ABL versions or vendors. */
#define AVF_IMAGE_SIZE 1089536
#define AVF_UNLOCK_LOAD_OFFSET 0x24588

static const char stock_hash[] =
    "7c0b96923fd8d7d30e3462aa2427cfc10cafdc1f7f5b8243ac6285fe0204442f";
static const char tee_hash[] =
    "39cfb80eb6cb3ce73c43b347cb9e63bf36694f24d733d79808df71d248d1ef52";
static const char avf_hash[] =
    "14058f4e11282bcbcc57eedac5f438bc73ab73cc24f4bec42d2dd812f2a29b68";

/* Small, dependency-free SHA-256 for the Linux, Windows and Android builds.
 * It is used for image identification, not signatures or key handling. */
static uint32_t ror32(uint32_t x, unsigned n) {
    return (x >> n) | (x << (32 - n));
}

static void sha256_block(uint32_t h[8], const uint8_t block[64]) {
    static const uint32_t k[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };
    uint32_t w[64];
    for (unsigned i = 0; i < 16; ++i) {
        const uint8_t *p = block + i * 4;
        w[i] = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
               ((uint32_t)p[2] << 8) | p[3];
    }
    for (unsigned i = 16; i < 64; ++i) {
        uint32_t s0 = ror32(w[i-15],7) ^ ror32(w[i-15],18) ^ (w[i-15] >> 3);
        uint32_t s1 = ror32(w[i-2],17) ^ ror32(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t a=h[0], b=h[1], c=h[2], d=h[3], e=h[4], f=h[5], g=h[6], z=h[7];
    for (unsigned i = 0; i < 64; ++i) {
        uint32_t s1 = ror32(e,6) ^ ror32(e,11) ^ ror32(e,25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = z + s1 + ch + k[i] + w[i];
        uint32_t s0 = ror32(a,2) ^ ror32(a,13) ^ ror32(a,22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = s0 + maj;
        z=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d;
    h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=z;
}

static void sha256_hex(const void *data, size_t size, char hex[65]) {
    uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                     0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    const uint8_t *p = data;
    size_t left = size;
    while (left >= 64) {
        sha256_block(h, p);
        p += 64;
        left -= 64;
    }
    uint8_t tail[128] = {0};
    if (left) memcpy(tail, p, left);
    tail[left] = 0x80;
    size_t padded = left < 56 ? 64 : 128;
    uint64_t bits = (uint64_t)size * 8;
    for (unsigned i = 0; i < 8; ++i)
        tail[padded - 1 - i] = (uint8_t)(bits >> (i * 8));
    sha256_block(h, tail);
    if (padded == 128) sha256_block(h, tail + 64);
    static const char digits[] = "0123456789abcdef";
    for (unsigned i = 0; i < 32; ++i) {
        uint8_t byte = (uint8_t)(h[i / 4] >> (24 - (i % 4) * 8));
        hex[i * 2] = digits[byte >> 4];
        hex[i * 2 + 1] = digits[byte & 15];
    }
    hex[64] = '\0';
}

#ifdef AVF_TESTING
void AvfTestSha256(const void *data, size_t size, char hex[65]) {
    sha256_hex(data, size, hex);
}
#endif

AvfImageKind ClassifyAvfImage(const char *data, int32_t size) {
    if (!data || size != AVF_IMAGE_SIZE) return AVF_IMAGE_UNKNOWN;
    char hash[65];
    sha256_hex(data, (size_t)size, hash);
    if (!strcmp(hash, stock_hash)) return AVF_IMAGE_STOCK;
    if (!strcmp(hash, tee_hash)) return AVF_IMAGE_TEE_PATCHED;
    if (!strcmp(hash, avf_hash)) return AVF_IMAGE_PATCHED;
    return AVF_IMAGE_UNKNOWN;
}

bool PatchAvfBuffer(char *data, int32_t size) {
    AvfImageKind kind = ClassifyAvfImage(data, size);
    if (kind == AVF_IMAGE_PATCHED) {
        printf("AVF: reviewed image already patched; no changes.\n");
        return true;
    }
    if (kind != AVF_IMAGE_TEE_PATCHED) {
        printf("AVF: image is not the reviewed TEE-patched nezha image; refusing.\n");
        return false;
    }
    const uint8_t original[4] = {0x29,0x75,0x77,0x39}; /* LDRB W9,[X9,#0xddd] */
    const uint8_t replacement[4] = {0x09,0x00,0x80,0x52}; /* MOV W9,#0 */
    if (memcmp(data + AVF_UNLOCK_LOAD_OFFSET, original, sizeof(original)))
        return false;
    memcpy(data + AVF_UNLOCK_LOAD_OFFSET, replacement, sizeof(replacement));
    if (ClassifyAvfImage(data, size) != AVF_IMAGE_PATCHED) {
        memcpy(data + AVF_UNLOCK_LOAD_OFFSET, original, sizeof(original));
        printf("AVF: output identity mismatch; reverted buffer change.\n");
        return false;
    }
    printf("AVF: 0x24588 LDRB W9,[X9,#0xddd] -> MOV W9,#0.\n");
    printf("AVF: TEE edits, global DevInfo, mode=3 and dummy fallback preserved.\n");
    return true;
}
