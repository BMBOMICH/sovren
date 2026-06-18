#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>

#define MAX_LABELS 4096
#define MAX_CODE 262144
#define MAX_SECTIONS 8

static uint8_t code[MAX_CODE];
static int code_len = 0;

typedef struct {
    char name[64];
    int address;
    int defined;
    int section;
} Label;

static Label labels[MAX_LABELS];
static int label_count = 0;

typedef struct {
    int code_offset;
    char target[128];
    int is_call;
} Relocation;

static Relocation relocations[MAX_LABELS];
static int reloc_count = 0;

typedef struct {
    char name[64];
    int start_offset;
    int size;
    int align;
    int is_data;
    int is_bss;
} Section;

static Section sections[MAX_SECTIONS];
static int section_count = 0;
static int current_section_idx = -1;

static uint8_t data_section[65536];
static int data_len = 0;
static uint8_t bss_section[65536];
static int bss_len = 0;

void *emit_ptr() { return code + code_len; }
void emit(int b) { code[code_len++] = b; }
void emit4(uint32_t v) { emit(v&0xFF); emit((v>>8)&0xFF); emit((v>>16)&0xFF); emit((v>>24)&0xFF); }
void emit8(uint64_t v) { for(int i=0;i<8;i++) emit((v>>(i*8))&0xFF); }

void emit_mov_reg_imm64(int reg, uint64_t imm) {
    emit(0x48 | ((reg>>3)&1));
    emit(0xB8 | (reg&7));
    emit8(imm);
}

void emit_mov_reg_reg(int dst, int src) {
    emit(0x48 | ((dst>>3)&1) | ((src>>2)&2));
    emit(0x89);
    emit(0xC0 | ((src&7)<<3) | (dst&7));
}

void emit_add_reg_reg(int dst, int src) {
    emit(0x48 | ((dst>>3)&1) | ((src>>2)&2));
    emit(0x01);
    emit(0xC0 | ((src&7)<<3) | (dst&7));
}

void emit_sub_reg_reg(int dst, int src) {
    emit(0x48 | ((dst>>3)&1) | ((src>>2)&2));
    emit(0x29);
    emit(0xC0 | ((src&7)<<3) | (dst&7));
}

void emit_ret() { emit(0xC3); }

void emit_call_rel(int32_t rel) { emit(0xE8); emit4(rel); }
void emit_jmp_rel(int32_t rel) { emit(0xE9); emit4(rel); }

void emit_call_label(const char *label) {
    int code_off = code_len;
    emit(0xE8); emit(0); emit(0); emit(0); emit(0);
    if (reloc_count < MAX_LABELS) {
        relocations[reloc_count].code_offset = code_off;
        strcpy(relocations[reloc_count].target, label);
        relocations[reloc_count].is_call = 1;
        reloc_count++;
    }
}

void emit_jmp_label(const char *label) {
    int code_off = code_len;
    emit(0xE9); emit(0); emit(0); emit(0); emit(0);
    if (reloc_count < MAX_LABELS) {
        relocations[reloc_count].code_offset = code_off;
        strcpy(relocations[reloc_count].target, label);
        relocations[reloc_count].is_call = 0;
        reloc_count++;
    }
}

int find_label(const char *name) {
    for (int i = 0; i < label_count; i++) if (strcmp(labels[i].name, name) == 0) return i;
    return -1;
}

int add_label(const char *name, int section) {
    if (label_count >= MAX_LABELS) return -1;
    strcpy(labels[label_count].name, name);
    labels[label_count].address = (section == 0) ? code_len : ((section == 1) ? data_len : bss_len);
    labels[label_count].defined = 1;
    labels[label_count].section = section;
    return label_count++;
}

int get_or_create_label(const char *name, int section) {
    int idx = find_label(name);
    if (idx >= 0) return idx;
    if (label_count >= MAX_LABELS) return -1;
    strcpy(labels[label_count].name, name);
    labels[label_count].address = 0;
    labels[label_count].defined = 0;
    labels[label_count].section = section;
    return label_count++;
}

int get_reg(const char *r) {
    if (strcmp(r, "rax")==0) return 0;  if (strcmp(r, "rcx")==0) return 1;
    if (strcmp(r, "rdx")==0) return 2;  if (strcmp(r, "rbx")==0) return 3;
    if (strcmp(r, "rsp")==0) return 4;  if (strcmp(r, "rbp")==0) return 5;
    if (strcmp(r, "rsi")==0) return 6;  if (strcmp(r, "rdi")==0) return 7;
    if (strcmp(r, "r8")==0) return 8;  if (strcmp(r, "r9")==0) return 9;
    if (strcmp(r, "r10")==0) return 10; if (strcmp(r, "r11")==0) return 11;
    if (strcmp(r, "r12")==0) return 12; if (strcmp(r, "r13")==0) return 13;
    if (strcmp(r, "r14")==0) return 14; if (strcmp(r, "r15")==0) return 15;
    if (strcmp(r, "eax")==0) return 0;  if (strcmp(r, "ecx")==0) return 1;
    if (strcmp(r, "edx")==0) return 2;  if (strcmp(r, "ebx")==0) return 3;
    if (strcmp(r, "esp")==0) return 4;  if (strcmp(r, "ebp")==0) return 5;
    if (strcmp(r, "esi")==0) return 6;  if (strcmp(r, "edi")==0) return 7;
    if (strcmp(r, "r8d")==0) return 8;  if (strcmp(r, "r9d")==0) return 9;
    return -1;
}

void write_elf(const char *output, int num_sections) {
    FILE *f = fopen(output, "wb"); if (!f) return;
    uint8_t elf[64]={0}; memcpy(elf, "\x7FELF", 4);
    elf[4]=2; elf[5]=1; elf[6]=1; elf[7]=0;
    *(uint16_t*)(elf+16)=2; elf[18]=0x3E; *(uint32_t*)(elf+20)=1;
    *(uint64_t*)(elf+24)=0x400100; *(uint64_t*)(elf+32)=64;
    uint8_t phdr[56]={0};
    *(uint32_t*)(phdr+0)=1; *(uint32_t*)(phdr+4)=5;
    *(uint64_t*)(phdr+8)=0x400100; *(uint64_t*)(phdr+16)=0x400100;
    *(uint64_t*)(phdr+24)=0x1000; *(uint64_t*)(phdr+32)=0x1000;
    *(uint64_t*)(phdr+40)=7; *(uint64_t*)(phdr+48)=0x1000;
    fwrite(elf, 1, 64, f); fwrite(phdr, 1, 56, f);
    fwrite(code, 1, code_len, f);
    if (data_len > 0) fwrite(data_section, 1, data_len, f);
    fclose(f);
}

void trim(char *s) {
    char *start=s; while(*start && isspace(*start)) start++;
    char *end=start+strlen(start)-1; while(end>start && isspace(*end)) *end--=0;
    memmove(s, start, end-start+1); s[end-start+1]=0;
}

int parse_imm(const char *s) {
    if (strncmp(s, "0x", 2) == 0) return strtol(s+2, NULL, 16);
    if (strncmp(s, "0b", 2) == 0) return strtol(s+2, NULL, 2);
    return strtol(s, NULL, 10);
}

int parse_mem_operand(const char *s, int *base, int *index, int *scale, int32_t *disp) {
    char buf[256];
    strncpy(buf, s, 255); buf[255]=0;
    trim(buf);
    if (buf[0] != '[') return 0;
    buf[strlen(buf)-1] = 0;
    char *inner = buf + 1;
    
    *base = -1; *index = -1; *scale = 1; *disp = 0;
    
    char *plus = strchr(inner, '+');
    if (plus) *plus = 0;
    
    trim(inner);
    *base = get_reg(inner);
    if (*base < 0) *disp = parse_imm(inner);
    
    if (plus) {
        char *part2 = plus + 1;
        char *star = strchr(part2, '*');
        if (star) {
            *star = 0;
            trim(part2);
            *index = get_reg(part2);
            if (*index < 0) return 0;
            char *scale_str = star + 1;
            *scale = parse_imm(scale_str);
        } else {
            trim(part2);
            *index = get_reg(part2);
            if (*index < 0) *disp = parse_imm(part2);
        }
    }
    return 1;
}

void db_data(const char *s) {
    char *p = strtok((char*)s, ",");
    while (p) {
        trim(p);
        if (*p == '\'' && p[strlen(p)-1] == '\'') {
            p[strlen(p)-1] = 0;
            data_section[data_len++] = p[1];
        } else {
            data_section[data_len++] = parse_imm(p) & 0xFF;
        }
        p = strtok(NULL, ",");
    }
}

void dq_data(const char *s) {
    char *p = strtok((char*)s, ",");
    while (p) {
        trim(p);
        uint64_t val = strtoull(p, NULL, 0);
        for (int i = 0; i < 8; i++) {
            data_section[data_len++] = (val >> (i*8)) & 0xFF;
        }
        p = strtok(NULL, ",");
    }
}

void resb_data(const char *s) {
    int count = parse_imm(s);
    data_len += count;
}

int main(int argc, char **argv) {
    if (argc < 3) { printf("Usage: assembler <input> <output>\n"); return 1; }
    FILE *f = fopen(argv[1], "r"); if (!f) { printf("Error reading %s\n", argv[1]); return 1; }
    fseek(f, 0, SEEK_END); long sz=ftell(f); fseek(f, 0, SEEK_SET);
    char *src=malloc(sz+1); fread(src, 1, sz, f); src[sz]=0; fclose(f);
    
    char *lines[4096]; int line_count=0;
    char *line = strtok(src, "\n");
    while (line && line_count<4096) {
        trim(line);
        if (*line && *line!=';') { char *t=strdup(line); trim(t); lines[line_count++]=t; }
        line = strtok(NULL, "\n");
    }
    
    code_len=0; reloc_count=0; data_len=0; bss_len=0;
    current_section_idx = 0;
    
    // Add .text section
    sections[section_count].name[0]='.'; sections[section_count].name[1]='t';
    sections[section_count].name[2]='e'; sections[section_count].name[3]='x'; sections[section_count].name[4]='t'; sections[section_count].name[5]=0;
    sections[section_count].start_offset = 0;
    sections[section_count].size = 0;
    sections[section_count].align = 16;
    sections[section_count].is_data = 0;
    sections[section_count].is_bss = 0;
    section_count++;
    
    // Pass 1: collect labels and section directives
    for (int i=0; i<line_count; i++) {
        char *start = lines[i];
        char *colon = strchr(start, ':');
        if (colon) {
            *colon=0; trim(start); if(*start) add_label(start, current_section_idx);
            continue;
        }
        
        if (strncmp(start, "section ", 8) == 0) {
            char *sec_name = start + 8;
            trim(sec_name);
            if (strcmp(sec_name, ".data") == 0) {
                current_section_idx = 1;
                sections[section_count].name[0]='.'; sections[section_count].name[1]='d';
                sections[section_count].name[2]='a'; sections[section_count].name[3]='t'; sections[section_count].name[4]='a'; sections[section_count].name[5]=0;
                sections[section_count].start_offset = data_len;
                sections[section_count].size = 0;
                sections[section_count].align = 16;
                sections[section_count].is_data = 1;
                sections[section_count].is_bss = 0;
                section_count++;
            } else if (strcmp(sec_name, ".bss") == 0) {
                current_section_idx = 2;
                sections[section_count].name[0]='.'; sections[section_count].name[1]='b';
                sections[section_count].name[2]='s'; sections[section_count].name[3]='s'; sections[section_count].name[4]=0;
                sections[section_count].start_offset = bss_len;
                sections[section_count].size = 0;
                sections[section_count].align = 16;
                sections[section_count].is_data = 0;
                sections[section_count].is_bss = 1;
                section_count++;
            } else if (strcmp(sec_name, ".text") == 0) {
                current_section_idx = 0;
            }
            continue;
        }
    }
    
    // Pass 2: emit code/data
    for (int i=0; i<line_count; i++) {
        char *start = lines[i];
        char *colon = strchr(start, ':');
        if (colon) {
            *colon=0; trim(start); if(*start) add_label(start, current_section_idx);
            continue;
        }
        
        if (strncmp(start, "section ", 8) == 0) {
            char *sec_name = start + 8;
            trim(sec_name);
            if (strcmp(sec_name, ".data") == 0) current_section_idx = 1;
            else if (strcmp(sec_name, ".bss") == 0) current_section_idx = 2;
            else current_section_idx = 0;
            continue;
        }
        
        char *op = strtok(start, " \t");
        if (!op) continue;
        char *a1 = strtok(NULL, ",");
        char *a2 = strtok(NULL, ",");
        char *a3 = strtok(NULL, ",");
        if (a1) trim(a1); if (a2) trim(a2); if (a3) trim(a3);
        
        if (current_section_idx == 1) {
            if (strcmp(op, "db") == 0 && a1) db_data(a1);
            else if (strcmp(op, "dq") == 0 && a1) dq_data(a1);
            else if (strcmp(op, "resb") == 0 && a1) resb_data(a1);
        } else if (current_section_idx == 2) {
            if (strcmp(op, "resb") == 0 && a1) bss_len += parse_imm(a1);
        } else {
            if (strcmp(op,"mov")==0 && a1 && a2) {
                int dst=get_reg(a1);
                if (dst >= 0) {
                    int src=get_reg(a2);
                    if (src >= 0) emit_mov_reg_reg(dst, src);
                    else if (a2[0]=='[') {
                        int base, index, scale; int32_t disp;
                        if (parse_mem_operand(a2, &base, &index, &scale, &disp)) {
                            // simplified for now
                        } else {
                            emit_mov_reg_imm64(dst, strtoull(a2,NULL,0));
                        }
                    } else {
                        emit_mov_reg_imm64(dst, strtoull(a2,NULL,0));
                    }
                }
            }
            else if (strcmp(op,"add")==0 && a1 && a2) {
                int dst=get_reg(a1); int src=get_reg(a2);
                if (dst>=0 && src>=0) emit_add_reg_reg(dst, src);
            }
            else if (strcmp(op,"sub")==0 && a1 && a2) {
                int dst=get_reg(a1); int src=get_reg(a2);
                if (dst>=0 && src>=0) emit_sub_reg_reg(dst, src);
            }
            else if (strcmp(op,"ret")==0) emit_ret();
            else if (strcmp(op,"call")==0 && a1) emit_call_label(a1);
            else if (strcmp(op,"jmp")==0 && a1) emit_jmp_label(a1);
        }
    }
    
    // Resolve relocations
    for (int i=0; i<reloc_count; i++) {
        int idx = find_label(relocations[i].target);
        if (idx >= 0 && labels[idx].defined) {
            int32_t rel = labels[idx].address - (relocations[i].code_offset + 5);
            code[relocations[i].code_offset + 1] = rel & 0xFF;
            code[relocations[i].code_offset + 2] = (rel >> 8) & 0xFF;
            code[relocations[i].code_offset + 3] = (rel >> 16) & 0xFF;
            code[relocations[i].code_offset + 4] = (rel >> 24) & 0xFF;
        } else {
            printf("Warning: unresolved label %s\n", relocations[i].target);
        }
    }
    
    write_elf(argv[2], section_count);
    printf("Assembled %d code bytes, %d data bytes\n", code_len, data_len);
    for (int i=0;i<line_count;i++) free(lines[i]); free(src);
    return 0;
}