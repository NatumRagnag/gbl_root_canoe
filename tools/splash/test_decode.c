/* Host verification using the exact LZMA SDK and pixel scaler linked in BDS. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "LzmaDec.h"
typedef uint8_t UINT8;
typedef uint32_t UINT32;
typedef size_t UINTN;
#define STATIC static
#define VOID void
#define IN
#define OUT
#define CONST const
#include "SuperFbSplashPixels.h"
static size_t scratch_used;
static void *alloc_mem(ISzAllocPtr p, size_t size) {
    (void)p;
    if (size > 65536 - scratch_used) return NULL;
    scratch_used += size;
    return malloc(size);
}
static void free_mem(ISzAllocPtr p, void *addr) { (void)p; free(addr); }
static uint32_t u32(const uint8_t *p) {
    return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static uint32_t crc32(const uint8_t *p, size_t n) {
    uint32_t c = ~0u;
    for (size_t i=0;i<n;i++) {
        c ^= p[i];
        for (int j=0;j<8;j++) c=(c>>1)^((0u-(c&1u))&0xedb88320u);
    }
    return ~c;
}
int main(int argc, char **argv) {
    if (argc < 2 || argc > 3) return 2;
    FILE *f=fopen(argv[1],"rb"); if (!f) return 1;
    fseek(f,0,SEEK_END); long length=ftell(f); rewind(f);
    if (length<45 || length>3*1024*1024) { fclose(f); return 1; }
    uint8_t *b=malloc((size_t)length);
    if (!b || fread(b,1,(size_t)length,f)!=(size_t)length) return 1;
    fclose(f);
    if (memcmp(b,"SFBSPL03",8) || u32(b+8)!=890 || u32(b+12)!=1920 ||
        u32(b+16)!=(uint32_t)length-32 || u32(b+20)!=SFB_ART_BYTES || u32(b+28) ||
        b[32]!=0x5d || u32(b+33)>16*1024*1024 || u32(b+37)!=SFB_ART_BYTES || u32(b+41)) {
        free(b); return 1;
    }
    uint8_t *pixels=calloc(1,SFB_ART_BYTES);
    uint8_t *screen=calloc(1,SFB_SCREEN_WIDTH*SFB_SCREEN_HEIGHT*4);
    if (!pixels || !screen) return 1;
    SizeT size=SFB_ART_BYTES, packed=(size_t)length-45;
    ELzmaStatus status;
    ISzAlloc allocator={alloc_mem,free_mem};
    int result=LzmaDecode(pixels,&size,b+45,&packed,b+32,5,LZMA_FINISH_END,&status,&allocator);
    if (result!=SZ_OK || size!=SFB_ART_BYTES || crc32(pixels,size)!=u32(b+24)) {
        free(screen);free(pixels);free(b);return 1;
    }
    SfbScaleSplash(pixels,screen);
    // Black border and exact interpolation endpoints, checked independently.
    size_t top=(SFB_SCREEN_HEIGHT-SFB_DRAW_HEIGHT)/2;
    for(size_t y=0;y<SFB_SCREEN_HEIGHT;y++) for(size_t x=0;x<SFB_SCREEN_WIDTH;x++) {
        if (y<top || y>=top+SFB_DRAW_HEIGHT || x<48 || x>=48+SFB_DRAW_WIDTH) {
            for(size_t c=0;c<4;c++) if(screen[(y*SFB_SCREEN_WIDTH+x)*4+c]) return 1;
        }
    }
    if (memcmp(screen+(top*SFB_SCREEN_WIDTH+48)*4,pixels,3)) return 1;
    if (argc==3) {
        f=fopen(argv[2],"wb");if(!f)return 1;
        if(fwrite(screen,4,SFB_SCREEN_WIDTH*SFB_SCREEN_HEIGHT,f)!=SFB_SCREEN_WIDTH*SFB_SCREEN_HEIGHT)return 1;
        fclose(f);
    }
    printf("PASS %s: CRC32 %08x, scratch %zu, 1200x2608 render\n",argv[1],u32(b+24),scratch_used);
    free(screen);free(pixels);free(b);return 0;
}
