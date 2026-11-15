#include "patchs/avf.h"
#include "arm64_inst/arm64_inst_decoder.h"

#include <stdio.h>
#include <string.h>

/* Known images are retained only for compatibility with already TEE-patched
 * inputs. They are not an allowlist for the normal stock/OTA patch pipeline. */
#define AVF_IMAGE_SIZE 1089536

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

/* Reviewed BCC mode block, with relocated addresses, stack displacement and
 * compiler-assigned temporary registers decoded rather than hard-coded:
 *   ADRP u; LDRB flags,[ctx,#3]; LDRB tmp,[ctx,#2]; MOV one,#1
 *   MOV W1,WZR; MOV W2,#0x28; LDRB u,[u,#unlock_offset]
 *   ORR flags,flags,tmp; ADD tmp,SP,#stack; ADD X0,tmp,#4
 *   CMP u,#0; CINC u,one,NE; CMP flags,#0; MOV flags,#3
 *   CSEL flags,u,flags,EQ; ADRP u; STR flags,[u,#mode_offset]
 * Only the unlock LDRB is replaced. The mode=3 condition stays intact.
 * A different instruction order/control flow requires a new reviewed pattern. */
static bool match_mode_block(const char *data, int32_t off, uint8_t *reg,
                             bool *already_patched) {
    DecodedInst d[17];
    for (int i = 0; i < 17; ++i) d[i] = decode_at(data, off + i * 4);
    uint8_t u=d[0].rt, flags=d[1].rt, tmp=d[2].rt, one=d[3].rt;
    const uint8_t regs[] = {u, flags, tmp, one};
    for (unsigned i = 0; i < sizeof(regs); ++i) {
        /* These temporaries must not clobber the memset arguments X0/W1/W2. */
        if (regs[i] < 3 || regs[i] == 31) return false;
        for (unsigned j = 0; j < i; ++j)
            if (regs[i] == regs[j]) return false;
    }
    if (d[0].type != INST_ADRP || d[1].type != INST_LDRB_IMM ||
        d[2].type != INST_LDRB_IMM || d[1].imm != 3 || d[2].imm != 2 ||
        d[1].rn != d[2].rn || d[1].rn == u || d[1].rn == flags ||
        d[1].rn == 31 || d[3].raw != encode_movz_w(one, 1) ||
        d[4].raw != 0x2a1f03e1 || d[5].raw != encode_movz_w(2, 0x28))
        return false;

    bool patched = d[6].raw == encode_movz_w(u, 0);
    if (!patched && !(d[6].type == INST_LDRB_IMM && d[6].rt == u && d[6].rn == u))
        return false;
    if (d[7].raw != (0x2a000000u | ((uint32_t)tmp << 16) | ((uint32_t)flags << 5) | flags) ||
        d[8].type != INST_ADD_X_IMM || d[8].rt != tmp || d[8].rn != 31 ||
        d[8].shift != 0 || d[9].raw != (0x91001000u | ((uint32_t)tmp << 5)) ||
        d[10].raw != (0x7100001fu | ((uint32_t)u << 5)) ||
        d[11].raw != (0x1a800400u | ((uint32_t)one << 16) | ((uint32_t)one << 5) | u) ||
        d[12].raw != (0x7100001fu | ((uint32_t)flags << 5)) ||
        d[13].raw != encode_movz_w(flags, 3) ||
        d[14].raw != (0x1a800000u | ((uint32_t)flags << 16) | ((uint32_t)u << 5) | flags) ||
        d[15].type != INST_ADRP || d[15].rt != u ||
        d[16].type != INST_STR_W_IMM || d[16].rt != flags || d[16].rn != u)
        return false;
    *reg = u;
    *already_patched = patched;
    return true;
}

/* Search only executable sections of a bounded ARM64 PE32+ image. No assumption
 * that section RVAs equal raw file offsets is needed for this instruction patch. */
int32_t FindAvfPatch(const char *data, int32_t size, uint8_t *reg, bool *patched) {
    if (!data || !reg || !patched || size < 64 || data[0] != 'M' || data[1] != 'Z')
        return -1;
    uint32_t pe = read_instr(data, 0x3c);
    if (pe > (uint32_t)size - 24 || read_instr(data, (int32_t)pe) != 0x4550)
        return -1;
    uint32_t coff = read_instr(data, (int32_t)pe + 4);
    uint32_t sections = coff >> 16;
    uint32_t optional_size = read_instr(data, (int32_t)pe + 20) & 0xffff;
    if ((coff & 0xffff) != 0xaa64 || !sections || optional_size < 4 ||
        optional_size > (uint32_t)size - pe - 24)
        return -1;
    uint32_t table = pe + 24 + optional_size;
    if ((read_instr(data, (int32_t)pe + 24) & 0xffff) != 0x20b ||
        sections > ((uint32_t)size - table) / 40)
        return -1;
    int32_t found = -1;
    for (uint32_t s = 0; s < sections; ++s) {
        int32_t hdr = (int32_t)(table + s * 40);
        uint32_t bytes = read_instr(data, hdr + 16), raw = read_instr(data, hdr + 20);
        uint32_t attributes = read_instr(data, hdr + 36);
        if (raw > (uint32_t)size || bytes > (uint32_t)size - raw) return -1;
        if (!(attributes & 0x20000000) || bytes < 68 || (raw & 3)) continue;
        for (uint32_t i = raw; i <= raw + bytes - 68; i += 4) {
            if (!match_mode_block(data, (int32_t)i, reg, patched)) continue;
            if (found >= 0) return -1; /* Never pick the first of multiple candidates. */
            found = (int32_t)i + 24;
        }
    }
    return found;
}

bool PatchAvfBuffer(char *data, int32_t size) {
    AvfImageKind kind = ClassifyAvfImage(data, size);
    uint8_t reg = 0;
    bool patched = false;
    int32_t off = FindAvfPatch(data, size, &reg, &patched);
    if (off < 0) {
        printf("AVF: no unique supported BCC mode pattern in executable ARM64 PE sections.\n");
        return false;
    }
    if (patched) {
        printf("AVF: mode input at 0x%X already patched; no changes.\n", off);
        return true;
    }
    uint32_t original = read_instr(data, off);
    write_instr(data, off, encode_movz_w(reg, 0));
    if (kind == AVF_IMAGE_TEE_PATCHED && ClassifyAvfImage(data, size) != AVF_IMAGE_PATCHED) {
        write_instr(data, off, original);
        printf("AVF: output identity mismatch; reverted buffer change.\n");
        return false;
    }
    printf("AVF: 0x%X LDRB W%u -> MOV W%u,#0 (BCC mode input).\n", off, reg, reg);
    printf("AVF: TEE edits, global DevInfo, mode=3 and dummy fallback preserved.\n");
    return true;
}
