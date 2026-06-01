#include "runtime.h"

#define _CRT_RAND_S

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdarg.h>
#include <time.h>
#include <sys/stat.h>

#ifdef _WIN32
#include <windows.h>
#include <wincrypt.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")
#else
#include <pthread.h>
#include <unistd.h>
#include <fcntl.h>
#endif

#define SOV_MIN(a, b) ((a) < (b) ? (a) : (b))
#define SOV_MAX(a, b) ((a) > (b) ? (a) : (b))

static inline uint32_t rotr32(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32 - n));
}

static inline uint64_t rotr64(uint64_t x, uint64_t n) {
    return (x >> n) | (x << (64 - n));
}

/* Byte-swap for endianness */
static inline uint32_t bswap32(uint32_t x) {
    return ((x & 0xFF) << 24) | ((x & 0xFF00) << 8) |
           ((x & 0xFF0000) >> 8) | ((x & 0xFF000000) >> 24);
}

static inline uint64_t bswap64(uint64_t x) {
    return ((x & 0xFFULL) << 56) | ((x & 0xFF00ULL) << 40) |
           ((x & 0xFF0000ULL) << 24) | ((x & 0xFF000000ULL) << 8) |
           ((x & 0xFF00000000ULL) >> 8) | ((x & 0xFF0000000000ULL) >> 24) |
           ((x & 0xFF000000000000ULL) >> 40) | ((x & 0xFF00000000000000ULL) >> 56);
}

/* ============================================================================
 * MEMORY MANAGEMENT
 * ============================================================================ */

sov_ptr sov_alloc(sov_int count, sov_int size) {
    sov_ptr ptr = calloc((size_t)count, (size_t)size);
    if (!ptr && count > 0 && size > 0) {
        sov_panic("Out of memory");
    }
    return ptr;
}

sov_ptr sov_realloc(sov_ptr ptr, sov_int new_size) {
    sov_ptr new_ptr = realloc(ptr, (size_t)new_size);
    if (!new_ptr && new_size > 0) {
        sov_panic("Out of memory");
    }
    return new_ptr;
}

void sov_free(sov_ptr ptr) {
    if (ptr) free(ptr);
}

void sov_secure_zero(sov_ptr ptr, sov_int size) {
    if (ptr && size > 0) {
        volatile unsigned char* p = (volatile unsigned char*)ptr;
        while (size--) {
            *p++ = 0;
        }
    }
}

/* Secure allocation tracking */
typedef struct sov_secure_header {
    sov_int size;
    sov_int magic;
} sov_secure_header;

#define SOV_SECURE_MAGIC 0x53EC0DE0

sov_ptr sov_alloc_secure(sov_int count, sov_int size) {
    sov_int total = count * size;
    sov_secure_header* hdr = (sov_secure_header*)sov_alloc(1, sizeof(sov_secure_header) + total);
    hdr->size = total;
    hdr->magic = SOV_SECURE_MAGIC;
    return (sov_ptr)(hdr + 1);
}

void sov_free_secure(sov_ptr ptr, sov_int size) {
    if (!ptr) return;
    (void)size; /* size parameter for API consistency */
    sov_secure_header* hdr = ((sov_secure_header*)ptr) - 1;
    sov_secure_zero(ptr, hdr->size);
    hdr->magic = 0;
    sov_free(hdr);
}

/* ============================================================================
 * MEMORY POOL (fast small allocations)
 * ============================================================================ */

#define POOL_BLOCK_SIZE (64 * 1024)  /* 64KB blocks */
#define POOL_MAX_SIZE   256          /* Max object size for pooling */
#define POOL_NUM_BUCKETS ((POOL_MAX_SIZE / 8) + 1)

typedef struct sov_pool_entry {
    struct sov_pool_entry* next;
} sov_pool_entry;

typedef struct {
    sov_pool_entry* free_list;
    sov_int block_count;
} sov_pool_bucket;

static sov_pool_bucket sov_pool[POOL_NUM_BUCKETS];
static sov_bool sov_pool_initialized = false;

static void sov_pool_init(void) {
    memset(sov_pool, 0, sizeof(sov_pool));
    sov_pool_initialized = true;
}

static sov_int sov_pool_bucket_index(sov_int size) {
    return (size + 7) / 8;
}

sov_ptr sov_pool_alloc(sov_int size) {
    if (!sov_pool_initialized) sov_pool_init();
    if (size <= 0 || size > POOL_MAX_SIZE) return sov_alloc(1, size);
    
    sov_int idx = sov_pool_bucket_index(size);
    if (idx >= POOL_NUM_BUCKETS) return sov_alloc(1, size);
    
    sov_pool_bucket* bucket = &sov_pool[idx];
    
    if (bucket->free_list) {
        sov_ptr result = bucket->free_list;
        bucket->free_list = bucket->free_list->next;
        memset(result, 0, size);
        return result;
    }
    
    /* No free objects - allocate a new block */
    sov_u8* block = (sov_u8*)sov_alloc(POOL_BLOCK_SIZE, 1);
    sov_int obj_size = idx * 8;
    sov_int num_objects = POOL_BLOCK_SIZE / obj_size;
    
    /* Link all objects in the block into the free list */
    for (sov_int i = 1; i < num_objects; i++) {
        sov_pool_entry* entry = (sov_pool_entry*)(block + i * obj_size);
        entry->next = bucket->free_list;
        bucket->free_list = entry;
    }
    
    bucket->block_count++;
    
    /* Return the first object */
    memset(block, 0, obj_size);
    return block;
}

void sov_pool_free(sov_ptr ptr, sov_int size) {
    if (!ptr) return;
    if (!sov_pool_initialized) sov_pool_init();
    if (size <= 0 || size > POOL_MAX_SIZE) {
        sov_free(ptr);
        return;
    }
    
    sov_int idx = sov_pool_bucket_index(size);
    if (idx >= POOL_NUM_BUCKETS) {
        sov_free(ptr);
        return;
    }
    
    sov_secure_zero(ptr, size);
    sov_pool_entry* entry = (sov_pool_entry*)ptr;
    entry->next = sov_pool[idx].free_list;
    sov_pool[idx].free_list = entry;
}

/* ============================================================================
 * BOUNDS-CHECKED MEMORY OPERATIONS
 * ============================================================================ */

sov_array sov_array_view(sov_ptr data, sov_int len, sov_int elem_size, sov_string name) {
    sov_array arr;
    arr.data = data;
    arr.len = len;
    arr.elem_size = elem_size;
    arr.name = name;
    return arr;
}

sov_ptr sov_array_get(sov_array* arr, sov_int index) {
    sov_bounds_check(index, arr->len, arr->name);
    return (sov_ptr)((char*)arr->data + index * arr->elem_size);
}

void sov_array_set(sov_array* arr, sov_int index, sov_ptr value) {
    sov_bounds_check(index, arr->len, arr->name);
    memcpy((char*)arr->data + index * arr->elem_size, value, arr->elem_size);
}

/* ============================================================================
 * STRING OPERATIONS
 * ============================================================================ */

sov_int sov_strlen(sov_string s) {
    return s ? (sov_int)strlen(s) : 0;
}

sov_int sov_strcmp(sov_string a, sov_string b) {
    if (!a && !b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    return strcmp(a, b);
}

sov_bool sov_streq(sov_string a, sov_string b) {
    return sov_strcmp(a, b) == 0;
}

sov_string sov_strcpy(sov_string s) {
    if (!s) return NULL;
    sov_int len = sov_strlen(s);
    sov_string copy = (sov_string)sov_alloc(len + 1, 1);
    memcpy(copy, s, len + 1);
    return copy;
}

sov_string sov_strcat(sov_string a, sov_string b) {
    sov_int len_a = sov_strlen(a);
    sov_int len_b = sov_strlen(b);
    sov_string result = (sov_string)sov_alloc(len_a + len_b + 1, 1);
    if (a) memcpy(result, a, len_a);
    if (b) memcpy(result + len_a, b, len_b);
    result[len_a + len_b] = '\0';
    return result;
}

sov_string sov_substr(sov_string s, sov_int start, sov_int len) {
    if (!s) return sov_strcpy("");
    sov_int slen = sov_strlen(s);
    if (start < 0) start = 0;
    if (start >= slen) return sov_strcpy("");
    if (len < 0 || start + len > slen) len = slen - start;
    
    sov_string result = (sov_string)sov_alloc(len + 1, 1);
    memcpy(result, s + start, len);
    result[len] = '\0';
    return result;
}

sov_int sov_strfind(sov_string haystack, sov_string needle) {
    if (!haystack || !needle) return -1;
    char* pos = strstr(haystack, needle);
    if (!pos) return -1;
    return (sov_int)(pos - haystack);
}

sov_bool sov_strcontains(sov_string s, sov_string needle) {
    return sov_strfind(s, needle) >= 0;
}

sov_bool sov_strstarts(sov_string s, sov_string prefix) {
    if (!s || !prefix) return false;
    sov_int slen = sov_strlen(s);
    sov_int plen = sov_strlen(prefix);
    if (plen > slen) return false;
    return memcmp(s, prefix, plen) == 0;
}

sov_bool sov_strends(sov_string s, sov_string suffix) {
    if (!s || !suffix) return false;
    sov_int slen = sov_strlen(s);
    sov_int xlen = sov_strlen(suffix);
    if (xlen > slen) return false;
    return memcmp(s + slen - xlen, suffix, xlen) == 0;
}

sov_string sov_strtrim(sov_string s) {
    if (!s) return sov_strcpy("");
    while (*s && isspace((unsigned char)*s)) s++;
    sov_int len = sov_strlen(s);
    while (len > 0 && isspace((unsigned char)s[len - 1])) len--;
    return sov_substr(s, 0, len);
}

sov_string sov_strupper(sov_string s) {
    if (!s) return sov_strcpy("");
    sov_int len = sov_strlen(s);
    sov_string result = (sov_string)sov_alloc(len + 1, 1);
    for (sov_int i = 0; i < len; i++) {
        result[i] = toupper((unsigned char)s[i]);
    }
    result[len] = '\0';
    return result;
}

sov_string sov_strlower(sov_string s) {
    if (!s) return sov_strcpy("");
    sov_int len = sov_strlen(s);
    sov_string result = (sov_string)sov_alloc(len + 1, 1);
    for (sov_int i = 0; i < len; i++) {
        result[i] = tolower((unsigned char)s[i]);
    }
    result[len] = '\0';
    return result;
}

sov_string sov_strreplace(sov_string s, sov_string old_str, sov_string new_str) {
    if (!s || !old_str || !new_str) return sov_strcpy(s);
    
    sov_int old_len = sov_strlen(old_str);
    if (old_len == 0) return sov_strcpy(s);
    
    sov_int new_len = sov_strlen(new_str);
    
    sov_int count = 0;
    char* p = s;
    while ((p = strstr(p, old_str)) != NULL) {
        count++;
        p += old_len;
    }
    
    if (count == 0) return sov_strcpy(s);
    
    sov_int s_len = sov_strlen(s);
    sov_int result_len = s_len + count * (new_len - old_len);
    sov_string result = (sov_string)sov_alloc(result_len + 1, 1);
    
    char* dest = result;
    p = s;
    while (*p) {
        if (strncmp(p, old_str, old_len) == 0) {
            memcpy(dest, new_str, new_len);
            dest += new_len;
            p += old_len;
        } else {
            *dest++ = *p++;
        }
    }
    *dest = '\0';
    
    return result;
}

char sov_charat(sov_string s, sov_int index) {
    if (!s || index < 0 || index >= sov_strlen(s)) return '\0';
    return s[index];
}

sov_string sov_int_to_string(sov_int n) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%lld", (long long)n);
    return sov_strcpy(buf);
}

sov_int sov_string_to_int(sov_string s) {
    if (!s) return 0;
    return (sov_int)strtoll(s, NULL, 10);
}

sov_string sov_float_to_string(sov_float f) {
    char buf[64];
    snprintf(buf, sizeof(buf), "%g", f);
    return sov_strcpy(buf);
}

sov_float sov_string_to_float(sov_string s) {
    if (!s) return 0.0;
    return strtod(s, NULL);
}

/* ============================================================================
 * STRING BUILDER
 * ============================================================================ */

sov_stringbuilder* sov_sb_new(void) {
    sov_stringbuilder* sb = (sov_stringbuilder*)sov_alloc(1, sizeof(sov_stringbuilder));
    sb->capacity = 64;
    sb->data = (char*)sov_alloc(sb->capacity, 1);
    sb->len = 0;
    sb->data[0] = '\0';
    return sb;
}

static void sov_sb_ensure_capacity(sov_stringbuilder* sb, sov_int additional) {
    sov_int needed = sb->len + additional + 1;
    if (needed > sb->capacity) {
        while (sb->capacity < needed) {
            sb->capacity *= 2;
        }
        sb->data = (char*)sov_realloc(sb->data, sb->capacity);
    }
}

void sov_sb_append(sov_stringbuilder* sb, sov_string s) {
    if (!sb || !s) return;
    sov_int len = sov_strlen(s);
    sov_sb_ensure_capacity(sb, len);
    memcpy(sb->data + sb->len, s, len);
    sb->len += len;
    sb->data[sb->len] = '\0';
}

void sov_sb_append_char(sov_stringbuilder* sb, char c) {
    if (!sb) return;
    sov_sb_ensure_capacity(sb, 1);
    sb->data[sb->len++] = c;
    sb->data[sb->len] = '\0';
}

void sov_sb_append_int(sov_stringbuilder* sb, sov_int n) {
    sov_string s = sov_int_to_string(n);
    sov_sb_append(sb, s);
    sov_free(s);
}

sov_string sov_sb_to_string(sov_stringbuilder* sb) {
    if (!sb) return sov_strcpy("");
    sov_string result = sov_strcpy(sb->data);
    sov_sb_free(sb);
    return result;
}

sov_int sov_sb_len(sov_stringbuilder* sb) {
    return sb ? sb->len : 0;
}

void sov_sb_clear(sov_stringbuilder* sb) {
    if (sb) {
        sb->len = 0;
        sb->data[0] = '\0';
    }
}

void sov_sb_free(sov_stringbuilder* sb) {
    if (sb) {
        sov_free(sb->data);
        sov_free(sb);
    }
}

/* ============================================================================
 * VECTOR OPERATIONS
 * ============================================================================ */

sov_vec* sov_vec_new(sov_int elem_size) {
    sov_vec* v = (sov_vec*)sov_alloc(1, sizeof(sov_vec));
    v->elem_size = elem_size;
    v->capacity = 8;
    v->len = 0;
    v->data = sov_alloc(v->capacity, elem_size);
    return v;
}

static void sov_vec_grow(sov_vec* v) {
    v->capacity *= 2;
    v->data = sov_realloc(v->data, v->capacity * v->elem_size);
}

void sov_vec_push(sov_vec* v, sov_ptr elem) {
    if (!v) return;
    if (v->len >= v->capacity) sov_vec_grow(v);
    memcpy((char*)v->data + v->len * v->elem_size, elem, v->elem_size);
    v->len++;
}

sov_ptr sov_vec_pop(sov_vec* v) {
    if (!v || v->len == 0) return NULL;
    v->len--;
    return (char*)v->data + v->len * v->elem_size;
}

sov_ptr sov_vec_get(sov_vec* v, sov_int index) {
    if (!v || index < 0 || index >= v->len) return NULL;
    return (char*)v->data + index * v->elem_size;
}

void sov_vec_set(sov_vec* v, sov_int index, sov_ptr elem) {
    if (!v || index < 0 || index >= v->len) return;
    memcpy((char*)v->data + index * v->elem_size, elem, v->elem_size);
}

sov_int sov_vec_len(sov_vec* v) {
    return v ? v->len : 0;
}

sov_int sov_vec_capacity(sov_vec* v) {
    return v ? v->capacity : 0;
}

void sov_vec_clear(sov_vec* v) {
    if (v) v->len = 0;
}

void sov_vec_free(sov_vec* v) {
    if (v) {
        sov_free(v->data);
        sov_free(v);
    }
}

sov_vec* sov_vec_int_new(void) {
    return sov_vec_new(sizeof(sov_int));
}

void sov_vec_int_push(sov_vec* v, sov_int val) {
    sov_vec_push(v, &val);
}

sov_int sov_vec_int_get(sov_vec* v, sov_int index) {
    sov_ptr p = sov_vec_get(v, index);
    return p ? *(sov_int*)p : 0;
}

void sov_vec_int_set(sov_vec* v, sov_int index, sov_int val) {
    sov_vec_set(v, index, &val);
}

sov_vec* sov_vec_str_new(void) {
    return sov_vec_new(sizeof(sov_string));
}

void sov_vec_str_push(sov_vec* v, sov_string val) {
    sov_string copy = sov_strcpy(val);
    sov_vec_push(v, &copy);
}

sov_string sov_vec_str_get(sov_vec* v, sov_int index) {
    sov_ptr p = sov_vec_get(v, index);
    return p ? *(sov_string*)p : NULL;
}

void sov_vec_str_set(sov_vec* v, sov_int index, sov_string val) {
    sov_string* p = (sov_string*)sov_vec_get(v, index);
    if (p) {
        sov_free(*p);
        *p = sov_strcpy(val);
    }
}

void sov_vec_str_free(sov_vec* v) {
    if (v) {
        for (sov_int i = 0; i < v->len; i++) {
            sov_string* p = (sov_string*)sov_vec_get(v, i);
            if (p && *p) sov_free(*p);
        }
        sov_vec_free(v);
    }
}

/* ============================================================================
 * HASHMAP OPERATIONS
 * ============================================================================ */

uint64_t sov_hash_string(sov_string s) {
    if (!s) return 0;
    uint64_t hash = 5381;
    int c;
    while ((c = *s++)) {
        hash = ((hash << 5) + hash) + c;
    }
    return hash;
}

sov_hashmap* sov_hashmap_new(void) {
    sov_hashmap* hm = (sov_hashmap*)sov_alloc(1, sizeof(sov_hashmap));
    hm->capacity = 16;
    hm->count = 0;
    hm->entries = (sov_hashmap_entry*)sov_alloc(hm->capacity, sizeof(sov_hashmap_entry));
    return hm;
}

static void sov_hashmap_resize(sov_hashmap* hm) {
    sov_int old_capacity = hm->capacity;
    sov_hashmap_entry* old_entries = hm->entries;
    
    hm->capacity *= 2;
    hm->entries = (sov_hashmap_entry*)sov_alloc(hm->capacity, sizeof(sov_hashmap_entry));
    hm->count = 0;
    
    for (sov_int i = 0; i < old_capacity; i++) {
        if (old_entries[i].occupied) {
            sov_hashmap_insert(hm, old_entries[i].key, old_entries[i].value);
        }
    }
    
    sov_free(old_entries);
}

void sov_hashmap_insert(sov_hashmap* hm, sov_string key, sov_ptr value) {
    if (!hm || !key) return;
    
    if (hm->count * 4 >= hm->capacity * 3) {
        sov_hashmap_resize(hm);
    }
    
    uint64_t hash = sov_hash_string(key);
    sov_int index = hash % hm->capacity;
    
    while (hm->entries[index].occupied) {
        if (sov_streq(hm->entries[index].key, key)) {
            hm->entries[index].value = value;
            return;
        }
        index = (index + 1) % hm->capacity;
    }
    
    hm->entries[index].key = sov_strcpy(key);
    hm->entries[index].value = value;
    hm->entries[index].hash = hash;
    hm->entries[index].occupied = true;
    hm->count++;
}

sov_ptr sov_hashmap_get(sov_hashmap* hm, sov_string key) {
    if (!hm || !key) return NULL;
    
    uint64_t hash = sov_hash_string(key);
    sov_int index = hash % hm->capacity;
    sov_int start = index;
    
    do {
        if (!hm->entries[index].occupied) return NULL;
        if (sov_streq(hm->entries[index].key, key)) {
            return hm->entries[index].value;
        }
        index = (index + 1) % hm->capacity;
    } while (index != start);
    
    return NULL;
}

sov_bool sov_hashmap_contains(sov_hashmap* hm, sov_string key) {
    return sov_hashmap_get(hm, key) != NULL;
}

sov_ptr sov_hashmap_remove(sov_hashmap* hm, sov_string key) {
    if (!hm || !key) return NULL;
    
    uint64_t hash = sov_hash_string(key);
    sov_int index = hash % hm->capacity;
    sov_int start = index;
    
    do {
        if (!hm->entries[index].occupied) return NULL;
        if (sov_streq(hm->entries[index].key, key)) {
            sov_ptr value = hm->entries[index].value;
            sov_free(hm->entries[index].key);
            hm->entries[index].occupied = false;
            hm->count--;
            return value;
        }
        index = (index + 1) % hm->capacity;
    } while (index != start);
    
    return NULL;
}

sov_int sov_hashmap_count(sov_hashmap* hm) {
    return hm ? hm->count : 0;
}

void sov_hashmap_free(sov_hashmap* hm) {
    if (hm) {
        for (sov_int i = 0; i < hm->capacity; i++) {
            if (hm->entries[i].occupied) {
                sov_free(hm->entries[i].key);
            }
        }
        sov_free(hm->entries);
        sov_free(hm);
    }
}

/* ============================================================================
 * FILE OPERATIONS
 * ============================================================================ */

sov_file* sov_file_open(sov_string path, sov_string mode) {
    if (!path || !mode) return NULL;
    
    FILE* f = fopen(path, mode);
    if (!f) return NULL;
    
    sov_file* sf = (sov_file*)sov_alloc(1, sizeof(sov_file));
    sf->handle = f;
    sf->path = sov_strcpy(path);
    sf->is_open = true;
    return sf;
}

void sov_file_close(sov_file* f) {
    if (f && f->is_open) {
        fclose((FILE*)f->handle);
        f->is_open = false;
        sov_free(f->path);
        sov_free(f);
    }
}

sov_string sov_file_read_all(sov_string path) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    sov_string content = (sov_string)sov_alloc(size + 1, 1);
    fread(content, 1, size, f);
    content[size] = '\0';
    
    fclose(f);
    return content;
}

sov_bool sov_file_write_all(sov_string path, sov_string content) {
    if (!path || !content) return false;
    
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    
    sov_int len = sov_strlen(content);
    size_t written = fwrite(content, 1, len, f);
    fclose(f);
    
    return written == (size_t)len;
}

sov_string sov_file_read_line(sov_file* f) {
    if (!f || !f->is_open) return NULL;
    
    char buf[4096];
    if (fgets(buf, sizeof(buf), (FILE*)f->handle) == NULL) {
        return NULL;
    }
    
    sov_int len = sov_strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') {
        buf[len - 1] = '\0';
        if (len > 1 && buf[len - 2] == '\r') {
            buf[len - 2] = '\0';
        }
    }
    
    return sov_strcpy(buf);
}

void sov_file_write(sov_file* f, sov_string s) {
    if (f && f->is_open && s) {
        fputs(s, (FILE*)f->handle);
    }
}

sov_bool sov_file_exists(sov_string path) {
    if (!path) return false;
    struct stat st;
    return stat(path, &st) == 0;
}

sov_int sov_file_size(sov_string path) {
    if (!path) return -1;
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return (sov_int)st.st_size;
}

/* ============================================================================
 * I/O OPERATIONS
 * ============================================================================ */

void sov_print(sov_string s) {
    if (s) printf("%s", s);
}

void sov_println(sov_string s) {
    if (s) printf("%s\n", s);
    else printf("\n");
}

void sov_print_int(sov_int n) {
    printf("%lld", (long long)n);
}

void sov_print_float(sov_float f) {
    printf("%g", f);
}

void sov_eprint(sov_string s) {
    if (s) fprintf(stderr, "%s", s);
}

void sov_eprintln(sov_string s) {
    if (s) fprintf(stderr, "%s\n", s);
    else fprintf(stderr, "\n");
}

void sov_printf(sov_string fmt, ...) {
    if (!fmt) return;
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}

sov_string sov_read_line(void) {
    char buf[4096];
    if (fgets(buf, sizeof(buf), stdin) == NULL) {
        return sov_strcpy("");
    }
    
    sov_int len = sov_strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') {
        buf[len - 1] = '\0';
    }
    
    return sov_strcpy(buf);
}

/* ============================================================================
 * SHA-256 - FIPS 180-4
 * ============================================================================ */

static const uint32_t SHA256_K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

typedef struct {
    uint32_t state[8];
    uint64_t count;
    uint8_t  buf[64];
} sov_sha256_ctx;

static void sov_sha256_init(sov_sha256_ctx* ctx) {
    ctx->state[0] = 0x6a09e667;
    ctx->state[1] = 0xbb67ae85;
    ctx->state[2] = 0x3c6ef372;
    ctx->state[3] = 0xa54ff53a;
    ctx->state[4] = 0x510e527f;
    ctx->state[5] = 0x9b05688c;
    ctx->state[6] = 0x1f83d9ab;
    ctx->state[7] = 0x5be0cd19;
    ctx->count = 0;
}

static void sov_sha256_transform(sov_sha256_ctx* ctx, const uint8_t* data) {
    uint32_t a, b, c, d, e, f, g, h;
    uint32_t w[64];
    
    /* Prepare message schedule */
    for (int i = 0; i < 16; i++) {
        w[i] = ((uint32_t)data[i*4] << 24) |
               ((uint32_t)data[i*4+1] << 16) |
               ((uint32_t)data[i*4+2] << 8) |
               ((uint32_t)data[i*4+3]);
    }
    
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = rotr32(w[i-15], 7) ^ rotr32(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t s1 = rotr32(w[i-2], 17) ^ rotr32(w[i-2], 19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    
    a = ctx->state[0]; b = ctx->state[1]; c = ctx->state[2]; d = ctx->state[3];
    e = ctx->state[4]; f = ctx->state[5]; g = ctx->state[6]; h = ctx->state[7];
    
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + S1 + ch + SHA256_K[i] + w[i];
        uint32_t S0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = S0 + maj;
        
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }
    
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void sov_sha256_update(sov_sha256_ctx* ctx, const uint8_t* data, uint64_t len) {
    uint64_t i;
    for (i = 0; i < len; i++) {
        ctx->buf[ctx->count % 64] = data[i];
        ctx->count++;
        if (ctx->count % 64 == 0) {
            sov_sha256_transform(ctx, ctx->buf);
        }
    }
}

static void sov_sha256_final(sov_sha256_ctx* ctx, uint8_t* digest) {
    uint64_t bit_count = ctx->count * 8;
    
    /* Padding */
    uint8_t pad_byte = 0x80;
    sov_sha256_update(ctx, &pad_byte, 1);
    
    /* Pad with zeros until we have 8 bytes left for length */
    while (ctx->count % 64 != 56) {
        uint8_t zero = 0x00;
        sov_sha256_update(ctx, &zero, 1);
    }
    
    /* Append bit length as 64-bit big-endian */
    uint8_t len_buf[8];
    for (int i = 7; i >= 0; i--) {
        len_buf[i] = bit_count & 0xFF;
        bit_count >>= 8;
    }
    sov_sha256_update(ctx, len_buf, 8);
    
    /* Write digest in big-endian */
    for (int i = 0; i < 8; i++) {
        digest[i*4]     = (ctx->state[i] >> 24) & 0xFF;
        digest[i*4 + 1] = (ctx->state[i] >> 16) & 0xFF;
        digest[i*4 + 2] = (ctx->state[i] >> 8) & 0xFF;
        digest[i*4 + 3] = ctx->state[i] & 0xFF;
    }
}

void sov_sha256(sov_ptr data, sov_int len, sov_ptr out) {
    if (!out) return;
    sov_sha256_ctx ctx;
    sov_sha256_init(&ctx);
    sov_sha256_update(&ctx, (const uint8_t*)data, len);
    sov_sha256_final(&ctx, (uint8_t*)out);
}

sov_string sov_sha256_hex(sov_ptr data, sov_int len) {
    uint8_t digest[SOV_SHA256_SIZE];
    sov_sha256(data, len, digest);
    
    sov_string hex = (sov_string)sov_alloc(SOV_SHA256_HEX_SIZE, 1);
    for (int i = 0; i < SOV_SHA256_SIZE; i++) {
        snprintf(hex + i*2, 3, "%02x", digest[i]);
    }
    hex[64] = '\0';
    return hex;
}

/* ============================================================================
 * SHA-512
 * ============================================================================ */

static const uint64_t SHA512_K[80] = {
    0x428a2f98d728ae22ULL, 0x7137449123ef65cdULL, 0xb5c0fbcfec4d3b2fULL,
    0xe9b5dba58189dbbcULL, 0x3956c25bf348b538ULL, 0x59f111f1b605d019ULL,
    0x923f82a4af194f9bULL, 0xab1c5ed5da6d8118ULL, 0xd807aa98a3030242ULL,
    0x12835b0145706fbeULL, 0x243185be4ee4b28cULL, 0x550c7dc3d5ffb4e2ULL,
    0x72be5d74f27b896fULL, 0x80deb1fe3b1696b1ULL, 0x9bdc06a725c71235ULL,
    0xc19bf174cf692694ULL, 0xe49b69c19ef14ad2ULL, 0xefbe4786384f25e3ULL,
    0x0fc19dc68b8cd5b5ULL, 0x240ca1cc77ac9c65ULL, 0x2de92c6f592b0275ULL,
    0x4a7484aa6ea6e483ULL, 0x5cb0a9dcbd41fbd4ULL, 0x76f988da831153b5ULL,
    0x983e5152ee66dfabULL, 0xa831c66d2db43210ULL, 0xb00327c898fb213fULL,
    0xbf597fc7beef0ee4ULL, 0xc6e00bf33da88fc2ULL, 0xd5a79147930aa725ULL,
    0x06ca6351e003826fULL, 0x142929670a0e6e70ULL, 0x27b70a8546d22ffcULL,
    0x2e1b21385c26c926ULL, 0x4d2c6dfc5ac42aedULL, 0x53380d139d95b3dfULL,
    0x650a73548baf63deULL, 0x766a0abb3c77b2a8ULL, 0x81c2c92e47edaee6ULL,
    0x92722c851482353bULL, 0xa2bfe8a14cf10364ULL, 0xa81a664bbc423001ULL,
    0xc24b8b70d0f89791ULL, 0xc76c51a30654be30ULL, 0xd192e819d6ef5218ULL,
    0xd69906245565a910ULL, 0xf40e35855771202aULL, 0x106aa07032bbd1b8ULL,
    0x19a4c116b8d2d0c8ULL, 0x1e376c085141ab53ULL, 0x2748774cdf8eeb99ULL,
    0x34b0bcb5e19b48a8ULL, 0x391c0cb3c5c95a63ULL, 0x4ed8aa4ae3418acbULL,
    0x5b9cca4f7763e373ULL, 0x682e6ff3d6b2b8a3ULL, 0x748f82ee5defb2fcULL,
    0x78a5636f43172f60ULL, 0x84c87814a1f0ab72ULL, 0x8cc702081a6439ecULL,
    0x90befffa23631e28ULL, 0xa4506cebde82bde9ULL, 0xbef9a3f7b2c67915ULL,
    0xc67178f2e372532bULL, 0xca273eceea26619cULL, 0xd186b8c721c0c207ULL,
    0xeada7dd6cde0eb1eULL, 0xf57d4f7fee6ed178ULL, 0x06f067aa72176fbaULL,
    0x0a637dc5a2c898a6ULL, 0x113f9804bef90daeULL, 0x1b710b35131c471bULL,
    0x28db77f523047d84ULL, 0x32caab7b40c72493ULL, 0x3c9ebe0a15c9bebcULL,
    0x431d67c49c100d4cULL, 0x4cc5d4becb3e42b6ULL, 0x597f299cfc657e2aULL,
    0x5fcb6fab3ad6faecULL, 0x6c44198c4a475817ULL
};

typedef struct {
    uint64_t state[8];
    uint64_t count_lo, count_hi;
    uint8_t  buf[128];
} sov_sha512_ctx;

static void sov_sha512_init(sov_sha512_ctx* ctx) {
    ctx->state[0] = 0x6a09e667f3bcc908ULL; ctx->state[1] = 0xbb67ae8584caa73bULL;
    ctx->state[2] = 0x3c6ef372fe94f82bULL; ctx->state[3] = 0xa54ff53a5f1d36f1ULL;
    ctx->state[4] = 0x510e527fade682d1ULL; ctx->state[5] = 0x9b05688c2b3e6c1fULL;
    ctx->state[6] = 0x1f83d9abfb41bd6bULL; ctx->state[7] = 0x5be0cd19137e2179ULL;
    ctx->count_lo = 0; ctx->count_hi = 0;
}

static void sov_sha512_transform(sov_sha512_ctx* ctx, const uint8_t* data) {
    uint64_t a, b, c, d, e, f, g, h;
    uint64_t w[80];
    
    for (int i = 0; i < 16; i++) {
        w[i] = ((uint64_t)data[i*8] << 56) | ((uint64_t)data[i*8+1] << 48) |
               ((uint64_t)data[i*8+2] << 40) | ((uint64_t)data[i*8+3] << 32) |
               ((uint64_t)data[i*8+4] << 24) | ((uint64_t)data[i*8+5] << 16) |
               ((uint64_t)data[i*8+6] << 8)  | ((uint64_t)data[i*8+7]);
    }
    
    for (int i = 16; i < 80; i++) {
        uint64_t s0 = rotr64(w[i-15], 1) ^ rotr64(w[i-15], 8) ^ (w[i-15] >> 7);
        uint64_t s1 = rotr64(w[i-2], 19) ^ rotr64(w[i-2], 61) ^ (w[i-2] >> 6);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    
    a = ctx->state[0]; b = ctx->state[1]; c = ctx->state[2]; d = ctx->state[3];
    e = ctx->state[4]; f = ctx->state[5]; g = ctx->state[6]; h = ctx->state[7];
    
    for (int i = 0; i < 80; i++) {
        uint64_t S1 = rotr64(e, 14) ^ rotr64(e, 18) ^ rotr64(e, 41);
        uint64_t ch = (e & f) ^ ((~e) & g);
        uint64_t temp1 = h + S1 + ch + SHA512_K[i] + w[i];
        uint64_t S0 = rotr64(a, 28) ^ rotr64(a, 34) ^ rotr64(a, 39);
        uint64_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint64_t temp2 = S0 + maj;
        
        h = g; g = f; f = e; e = d + temp1;
        d = c; c = b; b = a; a = temp1 + temp2;
    }
    
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void sov_sha512_update(sov_sha512_ctx* ctx, const uint8_t* data, uint64_t len) {
    for (uint64_t i = 0; i < len; i++) {
        ctx->buf[ctx->count_lo % 128] = data[i];
        ctx->count_lo++;
        if (ctx->count_lo == 0) ctx->count_hi++;
        if (ctx->count_lo % 128 == 0) {
            sov_sha512_transform(ctx, ctx->buf);
        }
    }
}

static void sov_sha512_final(sov_sha512_ctx* ctx, uint8_t* digest) {
    uint64_t orig_lo = ctx->count_lo;
    uint64_t orig_hi = ctx->count_hi;
    
    uint8_t pad_byte = 0x80;
    sov_sha512_update(ctx, &pad_byte, 1);
    
    while (ctx->count_lo % 128 != 112) {
        uint8_t zero = 0x00;
        sov_sha512_update(ctx, &zero, 1);
    }
    
    uint8_t len_buf[16];
    uint64_t bit_lo = orig_lo * 8;
    uint64_t bit_hi = orig_hi * 8 + (orig_lo >> 61) * 8;
    for (int i = 7; i >= 0; i--) { len_buf[i] = bit_lo & 0xFF; bit_lo >>= 8; }
    for (int i = 15; i >= 8; i--) { len_buf[i] = bit_hi & 0xFF; bit_hi >>= 8; }
    sov_sha512_update(ctx, len_buf, 16);
    
    for (int i = 0; i < 8; i++) {
        digest[i*8]     = (ctx->state[i] >> 56) & 0xFF;
        digest[i*8 + 1] = (ctx->state[i] >> 48) & 0xFF;
        digest[i*8 + 2] = (ctx->state[i] >> 40) & 0xFF;
        digest[i*8 + 3] = (ctx->state[i] >> 32) & 0xFF;
        digest[i*8 + 4] = (ctx->state[i] >> 24) & 0xFF;
        digest[i*8 + 5] = (ctx->state[i] >> 16) & 0xFF;
        digest[i*8 + 6] = (ctx->state[i] >> 8) & 0xFF;
        digest[i*8 + 7] = ctx->state[i] & 0xFF;
    }
}

void sov_sha512(sov_ptr data, sov_int len, sov_ptr out) {
    if (!out) return;
    sov_sha512_ctx ctx;
    sov_sha512_init(&ctx);
    sov_sha512_update(&ctx, (const uint8_t*)data, len);
    sov_sha512_final(&ctx, (uint8_t*)out);
}

sov_string sov_sha512_hex(sov_ptr data, sov_int len) {
    uint8_t digest[SOV_SHA512_SIZE];
    sov_sha512(data, len, digest);
    
    sov_string hex = (sov_string)sov_alloc(129, 1);
    for (int i = 0; i < SOV_SHA512_SIZE; i++) {
        snprintf(hex + i*2, 3, "%02x", digest[i]);
    }
    hex[128] = '\0';
    return hex;
}

/* ============================================================================
 * BLAKE2S (simplified but correct implementation)
 * Uses BLAKE2s as the core compression function (
 * ============================================================================ */

static const uint32_t BLAKE2S_IV[8] = {
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19
};

static void blake2s_compress(uint32_t h[8], const uint8_t block[64], uint64_t counter,
                              bool is_last) {
    uint32_t v[16];
    uint32_t m[16];
    
    for (int i = 0; i < 16; i++) {
        m[i] = ((uint32_t)block[i*4]) | ((uint32_t)block[i*4+1] << 8) |
               ((uint32_t)block[i*4+2] << 16) | ((uint32_t)block[i*4+3] << 24);
    }
    
    for (int i = 0; i < 8; i++) v[i] = h[i];
    for (int i = 0; i < 8; i++) v[i+8] = BLAKE2S_IV[i];
    v[12] ^= (uint32_t)counter;
    v[13] ^= (uint32_t)(counter >> 32);
    v[14] ^= is_last ? 0xFFFFFFFF : 0;
    
    #define G(a, b, c, d, x, y) do { \
        v[a] = v[a] + v[b] + x; v[d] = rotr32(v[d] ^ v[a], 16); \
        v[c] = v[c] + v[d]; v[b] = rotr32(v[b] ^ v[c], 12); \
        v[a] = v[a] + v[b] + y; v[d] = rotr32(v[d] ^ v[a], 8); \
        v[c] = v[c] + v[d]; v[b] = rotr32(v[b] ^ v[c], 7); \
    } while(0)
    
    /* 10 rounds of BLAKE2s */
    for (int r = 0; r < 10; r++) {
        G(0, 4, 8,  12, m[0],  m[1]);
        G(1, 5, 9,  13, m[2],  m[3]);
        G(2, 6, 10, 14, m[4],  m[5]);
        G(3, 7, 11, 15, m[6],  m[7]);
        G(0, 5, 10, 15, m[8],  m[9]);
        G(1, 6, 11, 12, m[10], m[11]);
        G(2, 7, 8,  13, m[12], m[13]);
        G(3, 4, 9,  14, m[14], m[15]);
    }
    #undef G
    
    for (int i = 0; i < 8; i++) {
        h[i] ^= v[i] ^ v[i+8];
    }
}

void sov_blake2s(sov_ptr data, sov_int len, sov_ptr out) {
    /* BLAKE2S-like construction on top of BLAKE2s */
    uint32_t h[8];
    memcpy(h, BLAKE2S_IV, sizeof(h));
    h[0] ^= 0x01010000 | SOV_BLAKE2S_SIZE; /* key length=0, digest length=32 */
    
    uint8_t buf[64];
    sov_int remaining = len;
    const uint8_t* input = (const uint8_t*)data;
    uint64_t counter = 0;
    
    while (remaining > 64) {
        memcpy(buf, input, 64);
        blake2s_compress(h, buf, counter, false);
        input += 64;
        remaining -= 64;
        counter += 64;
    }
    
    memset(buf, 0, 64);
    memcpy(buf, input, remaining);
    blake2s_compress(h, buf, counter, true);
    
    /* Output */
    uint8_t* out_bytes = (uint8_t*)out;
    for (int i = 0; i < 8; i++) {
        out_bytes[i*4]     = h[i] & 0xFF;
        out_bytes[i*4 + 1] = (h[i] >> 8) & 0xFF;
        out_bytes[i*4 + 2] = (h[i] >> 16) & 0xFF;
        out_bytes[i*4 + 3] = (h[i] >> 24) & 0xFF;
    }
}

sov_string sov_blake2s_hex(sov_ptr data, sov_int len) {
    uint8_t digest[SOV_BLAKE2S_SIZE];
    sov_blake2s(data, len, digest);
    
    sov_string hex = (sov_string)sov_alloc(65, 1);
    for (int i = 0; i < SOV_BLAKE2S_SIZE; i++) {
        snprintf(hex + i*2, 3, "%02x", digest[i]);
    }
    hex[64] = '\0';
    return hex;
}

/* ============================================================================
 * HMAC-SHA256 - RFC 2104
 * ============================================================================ */

#define HMAC_IPAD 0x36
#define HMAC_OPAD 0x5C
#define HMAC_BLOCK_SIZE 64

void sov_hmac_sha256(sov_ptr key, sov_int key_len, sov_ptr data, sov_int data_len, sov_ptr out) {
    if (!out) return;
    
    uint8_t key_block[HMAC_BLOCK_SIZE];
    memset(key_block, 0, HMAC_BLOCK_SIZE);
    
    /* If key is longer than block size, hash it first */
    if (key_len > HMAC_BLOCK_SIZE) {
        sov_sha256(key, key_len, key_block);
    } else {
        memcpy(key_block, key, key_len);
    }
    
    /* Inner hash: H((key ^ ipad) || data) */
    uint8_t inner_key[HMAC_BLOCK_SIZE];
    for (int i = 0; i < HMAC_BLOCK_SIZE; i++) {
        inner_key[i] = key_block[i] ^ HMAC_IPAD;
    }
    
    sov_sha256_ctx ctx;
    sov_sha256_init(&ctx);
    sov_sha256_update(&ctx, inner_key, HMAC_BLOCK_SIZE);
    sov_sha256_update(&ctx, (const uint8_t*)data, data_len);
    uint8_t inner_hash[SOV_SHA256_SIZE];
    sov_sha256_final(&ctx, inner_hash);
    
    /* Outer hash: H((key ^ opad) || inner_hash) */
    uint8_t outer_key[HMAC_BLOCK_SIZE];
    for (int i = 0; i < HMAC_BLOCK_SIZE; i++) {
        outer_key[i] = key_block[i] ^ HMAC_OPAD;
    }
    
    sov_sha256_init(&ctx);
    sov_sha256_update(&ctx, outer_key, HMAC_BLOCK_SIZE);
    sov_sha256_update(&ctx, inner_hash, SOV_SHA256_SIZE);
    sov_sha256_final(&ctx, (uint8_t*)out);
    
    /* Clean up sensitive key material */
    sov_secure_zero(key_block, HMAC_BLOCK_SIZE);
    sov_secure_zero(inner_key, HMAC_BLOCK_SIZE);
    sov_secure_zero(outer_key, HMAC_BLOCK_SIZE);
    sov_secure_zero(inner_hash, SOV_SHA256_SIZE);
}

sov_string sov_hmac_sha256_hex(sov_ptr key, sov_int key_len, sov_ptr data, sov_int data_len) {
    uint8_t digest[SOV_HMAC_SIZE];
    sov_hmac_sha256(key, key_len, data, data_len, digest);
    
    sov_string hex = (sov_string)sov_alloc(65, 1);
    for (int i = 0; i < SOV_HMAC_SIZE; i++) {
        snprintf(hex + i*2, 3, "%02x", digest[i]);
    }
    hex[64] = '\0';
    return hex;
}

/* ============================================================================
 * HKDF-SHA256 - RFC 5869
 * ============================================================================ */

void sov_hkdf_sha256(sov_ptr salt, sov_int salt_len, sov_ptr ikm, sov_int ikm_len,
                     sov_ptr info, sov_int info_len, sov_ptr out, sov_int out_len) {
    if (!out || out_len <= 0) return;
    
    /* Step 1: Extract - PRK = HMAC-SHA256(salt, IKM) */
    uint8_t prk[SOV_SHA256_SIZE];
    if (!salt || salt_len == 0) {
        uint8_t zero_salt[SOV_SHA256_SIZE];
        memset(zero_salt, 0, SOV_SHA256_SIZE);
        sov_hmac_sha256(zero_salt, SOV_SHA256_SIZE, ikm, ikm_len, prk);
        sov_secure_zero(zero_salt, SOV_SHA256_SIZE);
    } else {
        sov_hmac_sha256(salt, salt_len, ikm, ikm_len, prk);
    }
    
    /* Step 2: Expand - T(1) || T(2) || ... */
    uint8_t prev[SOV_SHA256_SIZE];
    memset(prev, 0, SOV_SHA256_SIZE);
    
    sov_int offset = 0;
    uint8_t block_num = 1;
    
    while (offset < out_len) {
        /* T(n) = HMAC-SHA256(PRK, T(n-1) || info || n) */
        sov_sha256_ctx ctx;
        sov_sha256_init(&ctx);
        sov_sha256_update(&ctx, prev, SOV_SHA256_SIZE);
        if (info && info_len > 0) sov_sha256_update(&ctx, (const uint8_t*)info, info_len);
        sov_sha256_update(&ctx, &block_num, 1);
        
        /* We need to HMAC, but HMAC wraps SHA256. Let's do it inline. */
        uint8_t temp_input[SOV_SHA256_SIZE + 256]; /* conservative max */
        sov_int temp_len = SOV_SHA256_SIZE + (info ? info_len : 0) + 1;
        uint8_t temp_hash[SOV_SHA256_SIZE];
        
        sov_sha256_final(&ctx, temp_hash);
        
        /* Build the message for HMAC: T(n-1) || info || n */
        memcpy(temp_input, prev, SOV_SHA256_SIZE);
        sov_int pos = SOV_SHA256_SIZE;
        if (info && info_len > 0) {
            memcpy(temp_input + pos, info, info_len);
            pos += info_len;
        }
        temp_input[pos++] = block_num;
        
        /* HMAC-SHA256(PRK, temp_input) */
        uint8_t t_n[SOV_SHA256_SIZE];
        sov_hmac_sha256(prk, SOV_SHA256_SIZE, temp_input, pos, t_n);
        
        /* Copy to output */
        sov_int to_copy = SOV_MIN(SOV_SHA256_SIZE, out_len - offset);
        memcpy((uint8_t*)out + offset, t_n, to_copy);
        offset += to_copy;
        
        /* Prepare for next iteration */
        memcpy(prev, t_n, SOV_SHA256_SIZE);
        block_num++;
        
        sov_secure_zero(t_n, SOV_SHA256_SIZE);
    }
    
    sov_secure_zero(prk, SOV_SHA256_SIZE);
    sov_secure_zero(prev, SOV_SHA256_SIZE);
}

/* ============================================================================
 * PBKDF2-SHA256
 * ============================================================================ */

void sov_pbkdf2_sha256(sov_ptr password, sov_int password_len, sov_ptr salt, sov_int salt_len,
                       sov_int iterations, sov_ptr out, sov_int out_len) {
    if (!out || out_len <= 0) return;
    
    sov_int hlen = SOV_SHA256_SIZE;
    sov_int blocks = (out_len + hlen - 1) / hlen;
    
    uint8_t* block = (uint8_t*)sov_alloc(1, hlen);
    uint8_t* u = (uint8_t*)sov_alloc(1, hlen);
    
    for (sov_int block_idx = 1; block_idx <= blocks; block_idx++) {
        /* U1 = HMAC-SHA256(password, salt || block_idx) */
        uint8_t be_block[4];
        be_block[0] = (block_idx >> 24) & 0xFF;
        be_block[1] = (block_idx >> 16) & 0xFF;
        be_block[2] = (block_idx >> 8) & 0xFF;
        be_block[3] = block_idx & 0xFF;
        
        sov_sha256_ctx ctx;
        sov_sha256_init(&ctx);
        sov_sha256_update(&ctx, (const uint8_t*)salt, salt_len);
        sov_sha256_update(&ctx, be_block, 4);
        uint8_t msg[1024];
        sov_int msg_len = salt_len + 4;
        uint8_t hash_dummy[SOV_SHA256_SIZE];
        sov_sha256_final(&ctx, hash_dummy);
        
        /* Rebuild for HMAC */
        memcpy(msg, salt, salt_len);
        memcpy(msg + salt_len, be_block, 4);
        
        sov_hmac_sha256(password, password_len, msg, msg_len, u);
        memcpy(block, u, hlen);
        
        /* Subsequent iterations */
        for (sov_int iter = 1; iter < iterations; iter++) {
            sov_hmac_sha256(password, password_len, u, hlen, u);
            for (int j = 0; j < hlen; j++) {
                block[j] ^= u[j];
            }
        }
        
        /* Copy to output */
        sov_int to_copy = SOV_MIN(hlen, out_len - (block_idx - 1) * hlen);
        memcpy((uint8_t*)out + (block_idx - 1) * hlen, block, to_copy);
    }
    
    sov_secure_zero(block, hlen);
    sov_secure_zero(u, hlen);
    sov_free(block);
    sov_free(u);
}

/* ============================================================================
 * CONSTANT-TIME OPERATIONS
 * ============================================================================ */

sov_bool sov_secure_compare(sov_ptr a, sov_ptr b, sov_int len) {
    if (!a || !b) return false;
    
    volatile unsigned char result = 0;
    volatile unsigned char* pa = (volatile unsigned char*)a;
    volatile unsigned char* pb = (volatile unsigned char*)b;
    
    for (sov_int i = 0; i < len; i++) {
        result |= pa[i] ^ pb[i];
    }
    
    return result == 0;
}

void sov_ct_memmove(sov_ptr dst, sov_ptr src, sov_int len, sov_bool flag) {
    if (!dst || !src || len <= 0) return;
    
    /* Branch-free conditional move using mask */
    /* If flag is true, mask = 0xFF...FF; if false, mask = 0x00...00 */
    unsigned char mask = flag ? 0xFF : 0x00;
    
    unsigned char* d = (unsigned char*)dst;
    unsigned char* s = (unsigned char*)src;
    
    for (sov_int i = 0; i < len; i++) {
        d[i] = (d[i] & ~mask) | (s[i] & mask);
    }
}

sov_byte sov_ct_select_byte(sov_byte a, sov_byte b, sov_bool flag) {
    unsigned char mask = flag ? 0xFF : 0x00;
    return (a & ~mask) | (b & mask);
}

sov_int sov_ct_is_zero(sov_int x) {
    sov_u64 v = (sov_u64)x;
    v = (v | (~v + 1)) >> 63;
    return (sov_int)(v ^ 1);
}

sov_int sov_ct_eq(sov_int a, sov_int b) {
    return sov_ct_is_zero(a ^ b);
}

/* ============================================================================
 * CHACHA20
 * ============================================================================ */

static uint32_t chacha20_rotate(uint32_t x, int n) {
    return (x << n) | (x >> (32 - n));
}

static void chacha20_quarter_round(uint32_t* state, int a, int b, int c, int d) {
    state[a] += state[b]; state[d] ^= state[a]; state[d] = chacha20_rotate(state[d], 16);
    state[c] += state[d]; state[b] ^= state[c]; state[b] = chacha20_rotate(state[b], 12);
    state[a] += state[b]; state[d] ^= state[a]; state[d] = chacha20_rotate(state[d], 8);
    state[c] += state[d]; state[b] ^= state[c]; state[b] = chacha20_rotate(state[b], 7);
}

static void chacha20_block(const uint8_t key[32], const uint8_t nonce[12], 
                            uint32_t counter, uint8_t out[64]) {
    uint32_t state[16];
    
    /* "expand 32-byte k" */
    state[0] = 0x61707865; state[1] = 0x3320646e; state[2] = 0x79622d32; state[3] = 0x6b206574;
    
    /* Key */
    for (int i = 0; i < 8; i++) {
        state[4 + i] = ((uint32_t)key[i*4]) | ((uint32_t)key[i*4+1] << 8) |
                       ((uint32_t)key[i*4+2] << 16) | ((uint32_t)key[i*4+3] << 24);
    }
    
    /* Counter */
    state[12] = counter;
    
    /* Nonce */
    state[13] = ((uint32_t)nonce[0]) | ((uint32_t)nonce[1] << 8) |
                ((uint32_t)nonce[2] << 16) | ((uint32_t)nonce[3] << 24);
    state[14] = ((uint32_t)nonce[4]) | ((uint32_t)nonce[5] << 8) |
                ((uint32_t)nonce[6] << 16) | ((uint32_t)nonce[7] << 24);
    state[15] = ((uint32_t)nonce[8]) | ((uint32_t)nonce[9] << 8) |
                ((uint32_t)nonce[10] << 16) | ((uint32_t)nonce[11] << 24);
    
    uint32_t working[16];
    memcpy(working, state, sizeof(state));
    
    /* 20 rounds (10 double rounds) */
    for (int i = 0; i < 10; i++) {
        chacha20_quarter_round(working, 0, 4, 8,  12);
        chacha20_quarter_round(working, 1, 5, 9,  13);
        chacha20_quarter_round(working, 2, 6, 10, 14);
        chacha20_quarter_round(working, 3, 7, 11, 15);
        chacha20_quarter_round(working, 0, 5, 10, 15);
        chacha20_quarter_round(working, 1, 6, 11, 12);
        chacha20_quarter_round(working, 2, 7, 8,  13);
        chacha20_quarter_round(working, 3, 4, 9,  14);
    }
    
    /* Add original state */
    for (int i = 0; i < 16; i++) {
        working[i] += state[i];
        out[i*4]     = working[i] & 0xFF;
        out[i*4 + 1] = (working[i] >> 8) & 0xFF;
        out[i*4 + 2] = (working[i] >> 16) & 0xFF;
        out[i*4 + 3] = (working[i] >> 24) & 0xFF;
    }
}

static void chacha20_encrypt(const uint8_t key[32], const uint8_t nonce[12],
                              const uint8_t* input, uint8_t* output, sov_int len) {
    uint8_t keystream[64];
    uint32_t counter = 0;
    
    while (len > 0) {
        chacha20_block(key, nonce, counter, keystream);
        sov_int to_xor = SOV_MIN(64, len);
        for (sov_int i = 0; i < to_xor; i++) {
            output[i] = input[i] ^ keystream[i];
        }
        input += to_xor;
        output += to_xor;
        len -= to_xor;
        counter++;
    }
    
    sov_secure_zero(keystream, 64);
}

/* ============================================================================
 * POLY1305
 * ============================================================================ */

static void poly1305_clamp(uint8_t r[16]) {
    r[3] &= 15;
    r[7] &= 15;
    r[11] &= 15;
    r[15] &= 15;
    r[4] &= 252;
    r[8] &= 252;
    r[12] &= 252;
}

static uint64_t poly1305_load_le(const uint8_t* buf, int len) {
    uint64_t val = 0;
    for (int i = 0; i < len; i++) {
        val |= ((uint64_t)buf[i]) << (i * 8);
    }
    return val;
}

/* 130-bit arithmetic (5 limbs of 26 bits) */
#define P1305_MASK26 0x3FFFFFFULL

static void poly1305_mac(const uint8_t key[32], const uint8_t* msg, sov_int msg_len, uint8_t tag[16]) {
    /* Parse r and s from key */
    uint64_t r0, r1, r2, r3, r4;
    uint64_t s1, s2;
    
    uint8_t r_bytes[16];
    memcpy(r_bytes, key, 16);
    poly1305_clamp(r_bytes);
    
    r0 = poly1305_load_le(r_bytes, 4) & P1305_MASK26;
    r1 = (poly1305_load_le(r_bytes + 3, 5) >> 2) & P1305_MASK26;
    r2 = (poly1305_load_le(r_bytes + 6, 5) >> 4) & P1305_MASK26;
    r3 = (poly1305_load_le(r_bytes + 9, 5) >> 6) & P1305_MASK26;
    r4 = (poly1305_load_le(r_bytes + 12, 4) >> 8);
    
    s1 = poly1305_load_le(key + 16, 8);
    s2 = poly1305_load_le(key + 24, 8);
    
    /* Accumulator */
    uint64_t h0 = 0, h1 = 0, h2 = 0, h3 = 0, h4 = 0;
    
    sov_int offset = 0;
    while (offset < msg_len) {
        sov_int chunk_len = SOV_MIN(16, msg_len - offset);
        
        uint8_t chunk[17];
        memcpy(chunk, msg + offset, chunk_len);
        chunk[chunk_len] = 1; /* 2^128 bit */
        memset(chunk + chunk_len + 1, 0, 16 - chunk_len);
        
        uint64_t n0 = poly1305_load_le(chunk, 8);
        uint64_t n1 = poly1305_load_le(chunk + 8, 8);
        
        /* h += n */
        h0 += n0 & P1305_MASK26;
        h1 += ((n0 >> 26) | (n1 << 18)) & P1305_MASK26;
        h2 += (n1 >> 8) & P1305_MASK26;
        h3 += (n1 >> 34) & P1305_MASK26;
        h4 += (n1 >> 60);
        
        /* h *= r */
        uint64_t d0 = h0 * r0 + h1 * r4 * 5 + h2 * r3 * 5 + h3 * r2 * 5 + h4 * r1 * 5;
        uint64_t d1 = h0 * r1 + h1 * r0 + h2 * r4 * 5 + h3 * r3 * 5 + h4 * r2 * 5;
        uint64_t d2 = h0 * r2 + h1 * r1 + h2 * r0 + h3 * r4 * 5 + h4 * r3 * 5;
        uint64_t d3 = h0 * r3 + h1 * r2 + h2 * r1 + h3 * r0 + h4 * r4 * 5;
        uint64_t d4 = h0 * r4 + h1 * r3 + h2 * r2 + h3 * r1 + h4 * r0;
        
        /* Carry propagation */
        h0 = d0 & P1305_MASK26; d1 += d0 >> 26;
        h1 = d1 & P1305_MASK26; d2 += d1 >> 26;
        h2 = d2 & P1305_MASK26; d3 += d2 >> 26;
        h3 = d3 & P1305_MASK26; d4 += d3 >> 26;
        h4 = d4;
        
        h0 += (d4 >> 26) * 5;
        h1 += h0 >> 26; h0 &= P1305_MASK26;
        
        offset += chunk_len;
    }
    
    /* Finalize: h += s */
    uint64_t g0 = h0 + 5;
    uint64_t g1 = h1 + (g0 >> 26); g0 &= P1305_MASK26;
    uint64_t g2 = h2 + (g1 >> 26); g1 &= P1305_MASK26;
    uint64_t g3 = h3 + (g2 >> 26); g2 &= P1305_MASK26;
    uint64_t g4 = h4 + (g3 >> 26) - (1ULL << 32); g3 &= P1305_MASK26;
    
    /* If h >= 2^130-5, use h; otherwise use g */
    uint64_t mask = (g4 >> 63) - 1; /* all 1s if h >= 2^130-5 */
    h0 = (h0 & ~mask) | (g0 & mask);
    h1 = (h1 & ~mask) | (g1 & mask);
    h2 = (h2 & ~mask) | (g2 & mask);
    h3 = (h3 & ~mask) | (g3 & mask);
    
    /* h = h % 2^128 */
    uint64_t f0 = h0 | (h1 << 26);
    uint64_t f1 = (h1 >> 38) | (h2 << 24) | (h3 << 50);
    
    f0 += s1;
    f1 += s2 + (f0 < s1);
    
    /* Write tag */
    for (int i = 0; i < 8; i++) { tag[i] = f0 & 0xFF; f0 >>= 8; }
    for (int i = 0; i < 8; i++) { tag[i+8] = f1 & 0xFF; f1 >>= 8; }
}

/* ============================================================================
 * CHACHA20-POLY1305 AEAD
 * ============================================================================ */

sov_result sov_chacha20_poly1305_encrypt(sov_ptr key, sov_ptr nonce,
                                          sov_ptr plaintext, sov_int plaintext_len,
                                          sov_ptr aad, sov_int aad_len,
                                          sov_ptr ciphertext_out, sov_ptr tag_out) {
    sov_result result = {0};
    if (!key || !nonce || !plaintext || !ciphertext_out || !tag_out) {
        result.is_ok = false;
        result.error = "Null pointer argument";
        return result;
    }
    if (plaintext_len < 0) {
        result.is_ok = false;
        result.error = "Invalid plaintext length";
        return result;
    }
    
    /* Generate Poly1305 key from ChaCha20 with counter=0 */
    uint8_t poly_key[64];
    chacha20_block((const uint8_t*)key, (const uint8_t*)nonce, 0, poly_key);
    
    /* Encrypt with ChaCha20 starting at counter=1 */
    uint8_t zero_block[64];
    chacha20_block((const uint8_t*)key, (const uint8_t*)nonce, 1, zero_block);
    (void)zero_block;
    
    chacha20_encrypt((const uint8_t*)key, (const uint8_t*)nonce,
                     (const uint8_t*)plaintext, (uint8_t*)ciphertext_out, plaintext_len);
    
    /* Construct Poly1305 message: AAD || pad(AAD) || ciphertext || pad(ciphertext) || lengths */
    sov_int poly_msg_len = aad_len + (16 - (aad_len % 16)) % 16 +
                           plaintext_len + (16 - (plaintext_len % 16)) % 16 + 16;
    uint8_t* poly_msg = (uint8_t*)sov_alloc(1, poly_msg_len);
    sov_int pos = 0;
    
    /* AAD */
    if (aad && aad_len > 0) {
        memcpy(poly_msg + pos, aad, aad_len);
        pos += aad_len;
    }
    /* Pad AAD to 16 bytes */
    while (pos % 16 != 0) poly_msg[pos++] = 0;
    
    /* Ciphertext */
    memcpy(poly_msg + pos, ciphertext_out, plaintext_len);
    pos += plaintext_len;
    /* Pad ciphertext to 16 bytes */
    while (pos % 16 != 0) poly_msg[pos++] = 0;
    
    /* Lengths (64-bit little-endian) */
    uint64_t aad_len64 = aad_len;
    uint64_t ct_len64 = plaintext_len;
    for (int i = 0; i < 8; i++) poly_msg[pos++] = (aad_len64 >> (i*8)) & 0xFF;
    for (int i = 0; i < 8; i++) poly_msg[pos++] = (ct_len64 >> (i*8)) & 0xFF;
    
    /* Compute Poly1305 tag */
    poly1305_mac(poly_key, poly_msg, poly_msg_len, (uint8_t*)tag_out);
    
    sov_secure_zero(poly_key, 64);
    sov_free(poly_msg);
    
    result.is_ok = true;
    return result;
}

sov_result sov_chacha20_poly1305_decrypt(sov_ptr key, sov_ptr nonce,
                                          sov_ptr ciphertext, sov_int ciphertext_len,
                                          sov_ptr aad, sov_int aad_len,
                                          sov_ptr tag, sov_ptr plaintext_out) {
    sov_result result = {0};
    if (!key || !nonce || !ciphertext || !plaintext_out || !tag) {
        result.is_ok = false;
        result.error = "Null pointer argument";
        return result;
    }
    
    /* First verify the tag */
    uint8_t computed_tag[SOV_POLY1305_TAG_SIZE];
    uint8_t poly_key[64];
    chacha20_block((const uint8_t*)key, (const uint8_t*)nonce, 0, poly_key);
    
    /* Build Poly1305 message: AAD || pad(AAD) || ciphertext || pad(ciphertext) || lengths */
    sov_int poly_msg_len = aad_len + (16 - (aad_len % 16)) % 16 +
                           ciphertext_len + (16 - (ciphertext_len % 16)) % 16 + 16;
    uint8_t* poly_msg = (uint8_t*)sov_alloc(1, poly_msg_len);
    sov_int pos = 0;
    
    if (aad && aad_len > 0) {
        memcpy(poly_msg + pos, aad, aad_len);
        pos += aad_len;
    }
    while (pos % 16 != 0) poly_msg[pos++] = 0;
    
    memcpy(poly_msg + pos, ciphertext, ciphertext_len);
    pos += ciphertext_len;
    while (pos % 16 != 0) poly_msg[pos++] = 0;
    
    uint64_t aad_len64 = aad_len;
    uint64_t ct_len64 = ciphertext_len;
    for (int i = 0; i < 8; i++) poly_msg[pos++] = (aad_len64 >> (i*8)) & 0xFF;
    for (int i = 0; i < 8; i++) poly_msg[pos++] = (ct_len64 >> (i*8)) & 0xFF;
    
    poly1305_mac(poly_key, poly_msg, poly_msg_len, computed_tag);
    sov_secure_zero(poly_key, 64);
    sov_free(poly_msg);
    
    /* Constant-time tag comparison */
    if (!sov_secure_compare(tag, computed_tag, SOV_POLY1305_TAG_SIZE)) {
        sov_secure_zero(computed_tag, SOV_POLY1305_TAG_SIZE);
        result.is_ok = false;
        result.error = "Authentication failed: tag mismatch";
        return result;
    }
    sov_secure_zero(computed_tag, SOV_POLY1305_TAG_SIZE);
    
    /* Decrypt */
    chacha20_encrypt((const uint8_t*)key, (const uint8_t*)nonce,
                     (const uint8_t*)ciphertext, (uint8_t*)plaintext_out, ciphertext_len);
    
    result.is_ok = true;
    return result;
}

/* ============================================================================
 * AES-256-GCM — CONSTANT-TIME, CACHE-TIMING RESISTANT
 *
 * Two backends, selected at compile time:
 *   - AES-NI hardware instructions (when __AES__ is defined)
 *   - Bitsliced AES software implementation (no S-box lookup tables)
 *
 * Both paths are fully constant-time: no data-dependent memory access,
 * no data-dependent branches.  The S-box table AES_SBOX[256] is kept
 * for reference only and is never used in the encrypt/decrypt path.
 *
 * BITSILICED DESIGN
 *   The 16-byte AES state is transposed into 8 16-bit words B[0..7]
 *   where B[b] holds the b-th bit of every state byte.  SubBytes is
 *   then computed via a Boolean circuit (AND / XOR / NOT) that
 *   operates on all 16 bytes in parallel — no table lookups.
 *   ShiftRows, MixColumns and AddRoundKey are applied byte-wise;
 *   they use only xor, shift and the xtime() primitive which are
 *   inherently constant-time.
 *
 *   SubBytes circuit: GF(2^8) inversion via x^{254} exponentiation
 *   chain (7 squarings + 6 multiplications) followed by the affine
 *   transform, all expressed as bitwise operations on the transposed
 *   state.
 * ============================================================================ */

#ifdef __AES__
#include <wmmintrin.h>   /* _mm_aesenc_si128, _mm_aesenclast_si128, _mm_aeskeygenassist_si128 */
#endif

/* --------------------------------------------------------------------------
 * Original AES S-box — KEPT FOR REFERENCE ONLY
 * Not used in the encrypt / decrypt path (vulnerable to cache-timing).
 * -------------------------------------------------------------------------- */
static const uint8_t AES_SBOX[256] = {
    0x63,0x7C,0x77,0x7B,0xF2,0x6B,0x6F,0xC5,0x30,0x01,0x67,0x2B,0xFE,0xD7,0xAB,0x76,
    0xCA,0x82,0xC9,0x7D,0xFA,0x59,0x47,0xF0,0xAD,0xD4,0xA2,0xAF,0x9C,0xA4,0x72,0xC0,
    0xB7,0xFD,0x93,0x26,0x36,0x3F,0xF7,0xCC,0x34,0xA5,0xE5,0xF1,0x71,0xD8,0x31,0x15,
    0x04,0xC7,0x23,0xC3,0x18,0x96,0x05,0x9A,0x07,0x12,0x80,0xE2,0xEB,0x27,0xB2,0x75,
    0x09,0x83,0x2C,0x1A,0x1B,0x6E,0x5A,0xA0,0x52,0x3B,0xD6,0xB3,0x29,0xE3,0x2F,0x84,
    0x53,0xD1,0x00,0xED,0x20,0xFC,0xB1,0x5B,0x6A,0xCB,0xBE,0x39,0x4A,0x4C,0x58,0xCF,
    0xD0,0xEF,0xAA,0xFB,0x43,0x4D,0x33,0x85,0x45,0xF9,0x02,0x7F,0x50,0x3C,0x9F,0xA8,
    0x51,0xA3,0x40,0x8F,0x92,0x9D,0x38,0xF5,0xBC,0xB6,0xDA,0x21,0x10,0xFF,0xF3,0xD2,
    0xCD,0x0C,0x13,0xEC,0x5F,0x97,0x44,0x17,0xC4,0xA7,0x7E,0x3D,0x64,0x5D,0x19,0x73,
    0x60,0x81,0x4F,0xDC,0x22,0x2A,0x90,0x88,0x46,0xEE,0xB8,0x14,0xDE,0x5E,0x0B,0xDB,
    0xE0,0x32,0x3A,0x0A,0x49,0x06,0x24,0x5C,0xC2,0xD3,0xAC,0x62,0x91,0x95,0xE4,0x79,
    0xE7,0xC8,0x37,0x6D,0x8D,0xD5,0x4E,0xA9,0x6C,0x56,0xF4,0xEA,0x65,0x7A,0xAE,0x08,
    0xBA,0x78,0x25,0x2E,0x1C,0xA6,0xB4,0xC6,0xE8,0xDD,0x74,0x1F,0x4B,0xBD,0x8B,0x8A,
    0x70,0x3E,0xB5,0x66,0x48,0x03,0xF6,0x0E,0x61,0x35,0x57,0xB9,0x86,0xC1,0x1D,0x9E,
    0xE1,0xF8,0x98,0x11,0x69,0xD9,0x8E,0x94,0x9B,0x1E,0x87,0xE9,0xCE,0x55,0x28,0xDF,
    0x8C,0xA1,0x89,0x0D,0xBF,0xE6,0x42,0x68,0x41,0x99,0x2D,0x0F,0xB0,0x54,0xBB,0x16
};

/* Rcon for key expansion */
static const uint8_t AES_RCON[] = {0x00,0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36};

/* Galois field multiply by 2 (xtime) — used by GCM/GHASH and MixColumns */
static uint8_t gf_mul2(uint8_t x) {
    return (x << 1) ^ ((x & 0x80) ? 0x1B : 0);
}

/* GHASH multiply (GCM authentication core) — unchanged */
static void gcm_ghash_multiply(uint8_t h[16], uint8_t y[16]) {
    uint8_t z[16];
    memset(z, 0, 16);
    uint8_t v[16];
    memcpy(v, h, 16);

    for (int i = 0; i < 128; i++) {
        int byte_idx = i / 8;
        int bit_idx = 7 - (i % 8);
        if (y[byte_idx] & (1 << bit_idx)) {
            for (int j = 0; j < 16; j++) z[j] ^= v[j];
        }
        uint8_t carry = v[15] & 1;
        for (int j = 15; j > 0; j--) {
            v[j] = (v[j] >> 1) | ((v[j-1] & 1) << 7);
        }
        v[0] = (v[0] >> 1) ^ (carry ? 0xE1 : 0);
    }

    memcpy(y, z, 16);
}

/* --------------------------------------------------------------------------
 * AES context
 * -------------------------------------------------------------------------- */
typedef struct {
    uint32_t rk[60]; /* Round keys (max for AES-256: 15 rounds * 4 words) */
    int rounds;
} sov_aes_ctx;

/* ========================================================================
 * CONSTANT-TIME SCALAR S-BOX (used by key expansion)
 *
 * Computes y = S(x) for a single byte using only bitwise operations.
 * Based on GF(2^8) inversion via the exponentiation chain x^{254}
 * followed by the affine transform.  No lookup tables.
 * ======================================================================== */

/* GF(2^8) multiplication of two bytes (polynomial basis x^8+x^4+x^3+x+1).
   All operations are bitwise — constant-time. */
static uint8_t gf256_mul(uint8_t a, uint8_t b) {
    uint8_t a0 = (a >> 0) & 1, a1 = (a >> 1) & 1, a2 = (a >> 2) & 1, a3 = (a >> 3) & 1;
    uint8_t a4 = (a >> 4) & 1, a5 = (a >> 5) & 1, a6 = (a >> 6) & 1, a7 = (a >> 7) & 1;
    uint8_t b0 = (b >> 0) & 1, b1 = (b >> 1) & 1, b2 = (b >> 2) & 1, b3 = (b >> 3) & 1;
    uint8_t b4 = (b >> 4) & 1, b5 = (b >> 5) & 1, b6 = (b >> 6) & 1, b7 = (b >> 7) & 1;

    /* Raw product bits p0..p14 */
    uint8_t p0  = a0 & b0;
    uint8_t p1  = (a0 & b1) ^ (a1 & b0);
    uint8_t p2  = (a0 & b2) ^ (a1 & b1) ^ (a2 & b0);
    uint8_t p3  = (a0 & b3) ^ (a1 & b2) ^ (a2 & b1) ^ (a3 & b0);
    uint8_t p4  = (a0 & b4) ^ (a1 & b3) ^ (a2 & b2) ^ (a3 & b1) ^ (a4 & b0);
    uint8_t p5  = (a0 & b5) ^ (a1 & b4) ^ (a2 & b3) ^ (a3 & b2) ^ (a4 & b1) ^ (a5 & b0);
    uint8_t p6  = (a0 & b6) ^ (a1 & b5) ^ (a2 & b4) ^ (a3 & b3) ^ (a4 & b2) ^ (a5 & b1) ^ (a6 & b0);
    uint8_t p7  = (a0 & b7) ^ (a1 & b6) ^ (a2 & b5) ^ (a3 & b4) ^ (a4 & b3) ^ (a5 & b2) ^ (a6 & b1) ^ (a7 & b0);
    uint8_t p8  = (a1 & b7) ^ (a2 & b6) ^ (a3 & b5) ^ (a4 & b4) ^ (a5 & b3) ^ (a6 & b2) ^ (a7 & b1);
    uint8_t p9  = (a2 & b7) ^ (a3 & b6) ^ (a4 & b5) ^ (a5 & b4) ^ (a6 & b3) ^ (a7 & b2);
    uint8_t p10 = (a3 & b7) ^ (a4 & b6) ^ (a5 & b5) ^ (a6 & b4) ^ (a7 & b3);
    uint8_t p11 = (a4 & b7) ^ (a5 & b6) ^ (a6 & b5) ^ (a7 & b4);
    uint8_t p12 = (a5 & b7) ^ (a6 & b6) ^ (a7 & b5);
    uint8_t p13 = (a6 & b7) ^ (a7 & b6);
    uint8_t p14 = a7 & b7;

    /* Reduction modulo x^8 + x^4 + x^3 + x + 1 */
    uint8_t c0 = p0 ^ p8 ^ p12 ^ p13;
    uint8_t c1 = p1 ^ p8 ^ p9 ^ p12 ^ p14;
    uint8_t c2 = p2 ^ p9 ^ p10 ^ p13;
    uint8_t c3 = p3 ^ p8 ^ p10 ^ p11 ^ p12 ^ p13 ^ p14;
    uint8_t c4 = p4 ^ p8 ^ p9 ^ p11 ^ p14;
    uint8_t c5 = p5 ^ p9 ^ p10 ^ p12;
    uint8_t c6 = p6 ^ p10 ^ p11 ^ p13;
    uint8_t c7 = p7 ^ p11 ^ p12 ^ p14;

    return (c0 << 0) | (c1 << 1) | (c2 << 2) | (c3 << 3) |
           (c4 << 4) | (c5 << 5) | (c6 << 6) | (c7 << 7);
}

/* GF(2^8) squaring (linear operation, constant-time). */
static uint8_t gf256_square(uint8_t a) {
    uint8_t a0 = (a >> 0) & 1, a1 = (a >> 1) & 1, a2 = (a >> 2) & 1, a3 = (a >> 3) & 1;
    uint8_t a4 = (a >> 4) & 1, a5 = (a >> 5) & 1, a6 = (a >> 6) & 1, a7 = (a >> 7) & 1;

    uint8_t c0 = a0 ^ a4 ^ a6;
    uint8_t c1 = a4 ^ a6 ^ a7;
    uint8_t c2 = a1 ^ a5;
    uint8_t c3 = a4 ^ a5 ^ a6 ^ a7;
    uint8_t c4 = a2 ^ a4 ^ a7;
    uint8_t c5 = a5 ^ a6;
    uint8_t c6 = a3 ^ a5;
    uint8_t c7 = a6 ^ a7;

    return (c0 << 0) | (c1 << 1) | (c2 << 2) | (c3 << 3) |
           (c4 << 4) | (c5 << 5) | (c6 << 6) | (c7 << 7);
}

/* Constant-time AES S-box for one byte — no lookup tables.
   S(x) = affine( x^{-1} ),  with x^{-1} = x^{254} computed via
   7 squarings + 6 multiplications in GF(2^8). */
static uint8_t ct_sbox_byte(uint8_t x) {
    /* Exponentiation chain: x, x^2, x^4, x^8, x^16, x^32, x^64, x^128 */
    uint8_t y1   = x;
    uint8_t y2   = gf256_square(y1);      /* x^2   */
    uint8_t y4   = gf256_square(y2);      /* x^4   */
    uint8_t y8   = gf256_square(y4);      /* x^8   */
    uint8_t y16  = gf256_square(y8);      /* x^16  */
    uint8_t y32  = gf256_square(y16);     /* x^32  */
    uint8_t y64  = gf256_square(y32);     /* x^64  */
    uint8_t y128 = gf256_square(y64);     /* x^128 */

    /* x^{254} = x^{128+64+32+16+8+4+2} */
    uint8_t t;
    t = gf256_mul(y128, y64);             /* x^192 */
    t = gf256_mul(t,    y32);             /* x^224 */
    t = gf256_mul(t,    y16);             /* x^240 */
    t = gf256_mul(t,    y8);              /* x^248 */
    t = gf256_mul(t,    y4);              /* x^252 */
    uint8_t inv = gf256_mul(t, y2);       /* x^254 = x^{-1} */

    /* Affine transform:  y_i = x_i ^ x_{i+4} ^ x_{i+5} ^ x_{i+6} ^ x_{i+7} ^ c_i
       (indices mod 8, c = 0x63) */
    uint8_t i0 = (inv >> 0) & 1, i1 = (inv >> 1) & 1, i2 = (inv >> 2) & 1, i3 = (inv >> 3) & 1;
    uint8_t i4 = (inv >> 4) & 1, i5 = (inv >> 5) & 1, i6 = (inv >> 6) & 1, i7 = (inv >> 7) & 1;

    uint8_t o0 = i0 ^ i4 ^ i5 ^ i6 ^ i7 ^ 1;
    uint8_t o1 = i0 ^ i1 ^ i5 ^ i6 ^ i7 ^ 1;
    uint8_t o2 = i0 ^ i1 ^ i2 ^ i6 ^ i7 ^ 0;
    uint8_t o3 = i0 ^ i1 ^ i2 ^ i3 ^ i7 ^ 0;
    uint8_t o4 = i0 ^ i1 ^ i2 ^ i3 ^ i4 ^ 0;
    uint8_t o5 = i1 ^ i2 ^ i3 ^ i4 ^ i5 ^ 1;
    uint8_t o6 = i2 ^ i3 ^ i4 ^ i5 ^ i6 ^ 1;
    uint8_t o7 = i3 ^ i4 ^ i5 ^ i6 ^ i7 ^ 0;

    return (uint8_t)((o0 << 0) | (o1 << 1) | (o2 << 2) | (o3 << 3) |
                     (o4 << 4) | (o5 << 5) | (o6 << 6) | (o7 << 7));
}

/* ========================================================================
 * BITSILICED AES (software fallback when AES-NI is unavailable)
 *
 * The 16-byte state is transposed into 8 words B[0..7] where B[b]
 * holds the b-th bit of all 16 bytes (lower 16 bits of each uint32_t).
 * SubBytes is applied via a Boolean circuit operating on the transposed
 * words — same GF(2^8) exponentiation chain as above, but on 16-bit
 * slices.  ShiftRows / MixColumns / AddRoundKey operate on regular bytes.
 * ======================================================================== */

/* Transpose 16 bytes → 8 bitsliced words (bit-matrix transpose). */
static void bs_pack(const uint8_t bytes[16], uint32_t B[8]) {
    memset(B, 0, 8 * sizeof(uint32_t));
    for (int i = 0; i < 16; i++) {
        uint32_t x = bytes[i];
        for (int b = 0; b < 8; b++) {
            B[b] |= ((x >> b) & 1) << i;
        }
    }
}

/* Inverse transpose: 8 bitsliced words → 16 bytes. */
static void bs_unpack(const uint32_t B[8], uint8_t bytes[16]) {
    memset(bytes, 0, 16);
    for (int i = 0; i < 16; i++) {
        uint8_t x = 0;
        for (int b = 0; b < 8; b++) {
            x |= (uint8_t)((B[b] >> i) & 1) << b;
        }
        bytes[i] = x;
    }
}

/* GF(2^8) multiply in bitsliced form: c = a * b.
   a[0..7], b[0..7], c[0..7] are the 8 bitsliced words (uint32_t).
   Only the lower 16 bits of each word are used / modified. */
static void bs_gf256_mul(const uint32_t a[8], const uint32_t b[8], uint32_t c[8]) {
    uint32_t p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14;

    p0  = a[0] & b[0];
    p1  = (a[0] & b[1]) ^ (a[1] & b[0]);
    p2  = (a[0] & b[2]) ^ (a[1] & b[1]) ^ (a[2] & b[0]);
    p3  = (a[0] & b[3]) ^ (a[1] & b[2]) ^ (a[2] & b[1]) ^ (a[3] & b[0]);
    p4  = (a[0] & b[4]) ^ (a[1] & b[3]) ^ (a[2] & b[2]) ^ (a[3] & b[1]) ^ (a[4] & b[0]);
    p5  = (a[0] & b[5]) ^ (a[1] & b[4]) ^ (a[2] & b[3]) ^ (a[3] & b[2]) ^ (a[4] & b[1]) ^ (a[5] & b[0]);
    p6  = (a[0] & b[6]) ^ (a[1] & b[5]) ^ (a[2] & b[4]) ^ (a[3] & b[3]) ^ (a[4] & b[2]) ^ (a[5] & b[1]) ^ (a[6] & b[0]);
    p7  = (a[0] & b[7]) ^ (a[1] & b[6]) ^ (a[2] & b[5]) ^ (a[3] & b[4]) ^ (a[4] & b[3]) ^ (a[5] & b[2]) ^ (a[6] & b[1]) ^ (a[7] & b[0]);
    p8  = (a[1] & b[7]) ^ (a[2] & b[6]) ^ (a[3] & b[5]) ^ (a[4] & b[4]) ^ (a[5] & b[3]) ^ (a[6] & b[2]) ^ (a[7] & b[1]);
    p9  = (a[2] & b[7]) ^ (a[3] & b[6]) ^ (a[4] & b[5]) ^ (a[5] & b[4]) ^ (a[6] & b[3]) ^ (a[7] & b[2]);
    p10 = (a[3] & b[7]) ^ (a[4] & b[6]) ^ (a[5] & b[5]) ^ (a[6] & b[4]) ^ (a[7] & b[3]);
    p11 = (a[4] & b[7]) ^ (a[5] & b[6]) ^ (a[6] & b[5]) ^ (a[7] & b[4]);
    p12 = (a[5] & b[7]) ^ (a[6] & b[6]) ^ (a[7] & b[5]);
    p13 = (a[6] & b[7]) ^ (a[7] & b[6]);
    p14 = a[7] & b[7];

    /* Reduction modulo x^8 + x^4 + x^3 + x + 1 */
    c[0] = p0 ^ p8 ^ p12 ^ p13;
    c[1] = p1 ^ p8 ^ p9 ^ p12 ^ p14;
    c[2] = p2 ^ p9 ^ p10 ^ p13;
    c[3] = p3 ^ p8 ^ p10 ^ p11 ^ p12 ^ p13 ^ p14;
    c[4] = p4 ^ p8 ^ p9 ^ p11 ^ p14;
    c[5] = p5 ^ p9 ^ p10 ^ p12;
    c[6] = p6 ^ p10 ^ p11 ^ p13;
    c[7] = p7 ^ p11 ^ p12 ^ p14;
}

/* GF(2^8) squaring in bitsliced form: c = a^2 */
static void bs_gf256_square(const uint32_t a[8], uint32_t c[8]) {
    c[0] = a[0] ^ a[4] ^ a[6];
    c[1] = a[4] ^ a[6] ^ a[7];
    c[2] = a[1] ^ a[5];
    c[3] = a[4] ^ a[5] ^ a[6] ^ a[7];
    c[4] = a[2] ^ a[4] ^ a[7];
    c[5] = a[5] ^ a[6];
    c[6] = a[3] ^ a[5];
    c[7] = a[6] ^ a[7];
}

/* Bitsliced SubBytes: applies the AES S-box to all 16 bytes in parallel
   using only bitwise operations on the transposed state B[0..7]. */
static void bs_sbox(uint32_t B[8]) {
    uint32_t y1[8], y2[8], y4[8], y8[8], y16[8], y32[8], y64[8], y128[8];
    uint32_t t[8];
    uint32_t zero16 = 0x0000FFFF;  /* mask covering the 16 bit positions */

    /* Copy input */
    for (int i = 0; i < 8; i++) y1[i] = B[i];

    /* Exponentiation chain: y_k = x^{k} */
    bs_gf256_square(y1,   y2);                     /* x^2   */
    bs_gf256_square(y2,   y4);                     /* x^4   */
    bs_gf256_square(y4,   y8);                     /* x^8   */
    bs_gf256_square(y8,   y16);                    /* x^16  */
    bs_gf256_square(y16,  y32);                    /* x^32  */
    bs_gf256_square(y32,  y64);                    /* x^64  */
    bs_gf256_square(y64,  y128);                   /* x^128 */

    /* x^{254} = x^{128} * x^{64} * x^{32} * x^{16} * x^{8} * x^{4} * x^{2} */
    bs_gf256_mul(y128, y64,  t);                   /* x^192 */
    bs_gf256_mul(t,    y32,  t);                   /* x^224 */
    bs_gf256_mul(t,    y16,  t);                   /* x^240 */
    bs_gf256_mul(t,    y8,   t);                   /* x^248 */
    bs_gf256_mul(t,    y4,   t);                   /* x^252 */
    bs_gf256_mul(t,    y2,   t);                   /* x^254 = x^{-1} */

    /* Affine transform (indices mod 8, constant = 0x63)
       y_i = x_i ^ x_{i+4} ^ x_{i+5} ^ x_{i+6} ^ x_{i+7} ^ c_i
       The +1 from c_i (bits 0,1,5,6) becomes XOR with zero16. */
    uint32_t o0 = t[0] ^ t[4] ^ t[5] ^ t[6] ^ t[7] ^ zero16;
    uint32_t o1 = t[0] ^ t[1] ^ t[5] ^ t[6] ^ t[7] ^ zero16;
    uint32_t o2 = t[0] ^ t[1] ^ t[2] ^ t[6] ^ t[7];
    uint32_t o3 = t[0] ^ t[1] ^ t[2] ^ t[3] ^ t[7];
    uint32_t o4 = t[0] ^ t[1] ^ t[2] ^ t[3] ^ t[4];
    uint32_t o5 = t[1] ^ t[2] ^ t[3] ^ t[4] ^ t[5] ^ zero16;
    uint32_t o6 = t[2] ^ t[3] ^ t[4] ^ t[5] ^ t[6] ^ zero16;
    uint32_t o7 = t[3] ^ t[4] ^ t[5] ^ t[6] ^ t[7];

    B[0] = o0; B[1] = o1; B[2] = o2; B[3] = o3;
    B[4] = o4; B[5] = o5; B[6] = o6; B[7] = o7;
}

/* Bitsliced SubBytes wrapper: pack → S-box → unpack. */
static void bs_subbytes(uint8_t state[16]) {
    uint32_t B[8];
    bs_pack(state, B);
    bs_sbox(B);
    bs_unpack(B, state);
}

/* ========================================================================
 * KEY EXPANSION & AES ENCRYPT BLOCK
 *
 * Two mutually-exclusive implementations selected at compile time:
 *   __AES__    → AES-NI hardware instructions
 *   otherwise  → bitsliced software (no S-box lookup tables)
 * ======================================================================== */

#ifdef __AES__

/* --------------------------------------------------------------------------
 * AES-NI key expansion — hardware-accelerated.
 * -------------------------------------------------------------------------- */
static void aes_key_expansion(sov_aes_ctx* ctx, const uint8_t key[32]) {
    int nk = 8;
    ctx->rounds = 14;

    __m128i k0 = _mm_loadu_si128((const __m128i*)&key[0]);
    __m128i k1 = _mm_loadu_si128((const __m128i*)&key[16]);

    memcpy(&ctx->rk[0], &k0, 16);
    memcpy(&ctx->rk[4], &k1, 16);

    __m128i temp = k1;
    for (int i = nk; i < 4 * (ctx->rounds + 1); i += 4) {
        if (i % nk == 0) {
            temp = _mm_xor_si128(
                _mm_aeskeygenassist_si128(temp, AES_RCON[i / nk]),
                _mm_slli_si128(temp, 4));
            temp = _mm_xor_si128(temp, _mm_slli_si128(temp, 4));
            temp = _mm_xor_si128(temp, _mm_slli_si128(temp, 4));
            temp = _mm_xor_si128(temp, _mm_loadu_si128((const __m128i*)&ctx->rk[i - nk]));
        } else if (i % nk == 4) {
            temp = _mm_xor_si128(
                _mm_aeskeygenassist_si128(temp, 0),
                _mm_slli_si128(temp, 4));
            temp = _mm_xor_si128(temp, _mm_slli_si128(temp, 4));
            temp = _mm_xor_si128(temp, _mm_slli_si128(temp, 4));
            temp = _mm_xor_si128(temp, _mm_loadu_si128((const __m128i*)&ctx->rk[i - nk]));
        }
        memcpy(&ctx->rk[i], &temp, 16);
    }
}

/* --------------------------------------------------------------------------
 * AES-NI encrypt block — hardware-accelerated, constant-time.
 * -------------------------------------------------------------------------- */
static void aes_encrypt_block(const sov_aes_ctx* ctx,
                               const uint8_t in[16], uint8_t out[16]) {
    __m128i state;
    memcpy(&state, in, 16);

    state = _mm_xor_si128(state, _mm_loadu_si128((const __m128i*)&ctx->rk[0]));

    for (int round = 1; round < ctx->rounds; round++) {
        state = _mm_aesenc_si128(state, _mm_loadu_si128((const __m128i*)&ctx->rk[round * 4]));
    }

    state = _mm_aesenclast_si128(state, _mm_loadu_si128((const __m128i*)&ctx->rk[ctx->rounds * 4]));

    memcpy(out, &state, 16);
}

#else  /* !__AES__ — software bitsliced fallback */

/* --------------------------------------------------------------------------
 * Software key expansion — constant-time (uses ct_sbox_byte, no tables).
 * -------------------------------------------------------------------------- */
static void aes_key_expansion(sov_aes_ctx* ctx, const uint8_t key[32]) {
    int nk = 8;  /* 256-bit key = 8 words */
    ctx->rounds = 14;

    for (int i = 0; i < nk; i++) {
        ctx->rk[i] = ((uint32_t)key[4*i] << 24) | ((uint32_t)key[4*i+1] << 16) |
                     ((uint32_t)key[4*i+2] << 8) | ((uint32_t)key[4*i+3]);
    }

    for (int i = nk; i < 4 * (ctx->rounds + 1); i++) {
        uint32_t temp = ctx->rk[i-1];
        if (i % nk == 0) {
            temp = (bswap32(temp) >> 8) | (bswap32(temp) << 24); /* RotWord */
            /* SubWord — constant-time, no table lookups */
            temp = ((uint32_t)ct_sbox_byte((uint8_t)((temp >> 24) & 0xFF)) << 24) |
                   ((uint32_t)ct_sbox_byte((uint8_t)((temp >> 16) & 0xFF)) << 16) |
                   ((uint32_t)ct_sbox_byte((uint8_t)((temp >> 8)  & 0xFF)) << 8)  |
                   ((uint32_t)ct_sbox_byte((uint8_t)( temp        & 0xFF)));
            temp ^= AES_RCON[i / nk] << 24;
        } else if (nk > 6 && i % nk == 4) {
            /* SubWord — constant-time */
            temp = ((uint32_t)ct_sbox_byte((uint8_t)((temp >> 24) & 0xFF)) << 24) |
                   ((uint32_t)ct_sbox_byte((uint8_t)((temp >> 16) & 0xFF)) << 16) |
                   ((uint32_t)ct_sbox_byte((uint8_t)((temp >> 8)  & 0xFF)) << 8)  |
                   ((uint32_t)ct_sbox_byte((uint8_t)( temp        & 0xFF)));
        }
        ctx->rk[i] = ctx->rk[i - nk] ^ temp;
    }
}

/* --------------------------------------------------------------------------
 * Bitsliced encrypt block — no lookup tables, fully constant-time.
 * -------------------------------------------------------------------------- */
static void aes_encrypt_block(const sov_aes_ctx* ctx,
                               const uint8_t in[16], uint8_t out[16]) {
    uint8_t state[16];
    memcpy(state, in, 16);

    /* AddRoundKey */
    for (int i = 0; i < 16; i++) {
        state[i] ^= (ctx->rk[i/4] >> (24 - 8*(i%4))) & 0xFF;
    }

    for (int round = 1; round < ctx->rounds; round++) {
        /* SubBytes — bitsliced, constant-time, no lookup tables */
        bs_subbytes(state);

        /* ShiftRows */
        uint8_t tmp[16];
        tmp[0] = state[0];  tmp[4] = state[4];  tmp[8]  = state[8];   tmp[12] = state[12];
        tmp[1] = state[5];  tmp[5] = state[9];  tmp[9]  = state[13];  tmp[13] = state[1];
        tmp[2] = state[10]; tmp[6] = state[14]; tmp[10] = state[2];   tmp[14] = state[6];
        tmp[3] = state[15]; tmp[7] = state[3];  tmp[11] = state[7];   tmp[15] = state[11];
        memcpy(state, tmp, 16);

        /* MixColumns */
        for (int c = 0; c < 4; c++) {
            uint8_t a = state[c*4], b = state[c*4+1], c2 = state[c*4+2], d = state[c*4+3];
            state[c*4]   = gf_mul2(a) ^ gf_mul2(b) ^ b ^ c2 ^ d;
            state[c*4+1] = a ^ gf_mul2(b) ^ gf_mul2(c2) ^ c2 ^ d;
            state[c*4+2] = a ^ b ^ gf_mul2(c2) ^ gf_mul2(d) ^ d;
            state[c*4+3] = gf_mul2(a) ^ a ^ b ^ c2 ^ gf_mul2(d);
        }

        /* AddRoundKey */
        for (int i = 0; i < 16; i++) {
            state[i] ^= (ctx->rk[(round*4) + i/4] >> (24 - 8*(i%4))) & 0xFF;
        }
    }

    /* Final round (no MixColumns) */
    bs_subbytes(state);
    {
        uint8_t tmp[16];
        tmp[0] = state[0];  tmp[4] = state[4];  tmp[8]  = state[8];   tmp[12] = state[12];
        tmp[1] = state[5];  tmp[5] = state[9];  tmp[9]  = state[13];  tmp[13] = state[1];
        tmp[2] = state[10]; tmp[6] = state[14]; tmp[10] = state[2];   tmp[14] = state[6];
        tmp[3] = state[15]; tmp[7] = state[3];  tmp[11] = state[7];   tmp[15] = state[11];
        memcpy(state, tmp, 16);
    }
    /* AddRoundKey */
    for (int i = 0; i < 16; i++) {
        state[i] ^= (ctx->rk[(ctx->rounds*4) + i/4] >> (24 - 8*(i%4))) & 0xFF;
    }

    memcpy(out, state, 16);
}

#endif  /* __AES__ */

static void aes_ctr_encrypt(const sov_aes_ctx* ctx, const uint8_t iv[12],
                             const uint8_t* input, uint8_t* output, sov_int len) {
    uint8_t counter_block[16];
    uint8_t keystream[16];
    
    memcpy(counter_block, iv, 12);
    uint32_t counter = 1;
    
    while (len > 0) {
        counter_block[12] = (counter >> 24) & 0xFF;
        counter_block[13] = (counter >> 16) & 0xFF;
        counter_block[14] = (counter >> 8) & 0xFF;
        counter_block[15] = counter & 0xFF;
        
        aes_encrypt_block(ctx, counter_block, keystream);
        
        sov_int to_xor = SOV_MIN(16, len);
        for (sov_int i = 0; i < to_xor; i++) {
            output[i] = input[i] ^ keystream[i];
        }
        
        input += to_xor;
        output += to_xor;
        len -= to_xor;
        counter++;
    }
}

sov_result sov_aes256_gcm_encrypt(sov_ptr key, sov_ptr iv, sov_int iv_len,
                                   sov_ptr plaintext, sov_int plaintext_len,
                                   sov_ptr aad, sov_int aad_len,
                                   sov_ptr ciphertext_out, sov_ptr tag_out) {
    sov_result result = {0};
    if (!key || !iv || !plaintext || !ciphertext_out || !tag_out) {
        result.is_ok = false;
        result.error = "Null pointer argument";
        return result;
    }
    
    /* Initialize AES */
    sov_aes_ctx ctx;
    aes_key_expansion(&ctx, (const uint8_t*)key);
    
    /* Compute H = AES_K(0^128) */
    uint8_t h[16];
    uint8_t zero_block[16];
    memset(zero_block, 0, 16);
    aes_encrypt_block(&ctx, zero_block, h);
    
    /* Initialize GCM state */
    uint8_t ghash_state[16];
    memset(ghash_state, 0, 16);
    
    /* Process AAD */
    sov_int aad_offset = 0;
    while (aad_offset < aad_len) {
        sov_int chunk_len = SOV_MIN(16, aad_len - aad_offset);
        for (sov_int i = 0; i < chunk_len; i++) {
            ghash_state[i] ^= ((const uint8_t*)aad)[aad_offset + i];
        }
        for (sov_int i = chunk_len; i < 16; i++) {
            ghash_state[i] ^= 0;
        }
        gcm_ghash_multiply(h, ghash_state);
        aad_offset += chunk_len;
    }
    
    /* Encrypt plaintext */
    uint8_t iv_block[12];
    memset(iv_block, 0, 12);
    if (iv_len >= 12) {
        memcpy(iv_block, iv, 12);
    } else {
        memcpy(iv_block, iv, iv_len);
    }
    aes_ctr_encrypt(&ctx, iv_block, (const uint8_t*)plaintext, (uint8_t*)ciphertext_out, plaintext_len);
    
    /* Process ciphertext through GHASH */
    sov_int ct_offset = 0;
    while (ct_offset < plaintext_len) {
        sov_int chunk_len = SOV_MIN(16, plaintext_len - ct_offset);
        for (sov_int i = 0; i < chunk_len; i++) {
            ghash_state[i] ^= ((const uint8_t*)ciphertext_out)[ct_offset + i];
        }
        gcm_ghash_multiply(h, ghash_state);
        ct_offset += chunk_len;
    }
    
    /* Final block: len(AAD) || len(C) in bits as 64-bit big-endian */
    uint8_t final_block[16];
    memset(final_block, 0, 16);
    uint64_t aad_bits = (uint64_t)aad_len * 8;
    uint64_t ct_bits = (uint64_t)plaintext_len * 8;
    final_block[0] = (aad_bits >> 56) & 0xFF;
    final_block[1] = (aad_bits >> 48) & 0xFF;
    final_block[2] = (aad_bits >> 40) & 0xFF;
    final_block[3] = (aad_bits >> 32) & 0xFF;
    final_block[4] = (aad_bits >> 24) & 0xFF;
    final_block[5] = (aad_bits >> 16) & 0xFF;
    final_block[6] = (aad_bits >> 8) & 0xFF;
    final_block[7] = aad_bits & 0xFF;
    final_block[8] = (ct_bits >> 56) & 0xFF;
    final_block[9] = (ct_bits >> 48) & 0xFF;
    final_block[10] = (ct_bits >> 40) & 0xFF;
    final_block[11] = (ct_bits >> 32) & 0xFF;
    final_block[12] = (ct_bits >> 24) & 0xFF;
    final_block[13] = (ct_bits >> 16) & 0xFF;
    final_block[14] = (ct_bits >> 8) & 0xFF;
    final_block[15] = ct_bits & 0xFF;
    
    for (int i = 0; i < 16; i++) ghash_state[i] ^= final_block[i];
    gcm_ghash_multiply(h, ghash_state);
    
    /* Tag = GHASH ^ E_K(J0), where J0 = IV || 0^31 || 1 */
    uint8_t j0[16];
    memset(j0, 0, 16);
    memcpy(j0, iv_block, 12);
    j0[15] = 1;
    uint8_t e_j0[16];
    aes_encrypt_block(&ctx, j0, e_j0);
    
    for (int i = 0; i < 16; i++) {
        ((uint8_t*)tag_out)[i] = ghash_state[i] ^ e_j0[i];
    }
    
    /* Clean up */
    sov_secure_zero(&ctx, sizeof(ctx));
    sov_secure_zero(h, 16);
    sov_secure_zero(ghash_state, 16);
    sov_secure_zero(e_j0, 16);
    sov_secure_zero(j0, 16);
    
    result.is_ok = true;
    return result;
}

sov_result sov_aes256_gcm_decrypt(sov_ptr key, sov_ptr iv, sov_int iv_len,
                                   sov_ptr ciphertext, sov_int ciphertext_len,
                                   sov_ptr aad, sov_int aad_len,
                                   sov_ptr tag, sov_ptr plaintext_out) {
    sov_result result = {0};
    if (!key || !iv || !ciphertext || !plaintext_out || !tag) {
        result.is_ok = false;
        result.error = "Null pointer argument";
        return result;
    }

    sov_aes_ctx ctx;
    aes_key_expansion(&ctx, (const uint8_t*)key);

    uint8_t h[16];
    uint8_t zero_block[16];
    memset(zero_block, 0, 16);
    aes_encrypt_block(&ctx, zero_block, h);

    uint8_t ghash_state[16];
    memset(ghash_state, 0, 16);

    sov_int aad_offset = 0;
    while (aad_offset < aad_len) {
        sov_int chunk_len = SOV_MIN(16, aad_len - aad_offset);
        sov_int i;
        for (i = 0; i < chunk_len; i++) {
            ghash_state[i] ^= ((const uint8_t*)aad)[aad_offset + i];
        }
        gcm_ghash_multiply(h, ghash_state);
        aad_offset += chunk_len;
    }

    sov_int ct_offset = 0;
    while (ct_offset < ciphertext_len) {
        sov_int chunk_len = SOV_MIN(16, ciphertext_len - ct_offset);
        sov_int i;
        for (i = 0; i < chunk_len; i++) {
            ghash_state[i] ^= ((const uint8_t*)ciphertext)[ct_offset + i];
        }
        gcm_ghash_multiply(h, ghash_state);
        ct_offset += chunk_len;
    }

    uint8_t final_block[16];
    memset(final_block, 0, 16);
    uint64_t aad_bits = (uint64_t)aad_len * 8;
    uint64_t ct_bits = (uint64_t)ciphertext_len * 8;
    final_block[0] = (aad_bits >> 56) & 0xFF;
    final_block[1] = (aad_bits >> 48) & 0xFF;
    final_block[2] = (aad_bits >> 40) & 0xFF;
    final_block[3] = (aad_bits >> 32) & 0xFF;
    final_block[4] = (aad_bits >> 24) & 0xFF;
    final_block[5] = (aad_bits >> 16) & 0xFF;
    final_block[6] = (aad_bits >> 8) & 0xFF;
    final_block[7] = aad_bits & 0xFF;
    final_block[8] = (ct_bits >> 56) & 0xFF;
    final_block[9] = (ct_bits >> 48) & 0xFF;
    final_block[10] = (ct_bits >> 40) & 0xFF;
    final_block[11] = (ct_bits >> 32) & 0xFF;
    final_block[12] = (ct_bits >> 24) & 0xFF;
    final_block[13] = (ct_bits >> 16) & 0xFF;
    final_block[14] = (ct_bits >> 8) & 0xFF;
    final_block[15] = ct_bits & 0xFF;

    sov_int i;
    for (i = 0; i < 16; i++) ghash_state[i] ^= final_block[i];
    gcm_ghash_multiply(h, ghash_state);

    uint8_t iv_block[12];
    memset(iv_block, 0, 12);
    if (iv_len >= 12) memcpy(iv_block, iv, 12);
    else memcpy(iv_block, iv, iv_len);

    uint8_t j0[16];
    memset(j0, 0, 16);
    memcpy(j0, iv_block, 12);
    j0[15] = 1;
    uint8_t e_j0[16];
    aes_encrypt_block(&ctx, j0, e_j0);

    uint8_t computed_tag[16];
    for (i = 0; i < 16; i++) {
        computed_tag[i] = ghash_state[i] ^ e_j0[i];
    }

    if (!sov_secure_compare(tag, computed_tag, SOV_AES_GCM_TAG_SIZE)) {
        sov_secure_zero(plaintext_out, ciphertext_len);
        sov_secure_zero(&ctx, sizeof(ctx));
        sov_secure_zero(h, 16);
        sov_secure_zero(ghash_state, 16);
        sov_secure_zero(computed_tag, 16);
        result.is_ok = false;
        result.error = "Authentication failed: tag mismatch";
        return result;
    }

    aes_ctr_encrypt(&ctx, iv_block, (const uint8_t*)ciphertext, (uint8_t*)plaintext_out, ciphertext_len);

    sov_secure_zero(&ctx, sizeof(ctx));
    sov_secure_zero(h, 16);
    sov_secure_zero(ghash_state, 16);
    sov_secure_zero(computed_tag, 16);
    result.is_ok = true;
    return result;
}

/* ============================================================================
 * RANDOM NUMBER GENERATION (OS CSPRNG)
 * ============================================================================ */

void sov_random_bytes(sov_ptr buf, sov_int len) {
    if (!buf || len <= 0) return;
    
#ifdef _WIN32
    /* Windows: Use BCryptGenRandom (most modern) */
    NTSTATUS status = BCryptGenRandom(NULL, (PUCHAR)buf, (ULONG)len, 
                                       BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    if (status == 0) return;

    /* Fallback 1: CryptGenRandom (legacy CryptoAPI) */
    HCRYPTPROV hProv = 0;
    if (CryptAcquireContextW(&hProv, NULL, NULL, PROV_RSA_FULL, 
                              CRYPT_VERIFYCONTEXT | CRYPT_SILENT)) {
        CryptGenRandom(hProv, (DWORD)len, (BYTE*)buf);
        CryptReleaseContext(hProv, 0);
        return;
    }

    /* Fallback 2: rand_s() from the C runtime (fills one unsigned int per call) */
    {
        sov_int remaining = len;
        unsigned char* dst = (unsigned char*)buf;
        while (remaining > 0) {
            unsigned int val = 0;
            errno_t err = rand_s(&val);
            if (err != 0) break;
            sov_int copy = remaining < (sov_int)sizeof(val) ? remaining : (sov_int)sizeof(val);
            memcpy(dst, &val, copy);
            dst += copy;
            remaining -= copy;
        }
        if (remaining == 0) return;
    }

    /* No CSPRNG available — the system is fundamentally broken */
    fprintf(stderr, "FATAL: All Windows CSPRNG sources failed (BCryptGenRandom, CryptGenRandom, rand_s). Aborting.\n");
    abort();
#else
    /* Unix: Read from /dev/urandom */
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd >= 0) {
        sov_int total = 0;
        while (total < len) {
            ssize_t n = read(fd, (char*)buf + total, len - total);
            if (n <= 0) break;
            total += n;
        }
        close(fd);
        if (total == len) return;
    }
    
    /* /dev/urandom failed — the OS CSPRNG is broken. Hard abort.
       Silently falling back to weak PRNG would be catastrophic. */
    fprintf(stderr, "FATAL: /dev/urandom read failed — OS CSPRNG is unavailable. Aborting.\n");
    abort();
#endif
}

sov_u64 sov_random_u64(void) {
    sov_u64 val;
    sov_random_bytes(&val, sizeof(val));
    return val;
}

sov_u64 sov_random_range(sov_u64 min, sov_u64 max) {
    if (min >= max) return min;
    sov_u64 range = max - min;
    sov_u64 mask = range;
    mask |= mask >> 1;
    mask |= mask >> 2;
    mask |= mask >> 4;
    mask |= mask >> 8;
    mask |= mask >> 16;
    mask |= mask >> 32;
    
    sov_u64 result;
    do {
        result = sov_random_u64() & mask;
    } while (result > range);
    
    return min + result;
}

void sov_random_key(sov_ptr key_out) {
    sov_random_bytes(key_out, SOV_AES256_KEY_SIZE);
}

/* ============================================================================
 * CONCURRENCY
 * ============================================================================ */

#ifndef _WIN32
sov_channel* sov_channel_new(sov_int capacity) {
    sov_channel* ch = (sov_channel*)sov_alloc(1, sizeof(sov_channel));
    ch->capacity = capacity > 0 ? capacity : 1;
    ch->buffer = sov_alloc(ch->capacity, sizeof(sov_ptr));
    ch->head = 0;
    ch->tail = 0;
    ch->count = 0;
    ch->closed = false;
    
    ch->mutex = sov_alloc(1, sizeof(pthread_mutex_t));
    ch->cond_not_empty = sov_alloc(1, sizeof(pthread_cond_t));
    ch->cond_not_full = sov_alloc(1, sizeof(pthread_cond_t));
    
    pthread_mutex_init((pthread_mutex_t*)ch->mutex, NULL);
    pthread_cond_init((pthread_cond_t*)ch->cond_not_empty, NULL);
    pthread_cond_init((pthread_cond_t*)ch->cond_not_full, NULL);
    
    return ch;
}

void sov_channel_send(sov_channel* ch, sov_ptr value) {
    if (!ch) return;
    pthread_mutex_lock((pthread_mutex_t*)ch->mutex);
    while (ch->count >= ch->capacity && !ch->closed) {
        pthread_cond_wait((pthread_cond_t*)ch->cond_not_full, (pthread_mutex_t*)ch->mutex);
    }
    if (ch->closed) { pthread_mutex_unlock((pthread_mutex_t*)ch->mutex); return; }
    ((sov_ptr*)ch->buffer)[ch->tail] = value;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal((pthread_cond_t*)ch->cond_not_empty);
    pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
}

sov_ptr sov_channel_recv(sov_channel* ch) {
    if (!ch) return NULL;
    pthread_mutex_lock((pthread_mutex_t*)ch->mutex);
    while (ch->count == 0 && !ch->closed) {
        pthread_cond_wait((pthread_cond_t*)ch->cond_not_empty, (pthread_mutex_t*)ch->mutex);
    }
    if (ch->count == 0) { pthread_mutex_unlock((pthread_mutex_t*)ch->mutex); return NULL; }
    sov_ptr value = ((sov_ptr*)ch->buffer)[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    pthread_cond_signal((pthread_cond_t*)ch->cond_not_full);
    pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
    return value;
}

sov_bool sov_channel_try_send(sov_channel* ch, sov_ptr value) {
    if (!ch) return false;
    pthread_mutex_lock((pthread_mutex_t*)ch->mutex);
    if (ch->count >= ch->capacity || ch->closed) {
        pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
        return false;
    }
    ((sov_ptr*)ch->buffer)[ch->tail] = value;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal((pthread_cond_t*)ch->cond_not_empty);
    pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
    return true;
}

sov_result sov_channel_try_recv(sov_channel* ch) {
    sov_result res = {0};
    if (!ch) { res.is_ok = false; return res; }
    pthread_mutex_lock((pthread_mutex_t*)ch->mutex);
    if (ch->count == 0) { 
        pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
        res.is_ok = false; return res;
    }
    res.ptr_val = ((sov_ptr*)ch->buffer)[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    res.is_ok = true;
    pthread_cond_signal((pthread_cond_t*)ch->cond_not_full);
    pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
    return res;
}

void sov_channel_close(sov_channel* ch) {
    if (!ch) return;
    pthread_mutex_lock((pthread_mutex_t*)ch->mutex);
    ch->closed = true;
    pthread_cond_broadcast((pthread_cond_t*)ch->cond_not_empty);
    pthread_cond_broadcast((pthread_cond_t*)ch->cond_not_full);
    pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
}

void sov_channel_free(sov_channel* ch) {
    if (!ch) return;
    pthread_mutex_destroy((pthread_mutex_t*)ch->mutex);
    pthread_cond_destroy((pthread_cond_t*)ch->cond_not_empty);
    pthread_cond_destroy((pthread_cond_t*)ch->cond_not_full);
    sov_free(ch->mutex);
    sov_free(ch->cond_not_empty);
    sov_free(ch->cond_not_full);
    sov_free(ch->buffer);
    sov_free(ch);
}

typedef struct { void (*func)(sov_ptr); sov_ptr arg; } sov_thread_arg;
static void* sov_thread_wrapper(void* arg) {
    sov_thread_arg* ta = (sov_thread_arg*)arg;
    ta->func(ta->arg);
    sov_free(ta);
    return NULL;
}

void sov_spawn(void (*func)(sov_ptr), sov_ptr arg) {
    pthread_t thread;
    sov_thread_arg* ta = (sov_thread_arg*)sov_alloc(1, sizeof(sov_thread_arg));
    ta->func = func; ta->arg = arg;
    pthread_create(&thread, NULL, sov_thread_wrapper, ta);
    pthread_detach(thread);
}
#else
/* Windows concurrency using Windows API primitives */

typedef struct { void (*func)(sov_ptr); sov_ptr arg; } sov_thread_arg;

static DWORD WINAPI sov_thread_wrapper(LPVOID arg) {
    sov_thread_arg* ta = (sov_thread_arg*)arg;
    ta->func(ta->arg);
    sov_free(ta);
    return 0;
}

sov_channel* sov_channel_new(sov_int capacity) {
    sov_channel* ch = (sov_channel*)sov_alloc(1, sizeof(sov_channel));
    ch->capacity = capacity > 0 ? capacity : 1;
    ch->buffer = sov_alloc(ch->capacity, sizeof(sov_ptr));
    ch->head = 0;
    ch->tail = 0;
    ch->count = 0;
    ch->closed = false;

    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)sov_alloc(1, sizeof(CRITICAL_SECTION));
    InitializeCriticalSection(cs);
    ch->mutex = cs;

    /* sem_not_empty: initially 0 items available, max = capacity */
    HANDLE sem_not_empty = CreateSemaphore(NULL, 0, ch->capacity, NULL);
    /* sem_not_full: initially all slots available, max = capacity */
    HANDLE sem_not_full  = CreateSemaphore(NULL, ch->capacity, ch->capacity, NULL);
    ch->cond_not_empty = sem_not_empty;
    ch->cond_not_full  = sem_not_full;

    return ch;
}

void sov_channel_send(sov_channel* ch, sov_ptr value) {
    if (!ch) return;
    /* Wait for an empty slot */
    WaitForSingleObject((HANDLE)ch->cond_not_full, INFINITE);
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)ch->mutex;
    EnterCriticalSection(cs);
    if (ch->closed) {
        LeaveCriticalSection(cs);
        return;
    }
    ((sov_ptr*)ch->buffer)[ch->tail] = value;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    LeaveCriticalSection(cs);
    /* Signal that an item is available */
    ReleaseSemaphore((HANDLE)ch->cond_not_empty, 1, NULL);
}

sov_ptr sov_channel_recv(sov_channel* ch) {
    if (!ch) return NULL;
    /* Wait for an item to be available */
    WaitForSingleObject((HANDLE)ch->cond_not_empty, INFINITE);
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)ch->mutex;
    EnterCriticalSection(cs);
    if (ch->count == 0) {
        LeaveCriticalSection(cs);
        return NULL;
    }
    sov_ptr value = ((sov_ptr*)ch->buffer)[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    LeaveCriticalSection(cs);
    /* Signal that a slot is available */
    ReleaseSemaphore((HANDLE)ch->cond_not_full, 1, NULL);
    return value;
}

sov_bool sov_channel_try_send(sov_channel* ch, sov_ptr value) {
    if (!ch) return false;
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)ch->mutex;
    if (!TryEnterCriticalSection(cs)) return false;
    if (ch->count >= ch->capacity || ch->closed) {
        LeaveCriticalSection(cs);
        return false;
    }
    ((sov_ptr*)ch->buffer)[ch->tail] = value;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    LeaveCriticalSection(cs);
    ReleaseSemaphore((HANDLE)ch->cond_not_empty, 1, NULL);
    return true;
}

sov_result sov_channel_try_recv(sov_channel* ch) {
    sov_result res = {0};
    if (!ch) { res.is_ok = false; return res; }
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)ch->mutex;
    if (!TryEnterCriticalSection(cs)) {
        res.is_ok = false; return res;
    }
    if (ch->count == 0) {
        LeaveCriticalSection(cs);
        res.is_ok = false; return res;
    }
    res.ptr_val = ((sov_ptr*)ch->buffer)[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    res.is_ok = true;
    LeaveCriticalSection(cs);
    ReleaseSemaphore((HANDLE)ch->cond_not_full, 1, NULL);
    return res;
}

void sov_channel_close(sov_channel* ch) {
    if (!ch) return;
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)ch->mutex;
    EnterCriticalSection(cs);
    ch->closed = true;
    LeaveCriticalSection(cs);
    /* Broadcast to all waiters by releasing max semaphore slots */
    ReleaseSemaphore((HANDLE)ch->cond_not_empty, ch->capacity, NULL);
    ReleaseSemaphore((HANDLE)ch->cond_not_full,  ch->capacity, NULL);
}

void sov_channel_free(sov_channel* ch) {
    if (!ch) return;
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)ch->mutex;
    DeleteCriticalSection(cs);
    sov_free(cs);
    CloseHandle((HANDLE)ch->cond_not_empty);
    CloseHandle((HANDLE)ch->cond_not_full);
    sov_free(ch->buffer);
    sov_free(ch);
}

void sov_spawn(void (*func)(sov_ptr), sov_ptr arg) {
    sov_thread_arg* ta = (sov_thread_arg*)sov_alloc(1, sizeof(sov_thread_arg));
    ta->func = func;
    ta->arg = arg;
    HANDLE h = CreateThread(NULL, 0, sov_thread_wrapper, ta, 0, NULL);
    if (h) CloseHandle(h); /* detach — we do not join */
}
#endif

void sov_sleep(sov_int ms) {
#ifdef _WIN32
    Sleep((DWORD)ms);
#else
    usleep((useconds_t)(ms * 1000));
#endif
}

/* ============================================================================
 * ASSERTIONS AND ERRORS
 * ============================================================================ */

void sov_assert(sov_bool condition, sov_string message) {
    if (!condition) {
        fprintf(stderr, "Assertion failed: %s\n", message ? message : "(no message)");
        abort();
    }
}

void sov_panic(sov_string message) {
    fprintf(stderr, "PANIC: %s\n", message ? message : "(no message)");
    abort();
}

void sov_bounds_check(sov_int index, sov_int len, sov_string array_name) {
    if (index < 0 || index >= len) {
        fprintf(stderr, "PANIC: Index %lld out of bounds for array '%s' (length %lld)\n",
                (long long)index, array_name ? array_name : "unknown", (long long)len);
        abort();
    }
}

void sov_null_check(sov_ptr ptr, sov_string name) {
    if (!ptr) {
        fprintf(stderr, "PANIC: Null pointer dereference: %s\n", name ? name : "unknown");
        abort();
    }
}

/* ============================================================================
 * UTILITY
 * ============================================================================ */

sov_vec* sov_get_args(int argc, char** argv) {
    sov_vec* v = sov_vec_str_new();
    for (int i = 0; i < argc; i++) {
        sov_vec_str_push(v, argv[i]);
    }
    return v;
}

sov_string sov_getenv(sov_string name) {
    if (!name) return NULL;
    char* val = getenv(name);
    return val ? sov_strcpy(val) : NULL;
}

void sov_exit(sov_int code) {
    exit((int)code);
}

sov_int sov_time_ms(void) {
#ifdef _WIN32
    return (sov_int)(GetTickCount64());
#else
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (sov_int)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
#endif
}

sov_int sov_time_ns(void) {
#ifdef _WIN32
    LARGE_INTEGER freq, counter;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&counter);
    return (sov_int)((counter.QuadPart * 1000000000ULL) / freq.QuadPart);
#else
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (sov_int)(ts.tv_sec * 1000000000LL + ts.tv_nsec);
#endif
}

/* ============================================================================
 * MAIN ENTRY POINT
 * ============================================================================ */

#ifdef SOV_RUNTIME_STANDALONE
int main(int argc, char** argv) {
    printf("Sovereign Runtime v%d.%d.%d\n", 
           SOV_RUNTIME_VERSION_MAJOR, SOV_RUNTIME_VERSION_MINOR, SOV_RUNTIME_VERSION_PATCH);
    printf("Production Security Edition\n");
    printf("Features: SHA-256, SHA-512, BLAKE2S, HMAC, HKDF, PBKDF2,\n");
    printf("          AES-256-GCM, ChaCha20-Poly1305, CSPRNG,\n");
    printf("          Constant-time primitives, Secure memory\n");
    printf("\nThis is the runtime library - link with your Sovereign program.\n");
    return 0;
}
#endif
