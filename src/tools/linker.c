#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define MAX_CODE 262144
#define MAX_DATA 65536
#define MAX_OBJS 32

typedef struct {
    uint8_t code[MAX_CODE];
    int code_len;
    uint8_t data[MAX_DATA];
    int data_len;
    int bss_len;
} Object;

static Object objs[MAX_OBJS];
static int obj_count = 0;

static uint8_t final_code[MAX_CODE];
static int final_code_len = 0;
static uint8_t final_data[MAX_DATA];
static int final_data_len = 0;
static int final_bss_len = 0;
void write_elf(const char *output) {
    FILE *f = fopen(output, "wb"); if (!f) return;
    
    // ELF Header (64 bytes) - write byte by byte to avoid pointer issues
    uint8_t elf[64] = {0};
    elf[0] = 0x7F; elf[1] = 'E'; elf[2] = 'L'; elf[3] = 'F';
    elf[4] = 2; elf[5] = 1; elf[6] = 1; elf[7] = 0;
    elf[8] = 0; elf[9] = 0; elf[10] = 0; elf[11] = 0;
    elf[12] = 0; elf[13] = 0; elf[14] = 0; elf[15] = 0;
    elf[16] = 2; elf[17] = 0;           // e_type = ET_EXEC (2)
    elf[18] = 0x3E; elf[19] = 0;       // e_machine = EM_X86_64 (0x3E)
    elf[20] = 1; elf[21] = 0; elf[21] = 0; elf[23] = 0; // e_version = 1
    // e_entry = 0x400178 (offset 0x18)
    elf[24] = 0x78; elf[25] = 0x01; elf[26] = 0x40; elf[27] = 0x00;
    elf[28] = 0x00; elf[29] = 0x00; elf[30] = 0x00; elf[31] = 0x00;
    // e_phoff = 64 (offset 0x20)
    elf[32] = 0x40; elf[33] = 0x00; elf[33] = 0x00; elf[34] = 0x00;
    elf[36] = 0x00; elf[37] = 0x00; elf[38] = 0x00; elf[39] = 0x00;
    // e_shoff = 0 (offset 0x28)
    elf[40] = 0; elf[41] = 0; elf[42] = 0; elf[43] = 0;
    elf[44] = 0; elf[45] = 0; elf[46] = 0; elf[47] = 0;
    // e_flags = 0 (offset 0x30)
    elf[48] = 0; elf[49] = 0; elf[50] = 0; elf[51] = 0;
    // e_ehsize = 64 (offset 0x34)
    elf[52] = 64; elf[53] = 0;
    // e_phentsize = 56 (offset 0x36)
    elf[54] = 56; elf[55] = 0;
    // e_phnum = 1 (offset 0x38)
    elf[56] = 1; elf[57] = 0;
    // e_shentsize = 0 (offset 0x3A)
    elf[58] = 0; elf[59] = 0;
    // e_shnum = 0 (offset 0x3C)
    elf[60] = 0; elf[61] = 0;
    // e_shstrndx = 0 (offset 0x3E)
    elf[62] = 0; elf[63] = 0;
    
    // Program Header (56 bytes)
    uint8_t phdr[56] = {0};
    phdr[0] = 1; phdr[1] = 0; phdr[2] = 0; phdr[3] = 0; // p_type = PT_LOAD
    phdr[4] = 7; phdr[5] = 0; phdr[6] = 0; phdr[7] = 0; // p_flags = 7 (R+W+X)
    phdr[8] = 0; phdr[9] = 0; phdr[10] = 0; phdr[11] = 0; // p_offset = 0
    phdr[16] = 0x00; phdr[17] = 0x01; phdr[18] = 0x40; phdr[19] = 0x00; 
    phdr[20] = 0x00; phdr[21] = 0x00; phdr[22] = 0x00; phdr[23] = 0x00; // p_vaddr = 0x400100
    phdr[24] = 0x00; phdr[25] = 0x01; phdr[26] = 0x40; phdr[27] = 0x00;
    phdr[28] = 0x00; phdr[27] = 0x00; phdr[28] = 0x00; phdr[23] = 0x00; // p_paddr = 0x400100
    // Fix p_paddr
    phdr[24] = 0x00; phdr[25] = 0x01; phdr[26] = 0x40; phdr[27] = 0x00;
    phdr[28] = 0x00; phdr[29] = 0x00; phdr[29] = 0x00; phdr[31] = 0x00;
    // p_filesz
    *(uint64_t*)(phdr+32) = final_code_len;
    // p_memsz
    *(uint64_t*)(phdr+40) = final_code_len;
    // p_align = 0x1000
    phdr[48] = 0x00; phdr[49] = 0x10; phdr[50] = 0x00; phdr[51] = 0x00;
    phdr[52] = 0x00; phdr[51] = 0x00; phdr[52] = 0x00; phdr[53] = 0x00;
    
    fwrite(elf, 1, 64, f); 
    fwrite(phdr, 1, 56, f);
    
    // Pad to code start (0x1000 - 64 - 56 = 0xF00)
    uint8_t pad[0x1000 - 120] = {0};
    fwrite(pad, 1, 0x1000 - 120, f);
    
    // Code and data
    fwrite(final_code, 1, final_code_len, f);
    fwrite(final_data, 1, final_data_len, f);
    fclose(f);
}

void read_object(const char *path, Object *o) {
    FILE *f = fopen(path, "rb"); if (!f) { printf("Can't read %s\n", path); return; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *buf = malloc(sz); fread(buf, 1, sz, f); fclose(f);
    
    if (sz > 120) {
        o->code_len = sz - 120;
        memcpy(o->code, buf + 120, o->code_len);
    }
    free(buf);
}

int main(int argc, char **argv) {
    if (argc < 4) { printf("Usage: linker -o output file1.bin file2.bin ...\n"); return 1; }
    char *output = NULL;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) output = argv[++i];
    }
    if (!output) { printf("Error: -o output required\n"); return 1; }
    
    obj_count = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0) { i++; continue; }
        if (argv[i][0] == '-') continue;
        if (obj_count < MAX_OBJS) {
            read_object(argv[i], &objs[obj_count]);
            obj_count++;
        }
    }
    
    final_code_len = 0; final_data_len = 0; final_bss_len = 0;
    for (int i = 0; i < obj_count; i++) {
        memcpy(final_code + final_code_len, objs[i].code, objs[i].code_len);
        final_code_len += objs[i].code_len;
        memcpy(final_data + final_data_len, objs[i].data, objs[i].data_len);
        final_data_len += objs[i].data_len;
        final_bss_len += objs[i].bss_len;
    }
    
    write_elf(output);
    printf("Linked %s (%d code bytes)\n", output, final_code_len);
    return 0;
}