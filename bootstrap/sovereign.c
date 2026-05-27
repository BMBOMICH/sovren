/*
 * ==========================================================================
 * SOVEREIGN BOOTSTRAP COMPILER
 * ==========================================================================
 * 
 * This is the pre-generated C code for the Sovereign compiler.
 * It was generated from the .sov source files and allows bootstrapping
 * the compiler without any Rust dependency.
 * 
 * BUILD:
 *   gcc -O2 -o sovereign bootstrap/sovereign.c
 *   
 * USAGE:
 *   ./sovereign build myfile.sov
 *   ./sovereign run myfile.sov
 *   ./sovereign check myfile.sov
 *   ./sovereign fmt myfile.sov
 *   
 * BOOTSTRAP:
 *   ./sovereign build src/main.sov -o bootstrap/sovereign_new.c
 *   gcc -O2 -o sovereign_new bootstrap/sovereign_new.c
 *   diff sovereign sovereign_new  # Should be identical
 *
 * Generated from:
 *   - src/stdlib_native.sov
 *   - src/stdlib_ast.sov  
 *   - src/lexer_self.sov
 *   - src/parser_self.sov
 *   - src/semantic_self.sov
 *   - src/codegen_self.sov
 *   - src/main.sov
 *
 * ==========================================================================
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <ctype.h>
#include <errno.h>
#include <time.h>

/* ==========================================================================
 * SECTION 1: TYPE DEFINITIONS
 * ========================================================================== */

typedef int64_t sov_int;
typedef double sov_float;
typedef char* sov_string;
typedef void* sov_ptr;
typedef bool sov_bool;

/* Forward declarations */
typedef struct Vec Vec;
typedef struct HashMap HashMap;
typedef struct StringBuilder StringBuilder;
typedef struct Token Token;
typedef struct Expr Expr;
typedef struct Stmt Stmt;
typedef struct Program Program;
typedef struct Lexer Lexer;
typedef struct Parser Parser;
typedef struct Analyzer Analyzer;
typedef struct Codegen Codegen;

/* ==========================================================================
 * SECTION 2: MEMORY MANAGEMENT  
 * ========================================================================== */

static size_t sov_alloc_count = 0;
static size_t sov_free_count = 0;

static void* sov_alloc(size_t size) {
    void* ptr = calloc(1, size);
    if (ptr) sov_alloc_count++;
    return ptr;
}

static void sov_free(void* ptr) {
    if (ptr) {
        free(ptr);
        sov_free_count++;
    }
}

static void* sov_realloc(void* ptr, size_t size) {
    return realloc(ptr, size);
}

/* Sensitive memory zeroing */
static void sov_secure_zero(void* ptr, size_t size) {
    volatile unsigned char* p = (volatile unsigned char*)ptr;
    while (size--) *p++ = 0;
}

/* ==========================================================================
 * SECTION 3: STRING OPERATIONS
 * ========================================================================== */

static sov_string sov_str_dup(const char* s) {
    if (!s) return NULL;
    size_t len = strlen(s);
    char* dup = (char*)sov_alloc(len + 1);
    if (dup) memcpy(dup, s, len + 1);
    return dup;
}

static sov_string sov_str_concat(const char* a, const char* b) {
    if (!a) a = "";
    if (!b) b = "";
    size_t la = strlen(a);
    size_t lb = strlen(b);
    char* result = (char*)sov_alloc(la + lb + 1);
    if (result) {
        memcpy(result, a, la);
        memcpy(result + la, b, lb + 1);
    }
    return result;
}

static sov_int sov_str_len(const char* s) {
    return s ? (sov_int)strlen(s) : 0;
}

static sov_bool sov_str_eq(const char* a, const char* b) {
    if (!a && !b) return true;
    if (!a || !b) return false;
    return strcmp(a, b) == 0;
}

static sov_bool sov_str_starts_with(const char* s, const char* prefix) {
    if (!s || !prefix) return false;
    size_t ls = strlen(s);
    size_t lp = strlen(prefix);
    if (lp > ls) return false;
    return strncmp(s, prefix, lp) == 0;
}

static sov_bool sov_str_ends_with(const char* s, const char* suffix) {
    if (!s || !suffix) return false;
    size_t ls = strlen(s);
    size_t lsuf = strlen(suffix);
    if (lsuf > ls) return false;
    return strcmp(s + ls - lsuf, suffix) == 0;
}

static sov_bool sov_str_contains(const char* s, const char* sub) {
    if (!s || !sub) return false;
    return strstr(s, sub) != NULL;
}

static sov_string sov_str_trim(const char* s) {
    if (!s) return sov_str_dup("");
    while (isspace((unsigned char)*s)) s++;
    if (*s == '\0') return sov_str_dup("");
    const char* end = s + strlen(s) - 1;
    while (end > s && isspace((unsigned char)*end)) end--;
    size_t len = end - s + 1;
    char* result = (char*)sov_alloc(len + 1);
    if (result) {
        memcpy(result, s, len);
        result[len] = '\0';
    }
    return result;
}

static sov_string sov_str_substring(const char* s, sov_int start, sov_int len) {
    if (!s) return sov_str_dup("");
    sov_int slen = sov_str_len(s);
    if (start < 0) start = 0;
    if (start >= slen) return sov_str_dup("");
    if (len < 0 || start + len > slen) len = slen - start;
    char* result = (char*)sov_alloc(len + 1);
    if (result) {
        memcpy(result, s + start, len);
        result[len] = '\0';
    }
    return result;
}

static sov_int sov_str_find(const char* s, const char* sub) {
    if (!s || !sub) return -1;
    const char* pos = strstr(s, sub);
    if (!pos) return -1;
    return (sov_int)(pos - s);
}

static sov_string sov_str_replace(const char* s, const char* old, const char* new_s) {
    if (!s || !old || !new_s) return sov_str_dup(s ? s : "");
    
    size_t old_len = strlen(old);
    size_t new_len = strlen(new_s);
    
    /* Count occurrences */
    size_t count = 0;
    const char* pos = s;
    while ((pos = strstr(pos, old)) != NULL) {
        count++;
        pos += old_len;
    }
    
    if (count == 0) return sov_str_dup(s);
    
    /* Allocate result */
    size_t result_len = strlen(s) + count * (new_len - old_len);
    char* result = (char*)sov_alloc(result_len + 1);
    if (!result) return NULL;
    
    /* Build result */
    char* dest = result;
    pos = s;
    const char* next;
    while ((next = strstr(pos, old)) != NULL) {
        size_t prefix_len = next - pos;
        memcpy(dest, pos, prefix_len);
        dest += prefix_len;
        memcpy(dest, new_s, new_len);
        dest += new_len;
        pos = next + old_len;
    }
    strcpy(dest, pos);
    
    return result;
}

static char sov_str_char_at(const char* s, sov_int index) {
    if (!s || index < 0 || index >= sov_str_len(s)) return '\0';
    return s[index];
}

/* ==========================================================================
 * SECTION 4: VECTOR (DYNAMIC ARRAY)
 * ========================================================================== */

struct Vec {
    void** data;
    size_t len;
    size_t cap;
};

static Vec* vec_new(void) {
    Vec* v = (Vec*)sov_alloc(sizeof(Vec));
    if (v) {
        v->data = NULL;
        v->len = 0;
        v->cap = 0;
    }
    return v;
}

static void vec_free(Vec* v) {
    if (v) {
        sov_free(v->data);
        sov_free(v);
    }
}

static void vec_push(Vec* v, void* item) {
    if (!v) return;
    if (v->len >= v->cap) {
        size_t new_cap = v->cap == 0 ? 8 : v->cap * 2;
        void** new_data = (void**)sov_realloc(v->data, new_cap * sizeof(void*));
        if (!new_data) return;
        v->data = new_data;
        v->cap = new_cap;
    }
    v->data[v->len++] = item;
}

static void* vec_get(Vec* v, size_t index) {
    if (!v || index >= v->len) return NULL;
    return v->data[index];
}

static size_t vec_len(Vec* v) {
    return v ? v->len : 0;
}

static void* vec_pop(Vec* v) {
    if (!v || v->len == 0) return NULL;
    return v->data[--v->len];
}

/* String vector helpers */
static void vec_push_str(Vec* v, const char* s) {
    vec_push(v, sov_str_dup(s));
}

static const char* vec_get_str(Vec* v, size_t index) {
    return (const char*)vec_get(v, index);
}

/* Integer vector helpers */
static void vec_push_int(Vec* v, sov_int val) {
    sov_int* p = (sov_int*)sov_alloc(sizeof(sov_int));
    if (p) {
        *p = val;
        vec_push(v, p);
    }
}

static sov_int vec_get_int(Vec* v, size_t index) {
    sov_int* p = (sov_int*)vec_get(v, index);
    return p ? *p : 0;
}

/* ==========================================================================
 * SECTION 5: HASH MAP
 * ========================================================================== */

#define HASHMAP_INITIAL_CAP 16
#define HASHMAP_LOAD_FACTOR 0.75

typedef struct HashEntry {
    char* key;
    void* value;
    struct HashEntry* next;
} HashEntry;

struct HashMap {
    HashEntry** buckets;
    size_t cap;
    size_t len;
};

static uint64_t hash_string(const char* s) {
    uint64_t h = 5381;
    while (*s) {
        h = ((h << 5) + h) + (unsigned char)*s++;
    }
    return h;
}

static HashMap* hashmap_new(void) {
    HashMap* m = (HashMap*)sov_alloc(sizeof(HashMap));
    if (m) {
        m->cap = HASHMAP_INITIAL_CAP;
        m->len = 0;
        m->buckets = (HashEntry**)sov_alloc(m->cap * sizeof(HashEntry*));
    }
    return m;
}

static void hashmap_free(HashMap* m) {
    if (!m) return;
    for (size_t i = 0; i < m->cap; i++) {
        HashEntry* e = m->buckets[i];
        while (e) {
            HashEntry* next = e->next;
            sov_free(e->key);
            sov_free(e);
            e = next;
        }
    }
    sov_free(m->buckets);
    sov_free(m);
}

static void hashmap_set(HashMap* m, const char* key, void* value) {
    if (!m || !key) return;
    
    uint64_t h = hash_string(key);
    size_t idx = h % m->cap;
    
    /* Check if key exists */
    HashEntry* e = m->buckets[idx];
    while (e) {
        if (strcmp(e->key, key) == 0) {
            e->value = value;
            return;
        }
        e = e->next;
    }
    
    /* Insert new entry */
    e = (HashEntry*)sov_alloc(sizeof(HashEntry));
    if (e) {
        e->key = sov_str_dup(key);
        e->value = value;
        e->next = m->buckets[idx];
        m->buckets[idx] = e;
        m->len++;
    }
}

static void* hashmap_get(HashMap* m, const char* key) {
    if (!m || !key) return NULL;
    
    uint64_t h = hash_string(key);
    size_t idx = h % m->cap;
    
    HashEntry* e = m->buckets[idx];
    while (e) {
        if (strcmp(e->key, key) == 0) {
            return e->value;
        }
        e = e->next;
    }
    return NULL;
}

static sov_bool hashmap_has(HashMap* m, const char* key) {
    return hashmap_get(m, key) != NULL;
}

/* ==========================================================================
 * SECTION 6: STRING BUILDER
 * ========================================================================== */

struct StringBuilder {
    char* data;
    size_t len;
    size_t cap;
};

static StringBuilder* sb_new(void) {
    StringBuilder* sb = (StringBuilder*)sov_alloc(sizeof(StringBuilder));
    if (sb) {
        sb->cap = 256;
        sb->data = (char*)sov_alloc(sb->cap);
        sb->len = 0;
        if (sb->data) sb->data[0] = '\0';
    }
    return sb;
}

static void sb_free(StringBuilder* sb) {
    if (sb) {
        sov_free(sb->data);
        sov_free(sb);
    }
}

static void sb_append(StringBuilder* sb, const char* s) {
    if (!sb || !s) return;
    size_t slen = strlen(s);
    if (sb->len + slen >= sb->cap) {
        size_t new_cap = (sb->len + slen + 1) * 2;
        char* new_data = (char*)sov_realloc(sb->data, new_cap);
        if (!new_data) return;
        sb->data = new_data;
        sb->cap = new_cap;
    }
    memcpy(sb->data + sb->len, s, slen + 1);
    sb->len += slen;
}

static void sb_append_char(StringBuilder* sb, char c) {
    char buf[2] = {c, '\0'};
    sb_append(sb, buf);
}

static void sb_append_int(StringBuilder* sb, sov_int n) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%lld", (long long)n);
    sb_append(sb, buf);
}

static sov_string sb_to_string(StringBuilder* sb) {
    return sb ? sov_str_dup(sb->data) : sov_str_dup("");
}

/* ==========================================================================
 * SECTION 7: FILE I/O
 * ========================================================================== */

static sov_string file_read_all(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    char* content = (char*)sov_alloc(size + 1);
    if (content) {
        fread(content, 1, size, f);
        content[size] = '\0';
    }
    fclose(f);
    return content;
}

static sov_bool file_write_all(const char* path, const char* content) {
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    
    size_t len = strlen(content);
    size_t written = fwrite(content, 1, len, f);
    fclose(f);
    
    return written == len;
}

static sov_bool file_exists(const char* path) {
    FILE* f = fopen(path, "r");
    if (f) {
        fclose(f);
        return true;
    }
    return false;
}

/* ==========================================================================
 * SECTION 8: TOKEN TYPES
 * ========================================================================== */

typedef enum {
    TOK_EOF = 0,
    TOK_NEWLINE,
    TOK_INDENT,
    TOK_DEDENT,
    
    /* Literals */
    TOK_INTEGER,
    TOK_FLOAT,
    TOK_STRING,
    TOK_CHAR,
    TOK_TRUE,
    TOK_FALSE,
    TOK_NULL,
    
    /* Identifiers */
    TOK_IDENT,
    
    /* Keywords */
    TOK_SET,
    TOK_TASK,
    TOK_CHECK,
    TOK_LOOP,
    TOK_RETURN,
    TOK_BREAK,
    TOK_CONTINUE,
    TOK_STRUCT,
    TOK_ENUM,
    TOK_MATCH,
    TOK_IMPORT,
    TOK_CONST,
    TOK_EXTERN,
    TOK_INLINE,
    TOK_SENSITIVE,
    TOK_OVERRIDE,
    TOK_PURGE,
    TOK_SPAWN,
    TOK_ASYNC,
    TOK_AWAIT,
    TOK_DEFER,
    TOK_TEST,
    TOK_ASSERT,
    TOK_PRINT,
    TOK_PRINT_FMT,
    TOK_ALLOC,
    TOK_FREE,
    TOK_ELSE,
    TOK_FROM,
    TOK_TO,
    TOK_TIMES,
    TOK_IN,
    TOK_AND,
    TOK_OR,
    TOK_NOT,
    TOK_AS,
    TOK_TYPE,
    TOK_COMPTIME,
    TOK_CONSTANT_TIME,
    TOK_NAMESPACE,
    TOK_USE,
    TOK_OK,
    TOK_ERR,
    TOK_FN,
    TOK_COPY,
    TOK_WHERE,
    TOK_STATIC_ASSERT,
    TOK_MAKE_CHAN,
    TOK_CHAN,
    
    /* Type keywords */
    TOK_INT8,
    TOK_INT16,
    TOK_INT64,
    TOK_UINT8,
    TOK_UINT16,
    TOK_UINT32,
    TOK_UINT64,
    
    /* Operators */
    TOK_PLUS,
    TOK_MINUS,
    TOK_STAR,
    TOK_SLASH,
    TOK_PERCENT,
    TOK_CARET,
    TOK_AMP,
    TOK_PIPE,
    TOK_TILDE,
    TOK_LT,
    TOK_GT,
    TOK_EQ,
    TOK_BANG,
    TOK_DOT,
    TOK_COMMA,
    TOK_COLON,
    TOK_SEMICOLON,
    TOK_QUESTION,
    TOK_AT,
    TOK_HASH,
    TOK_DOLLAR,
    
    /* Compound operators */
    TOK_EQEQ,
    TOK_NEQ,
    TOK_LEQ,
    TOK_GEQ,
    TOK_ARROW,
    TOK_FAT_ARROW,
    TOK_PLUS_EQ,
    TOK_MINUS_EQ,
    TOK_STAR_EQ,
    TOK_SLASH_EQ,
    TOK_SHL,
    TOK_SHR,
    TOK_DOTDOT,
    TOK_DOTDOTDOT,
    TOK_COLONCOLON,
    
    /* Delimiters */
    TOK_LPAREN,
    TOK_RPAREN,
    TOK_LBRACE,
    TOK_RBRACE,
    TOK_LBRACKET,
    TOK_RBRACKET,
    
    TOK_COUNT
} TokenKind;

struct Token {
    TokenKind kind;
    sov_string value;
    sov_int int_value;
    sov_float float_value;
    sov_int line;
    sov_int col;
};

static Token* token_new(TokenKind kind, sov_int line, sov_int col) {
    Token* t = (Token*)sov_alloc(sizeof(Token));
    if (t) {
        t->kind = kind;
        t->value = NULL;
        t->int_value = 0;
        t->float_value = 0.0;
        t->line = line;
        t->col = col;
    }
    return t;
}

static void token_free(Token* t) {
    if (t) {
        sov_free(t->value);
        sov_free(t);
    }
}

static const char* token_kind_name(TokenKind kind) {
    static const char* names[] = {
        "EOF", "NEWLINE", "INDENT", "DEDENT",
        "INTEGER", "FLOAT", "STRING", "CHAR", "TRUE", "FALSE", "NULL",
        "IDENT",
        "SET", "TASK", "CHECK", "LOOP", "RETURN", "BREAK", "CONTINUE",
        "STRUCT", "ENUM", "MATCH", "IMPORT", "CONST", "EXTERN", "INLINE",
        "SENSITIVE", "OVERRIDE", "PURGE", "SPAWN", "ASYNC", "AWAIT", "DEFER",
        "TEST", "ASSERT", "PRINT", "PRINT_FMT", "ALLOC", "FREE",
        "ELSE", "FROM", "TO", "TIMES", "IN", "AND", "OR", "NOT", "AS",
        "TYPE", "COMPTIME", "CONSTANT_TIME", "NAMESPACE", "USE", "OK", "ERR",
        "FN", "COPY", "WHERE", "STATIC_ASSERT", "MAKE_CHAN", "CHAN",
        "INT8", "INT16", "INT64", "UINT8", "UINT16", "UINT32", "UINT64",
        "+", "-", "*", "/", "%", "^", "&", "|", "~", "<", ">", "=", "!",
        ".", ",", ":", ";", "?", "@", "#", "$",
        "==", "!=", "<=", ">=", "->", "=>", "+=", "-=", "*=", "/=",
        "<<", ">>", "..", "...", "::",
        "(", ")", "{", "}", "[", "]"
    };
    if (kind >= 0 && kind < TOK_COUNT) return names[kind];
    return "UNKNOWN";
}

/* ==========================================================================
 * SECTION 9: LEXER
 * ========================================================================== */

struct Lexer {
    const char* source;
    size_t pos;
    size_t len;
    sov_int line;
    sov_int col;
    const char* filename;
};

static Lexer* lexer_new(const char* source, const char* filename) {
    Lexer* l = (Lexer*)sov_alloc(sizeof(Lexer));
    if (l) {
        l->source = source;
        l->pos = 0;
        l->len = source ? strlen(source) : 0;
        l->line = 1;
        l->col = 1;
        l->filename = filename;
    }
    return l;
}

static void lexer_free(Lexer* l) {
    sov_free(l);
}

static char lexer_peek(Lexer* l) {
    if (l->pos >= l->len) return '\0';
    return l->source[l->pos];
}

static char lexer_peek_next(Lexer* l) {
    if (l->pos + 1 >= l->len) return '\0';
    return l->source[l->pos + 1];
}

static char lexer_advance(Lexer* l) {
    if (l->pos >= l->len) return '\0';
    char c = l->source[l->pos++];
    if (c == '\n') {
        l->line++;
        l->col = 1;
    } else {
        l->col++;
    }
    return c;
}

static void lexer_skip_whitespace(Lexer* l) {
    while (l->pos < l->len) {
        char c = lexer_peek(l);
        if (c == ' ' || c == '\t' || c == '\r') {
            lexer_advance(l);
        } else if (c == '/' && lexer_peek_next(l) == '/') {
            /* Line comment */
            while (l->pos < l->len && lexer_peek(l) != '\n') {
                lexer_advance(l);
            }
        } else if (c == '/' && lexer_peek_next(l) == '*') {
            /* Block comment */
            lexer_advance(l);
            lexer_advance(l);
            while (l->pos < l->len) {
                if (lexer_peek(l) == '*' && lexer_peek_next(l) == '/') {
                    lexer_advance(l);
                    lexer_advance(l);
                    break;
                }
                lexer_advance(l);
            }
        } else {
            break;
        }
    }
}

static Token* lexer_read_string(Lexer* l) {
    sov_int start_line = l->line;
    sov_int start_col = l->col;
    
    char quote = lexer_advance(l); /* consume opening quote */
    StringBuilder* sb = sb_new();
    
    while (l->pos < l->len && lexer_peek(l) != quote) {
        char c = lexer_advance(l);
        if (c == '\\' && l->pos < l->len) {
            char esc = lexer_advance(l);
            switch (esc) {
                case 'n': sb_append_char(sb, '\n'); break;
                case 't': sb_append_char(sb, '\t'); break;
                case 'r': sb_append_char(sb, '\r'); break;
                case '\\': sb_append_char(sb, '\\'); break;
                case '"': sb_append_char(sb, '"'); break;
                case '\'': sb_append_char(sb, '\''); break;
                case '0': sb_append_char(sb, '\0'); break;
                default: sb_append_char(sb, esc); break;
            }
        } else {
            sb_append_char(sb, c);
        }
    }
    
    if (l->pos < l->len) lexer_advance(l); /* consume closing quote */
    
    Token* t = token_new(TOK_STRING, start_line, start_col);
    t->value = sb_to_string(sb);
    sb_free(sb);
    return t;
}

static Token* lexer_read_number(Lexer* l) {
    sov_int start_line = l->line;
    sov_int start_col = l->col;
    StringBuilder* sb = sb_new();
    
    sov_bool is_float = false;
    sov_bool is_hex = false;
    sov_bool is_bin = false;
    sov_bool is_oct = false;
    
    /* Check for hex/bin/oct prefix */
    if (lexer_peek(l) == '0' && l->pos + 1 < l->len) {
        char next = lexer_peek_next(l);
        if (next == 'x' || next == 'X') {
            is_hex = true;
            sb_append_char(sb, lexer_advance(l));
            sb_append_char(sb, lexer_advance(l));
        } else if (next == 'b' || next == 'B') {
            is_bin = true;
            sb_append_char(sb, lexer_advance(l));
            sb_append_char(sb, lexer_advance(l));
        } else if (next == 'o' || next == 'O') {
            is_oct = true;
            sb_append_char(sb, lexer_advance(l));
            sb_append_char(sb, lexer_advance(l));
        }
    }
    
    while (l->pos < l->len) {
        char c = lexer_peek(l);
        if (isdigit(c) || (is_hex && isxdigit(c)) || c == '_') {
            if (c != '_') sb_append_char(sb, c);
            lexer_advance(l);
        } else if (c == '.' && !is_float && !is_hex && !is_bin && !is_oct) {
            if (isdigit(lexer_peek_next(l))) {
                is_float = true;
                sb_append_char(sb, lexer_advance(l));
            } else {
                break;
            }
        } else if ((c == 'e' || c == 'E') && !is_hex && !is_bin && !is_oct) {
            is_float = true;
            sb_append_char(sb, lexer_advance(l));
            if (lexer_peek(l) == '+' || lexer_peek(l) == '-') {
                sb_append_char(sb, lexer_advance(l));
            }
        } else {
            break;
        }
    }
    
    Token* t;
    sov_string num_str = sb_to_string(sb);
    
    if (is_float) {
        t = token_new(TOK_FLOAT, start_line, start_col);
        t->float_value = strtod(num_str, NULL);
    } else {
        t = token_new(TOK_INTEGER, start_line, start_col);
        if (is_hex) {
            t->int_value = strtoll(num_str + 2, NULL, 16);
        } else if (is_bin) {
            t->int_value = strtoll(num_str + 2, NULL, 2);
        } else if (is_oct) {
            t->int_value = strtoll(num_str + 2, NULL, 8);
        } else {
            t->int_value = strtoll(num_str, NULL, 10);
        }
    }
    
    t->value = num_str;
    sb_free(sb);
    return t;
}

static TokenKind keyword_or_ident(const char* s) {
    /* Keywords */
    if (strcmp(s, "set") == 0) return TOK_SET;
    if (strcmp(s, "task") == 0) return TOK_TASK;
    if (strcmp(s, "check") == 0) return TOK_CHECK;
    if (strcmp(s, "loop") == 0) return TOK_LOOP;
    if (strcmp(s, "return") == 0) return TOK_RETURN;
    if (strcmp(s, "break") == 0) return TOK_BREAK;
    if (strcmp(s, "continue") == 0) return TOK_CONTINUE;
    if (strcmp(s, "struct") == 0) return TOK_STRUCT;
    if (strcmp(s, "enum") == 0) return TOK_ENUM;
    if (strcmp(s, "match") == 0) return TOK_MATCH;
    if (strcmp(s, "import") == 0) return TOK_IMPORT;
    if (strcmp(s, "const") == 0) return TOK_CONST;
    if (strcmp(s, "extern") == 0) return TOK_EXTERN;
    if (strcmp(s, "inline") == 0) return TOK_INLINE;
    if (strcmp(s, "sensitive") == 0) return TOK_SENSITIVE;
    if (strcmp(s, "override") == 0) return TOK_OVERRIDE;
    if (strcmp(s, "purge") == 0) return TOK_PURGE;
    if (strcmp(s, "spawn") == 0) return TOK_SPAWN;
    if (strcmp(s, "async") == 0) return TOK_ASYNC;
    if (strcmp(s, "await") == 0) return TOK_AWAIT;
    if (strcmp(s, "defer") == 0) return TOK_DEFER;
    if (strcmp(s, "test") == 0) return TOK_TEST;
    if (strcmp(s, "assert") == 0) return TOK_ASSERT;
    if (strcmp(s, "print") == 0) return TOK_PRINT;
    if (strcmp(s, "print_fmt") == 0) return TOK_PRINT_FMT;
    if (strcmp(s, "alloc") == 0) return TOK_ALLOC;
    if (strcmp(s, "free") == 0) return TOK_FREE;
    if (strcmp(s, "else") == 0) return TOK_ELSE;
    if (strcmp(s, "from") == 0) return TOK_FROM;
    if (strcmp(s, "to") == 0) return TOK_TO;
    if (strcmp(s, "times") == 0) return TOK_TIMES;
    if (strcmp(s, "in") == 0) return TOK_IN;
    if (strcmp(s, "and") == 0) return TOK_AND;
    if (strcmp(s, "or") == 0) return TOK_OR;
    if (strcmp(s, "not") == 0) return TOK_NOT;
    if (strcmp(s, "as") == 0) return TOK_AS;
    if (strcmp(s, "true") == 0) return TOK_TRUE;
    if (strcmp(s, "false") == 0) return TOK_FALSE;
    if (strcmp(s, "null") == 0) return TOK_NULL;
    if (strcmp(s, "type") == 0) return TOK_TYPE;
    if (strcmp(s, "comptime") == 0) return TOK_COMPTIME;
    if (strcmp(s, "constant_time") == 0) return TOK_CONSTANT_TIME;
    if (strcmp(s, "namespace") == 0) return TOK_NAMESPACE;
    if (strcmp(s, "use") == 0) return TOK_USE;
    if (strcmp(s, "ok") == 0) return TOK_OK;
    if (strcmp(s, "err") == 0) return TOK_ERR;
    if (strcmp(s, "copy") == 0) return TOK_COPY;
    if (strcmp(s, "where") == 0) return TOK_WHERE;
    if (strcmp(s, "static_assert") == 0) return TOK_STATIC_ASSERT;
    if (strcmp(s, "make_chan") == 0) return TOK_MAKE_CHAN;
    if (strcmp(s, "chan") == 0) return TOK_CHAN;
    
    /* Type keywords */
    if (strcmp(s, "int8") == 0) return TOK_INT8;
    if (strcmp(s, "int16") == 0) return TOK_INT16;
    if (strcmp(s, "int64") == 0) return TOK_INT64;
    if (strcmp(s, "uint8") == 0) return TOK_UINT8;
    if (strcmp(s, "uint16") == 0) return TOK_UINT16;
    if (strcmp(s, "uint32") == 0) return TOK_UINT32;
    if (strcmp(s, "uint64") == 0) return TOK_UINT64;
    
    /* Aliases for familiar syntax */
    if (strcmp(s, "fn") == 0) return TOK_FN;
    if (strcmp(s, "def") == 0) return TOK_TASK;
    if (strcmp(s, "func") == 0) return TOK_TASK;
    if (strcmp(s, "let") == 0) return TOK_SET;
    if (strcmp(s, "var") == 0) return TOK_SET;
    if (strcmp(s, "if") == 0) return TOK_CHECK;
    if (strcmp(s, "for") == 0) return TOK_LOOP;
    if (strcmp(s, "while") == 0) return TOK_LOOP;
    if (strcmp(s, "unsafe") == 0) return TOK_OVERRIDE;
    if (strcmp(s, "None") == 0) return TOK_NULL;
    if (strcmp(s, "nil") == 0) return TOK_NULL;
    if (strcmp(s, "switch") == 0) return TOK_MATCH;
    
    return TOK_IDENT;
}

static Token* lexer_read_ident(Lexer* l) {
    sov_int start_line = l->line;
    sov_int start_col = l->col;
    StringBuilder* sb = sb_new();
    
    while (l->pos < l->len) {
        char c = lexer_peek(l);
        if (isalnum(c) || c == '_') {
            sb_append_char(sb, lexer_advance(l));
        } else {
            break;
        }
    }
    
    sov_string ident = sb_to_string(sb);
    TokenKind kind = keyword_or_ident(ident);
    
    Token* t = token_new(kind, start_line, start_col);
    if (kind == TOK_IDENT) {
        t->value = ident;
    } else {
        sov_free(ident);
    }
    
    sb_free(sb);
    return t;
}

static Token* lexer_next_token(Lexer* l) {
    lexer_skip_whitespace(l);
    
    if (l->pos >= l->len) {
        return token_new(TOK_EOF, l->line, l->col);
    }
    
    sov_int line = l->line;
    sov_int col = l->col;
    char c = lexer_peek(l);
    
    /* Newline */
    if (c == '\n') {
        lexer_advance(l);
        return token_new(TOK_NEWLINE, line, col);
    }
    
    /* String */
    if (c == '"' || c == '\'') {
        return lexer_read_string(l);
    }
    
    /* Number */
    if (isdigit(c)) {
        return lexer_read_number(l);
    }
    
    /* Identifier or keyword */
    if (isalpha(c) || c == '_') {
        return lexer_read_ident(l);
    }
    
    /* Two-character operators */
    char next = lexer_peek_next(l);
    
    if (c == '=' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_EQEQ, line, col); }
    if (c == '!' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_NEQ, line, col); }
    if (c == '<' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_LEQ, line, col); }
    if (c == '>' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_GEQ, line, col); }
    if (c == '-' && next == '>') { lexer_advance(l); lexer_advance(l); return token_new(TOK_ARROW, line, col); }
    if (c == '=' && next == '>') { lexer_advance(l); lexer_advance(l); return token_new(TOK_FAT_ARROW, line, col); }
    if (c == '+' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_PLUS_EQ, line, col); }
    if (c == '-' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_MINUS_EQ, line, col); }
    if (c == '*' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_STAR_EQ, line, col); }
    if (c == '/' && next == '=') { lexer_advance(l); lexer_advance(l); return token_new(TOK_SLASH_EQ, line, col); }
    if (c == '<' && next == '<') { lexer_advance(l); lexer_advance(l); return token_new(TOK_SHL, line, col); }
    if (c == '>' && next == '>') { lexer_advance(l); lexer_advance(l); return token_new(TOK_SHR, line, col); }
    if (c == ':' && next == ':') { lexer_advance(l); lexer_advance(l); return token_new(TOK_COLONCOLON, line, col); }
    if (c == '.' && next == '.') {
        lexer_advance(l);
        lexer_advance(l);
        if (lexer_peek(l) == '.') {
            lexer_advance(l);
            return token_new(TOK_DOTDOTDOT, line, col);
        }
        return token_new(TOK_DOTDOT, line, col);
    }
    
    /* Single-character operators */
    lexer_advance(l);
    switch (c) {
        case '+': return token_new(TOK_PLUS, line, col);
        case '-': return token_new(TOK_MINUS, line, col);
        case '*': return token_new(TOK_STAR, line, col);
        case '/': return token_new(TOK_SLASH, line, col);
        case '%': return token_new(TOK_PERCENT, line, col);
        case '^': return token_new(TOK_CARET, line, col);
        case '&': return token_new(TOK_AMP, line, col);
        case '|': return token_new(TOK_PIPE, line, col);
        case '~': return token_new(TOK_TILDE, line, col);
        case '<': return token_new(TOK_LT, line, col);
        case '>': return token_new(TOK_GT, line, col);
        case '=': return token_new(TOK_EQ, line, col);
        case '!': return token_new(TOK_BANG, line, col);
        case '.': return token_new(TOK_DOT, line, col);
        case ',': return token_new(TOK_COMMA, line, col);
        case ':': return token_new(TOK_COLON, line, col);
        case ';': return token_new(TOK_SEMICOLON, line, col);
        case '?': return token_new(TOK_QUESTION, line, col);
        case '@': return token_new(TOK_AT, line, col);
        case '#': return token_new(TOK_HASH, line, col);
        case '$': return token_new(TOK_DOLLAR, line, col);
        case '(': return token_new(TOK_LPAREN, line, col);
        case ')': return token_new(TOK_RPAREN, line, col);
        case '{': return token_new(TOK_LBRACE, line, col);
        case '}': return token_new(TOK_RBRACE, line, col);
        case '[': return token_new(TOK_LBRACKET, line, col);
        case ']': return token_new(TOK_RBRACKET, line, col);
        default: {
            Token* t = token_new(TOK_IDENT, line, col);
            char buf[2] = {c, '\0'};
            t->value = sov_str_dup(buf);
            return t;
        }
    }
}

static Vec* lexer_tokenize(Lexer* l) {
    Vec* tokens = vec_new();
    while (true) {
        Token* t = lexer_next_token(l);
        vec_push(tokens, t);
        if (t->kind == TOK_EOF) break;
    }
    return tokens;
}

/* ==========================================================================
 * SECTION 10: AST TYPES
 * ========================================================================== */

typedef enum {
    EXPR_INT,
    EXPR_FLOAT,
    EXPR_STRING,
    EXPR_BOOL,
    EXPR_NULL,
    EXPR_IDENT,
    EXPR_BINARY,
    EXPR_UNARY,
    EXPR_CALL,
    EXPR_INDEX,
    EXPR_FIELD,
    EXPR_STRUCT_INIT,
    EXPR_ARRAY_INIT,
    EXPR_LAMBDA,
    EXPR_CAST,
    EXPR_SIZEOF,
    EXPR_ADDRESSOF,
    EXPR_DEREF
} ExprKind;

typedef enum {
    STMT_EXPR,
    STMT_SET,
    STMT_ASSIGN,
    STMT_TASK,
    STMT_RETURN,
    STMT_CHECK,
    STMT_LOOP,
    STMT_BREAK,
    STMT_CONTINUE,
    STMT_STRUCT,
    STMT_ENUM,
    STMT_MATCH,
    STMT_IMPORT,
    STMT_CONST,
    STMT_EXTERN,
    STMT_PRINT,
    STMT_PRINT_FMT,
    STMT_ALLOC,
    STMT_FREE,
    STMT_PURGE,
    STMT_DEFER,
    STMT_SPAWN,
    STMT_TEST,
    STMT_ASSERT,
    STMT_BLOCK
} StmtKind;

struct Expr {
    ExprKind kind;
    sov_int line;
    sov_int col;
    
    /* Literal values */
    sov_int int_val;
    sov_float float_val;
    sov_string str_val;
    sov_bool bool_val;
    
    /* Identifier name */
    sov_string name;
    
    /* Binary/Unary operator */
    sov_string op;
    Expr* left;
    Expr* right;
    Expr* operand;
    
    /* Call expression */
    Expr* callee;
    Vec* args;  /* Vec<Expr*> */
    
    /* Index expression */
    Expr* object;
    Expr* index;
    
    /* Field access */
    sov_string field;
    
    /* Struct init */
    Vec* field_names;  /* Vec<string> */
    Vec* field_values; /* Vec<Expr*> */
    
    /* Array init */
    Vec* elements;  /* Vec<Expr*> */
    
    /* Lambda */
    Vec* params;  /* Vec<string> */
    Vec* body;    /* Vec<Stmt*> */
    
    /* Type cast */
    sov_string type_name;
};

struct Stmt {
    StmtKind kind;
    sov_int line;
    sov_int col;
    
    /* Expression statement */
    Expr* expr;
    
    /* Variable declaration */
    sov_string name;
    sov_string type_annotation;
    Expr* init_value;
    sov_bool is_sensitive;
    sov_bool is_const;
    
    /* Function/task declaration */
    sov_string task_name;
    Vec* params;       /* Vec<{name, type}> */
    sov_string return_type;
    Vec* body;         /* Vec<Stmt*> */
    sov_bool is_inline;
    sov_bool is_extern;
    sov_bool is_async;
    
    /* Return statement */
    Expr* return_value;
    
    /* Conditional (check) */
    Expr* condition;
    Vec* then_block;   /* Vec<Stmt*> */
    Vec* else_block;   /* Vec<Stmt*> */
    
    /* Loop */
    sov_string loop_var;
    Expr* loop_start;
    Expr* loop_end;
    Expr* loop_times;
    Vec* loop_body;    /* Vec<Stmt*> */
    
    /* Struct definition */
    sov_string struct_name;
    Vec* struct_fields; /* Vec<{name, type}> */
    
    /* Enum definition */
    sov_string enum_name;
    Vec* enum_variants; /* Vec<string> */
    
    /* Match */
    Expr* match_expr;
    Vec* match_arms;   /* Vec<{pattern, body}> */
    
    /* Import */
    sov_string import_path;
    
    /* Print */
    Expr* print_expr;
    sov_string format_string;
    Vec* format_args;  /* Vec<Expr*> */
    
    /* Spawn */
    sov_string thread_handle;
    Vec* spawn_body;   /* Vec<Stmt*> */
    
    /* Test */
    sov_string test_name;
    Vec* test_body;    /* Vec<Stmt*> */
    
    /* Assert */
    Expr* assert_expr;
    sov_string assert_msg;
    
    /* Block */
    Vec* block_stmts;  /* Vec<Stmt*> */
};

struct Program {
    Vec* statements;  /* Vec<Stmt*> */
    const char* filename;
};

static Expr* expr_new(ExprKind kind, sov_int line, sov_int col) {
    Expr* e = (Expr*)sov_alloc(sizeof(Expr));
    if (e) {
        memset(e, 0, sizeof(Expr));
        e->kind = kind;
        e->line = line;
        e->col = col;
    }
    return e;
}

static Stmt* stmt_new(StmtKind kind, sov_int line, sov_int col) {
    Stmt* s = (Stmt*)sov_alloc(sizeof(Stmt));
    if (s) {
        memset(s, 0, sizeof(Stmt));
        s->kind = kind;
        s->line = line;
        s->col = col;
    }
    return s;
}

static Program* program_new(const char* filename) {
    Program* p = (Program*)sov_alloc(sizeof(Program));
    if (p) {
        p->statements = vec_new();
        p->filename = filename;
    }
    return p;
}

/* ==========================================================================
 * SECTION 11: PARSER
 * ========================================================================== */

struct Parser {
    Vec* tokens;
    size_t pos;
    const char* filename;
    Vec* errors;
};

static Parser* parser_new(Vec* tokens, const char* filename) {
    Parser* p = (Parser*)sov_alloc(sizeof(Parser));
    if (p) {
        p->tokens = tokens;
        p->pos = 0;
        p->filename = filename;
        p->errors = vec_new();
    }
    return p;
}

static Token* parser_current(Parser* p) {
    return (Token*)vec_get(p->tokens, p->pos);
}

static Token* parser_peek(Parser* p) {
    if (p->pos + 1 < vec_len(p->tokens)) {
        return (Token*)vec_get(p->tokens, p->pos + 1);
    }
    return parser_current(p);
}

static Token* parser_advance(Parser* p) {
    Token* t = parser_current(p);
    if (t->kind != TOK_EOF) p->pos++;
    return t;
}

static sov_bool parser_check(Parser* p, TokenKind kind) {
    return parser_current(p)->kind == kind;
}

static sov_bool parser_match(Parser* p, TokenKind kind) {
    if (parser_check(p, kind)) {
        parser_advance(p);
        return true;
    }
    return false;
}

static void parser_skip_newlines(Parser* p) {
    while (parser_check(p, TOK_NEWLINE)) {
        parser_advance(p);
    }
}

static void parser_error(Parser* p, const char* msg) {
    Token* t = parser_current(p);
    char buf[256];
    snprintf(buf, sizeof(buf), "%s:%lld:%lld: %s", 
             p->filename, (long long)t->line, (long long)t->col, msg);
    vec_push_str(p->errors, buf);
}

/* Forward declarations */
static Expr* parse_expr(Parser* p);
static Stmt* parse_stmt(Parser* p);
static Vec* parse_block(Parser* p);

static Expr* parse_primary(Parser* p) {
    Token* t = parser_current(p);
    
    if (t->kind == TOK_INTEGER) {
        parser_advance(p);
        Expr* e = expr_new(EXPR_INT, t->line, t->col);
        e->int_val = t->int_value;
        return e;
    }
    
    if (t->kind == TOK_FLOAT) {
        parser_advance(p);
        Expr* e = expr_new(EXPR_FLOAT, t->line, t->col);
        e->float_val = t->float_value;
        return e;
    }
    
    if (t->kind == TOK_STRING) {
        parser_advance(p);
        Expr* e = expr_new(EXPR_STRING, t->line, t->col);
        e->str_val = sov_str_dup(t->value);
        return e;
    }
    
    if (t->kind == TOK_TRUE || t->kind == TOK_FALSE) {
        parser_advance(p);
        Expr* e = expr_new(EXPR_BOOL, t->line, t->col);
        e->bool_val = (t->kind == TOK_TRUE);
        return e;
    }
    
    if (t->kind == TOK_NULL) {
        parser_advance(p);
        return expr_new(EXPR_NULL, t->line, t->col);
    }
    
    if (t->kind == TOK_IDENT) {
        parser_advance(p);
        Expr* e = expr_new(EXPR_IDENT, t->line, t->col);
        e->name = sov_str_dup(t->value);
        return e;
    }
    
    if (t->kind == TOK_LPAREN) {
        parser_advance(p);
        Expr* e = parse_expr(p);
        if (!parser_match(p, TOK_RPAREN)) {
            parser_error(p, "expected ')'");
        }
        return e;
    }
    
    parser_error(p, "expected expression");
    parser_advance(p);
    return expr_new(EXPR_NULL, t->line, t->col);
}

static Expr* parse_postfix(Parser* p) {
    Expr* left = parse_primary(p);
    
    while (true) {
        Token* t = parser_current(p);
        
        /* Function call */
        if (t->kind == TOK_LPAREN) {
            parser_advance(p);
            Expr* call = expr_new(EXPR_CALL, t->line, t->col);
            call->callee = left;
            call->args = vec_new();
            
            if (!parser_check(p, TOK_RPAREN)) {
                do {
                    vec_push(call->args, parse_expr(p));
                } while (parser_match(p, TOK_COMMA));
            }
            
            if (!parser_match(p, TOK_RPAREN)) {
                parser_error(p, "expected ')'");
            }
            
            left = call;
            continue;
        }
        
        /* Index */
        if (t->kind == TOK_LBRACKET) {
            parser_advance(p);
            Expr* idx = expr_new(EXPR_INDEX, t->line, t->col);
            idx->object = left;
            idx->index = parse_expr(p);
            
            if (!parser_match(p, TOK_RBRACKET)) {
                parser_error(p, "expected ']'");
            }
            
            left = idx;
            continue;
        }
        
        /* Field access */
        if (t->kind == TOK_DOT) {
            parser_advance(p);
            Token* field = parser_current(p);
            if (field->kind != TOK_IDENT) {
                parser_error(p, "expected field name");
            } else {
                parser_advance(p);
                Expr* fld = expr_new(EXPR_FIELD, t->line, t->col);
                fld->object = left;
                fld->field = sov_str_dup(field->value);
                left = fld;
            }
            continue;
        }
        
        break;
    }
    
    return left;
}

static Expr* parse_unary(Parser* p) {
    Token* t = parser_current(p);
    
    if (t->kind == TOK_MINUS || t->kind == TOK_BANG || 
        t->kind == TOK_NOT || t->kind == TOK_AMP || t->kind == TOK_STAR) {
        parser_advance(p);
        Expr* e = expr_new(EXPR_UNARY, t->line, t->col);
        e->op = sov_str_dup(token_kind_name(t->kind));
        e->operand = parse_unary(p);
        return e;
    }
    
    return parse_postfix(p);
}

static Expr* parse_multiplicative(Parser* p) {
    Expr* left = parse_unary(p);
    
    while (parser_check(p, TOK_STAR) || parser_check(p, TOK_SLASH) || parser_check(p, TOK_PERCENT)) {
        Token* t = parser_advance(p);
        Expr* e = expr_new(EXPR_BINARY, t->line, t->col);
        e->op = sov_str_dup(token_kind_name(t->kind));
        e->left = left;
        e->right = parse_unary(p);
        left = e;
    }
    
    return left;
}

static Expr* parse_additive(Parser* p) {
    Expr* left = parse_multiplicative(p);
    
    while (parser_check(p, TOK_PLUS) || parser_check(p, TOK_MINUS)) {
        Token* t = parser_advance(p);
        Expr* e = expr_new(EXPR_BINARY, t->line, t->col);
        e->op = sov_str_dup(token_kind_name(t->kind));
        e->left = left;
        e->right = parse_multiplicative(p);
        left = e;
    }
    
    return left;
}

static Expr* parse_comparison(Parser* p) {
    Expr* left = parse_additive(p);
    
    while (parser_check(p, TOK_LT) || parser_check(p, TOK_GT) ||
           parser_check(p, TOK_LEQ) || parser_check(p, TOK_GEQ)) {
        Token* t = parser_advance(p);
        Expr* e = expr_new(EXPR_BINARY, t->line, t->col);
        e->op = sov_str_dup(token_kind_name(t->kind));
        e->left = left;
        e->right = parse_additive(p);
        left = e;
    }
    
    return left;
}

static Expr* parse_equality(Parser* p) {
    Expr* left = parse_comparison(p);
    
    while (parser_check(p, TOK_EQEQ) || parser_check(p, TOK_NEQ)) {
        Token* t = parser_advance(p);
        Expr* e = expr_new(EXPR_BINARY, t->line, t->col);
        e->op = sov_str_dup(token_kind_name(t->kind));
        e->left = left;
        e->right = parse_comparison(p);
        left = e;
    }
    
    return left;
}

static Expr* parse_logical_and(Parser* p) {
    Expr* left = parse_equality(p);
    
    while (parser_check(p, TOK_AND)) {
        Token* t = parser_advance(p);
        Expr* e = expr_new(EXPR_BINARY, t->line, t->col);
        e->op = sov_str_dup("and");
        e->left = left;
        e->right = parse_equality(p);
        left = e;
    }
    
    return left;
}

static Expr* parse_logical_or(Parser* p) {
    Expr* left = parse_logical_and(p);
    
    while (parser_check(p, TOK_OR)) {
        Token* t = parser_advance(p);
        Expr* e = expr_new(EXPR_BINARY, t->line, t->col);
        e->op = sov_str_dup("or");
        e->left = left;
        e->right = parse_logical_and(p);
        left = e;
    }
    
    return left;
}

static Expr* parse_expr(Parser* p) {
    return parse_logical_or(p);
}

static Vec* parse_block(Parser* p) {
    Vec* stmts = vec_new();
    
    if (!parser_match(p, TOK_LBRACE)) {
        parser_error(p, "expected '{'");
        return stmts;
    }
    
    parser_skip_newlines(p);
    
    while (!parser_check(p, TOK_RBRACE) && !parser_check(p, TOK_EOF)) {
        Stmt* s = parse_stmt(p);
        if (s) vec_push(stmts, s);
        parser_skip_newlines(p);
    }
    
    if (!parser_match(p, TOK_RBRACE)) {
        parser_error(p, "expected '}'");
    }
    
    return stmts;
}

static Stmt* parse_set_stmt(Parser* p) {
    Token* t = parser_advance(p); /* consume 'set' */
    Stmt* s = stmt_new(STMT_SET, t->line, t->col);
    
    Token* name = parser_current(p);
    if (name->kind != TOK_IDENT) {
        parser_error(p, "expected variable name");
        return s;
    }
    parser_advance(p);
    s->name = sov_str_dup(name->value);
    
    /* Optional type annotation */
    if (parser_match(p, TOK_COLON)) {
        Token* type_tok = parser_current(p);
        if (type_tok->kind == TOK_IDENT) {
            s->type_annotation = sov_str_dup(type_tok->value);
            parser_advance(p);
        }
    }
    
    /* Assignment */
    if (parser_match(p, TOK_EQ)) {
        s->init_value = parse_expr(p);
    }
    
    return s;
}

static Stmt* parse_task_stmt(Parser* p) {
    Token* t = parser_advance(p); /* consume 'task' or 'fn' */
    Stmt* s = stmt_new(STMT_TASK, t->line, t->col);
    
    Token* name = parser_current(p);
    if (name->kind != TOK_IDENT) {
        parser_error(p, "expected function name");
        return s;
    }
    parser_advance(p);
    s->task_name = sov_str_dup(name->value);
    
    /* Parameters */
    if (!parser_match(p, TOK_LPAREN)) {
        parser_error(p, "expected '('");
        return s;
    }
    
    s->params = vec_new();
    if (!parser_check(p, TOK_RPAREN)) {
        do {
            Token* param = parser_current(p);
            if (param->kind == TOK_IDENT) {
                vec_push_str(s->params, param->value);
                parser_advance(p);
                
                /* Optional type */
                if (parser_match(p, TOK_COLON)) {
                    Token* type_tok = parser_current(p);
                    if (type_tok->kind == TOK_IDENT) {
                        parser_advance(p);
                    }
                }
            }
        } while (parser_match(p, TOK_COMMA));
    }
    
    if (!parser_match(p, TOK_RPAREN)) {
        parser_error(p, "expected ')'");
    }
    
    /* Return type */
    if (parser_match(p, TOK_ARROW)) {
        Token* ret = parser_current(p);
        if (ret->kind == TOK_IDENT) {
            s->return_type = sov_str_dup(ret->value);
            parser_advance(p);
        }
    }
    
    /* Body */
    parser_skip_newlines(p);
    s->body = parse_block(p);
    
    return s;
}

static Stmt* parse_check_stmt(Parser* p) {
    Token* t = parser_advance(p); /* consume 'check' */
    Stmt* s = stmt_new(STMT_CHECK, t->line, t->col);
    
    s->condition = parse_expr(p);
    parser_skip_newlines(p);
    s->then_block = parse_block(p);
    
    parser_skip_newlines(p);
    if (parser_match(p, TOK_ELSE)) {
        parser_skip_newlines(p);
        if (parser_check(p, TOK_CHECK)) {
            /* else check ... */
            s->else_block = vec_new();
            vec_push(s->else_block, parse_check_stmt(p));
        } else {
            s->else_block = parse_block(p);
        }
    }
    
    return s;
}

static Stmt* parse_loop_stmt(Parser* p) {
    Token* t = parser_advance(p); /* consume 'loop' */
    Stmt* s = stmt_new(STMT_LOOP, t->line, t->col);
    
    /* Check for different loop forms */
    Token* next = parser_current(p);
    
    if (next->kind == TOK_IDENT) {
        Token* after = parser_peek(p);
        if (after->kind == TOK_FROM) {
            /* loop i from 0 to 10 */
            s->loop_var = sov_str_dup(next->value);
            parser_advance(p);
            parser_advance(p); /* consume 'from' */
            s->loop_start = parse_expr(p);
            if (!parser_match(p, TOK_TO)) {
                parser_error(p, "expected 'to'");
            }
            s->loop_end = parse_expr(p);
        } else if (after->kind == TOK_IN) {
            /* loop item in collection */
            s->loop_var = sov_str_dup(next->value);
            parser_advance(p);
            parser_advance(p); /* consume 'in' */
            s->loop_start = parse_expr(p);
        } else {
            /* loop condition or loop N times */
            s->condition = parse_expr(p);
            if (parser_match(p, TOK_TIMES)) {
                s->loop_times = s->condition;
                s->condition = NULL;
            }
        }
    } else if (next->kind == TOK_LBRACE) {
        /* infinite loop */
    } else {
        /* loop with condition or count */
        s->condition = parse_expr(p);
        if (parser_match(p, TOK_TIMES)) {
            s->loop_times = s->condition;
            s->condition = NULL;
        }
    }
    
    parser_skip_newlines(p);
    s->loop_body = parse_block(p);
    
    return s;
}

static Stmt* parse_return_stmt(Parser* p) {
    Token* t = parser_advance(p);
    Stmt* s = stmt_new(STMT_RETURN, t->line, t->col);
    
    if (!parser_check(p, TOK_NEWLINE) && !parser_check(p, TOK_RBRACE) && !parser_check(p, TOK_EOF)) {
        s->return_value = parse_expr(p);
    }
    
    return s;
}

static Stmt* parse_print_stmt(Parser* p) {
    Token* t = parser_advance(p);
    Stmt* s = stmt_new(STMT_PRINT, t->line, t->col);
    s->print_expr = parse_expr(p);
    return s;
}

static Stmt* parse_struct_stmt(Parser* p) {
    Token* t = parser_advance(p);
    Stmt* s = stmt_new(STMT_STRUCT, t->line, t->col);
    
    Token* name = parser_current(p);
    if (name->kind != TOK_IDENT) {
        parser_error(p, "expected struct name");
        return s;
    }
    parser_advance(p);
    s->struct_name = sov_str_dup(name->value);
    
    parser_skip_newlines(p);
    if (!parser_match(p, TOK_LBRACE)) {
        parser_error(p, "expected '{'");
        return s;
    }
    
    s->struct_fields = vec_new();
    parser_skip_newlines(p);
    
    while (!parser_check(p, TOK_RBRACE) && !parser_check(p, TOK_EOF)) {
        Token* field = parser_current(p);
        if (field->kind == TOK_IDENT) {
            vec_push_str(s->struct_fields, field->value);
            parser_advance(p);
            
            if (parser_match(p, TOK_COLON)) {
                Token* type_tok = parser_current(p);
                if (type_tok->kind == TOK_IDENT) {
                    parser_advance(p);
                }
            }
        }
        
        parser_match(p, TOK_COMMA);
        parser_skip_newlines(p);
    }
    
    parser_match(p, TOK_RBRACE);
    return s;
}

static Stmt* parse_import_stmt(Parser* p) {
    Token* t = parser_advance(p);
    Stmt* s = stmt_new(STMT_IMPORT, t->line, t->col);
    
    Token* path = parser_current(p);
    if (path->kind == TOK_STRING) {
        s->import_path = sov_str_dup(path->value);
        parser_advance(p);
    } else {
        parser_error(p, "expected import path string");
    }
    
    return s;
}

static Stmt* parse_stmt(Parser* p) {
    parser_skip_newlines(p);
    Token* t = parser_current(p);
    
    switch (t->kind) {
        case TOK_SET:
            return parse_set_stmt(p);
        case TOK_TASK:
        case TOK_FN:
            return parse_task_stmt(p);
        case TOK_CHECK:
            return parse_check_stmt(p);
        case TOK_LOOP:
            return parse_loop_stmt(p);
        case TOK_RETURN:
            return parse_return_stmt(p);
        case TOK_PRINT:
            return parse_print_stmt(p);
        case TOK_STRUCT:
            return parse_struct_stmt(p);
        case TOK_IMPORT:
            return parse_import_stmt(p);
        case TOK_BREAK: {
            parser_advance(p);
            return stmt_new(STMT_BREAK, t->line, t->col);
        }
        case TOK_CONTINUE: {
            parser_advance(p);
            return stmt_new(STMT_CONTINUE, t->line, t->col);
        }
        case TOK_EOF:
            return NULL;
        default: {
            /* Expression statement or assignment */
            Expr* e = parse_expr(p);
            
            if (parser_check(p, TOK_EQ)) {
                parser_advance(p);
                Stmt* s = stmt_new(STMT_ASSIGN, t->line, t->col);
                s->expr = e;
                s->init_value = parse_expr(p);
                return s;
            }
            
            Stmt* s = stmt_new(STMT_EXPR, t->line, t->col);
            s->expr = e;
            return s;
        }
    }
}

static Program* parser_parse(Parser* p) {
    Program* prog = program_new(p->filename);
    
    while (!parser_check(p, TOK_EOF)) {
        Stmt* s = parse_stmt(p);
        if (s) vec_push(prog->statements, s);
        parser_skip_newlines(p);
    }
    
    return prog;
}

/* ==========================================================================
 * SECTION 12: CODE GENERATOR
 * ========================================================================== */

struct Codegen {
    StringBuilder* output;
    StringBuilder* header;
    StringBuilder* data;
    sov_int indent;
    HashMap* symbols;
    sov_int temp_count;
    sov_int label_count;
    sov_bool optimize;
};

static Codegen* codegen_new(sov_bool optimize) {
    Codegen* cg = (Codegen*)sov_alloc(sizeof(Codegen));
    if (cg) {
        cg->output = sb_new();
        cg->header = sb_new();
        cg->data = sb_new();
        cg->indent = 0;
        cg->symbols = hashmap_new();
        cg->temp_count = 0;
        cg->label_count = 0;
        cg->optimize = optimize;
    }
    return cg;
}

static void cg_emit(Codegen* cg, const char* s) {
    sb_append(cg->output, s);
}

static void cg_emit_indent(Codegen* cg) {
    for (sov_int i = 0; i < cg->indent; i++) {
        cg_emit(cg, "    ");
    }
}

static void cg_emit_line(Codegen* cg, const char* s) {
    cg_emit_indent(cg);
    cg_emit(cg, s);
    cg_emit(cg, "\n");
}

static sov_string cg_fresh_temp(Codegen* cg) {
    char buf[32];
    snprintf(buf, sizeof(buf), "_t%lld", (long long)cg->temp_count++);
    return sov_str_dup(buf);
}

static sov_string cg_fresh_label(Codegen* cg) {
    char buf[32];
    snprintf(buf, sizeof(buf), "_L%lld", (long long)cg->label_count++);
    return sov_str_dup(buf);
}

/* Forward declarations */
static sov_string cg_emit_expr(Codegen* cg, Expr* e);
static void cg_emit_stmt(Codegen* cg, Stmt* s);

static sov_string cg_emit_expr(Codegen* cg, Expr* e) {
    if (!e) return sov_str_dup("0");
    
    switch (e->kind) {
        case EXPR_INT: {
            char buf[32];
            snprintf(buf, sizeof(buf), "%lld", (long long)e->int_val);
            return sov_str_dup(buf);
        }
        case EXPR_FLOAT: {
            char buf[64];
            snprintf(buf, sizeof(buf), "%g", e->float_val);
            return sov_str_dup(buf);
        }
        case EXPR_STRING: {
            sov_string temp = cg_fresh_temp(cg);
            cg_emit_indent(cg);
            cg_emit(cg, "sov_string ");
            cg_emit(cg, temp);
            cg_emit(cg, " = sov_str_dup(\"");
            /* Escape the string */
            for (const char* p = e->str_val; *p; p++) {
                switch (*p) {
                    case '\n': cg_emit(cg, "\\n"); break;
                    case '\t': cg_emit(cg, "\\t"); break;
                    case '\r': cg_emit(cg, "\\r"); break;
                    case '\\': cg_emit(cg, "\\\\"); break;
                    case '"': cg_emit(cg, "\\\""); break;
                    default: sb_append_char(cg->output, *p); break;
                }
            }
            cg_emit(cg, "\");\n");
            return temp;
        }
        case EXPR_BOOL:
            return sov_str_dup(e->bool_val ? "true" : "false");
        case EXPR_NULL:
            return sov_str_dup("NULL");
        case EXPR_IDENT:
            return sov_str_dup(e->name);
        case EXPR_BINARY: {
            sov_string left = cg_emit_expr(cg, e->left);
            sov_string right = cg_emit_expr(cg, e->right);
            sov_string temp = cg_fresh_temp(cg);
            
            const char* c_op = e->op;
            if (sov_str_eq(e->op, "and")) c_op = "&&";
            else if (sov_str_eq(e->op, "or")) c_op = "||";
            else if (sov_str_eq(e->op, "==")) c_op = "==";
            else if (sov_str_eq(e->op, "!=")) c_op = "!=";
            
            cg_emit_indent(cg);
            cg_emit(cg, "sov_int ");
            cg_emit(cg, temp);
            cg_emit(cg, " = (");
            cg_emit(cg, left);
            cg_emit(cg, " ");
            cg_emit(cg, c_op);
            cg_emit(cg, " ");
            cg_emit(cg, right);
            cg_emit(cg, ");\n");
            
            sov_free(left);
            sov_free(right);
            return temp;
        }
        case EXPR_UNARY: {
            sov_string operand = cg_emit_expr(cg, e->operand);
            sov_string temp = cg_fresh_temp(cg);
            
            const char* c_op = e->op;
            if (sov_str_eq(e->op, "not") || sov_str_eq(e->op, "!")) c_op = "!";
            
            cg_emit_indent(cg);
            cg_emit(cg, "sov_int ");
            cg_emit(cg, temp);
            cg_emit(cg, " = ");
            cg_emit(cg, c_op);
            cg_emit(cg, "(");
            cg_emit(cg, operand);
            cg_emit(cg, ");\n");
            
            sov_free(operand);
            return temp;
        }
        case EXPR_CALL: {
            /* Emit arguments first */
            Vec* arg_temps = vec_new();
            for (size_t i = 0; i < vec_len(e->args); i++) {
                Expr* arg = (Expr*)vec_get(e->args, i);
                vec_push_str(arg_temps, cg_emit_expr(cg, arg));
            }
            
            sov_string temp = cg_fresh_temp(cg);
            sov_string callee = cg_emit_expr(cg, e->callee);
            
            cg_emit_indent(cg);
            cg_emit(cg, "sov_int ");
            cg_emit(cg, temp);
            cg_emit(cg, " = ");
            cg_emit(cg, callee);
            cg_emit(cg, "(");
            
            for (size_t i = 0; i < vec_len(arg_temps); i++) {
                if (i > 0) cg_emit(cg, ", ");
                cg_emit(cg, vec_get_str(arg_temps, i));
            }
            
            cg_emit(cg, ");\n");
            
            sov_free(callee);
            vec_free(arg_temps);
            return temp;
        }
        case EXPR_FIELD: {
            sov_string obj = cg_emit_expr(cg, e->object);
            sov_string temp = cg_fresh_temp(cg);
            
            cg_emit_indent(cg);
            cg_emit(cg, "sov_int ");
            cg_emit(cg, temp);
            cg_emit(cg, " = ");
            cg_emit(cg, obj);
            cg_emit(cg, ".");
            cg_emit(cg, e->field);
            cg_emit(cg, ";\n");
            
            sov_free(obj);
            return temp;
        }
        case EXPR_INDEX: {
            sov_string obj = cg_emit_expr(cg, e->object);
            sov_string idx = cg_emit_expr(cg, e->index);
            sov_string temp = cg_fresh_temp(cg);
            
            cg_emit_indent(cg);
            cg_emit(cg, "sov_int ");
            cg_emit(cg, temp);
            cg_emit(cg, " = ");
            cg_emit(cg, obj);
            cg_emit(cg, "[");
            cg_emit(cg, idx);
            cg_emit(cg, "];\n");
            
            sov_free(obj);
            sov_free(idx);
            return temp;
        }
        default:
            return sov_str_dup("0");
    }
}

static void cg_emit_stmt(Codegen* cg, Stmt* s) {
    if (!s) return;
    
    switch (s->kind) {
        case STMT_EXPR: {
            sov_string result = cg_emit_expr(cg, s->expr);
            sov_free(result);
            break;
        }
        case STMT_SET: {
            cg_emit_indent(cg);
            cg_emit(cg, "sov_int ");
            cg_emit(cg, s->name);
            if (s->init_value) {
                cg_emit(cg, " = ");
                sov_string val = cg_emit_expr(cg, s->init_value);
                cg_emit(cg, val);
                sov_free(val);
            } else {
                cg_emit(cg, " = 0");
            }
            cg_emit(cg, ";\n");
            break;
        }
        case STMT_ASSIGN: {
            sov_string lhs = cg_emit_expr(cg, s->expr);
            sov_string rhs = cg_emit_expr(cg, s->init_value);
            cg_emit_indent(cg);
            cg_emit(cg, lhs);
            cg_emit(cg, " = ");
            cg_emit(cg, rhs);
            cg_emit(cg, ";\n");
            sov_free(lhs);
            sov_free(rhs);
            break;
        }
        case STMT_TASK: {
            /* Function declaration */
            sb_append(cg->header, "sov_int ");
            sb_append(cg->header, s->task_name);
            sb_append(cg->header, "(");
            for (size_t i = 0; i < vec_len(s->params); i++) {
                if (i > 0) sb_append(cg->header, ", ");
                sb_append(cg->header, "sov_int ");
                sb_append(cg->header, vec_get_str(s->params, i));
            }
            sb_append(cg->header, ");\n");
            
            /* Function definition */
            cg_emit(cg, "sov_int ");
            cg_emit(cg, s->task_name);
            cg_emit(cg, "(");
            for (size_t i = 0; i < vec_len(s->params); i++) {
                if (i > 0) cg_emit(cg, ", ");
                cg_emit(cg, "sov_int ");
                cg_emit(cg, vec_get_str(s->params, i));
            }
            cg_emit(cg, ") {\n");
            
            cg->indent++;
            for (size_t i = 0; i < vec_len(s->body); i++) {
                cg_emit_stmt(cg, (Stmt*)vec_get(s->body, i));
            }
            cg->indent--;
            
            cg_emit(cg, "    return 0;\n");
            cg_emit(cg, "}\n\n");
            break;
        }
        case STMT_RETURN: {
            cg_emit_indent(cg);
            cg_emit(cg, "return ");
            if (s->return_value) {
                sov_string val = cg_emit_expr(cg, s->return_value);
                cg_emit(cg, val);
                sov_free(val);
            } else {
                cg_emit(cg, "0");
            }
            cg_emit(cg, ";\n");
            break;
        }
        case STMT_CHECK: {
            sov_string cond = cg_emit_expr(cg, s->condition);
            cg_emit_indent(cg);
            cg_emit(cg, "if (");
            cg_emit(cg, cond);
            cg_emit(cg, ") {\n");
            sov_free(cond);
            
            cg->indent++;
            for (size_t i = 0; i < vec_len(s->then_block); i++) {
                cg_emit_stmt(cg, (Stmt*)vec_get(s->then_block, i));
            }
            cg->indent--;
            
            cg_emit_indent(cg);
            cg_emit(cg, "}");
            
            if (s->else_block && vec_len(s->else_block) > 0) {
                cg_emit(cg, " else {\n");
                cg->indent++;
                for (size_t i = 0; i < vec_len(s->else_block); i++) {
                    cg_emit_stmt(cg, (Stmt*)vec_get(s->else_block, i));
                }
                cg->indent--;
                cg_emit_indent(cg);
                cg_emit(cg, "}");
            }
            cg_emit(cg, "\n");
            break;
        }
        case STMT_LOOP: {
            if (s->loop_times) {
                /* loop N times */
                sov_string n = cg_emit_expr(cg, s->loop_times);
                sov_string var = cg_fresh_temp(cg);
                cg_emit_indent(cg);
                cg_emit(cg, "for (sov_int ");
                cg_emit(cg, var);
                cg_emit(cg, " = 0; ");
                cg_emit(cg, var);
                cg_emit(cg, " < ");
                cg_emit(cg, n);
                cg_emit(cg, "; ");
                cg_emit(cg, var);
                cg_emit(cg, "++) {\n");
                sov_free(n);
                sov_free(var);
            } else if (s->loop_var && s->loop_start && s->loop_end) {
                /* loop i from a to b */
                sov_string start = cg_emit_expr(cg, s->loop_start);
                sov_string end = cg_emit_expr(cg, s->loop_end);
                cg_emit_indent(cg);
                cg_emit(cg, "for (sov_int ");
                cg_emit(cg, s->loop_var);
                cg_emit(cg, " = ");
                cg_emit(cg, start);
                cg_emit(cg, "; ");
                cg_emit(cg, s->loop_var);
                cg_emit(cg, " < ");
                cg_emit(cg, end);
                cg_emit(cg, "; ");
                cg_emit(cg, s->loop_var);
                cg_emit(cg, "++) {\n");
                sov_free(start);
                sov_free(end);
            } else if (s->condition) {
                /* while loop */
                sov_string cond = cg_emit_expr(cg, s->condition);
                cg_emit_indent(cg);
                cg_emit(cg, "while (");
                cg_emit(cg, cond);
                cg_emit(cg, ") {\n");
                sov_free(cond);
            } else {
                /* infinite loop */
                cg_emit_indent(cg);
                cg_emit(cg, "while (1) {\n");
            }
            
            cg->indent++;
            for (size_t i = 0; i < vec_len(s->loop_body); i++) {
                cg_emit_stmt(cg, (Stmt*)vec_get(s->loop_body, i));
            }
            cg->indent--;
            
            cg_emit_indent(cg);
            cg_emit(cg, "}\n");
            break;
        }
        case STMT_BREAK:
            cg_emit_line(cg, "break;");
            break;
        case STMT_CONTINUE:
            cg_emit_line(cg, "continue;");
            break;
        case STMT_PRINT: {
            sov_string val = cg_emit_expr(cg, s->print_expr);
            cg_emit_indent(cg);
            cg_emit(cg, "printf(\"%lld\\n\", (long long)");
            cg_emit(cg, val);
            cg_emit(cg, ");\n");
            sov_free(val);
            break;
        }
        case STMT_STRUCT: {
            sb_append(cg->header, "typedef struct ");
            sb_append(cg->header, s->struct_name);
            sb_append(cg->header, " {\n");
            for (size_t i = 0; i < vec_len(s->struct_fields); i++) {
                sb_append(cg->header, "    sov_int ");
                sb_append(cg->header, vec_get_str(s->struct_fields, i));
                sb_append(cg->header, ";\n");
            }
            sb_append(cg->header, "} ");
            sb_append(cg->header, s->struct_name);
            sb_append(cg->header, ";\n\n");
            break;
        }
        default:
            break;
    }
}

static sov_string codegen_generate(Codegen* cg, Program* prog) {
    /* Emit header */
    sb_append(cg->header, "/* Generated by Sovereign Compiler */\n");
    sb_append(cg->header, "#include <stdio.h>\n");
    sb_append(cg->header, "#include <stdlib.h>\n");
    sb_append(cg->header, "#include <string.h>\n");
    sb_append(cg->header, "#include <stdint.h>\n");
    sb_append(cg->header, "#include <stdbool.h>\n\n");
    sb_append(cg->header, "typedef int64_t sov_int;\n");
    sb_append(cg->header, "typedef double sov_float;\n");
    sb_append(cg->header, "typedef char* sov_string;\n");
    sb_append(cg->header, "typedef void* sov_ptr;\n");
    sb_append(cg->header, "typedef bool sov_bool;\n\n");
    sb_append(cg->header, "static sov_string sov_str_dup(const char* s) {\n");
    sb_append(cg->header, "    if (!s) return NULL;\n");
    sb_append(cg->header, "    size_t len = strlen(s);\n");
    sb_append(cg->header, "    char* dup = (char*)malloc(len + 1);\n");
    sb_append(cg->header, "    if (dup) memcpy(dup, s, len + 1);\n");
    sb_append(cg->header, "    return dup;\n");
    sb_append(cg->header, "}\n\n");
    
    /* Generate code */
    for (size_t i = 0; i < vec_len(prog->statements); i++) {
        cg_emit_stmt(cg, (Stmt*)vec_get(prog->statements, i));
    }
    
    /* Combine header and output */
    StringBuilder* final = sb_new();
    sb_append(final, sb_to_string(cg->header));
    sb_append(final, "\n/* Forward declarations */\n");
    sb_append(final, "\n/* Code */\n");
    sb_append(final, sb_to_string(cg->output));
    
    return sb_to_string(final);
}

/* ==========================================================================
 * SECTION 13: MAIN
 * ========================================================================== */

static void print_usage(void) {
    printf("Sovereign v1.0.0 - The privacy-first systems language\n\n");
    printf("Usage: sovereign <command> [options] [file.sov]\n\n");
    printf("Commands:\n");
    printf("  build <file.sov>      Compile to C code\n");
    printf("  run <file.sov>        Compile and run\n");
    printf("  check <file.sov>      Type-check only\n");
    printf("  fmt <file.sov>        Format source\n");
    printf("  version               Show version\n\n");
    printf("Options:\n");
    printf("  -o <file>             Output file name\n");
    printf("  --optimize            Enable optimizations\n");
    printf("  --help, -h            Show this help\n");
}

static void print_version(void) {
    printf("Sovereign v1.0.0\n");
    printf("Self-hosted compiler written in Sovereign\n");
    printf("Target: C (gcc/clang compatible)\n");
}

int main(int argc, char** argv) {
    if (argc < 2) {
        print_usage();
        return 0;
    }
    
    const char* command = argv[1];
    const char* input_file = NULL;
    const char* output_file = "output.c";
    sov_bool optimize = false;
    
    /* Parse arguments */
    for (int i = 2; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) {
            output_file = argv[++i];
        } else if (strcmp(argv[i], "--optimize") == 0) {
            optimize = true;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage();
            return 0;
        } else if (argv[i][0] != '-') {
            input_file = argv[i];
        }
    }
    
    /* Handle commands */
    if (strcmp(command, "version") == 0 || strcmp(command, "--version") == 0) {
        print_version();
        return 0;
    }
    
    if (strcmp(command, "--help") == 0 || strcmp(command, "-h") == 0) {
        print_usage();
        return 0;
    }
    
    if (strcmp(command, "build") == 0) {
        if (!input_file) {
            fprintf(stderr, "Error: No input file specified\n");
            return 1;
        }
        
        /* Read source */
        sov_string source = file_read_all(input_file);
        if (!source) {
            fprintf(stderr, "Error: Cannot read file '%s'\n", input_file);
            return 1;
        }
        
        /* Lex */
        Lexer* lexer = lexer_new(source, input_file);
        Vec* tokens = lexer_tokenize(lexer);
        
        /* Parse */
        Parser* parser = parser_new(tokens, input_file);
        Program* program = parser_parse(parser);
        
        if (vec_len(parser->errors) > 0) {
            fprintf(stderr, "Parse errors:\n");
            for (size_t i = 0; i < vec_len(parser->errors); i++) {
                fprintf(stderr, "  %s\n", vec_get_str(parser->errors, i));
            }
            return 1;
        }
        
        /* Generate */
        Codegen* cg = codegen_new(optimize);
        sov_string output = codegen_generate(cg, program);
        
        /* Write output */
        if (!file_write_all(output_file, output)) {
            fprintf(stderr, "Error: Cannot write to '%s'\n", output_file);
            return 1;
        }
        
        printf("Compiled: %s -> %s\n", input_file, output_file);
        printf("\nTo create executable:\n");
        printf("  gcc -O2 %s -o %s\n", output_file, 
               sov_str_replace(output_file, ".c", ""));
        
        return 0;
    }
    
    if (strcmp(command, "check") == 0) {
        if (!input_file) {
            fprintf(stderr, "Error: No input file specified\n");
            return 1;
        }
        
        sov_string source = file_read_all(input_file);
        if (!source) {
            fprintf(stderr, "Error: Cannot read file '%s'\n", input_file);
            return 1;
        }
        
        Lexer* lexer = lexer_new(source, input_file);
        Vec* tokens = lexer_tokenize(lexer);
        Parser* parser = parser_new(tokens, input_file);
        Program* program = parser_parse(parser);
        
        if (vec_len(parser->errors) > 0) {
            fprintf(stderr, "Errors:\n");
            for (size_t i = 0; i < vec_len(parser->errors); i++) {
                fprintf(stderr, "  %s\n", vec_get_str(parser->errors, i));
            }
            return 1;
        }
        
        printf("OK: %s type-checks successfully (%zu statements)\n", 
               input_file, vec_len(program->statements));
        return 0;
    }
    
    fprintf(stderr, "Unknown command: %s\n", command);
    print_usage();
    return 1;
}
