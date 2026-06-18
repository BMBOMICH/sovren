/*
 * Minimal Sovereign Bootstrapping Compiler in C
 * Compiles OLD syntax Sovereign -> x86-64 assembly
 * Compiled with gcc, no dependencies on sovereign C compiler
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdint.h>
#include <stdarg.h>

#define MAX_SOURCE (1 << 20)
#define MAX_TOKENS 65536
#define MAX_NODES 65536
#define MAX_OUTPUT (1 << 20)

// Token types
enum {
    TK_EOF = 0, TK_NL = 1, TK_NUM = 2, TK_STR = 3, TK_ID = 4,
    TK_SET = 5, TK_TASK = 6, TK_IF = 7, TK_LOOP = 8, TK_RET = 9, TK_PR = 10,
    TK_ELSE = 11, TK_FROM = 12, TK_TO = 13, TK_TIMES = 14, TK_IN = 15,
    TK_AND = 16, TK_OR = 17, TK_NOT = 18,
    TK_PLUS = 20, TK_MINUS = 21, TK_STAR = 22, TK_SLASH = 23,
    TK_EQ = 24, TK_LT = 25, TK_GT = 26, TK_EQEQ = 27, TK_NEQ = 28,
    TK_LE = 29, TK_GE = 30,
    TK_LP = 30, TK_RP = 31, TK_LB = 32, TK_RB = 33, TK_AS = 34, TK_CM = 35, TK_CO = 35,
    TK_ARROW = 26,
};

typedef struct {
    int type;
    const char* text;
    int len;
} Token;

Token tokens[MAX_TOKENS];
int token_count = 0;
int token_pos = 0;

char* source;
int src_len;

// AST node types
enum {
    ND_NUM = 0, ND_VAR = 1, ND_BIN = 2, ND_STR = 3, ND_CALL = 4, ND_UNARY = 5,
};

typedef struct Node {
    int kind;
    long long ival;
    const char* name;
    int name_len;
    const char* str_val;
    struct Node* left;
    struct Node* right;
    char* op;
} Node;

Node nodes[MAX_NODES];
int node_count = 0;

Node* new_node(int kind) {
    if (node_count >= MAX_NODES) return NULL;
    Node* n = &nodes[node_count++];
    memset(n, 0, sizeof(Node));
    n->kind = kind;
    return n;
}

Node* new_num(long long v) {
    Node* n = new_node(ND_NUM);
    n->ival = v;
    return n;
}

Node* new_var(const char* name, int len) {
    Node* n = new_node(ND_VAR);
    n->name = name;
    n->name_len = len;
    return n;
}

Node* new_bin(Node* l, Node* r, const char* op) {
    Node* n = new_node(ND_BIN);
    n->left = l;
    n->right = r;
    n->op = strdup(op);
    return n;
}

Node* new_unary(Node* l, const char* op) {
    Node* n = new_node(ND_UNARY);
    n->left = l;
    n->op = strdup(op);
    return n;
}

Node* new_str(const char* s, int len) {
    Node* n = new_node(ND_STR);
    n->str_val = malloc(len + 1);
    memcpy((void*)n->str_val, s, len);
    ((char*)n->str_val)[len] = 0;
    return n;
}

// Lexer
void lex() {
    int pos = 0, line = 1, col = 1;
    while (pos < src_len && token_count < MAX_TOKENS) {
        while (pos < src_len && (source[pos] == ' ' || source[pos] == '\t' || source[pos] == '\r')) {
            if (source[pos] == '\n') { line++; col = 1; } else col++;
            pos++;
        }
        if (pos >= src_len) break;
        
        char c = source[pos];
        
        if (c == '\n') {
            tokens[token_count++] = (Token){TK_NL, NULL, 0};
            pos++; line++; col = 1; continue;
        }
        
        if (c == '#') {
            while (pos < src_len && source[pos] != '\n') pos++;
            continue;
        }
        
        if (isalpha(c) || c == '_') {
            int start = pos;
            while (pos < src_len && (isalnum(source[pos]) || source[pos] == '_')) pos++;
            int len = pos - start;
            int kind = TK_ID;
            if (len == 3 && strncmp(source+start, "set", 3) == 0) kind = TK_SET;
            else if (len == 4 && strncmp(source+start, "task", 4) == 0) kind = TK_TASK;
            else if (len == 2 && strncmp(source+start, "if", 2) == 0) kind = TK_IF;
            else if (len == 4 && strncmp(source+start, "loop", 4) == 0) kind = TK_LOOP;
            else if (len == 6 && strncmp(source+start, "return", 6) == 0) kind = TK_RET;
            else if (len == 3 && strncmp(source+start, "ret", 3) == 0) kind = TK_RET;
            else if (len == 5 && strncmp(source+start, "print", 5) == 0) kind = TK_PR;
            else if (len == 4 && strncmp(source+start, "else", 4) == 0) kind = TK_ELSE;
            else if (len == 4 && strncmp(source+start, "from", 4) == 0) kind = TK_FROM;
            else if (len == 2 && strncmp(source+start, "to", 2) == 0) kind = TK_TO;
            else if (len == 5 && strncmp(source+start, "times", 5) == 0) kind = TK_TIMES;
            else if (len == 2 && strncmp(source+start, "in", 2) == 0) kind = TK_IN;
            else if (len == 3 && strncmp(source+start, "and", 3) == 0) kind = TK_AND;
            else if (len == 2 && strncmp(source+start, "or", 2) == 0) kind = TK_OR;
            else if (len == 3 && strncmp(source+start, "not", 3) == 0) kind = TK_NOT;
            
            tokens[token_count++] = (Token){kind, source+start, len};
            continue;
        }
        
        if (isdigit(c)) {
            int start = pos;
            while (pos < src_len && (isdigit(source[pos]) || source[pos] == '.')) pos++;
            int len = pos - start;
            tokens[token_count++] = (Token){TK_NUM, source+start, len};
            continue;
        }
        
        if (c == '"') {
            pos++;
            int start = pos;
            while (pos < src_len && source[pos] != '"') pos++;
            int len = pos - start;
            tokens[token_count++] = (Token){TK_STR, source+start, len};
            pos++;
            continue;
        }
        
        const char* two = &source[pos];
        if (pos+1 < src_len) {
            if (strncmp(two, "->", 2) == 0) { tokens[token_count++] = (Token){TK_ARROW, NULL, 0}; pos += 2; continue; }
            if (strncmp(two, "==", 2) == 0) { tokens[token_count++] = (Token){TK_EQEQ, NULL, 0}; pos += 2; continue; }
            if (strncmp(two, "!=", 2) == 0) { tokens[token_count++] = (Token){TK_NEQ, NULL, 0}; pos += 2; continue; }
            if (strncmp(two, "<=", 2) == 0) { tokens[token_count++] = (Token){TK_LE, NULL, 0}; pos += 2; continue; }
            if (strncmp(two, ">=", 2) == 0) { tokens[token_count++] = (Token){TK_GE, NULL, 0}; pos += 2; continue; }
        }
        
        int kind = 0;
        switch (c) {
            case '+': kind = TK_PLUS; break;
            case '-': kind = TK_MINUS; break;
            case '*': kind = TK_STAR; break;
            case '/': kind = TK_SLASH; break;
            case '<': kind = TK_LT; break;
            case '>': kind = TK_GT; break;
            case '=': kind = TK_EQ; break;
            case '!': kind = TK_NOT; break;
            case '(': kind = TK_LP; break;
            case ')': kind = TK_RP; break;
            case '{': kind = TK_LB; break;
            case '}': kind = TK_RB; break;
            case ',': kind = TK_CM; break;
            case ':': kind = TK_CO; break;
        }
        if (kind) {
            tokens[token_count++] = (Token){kind, NULL, 0};
            pos++;
            continue;
        }
        
        pos++;
    }
    tokens[token_count++] = (Token){TK_EOF, NULL, 0};
}

// Parser
int precedence(int kind) {
    switch (kind) {
        case TK_PLUS: case TK_MINUS: return 10;
        case TK_STAR: case TK_SLASH: return 20;
        case TK_LT: case TK_GT: case TK_EQEQ: case TK_NEQ: case TK_LE: case TK_GE: return 5;
        case TK_AND: return 3;
        case TK_OR: return 2;
    }
    return 0;
}

Node* parse_primary();
Node* parse_expr(int min_prec);

Node* parse_primary() {
    Token* t = &tokens[token_pos++];
    switch (t->type) {
        case TK_NUM: {
            long long v = strtoll(t->text, NULL, 10);
            return new_num(v);
        }
        case TK_STR:
            return new_str(t->text, t->len);
        case TK_ID: {
            Node* n = new_var(t->text, t->len);
            return n;
        }
        case TK_LP: {
            Node* e = parse_expr(0);
            if (token_pos < token_count && tokens[token_pos].type == TK_RP) token_pos++;
            return e;
        }
        case TK_MINUS: {
            Node* inner = parse_primary();
            return new_unary(inner, "-");
        }
        case TK_NOT: {
            Node* inner = parse_primary();
            return new_unary(inner, "!");
        }
        default:
            return new_num(0);
    }
}

Node* parse_expr(int min_prec) {
    Node* left = parse_primary();
    
    while (token_pos < token_count) {
        Token* t = &tokens[token_pos];
        int prec = precedence(t->type);
        if (prec == 0 || prec < min_prec) break;
        
        int kind = t->type;
        token_pos++;
        
        int next_prec = prec + 1;
        Node* right = parse_expr(next_prec);
        
        const char* op = "";
        switch (kind) {
            case TK_PLUS: op = "+"; break;
            case TK_MINUS: op = "-"; break;
            case TK_STAR: op = "*"; break;
            case TK_SLASH: op = "/"; break;
            case TK_LT: op = "<"; break;
            case TK_GT: op = ">"; break;
            case TK_EQEQ: op = "=="; break;
            case TK_NEQ: op = "!="; break;
            case TK_LE: op = "<="; break;
            case TK_GE: op = ">="; break;
            case TK_AND: op = "and"; break;
            case TK_OR: op = "or"; break;
        }
        left = new_bin(left, right, op);
    }
    return left;
}

Node* parse_stmt() {
    if (token_pos >= token_count) return NULL;
    Token* t = &tokens[token_pos];
    
    if (t->type == TK_SET) {
        token_pos++;
        if (token_pos < token_count && tokens[token_pos].type == TK_ID) {
            Token* name = &tokens[token_pos++];
            Node* val = NULL;
            if (token_pos < token_count && tokens[token_pos].type == TK_EQ) {
                token_pos++;
                val = parse_expr(0);
            } else if (token_pos < token_count && tokens[token_pos].type == TK_TO) {
                token_pos++;
                val = parse_expr(0);
            }
            Node* n = new_bin(new_var(name->text, name->len), val ? val : new_num(0), "=");
            return n;
        }
    }
    if (t->type == TK_TASK) {
        token_pos++;
        if (token_pos < token_count && tokens[token_pos].type == TK_ID) {
            Token* name = &tokens[token_pos++];
            Node* n = new_bin(new_var(name->text, name->len), NULL, "task");
            return n;
        }
    }
    if (t->type == TK_IF) {
        token_pos++;
        Node* cond = parse_expr(0);
        Node* then_n = new_num(0);
        if (token_pos < token_count && tokens[token_pos].type == TK_LB) {
            token_pos++;
            while (token_pos < token_count && tokens[token_pos].type != TK_RB) token_pos++;
            if (token_pos < token_count) token_pos++;
        }
        Node* else_n = NULL;
        if (token_pos < token_count && tokens[token_pos].type == TK_ELSE) {
            token_pos++;
            if (token_pos < token_count && tokens[token_pos].type == TK_LB) {
                token_pos++;
                while (token_pos < token_count && tokens[token_pos].type != TK_RB) token_pos++;
                if (token_pos < token_count) token_pos++;
                else_n = new_num(0);
            }
        }
        Node* n = new_bin(cond, then_n, "if");
        if (else_n) n->right = else_n;
        return n;
    }
    if (t->type == TK_LOOP) {
        token_pos++;
        Node* cond = parse_expr(0);
        if (token_pos < token_count && tokens[token_pos].type == TK_LB) {
            token_pos++;
            while (token_pos < token_count && tokens[token_pos].type != TK_RB) token_pos++;
            if (token_pos < token_count) token_pos++;
        }
        Node* n = new_bin(cond, new_num(0), "loop");
        return n;
    }
    if (t->type == TK_RET) {
        token_pos++;
        Node* val = NULL;
        if (token_pos < token_count && tokens[token_pos].type != TK_NL && tokens[token_pos].type != TK_RB && tokens[token_pos].type != TK_EOF) {
            val = parse_expr(0);
        }
        Node* n = new_bin(val ? val : new_num(0), NULL, "ret");
        return n;
    }
    if (t->type == TK_PR) {
        token_pos++;
        Node* val = parse_expr(0);
        Node* n = new_bin(val, NULL, "print");
        return n;
    }
    
    Node* e = parse_expr(0);
    if (e->kind == ND_VAR && token_pos < token_count && tokens[token_pos].type == TK_EQ) {
        token_pos++;
        Node* val = parse_expr(0);
        e = new_bin(e, val, "=");
    }
    return e;
}

// Codegen
char output[MAX_OUTPUT];
int out_len = 0;

void emit(const char* fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    int l = strlen(buf);
    if (out_len + l + 1 >= MAX_OUTPUT) return;
    memcpy(output + out_len, buf, l + 1);
    out_len += l;
}

int label_count = 0;

char* next_label() {
    static char buf[32];
    snprintf(buf, sizeof(buf), "_L%d", label_count++);
    return buf;
}

void gen_expr(Node* n) {
    if (!n) return;
    switch (n->kind) {
        case ND_NUM:
            emit("    mov rax, %lld\n", n->ival);
            break;
        case ND_VAR:
            emit("    mov rax, [%.*s]\n", n->name_len, n->name);
            break;
        case ND_STR:
            {
                char* label = next_label();
                emit("    lea rax, [%s]\n", label);
            }
            break;
        case ND_BIN:
            if (strcmp(n->op, "=") == 0) {
                gen_expr(n->right);
                emit("    mov [%.*s], rax\n", n->left->name_len, n->left->name);
            } else {
                gen_expr(n->left);
                emit("    push rax\n");
                gen_expr(n->right);
                emit("    pop rbx\n");
                if (strcmp(n->op, "+") == 0) emit("    add rax, rbx\n");
                else if (strcmp(n->op, "-") == 0) emit("    sub rax, rbx\n");
                else if (strcmp(n->op, "*") == 0) emit("    imul rax, rbx\n");
                else if (strcmp(n->op, "/") == 0) { emit("    cqo\n"); emit("    idiv rbx\n"); }
                else if (strcmp(n->op, "<") == 0) { emit("    cmp rax, rbx\n"); emit("    setl al\n"); emit("    movzx rax, al\n"); }
                else if (strcmp(n->op, ">") == 0) { emit("    cmp rax, rbx\n"); emit("    setg al\n"); emit("    movzx rax, al\n"); }
                else if (strcmp(n->op, "==") == 0) { emit("    cmp rax, rbx\n"); emit("    sete al\n"); emit("    movzx rax, al\n"); }
                else if (strcmp(n->op, "!=") == 0) { emit("    cmp rax, rbx\n"); emit("    setne al\n"); emit("    movzx rax, al\n"); }
                else if (strcmp(n->op, "<=") == 0) { emit("    cmp rax, rbx\n"); emit("    setle al\n"); emit("    movzx rax, al\n"); }
                else if (strcmp(n->op, ">=") == 0) { emit("    cmp rax, rbx\n"); emit("    setge al\n"); emit("    movzx rax, al\n"); }
            }
            break;
        case ND_UNARY:
            gen_expr(n->left);
            if (strcmp(n->op, "-") == 0) emit("    neg rax\n");
            else if (strcmp(n->op, "!") == 0) {
                emit("    test rax, rax\n");
                emit("    setz al\n");
                emit("    movzx rax, al\n");
            }
            break;
    }
}

void gen_stmt(Node* n) {
    if (!n) return;
    if (n->kind == ND_BIN) {
        const char* op = n->op;
        if (strcmp(op, "=") == 0) {
            gen_expr(n);
        } else if (strcmp(op, "task") == 0) {
            emit("%.*s:\n", n->left->name_len, n->left->name);
            emit("    push rbp\n");
            emit("    mov rbp, rsp\n");
            emit("    leave\n");
            emit("    ret\n");
        } else if (strcmp(op, "if") == 0) {
            char* end_label = next_label();
            char* else_label = next_label();
            gen_expr(n->left);
            emit("    test rax, rax\n");
            emit("    jz %s\n", else_label);
            emit("    jmp %s\n", end_label);
            emit("%s:\n", else_label);
            emit("%s:\n", end_label);
        } else if (strcmp(op, "loop") == 0) {
            char* loop_start = next_label();
            char* loop_end = next_label();
            emit("%s:\n", loop_start);
            gen_expr(n->left);
            emit("    test rax, rax\n");
            emit("    jz %s\n", loop_end);
            emit("    jmp %s\n", loop_start);
            emit("%s:\n", loop_end);
        } else if (strcmp(op, "ret") == 0) {
            if (n->left) gen_expr(n->left);
            emit("    leave\n");
            emit("    ret\n");
        } else if (strcmp(op, "print") == 0) {
            gen_expr(n->left);
            emit("    mov rdi, rax\n");
            emit("    call print_int\n");
        } else {
            gen_expr(n);
        }
    } else {
        gen_expr(n);
    }
}

void generate(Node** stmts, int count) {
    emit("section .text\n");
    emit("global _start\n");
    emit("_start:\n");
    emit("    push rbp\n");
    emit("    mov rbp, rsp\n");
    
    for (int i = 0; i < count; i++) {
        gen_stmt(stmts[i]);
    }
    
    emit("    mov rax, 60\n");
    emit("    xor rdi, rdi\n");
    emit("    syscall\n");
    
    emit("\nprint_int:\n");
    emit("    push rbp\n");
    emit("    mov rbp, rsp\n");
    emit("    sub rsp, 32\n");
    emit("    mov [rbp-8], rdi\n");
    emit("    lea rsi, [rbp-16]\n");
    emit("    mov rax, [rbp-8]\n");
    emit("    test rax, rax\n");
    emit("    jns .Lpos\n");
    emit("    neg rax\n");
    emit("    mov byte [rsi], 45\n");
    emit("    inc rsi\n");
    emit(".Lpos:\n");
    emit("    mov rcx, 10\n");
    emit(".Ldig:\n");
    emit("    xor rdx, rdx\n");
    emit("    div rcx\n");
    emit("    add dl, 48\n");
    emit("    dec rsi\n");
    emit("    mov [rsi], dl\n");
    emit("    test rax, rax\n");
    emit("    jnz .Ldig\n");
    emit("    mov rdx, rsi\n");
    emit("    neg rdx\n");
    emit("    add rdx, 16\n");
    emit("    lea rsi, [rbp-16]\n");
    emit("    mov rax, 1\n");
    emit("    mov rdi, 1\n");
    emit("    syscall\n");
    emit("    leave\n");
    emit("    ret\n");
}

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <input.sov> <output.asm>\n", argv[0]);
        return 1;
    }
    
    FILE* f = fopen(argv[1], "rb");
    if (!f) { perror("fopen"); return 1; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    source = malloc(sz + 1);
    fread(source, 1, sz, f);
    source[sz] = 0;
    src_len = sz;
    fclose(f);
    
    lex();
    
    // Parse all statements
    Node* stmts[MAX_NODES];
    int stmt_count = 0;
    while (token_pos < token_count && tokens[token_pos].type != TK_EOF) {
        Node* s = parse_stmt();
        if (s) stmts[stmt_count++] = s;
        while (token_pos < token_count && tokens[token_pos].type == TK_NL) token_pos++;
    }
    
    generate((Node**)stmts, stmt_count);
    
    FILE* out = fopen(argv[2], "w");
    if (!out) { perror("fopen out"); return 1; }
    fwrite(output, 1, out_len, out);
    fclose(out);
    
    printf("OK %s -> %s (%d bytes)\n", argv[1], argv[2], out_len);
    return 0;
}