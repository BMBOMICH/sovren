.intel_syntax noprefix
.text
.globl cfind1n_swar
.globl pu_find_swar
.globl sp_hinc_swar

# ---- twin for cfind1n: rdi=s rsi=st rdx=lim rcx=ch -> rax
# first index in [st,lim) with byte==ch, else -1; s==0 -> 0.
# volatile-only: rax rcx rdx rsi rdi r8 r9 r10 r11. no calls.
cfind1n_swar:
    mov     rax, rdi
    test    rdi, rdi
    jz      .cz0
    movzx   ecx, cl
    mov     r8, 0x0101010101010101
    imul    r8, rcx
    mov     r9, 0x0101010101010101
    mov     r10, 0x8080808080808080
    lea     r11, [rdi+rsi]
    lea     rdx, [rdi+rdx]
.cs:
    lea     rax, [r11+8]
    cmp     rax, rdx
    ja      .ct
    mov     rax, [r11]
    xor     rax, r8
    mov     rcx, rax
    sub     rcx, r9
    not     rax
    and     rcx, rax
    and     rcx, r10
    jz      .cadv
    bsf     rcx, rcx
    shr     rcx, 3
    lea     rax, [r11+rcx]
    sub     rax, rdi
    jmp     .cdone
.cadv:
    add     r11, 8
    jmp     .cs
.ct:
    cmp     r11, rdx
    jae     .cnf
    movzx   eax, byte ptr [r11]
    cmp     al, r8b
    je      .ctf
    inc     r11
    jmp     .ct
.ctf:
    mov     rax, r11
    sub     rax, rdi
    jmp     .cdone
.cnf:
    mov     rax, -1
    jmp     .cdone
.cz0:
.cdone:
    ret

# ---- twin for pu_find_use: rdi=text rsi=st rdx=lim -> rax
# index of the 'u' of the next `use `/`use:` line at/after st, else -1.
# volatile-only, no calls.
pu_find_swar:
    mov     r8, 0x0A0A0A0A0A0A0A0A
    mov     r9, 0x0101010101010101
    mov     r10, 0x8080808080808080
    lea     r11, [rdi+rdx]
    lea     rsi, [rdi+rsi]
.ph:
    cmp     rsi, r11
    jae     .pnf
    movzx   eax, byte ptr [rsi]
    cmp     al, 32
    je      .pw
    cmp     al, 9
    je      .pw
    cmp     al, 13
    je      .pw
    jmp     .pck
.pw:
    inc     rsi
    jmp     .ph
.pck:
    lea     rax, [rsi+4]
    cmp     rax, r11
    ja      .pnl
    mov     eax, [rsi]
    cmp     eax, 0x20657375
    je      .phit
    cmp     eax, 0x3A657375
    je      .phit
    jmp     .pnl
.phit:
    mov     rax, rsi
    sub     rax, rdi
    jmp     .pdone
.pnl:
    lea     rax, [rsi+8]
    cmp     rax, r11
    ja      .pnt
    mov     rax, [rsi]
    xor     rax, r8
    mov     rcx, rax
    sub     rcx, r9
    not     rax
    and     rcx, rax
    and     rcx, r10
    jz      .pnadv
    bsf     rcx, rcx
    shr     rcx, 3
    add     rsi, rcx
    inc     rsi
    jmp     .ph
.pnadv:
    add     rsi, 8
    jmp     .pnl
.pnt:
    cmp     rsi, r11
    jae     .pnf
    movzx   eax, byte ptr [rsi]
    inc     rsi
    cmp     al, 10
    jne     .pnt
    jmp     .ph
.pnf:
    mov     rax, -1
.pdone:
    ret

# ---- twin for sp_hinc_lim: rdi=text rsi=lim -> rax
# 1 iff some line in [0,lim) starts (after ws 32/9/13) with "include ".
# volatile-only, no calls.
sp_hinc_swar:
    mov     rdx, 0x0A0A0A0A0A0A0A0A
    mov     r8, 0x0101010101010101
    mov     r9, 0x8080808080808080
    lea     r10, [rdi+rsi]
    mov     r11, rdi
.sh:
    cmp     r11, r10
    jae     .s0
    movzx   eax, byte ptr [r11]
    cmp     al, 32
    je      .sw
    cmp     al, 9
    je      .sw
    cmp     al, 13
    je      .sw
    jmp     .sck
.sw:
    inc     r11
    jmp     .sh
.sck:
    lea     rax, [r11+8]
    cmp     rax, r10
    ja      .snl
    mov     rax, [r11]
    mov     rcx, 0x206564756C636E69
    cmp     rax, rcx
    je      .s1
.snl:
    lea     rax, [r11+8]
    cmp     rax, r10
    ja      .snt
    mov     rax, [r11]
    xor     rax, rdx
    mov     rcx, rax
    sub     rcx, r8
    not     rax
    and     rcx, rax
    and     rcx, r9
    jz      .snadv
    bsf     rcx, rcx
    shr     rcx, 3
    add     r11, rcx
    inc     r11
    jmp     .sh
.snadv:
    add     r11, 8
    jmp     .snl
.snt:
    cmp     r11, r10
    jae     .s0
    movzx   eax, byte ptr [r11]
    inc     r11
    cmp     al, 10
    jne     .snt
    jmp     .sh
.s0:
    xor     eax, eax
    jmp     .sdone
.s1:
    mov     eax, 1
.sdone:
    ret
