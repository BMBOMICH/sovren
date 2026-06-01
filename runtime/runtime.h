#ifndef SOVEREIGN_RUNTIME_H
#define SOVEREIGN_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define SOV_RUNTIME_VERSION_MAJOR 0
#define SOV_RUNTIME_VERSION_MINOR 1
#define SOV_RUNTIME_VERSION_PATCH 0

typedef int64_t sov_int;
typedef double sov_float;
typedef bool sov_bool;
typedef char* sov_string;
typedef void* sov_ptr;
typedef uint8_t sov_byte;

typedef int8_t   sov_i8;
typedef int16_t  sov_i16;
typedef int32_t  sov_i32;
typedef int64_t  sov_i64;
typedef uint8_t  sov_u8;
typedef uint16_t sov_u16;
typedef uint32_t sov_u32;
typedef uint64_t sov_u64;

typedef struct {
    bool is_ok;
    union {
        sov_int int_val;
        sov_ptr ptr_val;
        sov_string str_val;
        sov_u64 u64_val;
    };
    sov_string error;
} sov_result;

typedef struct {
    bool is_some;
    union {
        sov_int int_val;
        sov_ptr ptr_val;
        sov_string str_val;
    };
} sov_option;

typedef struct {
    sov_ptr data;
    sov_int len;
    sov_int capacity;
    sov_int elem_size;
} sov_vec;

typedef struct {
    sov_ptr data;
    sov_int len;
    sov_int elem_size;
    sov_string name;
} sov_array;

typedef struct {
    sov_string key;
    sov_ptr value;
    uint64_t hash;
    bool occupied;
} sov_hashmap_entry;

typedef struct {
    sov_hashmap_entry* entries;
    sov_int count;
    sov_int capacity;
} sov_hashmap;

typedef struct {
    char* data;
    sov_int len;
    sov_int capacity;
} sov_stringbuilder;

typedef struct {
    void* handle;
    sov_string path;
    bool is_open;
} sov_file;

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

sov_ptr sov_alloc(sov_int count, sov_int size);
sov_ptr sov_realloc(sov_ptr ptr, sov_int new_size);
void sov_free(sov_ptr ptr);
void sov_secure_zero(sov_ptr ptr, sov_int size);
sov_ptr sov_alloc_secure(sov_int count, sov_int size);
void sov_free_secure(sov_ptr ptr, sov_int size);
sov_ptr sov_pool_alloc(sov_int size);
void sov_pool_free(sov_ptr ptr, sov_int size);

sov_array sov_array_view(sov_ptr data, sov_int len, sov_int elem_size, sov_string name);
sov_ptr sov_array_get(sov_array* arr, sov_int index);
void sov_array_set(sov_array* arr, sov_int index, sov_ptr value);

sov_int sov_strlen(sov_string s);
sov_int sov_strcmp(sov_string a, sov_string b);
sov_bool sov_streq(sov_string a, sov_string b);
sov_string sov_strcpy(sov_string s);
sov_string sov_strcat(sov_string a, sov_string b);
sov_string sov_substr(sov_string s, sov_int start, sov_int len);
sov_int sov_strfind(sov_string haystack, sov_string needle);
sov_bool sov_strcontains(sov_string s, sov_string needle);
sov_bool sov_strstarts(sov_string s, sov_string prefix);
sov_bool sov_strends(sov_string s, sov_string suffix);
sov_string sov_strtrim(sov_string s);
sov_string sov_strupper(sov_string s);
sov_string sov_strlower(sov_string s);
sov_string sov_strreplace(sov_string s, sov_string old_str, sov_string new_str);
char sov_charat(sov_string s, sov_int index);
sov_string sov_int_to_string(sov_int n);
sov_int sov_string_to_int(sov_string s);
sov_string sov_float_to_string(sov_float f);
sov_float sov_string_to_float(sov_string s);

sov_stringbuilder* sov_sb_new(void);
void sov_sb_append(sov_stringbuilder* sb, sov_string s);
void sov_sb_append_char(sov_stringbuilder* sb, char c);
void sov_sb_append_int(sov_stringbuilder* sb, sov_int n);
sov_string sov_sb_to_string(sov_stringbuilder* sb);
sov_int sov_sb_len(sov_stringbuilder* sb);
void sov_sb_clear(sov_stringbuilder* sb);
void sov_sb_free(sov_stringbuilder* sb);

sov_vec* sov_vec_new(sov_int elem_size);
void sov_vec_push(sov_vec* v, sov_ptr elem);
sov_ptr sov_vec_pop(sov_vec* v);
sov_ptr sov_vec_get(sov_vec* v, sov_int index);
void sov_vec_set(sov_vec* v, sov_int index, sov_ptr elem);
sov_int sov_vec_len(sov_vec* v);
sov_int sov_vec_capacity(sov_vec* v);
void sov_vec_clear(sov_vec* v);
void sov_vec_free(sov_vec* v);

sov_vec* sov_vec_int_new(void);
void sov_vec_int_push(sov_vec* v, sov_int val);
sov_int sov_vec_int_get(sov_vec* v, sov_int index);
void sov_vec_int_set(sov_vec* v, sov_int index, sov_int val);

sov_vec* sov_vec_str_new(void);
void sov_vec_str_push(sov_vec* v, sov_string val);
sov_string sov_vec_str_get(sov_vec* v, sov_int index);
void sov_vec_str_set(sov_vec* v, sov_int index, sov_string val);
void sov_vec_str_free(sov_vec* v);

sov_hashmap* sov_hashmap_new(void);
void sov_hashmap_insert(sov_hashmap* hm, sov_string key, sov_ptr value);
sov_ptr sov_hashmap_get(sov_hashmap* hm, sov_string key);
sov_bool sov_hashmap_contains(sov_hashmap* hm, sov_string key);
sov_ptr sov_hashmap_remove(sov_hashmap* hm, sov_string key);
sov_int sov_hashmap_count(sov_hashmap* hm);
void sov_hashmap_free(sov_hashmap* hm);

sov_file* sov_file_open(sov_string path, sov_string mode);
void sov_file_close(sov_file* f);
sov_string sov_file_read_all(sov_string path);
sov_bool sov_file_write_all(sov_string path, sov_string content);
sov_string sov_file_read_line(sov_file* f);
void sov_file_write(sov_file* f, sov_string s);
sov_bool sov_file_exists(sov_string path);
sov_int sov_file_size(sov_string path);

void sov_print(sov_string s);
void sov_println(sov_string s);
void sov_print_int(sov_int n);
void sov_print_float(sov_float f);
void sov_eprint(sov_string s);
void sov_eprintln(sov_string s);
void sov_printf(sov_string fmt, ...);
sov_string sov_read_line(void);

#define SOV_SHA256_SIZE      32
#define SOV_SHA256_HEX_SIZE  65
#define SOV_SHA512_SIZE      64
#define SOV_BLAKE2S_SIZE      32
#define SOV_HMAC_SIZE        32

void sov_sha256(sov_ptr data, sov_int len, sov_ptr out);
sov_string sov_sha256_hex(sov_ptr data, sov_int len);

void sov_sha512(sov_ptr data, sov_int len, sov_ptr out);
sov_string sov_sha512_hex(sov_ptr data, sov_int len);

void sov_blake2s(sov_ptr data, sov_int len, sov_ptr out);
sov_string sov_blake2s_hex(sov_ptr data, sov_int len);

void sov_hmac_sha256(sov_ptr key, sov_int key_len, sov_ptr data, sov_int data_len, sov_ptr out);
sov_string sov_hmac_sha256_hex(sov_ptr key, sov_int key_len, sov_ptr data, sov_int data_len);

void sov_hkdf_sha256(sov_ptr salt, sov_int salt_len, sov_ptr ikm, sov_int ikm_len,
                     sov_ptr info, sov_int info_len, sov_ptr out, sov_int out_len);

void sov_pbkdf2_sha256(sov_ptr password, sov_int password_len, sov_ptr salt, sov_int salt_len,
                       sov_int iterations, sov_ptr out, sov_int out_len);

#define SOV_AES256_KEY_SIZE  32
#define SOV_AES_BLOCK_SIZE   16
#define SOV_AES_GCM_IV_SIZE  12
#define SOV_AES_GCM_TAG_SIZE 16
#define SOV_CHACHA20_KEY_SIZE   32
#define SOV_CHACHA20_NONCE_SIZE 12
#define SOV_POLY1305_TAG_SIZE   16

sov_result sov_aes256_gcm_encrypt(sov_ptr key, sov_ptr iv, sov_int iv_len,
                                   sov_ptr plaintext, sov_int plaintext_len,
                                   sov_ptr aad, sov_int aad_len,
                                   sov_ptr ciphertext_out, sov_ptr tag_out);
sov_result sov_aes256_gcm_decrypt(sov_ptr key, sov_ptr iv, sov_int iv_len,
                                   sov_ptr ciphertext, sov_int ciphertext_len,
                                   sov_ptr aad, sov_int aad_len,
                                   sov_ptr tag, sov_ptr plaintext_out);

sov_result sov_chacha20_poly1305_encrypt(sov_ptr key, sov_ptr nonce,
                                          sov_ptr plaintext, sov_int plaintext_len,
                                          sov_ptr aad, sov_int aad_len,
                                          sov_ptr ciphertext_out, sov_ptr tag_out);
sov_result sov_chacha20_poly1305_decrypt(sov_ptr key, sov_ptr nonce,
                                          sov_ptr ciphertext, sov_int ciphertext_len,
                                          sov_ptr aad, sov_int aad_len,
                                          sov_ptr tag, sov_ptr plaintext_out);

void sov_random_bytes(sov_ptr buf, sov_int len);
sov_u64 sov_random_u64(void);
sov_u64 sov_random_range(sov_u64 min, sov_u64 max);
void sov_random_key(sov_ptr key_out);

sov_bool sov_secure_compare(sov_ptr a, sov_ptr b, sov_int len);
void sov_ct_memmove(sov_ptr dst, sov_ptr src, sov_int len, sov_bool flag);
sov_byte sov_ct_select_byte(sov_byte a, sov_byte b, sov_bool flag);
sov_int sov_ct_is_zero(sov_int x);
sov_int sov_ct_eq(sov_int a, sov_int b);

sov_channel* sov_channel_new(sov_int capacity);
void sov_channel_send(sov_channel* ch, sov_ptr value);
sov_ptr sov_channel_recv(sov_channel* ch);
sov_bool sov_channel_try_send(sov_channel* ch, sov_ptr value);
sov_result sov_channel_try_recv(sov_channel* ch);
void sov_channel_close(sov_channel* ch);
void sov_channel_free(sov_channel* ch);
void sov_spawn(void (*func)(sov_ptr), sov_ptr arg);
void sov_sleep(sov_int ms);

#define SOV_STATIC_ASSERT(cond, msg) _Static_assert(cond, msg)

void sov_assert(sov_bool condition, sov_string message);
void sov_panic(sov_string message);
void sov_bounds_check(sov_int index, sov_int len, sov_string array_name);
void sov_null_check(sov_ptr ptr, sov_string name);

sov_vec* sov_get_args(int argc, char** argv);
sov_string sov_getenv(sov_string name);
void sov_exit(sov_int code);
sov_int sov_time_ms(void);
sov_int sov_time_ns(void);
uint64_t sov_hash_string(sov_string s);

#endif
