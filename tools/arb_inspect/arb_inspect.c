/* Read-only Qualcomm ELF / MBN v7 metadata inspector. No signature verification.
 * Layout reference: coreboot util/qualcomm/mbn_tools.py (Boot_Hdr), and
 * Qualcomm Secure Boot and Image Authentication technical overview.
 * Unsupported formats fail closed; never infer a version from arbitrary bytes.
 */
#define _FILE_OFFSET_BITS 64
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <inttypes.h>

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t le64(const unsigned char *p) {
    return le32(p) | (uint64_t)le32(p + 4) << 32;
}
static unsigned le16(const unsigned char *p) { return p[0] | (unsigned)p[1] << 8; }
static int read_at(FILE *f, uint64_t offset, void *buf, size_t n) {
    return offset <= INT64_MAX && n <= (uint64_t)INT64_MAX - offset &&
           fseeko(f, (off_t)offset, SEEK_SET) == 0 && fread(buf, 1, n, f) == n;
}
static const char *inspect(FILE *f) {
    unsigned char h[64], ph[56], m[40], common[24], meta[224];
    uint64_t phoff, off = 0, len = 0, total, metaoff;
    uint32_t qsize, osize, csize, swid, secondary, arb[2] = {0, 0};
    unsigned entsize, count, matches = 0, present[2] = {0, 0};
    struct stat st;
    if (fstat(fileno(f), &st) || (!S_ISREG(st.st_mode) && !S_ISBLK(st.st_mode)))
        return "NOT_FILE_OR_BLOCK_DEVICE";
    if (!read_at(f, 0, h, 16)) return "TRUNCATED_ELF";
    if (memcmp(h, "\177ELF", 4) || (h[4] != 1 && h[4] != 2) || h[5] != 1 || h[6] != 1)
        return "UNSUPPORTED_FORMAT";
    unsigned is64 = h[4] == 2;
    if (!read_at(f, 0, h, is64 ? 64 : 52)) return "TRUNCATED_ELF";
    phoff = is64 ? le64(h + 32) : le32(h + 28);
    entsize = le16(h + (is64 ? 54 : 42));
    count = le16(h + (is64 ? 56 : 44));
    if (entsize != (is64 ? 56 : 32) || !count || count > 1024 ||
        phoff > (uint64_t)INT64_MAX - (uint64_t)count * entsize)
        return "INVALID_PROGRAM_HEADERS";
    for (unsigned i = 0; i < count; i++) {
        if (!read_at(f, phoff + (uint64_t)i * entsize, ph, entsize))
            return "TRUNCATED_PROGRAM_HEADERS";
        uint32_t flags = le32(ph + (is64 ? 4 : 24));
        if (((flags >> 24) & 7) != 2) continue;
        matches++;
        off = is64 ? le64(ph + 8) : le32(ph + 4);
        len = is64 ? le64(ph + 32) : le32(ph + 16);
    }
    if (matches != 1) return "MISSING_OR_AMBIGUOUS_HASH_SEGMENT";
    if (len < sizeof(m) || len > INT64_MAX || off > (uint64_t)INT64_MAX - len ||
        (S_ISREG(st.st_mode) && off + len > (uint64_t)st.st_size) ||
        !read_at(f, off, m, sizeof(m))) return "TRUNCATED_HASH_SEGMENT";
    if (le32(m + 4) != 7) return "UNSUPPORTED_MBN_VERSION";
    csize = le32(m + 8); qsize = le32(m + 12); osize = le32(m + 16);
    if (csize != 24 || (qsize && qsize != 224) || (osize && osize != 224))
        return "UNSUPPORTED_METADATA_SIZE";
    total = 40ULL + csize + qsize + osize;
    for (unsigned i = 5; i < 10; i++) total += le32(m + i * 4);
    if (total > len || !read_at(f, off + total - 1, h, 1)) return "TRUNCATED_MBN";
    if (!read_at(f, off + 40, common, sizeof(common))) return "TRUNCATED_METADATA";
    if (le32(common) != 0 || le32(common + 4) != 0) return "UNSUPPORTED_COMMON_METADATA";
    swid = le32(common + 8); secondary = le32(common + 12);
    metaoff = off + 40 + csize;
    for (unsigned i = 0; i < 2; i++) {
        uint32_t size = i ? osize : qsize;
        if (!size) continue;
        if (!read_at(f, metaoff, meta, size)) return "TRUNCATED_METADATA";
        metaoff += size;
        /* OEM metadata versions 2.0 and 3.0 share this ARB field. */
        if ((le32(meta) != 2 && le32(meta) != 3) || le32(meta + 4) != 0)
            return "UNSUPPORTED_AUTHORITY_METADATA";
        present[i] = 1;
        arb[i] = le32(meta + 8);
    }
    if (!present[0] && !present[1]) return "NO_ARB_METADATA";
    printf("STATUS=ok\nMBN_VERSION=7\nSW_ID=%" PRIu32 "\nSECONDARY_SW_ID=%" PRIu32 "\n", swid, secondary);
    for (unsigned i = 0; i < 2; i++) {
        printf("%s_ARB=", i ? "OEM" : "QTI");
        if (present[i]) printf("%" PRIu32, arb[i]);
        else printf("absent");
        putchar('\n');
    }
    return NULL;
}
int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "Usage: arb_inspect IMAGE_OR_PARTITION\n"); return 2; }
    /* Precheck avoids blocking on pipes/devices supplied as image paths. */
    struct stat st;
    if (stat(argv[1], &st) || (!S_ISREG(st.st_mode) && !S_ISBLK(st.st_mode))) {
        puts("STATUS=error\nERROR=NOT_FILE_OR_BLOCK_DEVICE"); return 1;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { puts("STATUS=error\nERROR=OPEN_FAILED"); return 1; }
    const char *error = inspect(f);
    fclose(f);
    if (error) { printf("STATUS=error\nERROR=%s\n", error); return 1; }
    return 0;
}
