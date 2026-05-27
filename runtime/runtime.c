/*
 * Sovereign Runtime Library - Implementation
 * 
 * This provides the runtime support for Sovereign programs compiled to C.
 * Compile with: gcc -c runtime.c -o runtime.o
 * Link with: gcc -o program program.o runtime.o -lpthread
 */

#include "runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdarg.h>
#include <time.h>
#include <sys/stat.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#include <unistd.h>
#endif

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
    if (ptr) {
        free(ptr);
    }
}

void sov_secure_zero(sov_ptr ptr, sov_int size) {
    if (ptr && size > 0) {
        volatile unsigned char* p = (volatile unsigned char*)ptr;
        while (size--) {
            *p++ = 0;
        }
    }
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

sov_string sov_strreplace(sov_string s, sov_string old, sov_string new_str) {
    if (!s || !old || !new_str) return sov_strcpy(s);
    
    sov_int old_len = sov_strlen(old);
    if (old_len == 0) return sov_strcpy(s);
    
    sov_int new_len = sov_strlen(new_str);
    
    /* Count occurrences */
    sov_int count = 0;
    char* p = s;
    while ((p = strstr(p, old)) != NULL) {
        count++;
        p += old_len;
    }
    
    if (count == 0) return sov_strcpy(s);
    
    /* Allocate result */
    sov_int s_len = sov_strlen(s);
    sov_int result_len = s_len + count * (new_len - old_len);
    sov_string result = (sov_string)sov_alloc(result_len + 1, 1);
    
    /* Build result */
    char* dest = result;
    p = s;
    while (*p) {
        if (strncmp(p, old, old_len) == 0) {
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
    if (v->len >= v->capacity) {
        sov_vec_grow(v);
    }
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

/* Integer vector specialization */
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

/* String vector specialization */
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
        hash = ((hash << 5) + hash) + c; /* hash * 33 + c */
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
            /* Don't free old key - it's reused */
        }
    }
    
    sov_free(old_entries);
}

void sov_hashmap_insert(sov_hashmap* hm, sov_string key, sov_ptr value) {
    if (!hm || !key) return;
    
    /* Resize if load factor > 0.75 */
    if (hm->count * 4 >= hm->capacity * 3) {
        sov_hashmap_resize(hm);
    }
    
    uint64_t hash = sov_hash_string(key);
    sov_int index = hash % hm->capacity;
    
    /* Linear probing */
    while (hm->entries[index].occupied) {
        if (sov_streq(hm->entries[index].key, key)) {
            /* Update existing */
            hm->entries[index].value = value;
            return;
        }
        index = (index + 1) % hm->capacity;
    }
    
    /* Insert new */
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
        if (!hm->entries[index].occupied) {
            return NULL;
        }
        if (sov_streq(hm->entries[index].key, key)) {
            return hm->entries[index].value;
        }
        index = (index + 1) % hm->capacity;
    } while (index != start);
    
    return NULL;
}

sov_bool sov_hashmap_contains(sov_hashmap* hm, sov_string key) {
    return sov_hashmap_get(hm, key) != NULL || 
           (hm && key && sov_hashmap_get(hm, key) == NULL && false); /* Check explicitly */
}

sov_ptr sov_hashmap_remove(sov_hashmap* hm, sov_string key) {
    if (!hm || !key) return NULL;
    
    uint64_t hash = sov_hash_string(key);
    sov_int index = hash % hm->capacity;
    sov_int start = index;
    
    do {
        if (!hm->entries[index].occupied) {
            return NULL;
        }
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
    
    /* Remove trailing newline */
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
 * SECURITY OPERATIONS
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

void sov_random_bytes(sov_ptr buf, sov_int len) {
    if (!buf || len <= 0) return;
    
#ifdef _WIN32
    /* Windows: Use CryptGenRandom or BCryptGenRandom */
    for (sov_int i = 0; i < len; i++) {
        ((unsigned char*)buf)[i] = (unsigned char)(rand() % 256);
    }
#else
    /* Unix: Read from /dev/urandom */
    FILE* f = fopen("/dev/urandom", "rb");
    if (f) {
        fread(buf, 1, len, f);
        fclose(f);
    } else {
        /* Fallback */
        for (sov_int i = 0; i < len; i++) {
            ((unsigned char*)buf)[i] = (unsigned char)(rand() % 256);
        }
    }
#endif
}

void sov_sha256(sov_ptr data, sov_int len, sov_ptr out) {
    /* Placeholder - in production use OpenSSL or similar */
    (void)data;
    (void)len;
    memset(out, 0, 32);
}

void sov_hmac_sha256(sov_ptr key, sov_int key_len, sov_ptr data, sov_int data_len, sov_ptr out) {
    /* Placeholder - in production use OpenSSL or similar */
    (void)key;
    (void)key_len;
    (void)data;
    (void)data_len;
    memset(out, 0, 32);
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
    
    if (ch->closed) {
        pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
        return;
    }
    
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
    
    if (ch->count == 0) {
        pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
        return NULL;
    }
    
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
    if (!ch) {
        res.is_ok = false;
        return res;
    }
    
    pthread_mutex_lock((pthread_mutex_t*)ch->mutex);
    
    if (ch->count == 0) {
        pthread_mutex_unlock((pthread_mutex_t*)ch->mutex);
        res.is_ok = false;
        return res;
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

typedef struct {
    void (*func)(sov_ptr);
    sov_ptr arg;
} sov_thread_arg;

static void* sov_thread_wrapper(void* arg) {
    sov_thread_arg* ta = (sov_thread_arg*)arg;
    ta->func(ta->arg);
    sov_free(ta);
    return NULL;
}

void sov_spawn(void (*func)(sov_ptr), sov_ptr arg) {
    pthread_t thread;
    sov_thread_arg* ta = (sov_thread_arg*)sov_alloc(1, sizeof(sov_thread_arg));
    ta->func = func;
    ta->arg = arg;
    pthread_create(&thread, NULL, sov_thread_wrapper, ta);
    pthread_detach(thread);
}
#else
/* Windows stubs */
sov_channel* sov_channel_new(sov_int capacity) { return NULL; }
void sov_channel_send(sov_channel* ch, sov_ptr value) {}
sov_ptr sov_channel_recv(sov_channel* ch) { return NULL; }
sov_bool sov_channel_try_send(sov_channel* ch, sov_ptr value) { return false; }
sov_result sov_channel_try_recv(sov_channel* ch) { sov_result r = {0}; return r; }
void sov_channel_close(sov_channel* ch) {}
void sov_channel_free(sov_channel* ch) {}
void sov_spawn(void (*func)(sov_ptr), sov_ptr arg) {}
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
    struct timespec ts;
#ifdef _WIN32
    return (sov_int)(GetTickCount64());
#else
    clock_gettime(CLOCK_REALTIME, &ts);
    return (sov_int)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
#endif
}

/* ============================================================================
 * MAIN ENTRY POINT (if compiled standalone)
 * ============================================================================ */

#ifdef SOV_RUNTIME_STANDALONE
int main(int argc, char** argv) {
    printf("Sovereign Runtime v1.0.0\n");
    printf("This is the runtime library - link with your Sovereign program.\n");
    return 0;
}
#endif
