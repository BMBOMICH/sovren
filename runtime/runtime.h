/*
 * Sovereign Runtime Library - Header
 * 
 * This provides the runtime support for Sovereign programs compiled to C.
 * Link with: gcc -o program program.c runtime.c
 */

#ifndef SOVEREIGN_RUNTIME_H
#define SOVEREIGN_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* ============================================================================
 * TYPE DEFINITIONS
 * ============================================================================ */

typedef int64_t sov_int;
typedef double sov_float;
typedef bool sov_bool;
typedef char* sov_string;
typedef void* sov_ptr;

/* Result type for operations that can fail */
typedef struct {
    bool is_ok;
    union {
        sov_int int_val;
        sov_ptr ptr_val;
        sov_string str_val;
    };
    sov_string error;
} sov_result;

/* Dynamic array (Vec) */
typedef struct {
    sov_ptr data;
    sov_int len;
    sov_int capacity;
    sov_int elem_size;
} sov_vec;

/* Hash map entry */
typedef struct {
    sov_string key;
    sov_ptr value;
    uint64_t hash;
    bool occupied;
} sov_hashmap_entry;

/* Hash map */
typedef struct {
    sov_hashmap_entry* entries;
    sov_int count;
    sov_int capacity;
} sov_hashmap;

/* String builder */
typedef struct {
    char* data;
    sov_int len;
    sov_int capacity;
} sov_stringbuilder;

/* File handle */
typedef struct {
    void* handle;
    sov_string path;
    bool is_open;
} sov_file;

/* Channel for concurrency */
typedef struct {
    sov_ptr buffer;
    sov_int capacity;
    sov_int head;
    sov_int tail;
    sov_int count;
    void* mutex;
    void* cond_not_empty;
    void* cond_not_full;
    bool closed;
} sov_channel;

/* ============================================================================
 * MEMORY MANAGEMENT
 * ============================================================================ */

/* Allocate memory */
sov_ptr sov_alloc(sov_int count, sov_int size);

/* Reallocate memory */
sov_ptr sov_realloc(sov_ptr ptr, sov_int new_size);

/* Free memory */
void sov_free(sov_ptr ptr);

/* Secure zero memory (for sensitive data) */
void sov_secure_zero(sov_ptr ptr, sov_int size);

/* ============================================================================
 * STRING OPERATIONS
 * ============================================================================ */

/* String length */
sov_int sov_strlen(sov_string s);

/* String comparison */
sov_int sov_strcmp(sov_string a, sov_string b);

/* String equality */
sov_bool sov_streq(sov_string a, sov_string b);

/* String copy (allocates new string) */
sov_string sov_strcpy(sov_string s);

/* String concatenation (allocates new string) */
sov_string sov_strcat(sov_string a, sov_string b);

/* Substring (allocates new string) */
sov_string sov_substr(sov_string s, sov_int start, sov_int len);

/* Find substring (-1 if not found) */
sov_int sov_strfind(sov_string haystack, sov_string needle);

/* String contains */
sov_bool sov_strcontains(sov_string s, sov_string needle);

/* String starts with */
sov_bool sov_strstarts(sov_string s, sov_string prefix);

/* String ends with */
sov_bool sov_strends(sov_string s, sov_string suffix);

/* String trim (allocates new string) */
sov_string sov_strtrim(sov_string s);

/* String to uppercase (allocates new string) */
sov_string sov_strupper(sov_string s);

/* String to lowercase (allocates new string) */
sov_string sov_strlower(sov_string s);

/* String replace all (allocates new string) */
sov_string sov_strreplace(sov_string s, sov_string old, sov_string new_str);

/* Character at index */
char sov_charat(sov_string s, sov_int index);

/* Integer to string */
sov_string sov_int_to_string(sov_int n);

/* String to integer */
sov_int sov_string_to_int(sov_string s);

/* Float to string */
sov_string sov_float_to_string(sov_float f);

/* String to float */
sov_float sov_string_to_float(sov_string s);

/* ============================================================================
 * STRING BUILDER
 * ============================================================================ */

/* Create new string builder */
sov_stringbuilder* sov_sb_new(void);

/* Append string */
void sov_sb_append(sov_stringbuilder* sb, sov_string s);

/* Append character */
void sov_sb_append_char(sov_stringbuilder* sb, char c);

/* Append integer */
void sov_sb_append_int(sov_stringbuilder* sb, sov_int n);

/* Convert to string (consumes builder) */
sov_string sov_sb_to_string(sov_stringbuilder* sb);

/* Get current length */
sov_int sov_sb_len(sov_stringbuilder* sb);

/* Clear builder */
void sov_sb_clear(sov_stringbuilder* sb);

/* Free builder */
void sov_sb_free(sov_stringbuilder* sb);

/* ============================================================================
 * VECTOR OPERATIONS
 * ============================================================================ */

/* Create new vector */
sov_vec* sov_vec_new(sov_int elem_size);

/* Push element */
void sov_vec_push(sov_vec* v, sov_ptr elem);

/* Pop element */
sov_ptr sov_vec_pop(sov_vec* v);

/* Get element at index */
sov_ptr sov_vec_get(sov_vec* v, sov_int index);

/* Set element at index */
void sov_vec_set(sov_vec* v, sov_int index, sov_ptr elem);

/* Get length */
sov_int sov_vec_len(sov_vec* v);

/* Get capacity */
sov_int sov_vec_capacity(sov_vec* v);

/* Clear vector */
void sov_vec_clear(sov_vec* v);

/* Free vector */
void sov_vec_free(sov_vec* v);

/* Vector of integers */
sov_vec* sov_vec_int_new(void);
void sov_vec_int_push(sov_vec* v, sov_int val);
sov_int sov_vec_int_get(sov_vec* v, sov_int index);
void sov_vec_int_set(sov_vec* v, sov_int index, sov_int val);

/* Vector of strings */
sov_vec* sov_vec_str_new(void);
void sov_vec_str_push(sov_vec* v, sov_string val);
sov_string sov_vec_str_get(sov_vec* v, sov_int index);
void sov_vec_str_set(sov_vec* v, sov_int index, sov_string val);
void sov_vec_str_free(sov_vec* v);

/* ============================================================================
 * HASHMAP OPERATIONS
 * ============================================================================ */

/* Create new hashmap */
sov_hashmap* sov_hashmap_new(void);

/* Insert key-value pair */
void sov_hashmap_insert(sov_hashmap* hm, sov_string key, sov_ptr value);

/* Get value by key (NULL if not found) */
sov_ptr sov_hashmap_get(sov_hashmap* hm, sov_string key);

/* Check if key exists */
sov_bool sov_hashmap_contains(sov_hashmap* hm, sov_string key);

/* Remove key */
sov_ptr sov_hashmap_remove(sov_hashmap* hm, sov_string key);

/* Get count */
sov_int sov_hashmap_count(sov_hashmap* hm);

/* Free hashmap */
void sov_hashmap_free(sov_hashmap* hm);

/* ============================================================================
 * FILE OPERATIONS
 * ============================================================================ */

/* Open file */
sov_file* sov_file_open(sov_string path, sov_string mode);

/* Close file */
void sov_file_close(sov_file* f);

/* Read all contents */
sov_string sov_file_read_all(sov_string path);

/* Write all contents */
sov_bool sov_file_write_all(sov_string path, sov_string content);

/* Read line */
sov_string sov_file_read_line(sov_file* f);

/* Write string */
void sov_file_write(sov_file* f, sov_string s);

/* Check if file exists */
sov_bool sov_file_exists(sov_string path);

/* Get file size */
sov_int sov_file_size(sov_string path);

/* ============================================================================
 * I/O OPERATIONS
 * ============================================================================ */

/* Print string */
void sov_print(sov_string s);

/* Print string with newline */
void sov_println(sov_string s);

/* Print integer */
void sov_print_int(sov_int n);

/* Print float */
void sov_print_float(sov_float f);

/* Print to stderr */
void sov_eprint(sov_string s);

/* Print to stderr with newline */
void sov_eprintln(sov_string s);

/* Formatted print */
void sov_printf(sov_string fmt, ...);

/* Read line from stdin */
sov_string sov_read_line(void);

/* ============================================================================
 * SECURITY OPERATIONS
 * ============================================================================ */

/* Constant-time memory comparison (prevents timing attacks) */
sov_bool sov_secure_compare(sov_ptr a, sov_ptr b, sov_int len);

/* Generate random bytes */
void sov_random_bytes(sov_ptr buf, sov_int len);

/* SHA-256 hash */
void sov_sha256(sov_ptr data, sov_int len, sov_ptr out);

/* HMAC-SHA256 */
void sov_hmac_sha256(sov_ptr key, sov_int key_len, sov_ptr data, sov_int data_len, sov_ptr out);

/* ============================================================================
 * CONCURRENCY
 * ============================================================================ */

/* Create channel */
sov_channel* sov_channel_new(sov_int capacity);

/* Send to channel (blocks if full) */
void sov_channel_send(sov_channel* ch, sov_ptr value);

/* Receive from channel (blocks if empty) */
sov_ptr sov_channel_recv(sov_channel* ch);

/* Try send (non-blocking) */
sov_bool sov_channel_try_send(sov_channel* ch, sov_ptr value);

/* Try receive (non-blocking) */
sov_result sov_channel_try_recv(sov_channel* ch);

/* Close channel */
void sov_channel_close(sov_channel* ch);

/* Free channel */
void sov_channel_free(sov_channel* ch);

/* Spawn thread */
void sov_spawn(void (*func)(sov_ptr), sov_ptr arg);

/* Sleep milliseconds */
void sov_sleep(sov_int ms);

/* ============================================================================
 * ASSERTIONS AND ERRORS
 * ============================================================================ */

/* Assert with message */
void sov_assert(sov_bool condition, sov_string message);

/* Panic with message */
void sov_panic(sov_string message);

/* ============================================================================
 * UTILITY
 * ============================================================================ */

/* Get command line arguments */
sov_vec* sov_get_args(int argc, char** argv);

/* Get environment variable */
sov_string sov_getenv(sov_string name);

/* Exit with code */
void sov_exit(sov_int code);

/* Get current time (milliseconds since epoch) */
sov_int sov_time_ms(void);

/* Hash string (djb2) */
uint64_t sov_hash_string(sov_string s);

#endif /* SOVEREIGN_RUNTIME_H */
