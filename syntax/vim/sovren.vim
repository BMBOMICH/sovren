" Sovren colors for Vim / Neovim
" Put this file in ~/.vim/syntax/sovren.vim
" and add to ~/.vimrc:
"   autocmd BufRead,BufNewFile *.sov set filetype=sovren

if exists("b:current_syntax")
  finish
endif

syntax keyword sovTask return if times stop use wipe private print and or is not blank
syntax match sovTask "\<if not\>"
syntax match sovTask "\<as long as\>"
syntax match sovOp "==\|!=\|<=\|>=\|&&\|||"
syntax match sovOp "[+\-*/%<>=:]"
syntax keyword sovFn syscall peek_byte peek_i64 peek_ptr poke_byte poke_i64
syntax match sovNum "\<[0-9]\+\>"
syntax match sovComment "#.*$"
syntax region sovString start=+"+ skip=+\\"+ end=+"+

highlight default link sovTask Keyword
highlight default link sovOp Operator
highlight default link sovFn Function
highlight default link sovNum Number
highlight default link sovComment Comment
highlight default link sovString String

let b:current_syntax = "sovren"
