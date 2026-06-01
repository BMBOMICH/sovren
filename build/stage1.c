#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>
extern sov_int lexer_new(sov_string, sov_string);
extern sov_int lexer_tokenize(sov_int);
extern sov_int parser_new(sov_int, sov_string);
extern sov_int parser_parse(sov_int);
extern sov_int codegen_new(void);
extern sov_int codegen_generate(sov_int, sov_int);
int main(int argc, char** argv) {
    if (argc < 3) { printf("Sovereign v0.1.0 - Usage: sovereign build <in.sov> -o <out.c>\n"); return 1; }
    sov_string in = NULL, out = NULL;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 && i+1 < argc) out = argv[++i];
        else if (argv[i][0] != '-') in = argv[i];
    }
    if (!in || !out) { printf("Missing args\n"); return 1; }
    sov_string src = sov_file_read_all(in);
    if (!src) { printf("Cannot read %s\n", in); return 1; }
    sov_int lex = lexer_new(src, in);
    sov_int tok = lexer_tokenize(lex);
    sov_int par = parser_new(tok, in);
    sov_int prog = parser_parse(par);
    sov_int cg = codegen_new();
    sov_int result = codegen_generate(cg, prog);
    sov_file_write_all(out, (sov_string)result);
    printf("%s -> %s\n", in, out);
    sov_free(src);
    return 0;
}
