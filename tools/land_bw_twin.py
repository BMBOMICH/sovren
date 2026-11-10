#!/usr/bin/env python3
"""Land / unland the bw twin (native statement lowering dispatch).

Landing (v2 design, work/p4/SESSION_2026-11-02_NIGHT_BW_TWIN_AND_PATCH_BUG.md):
  statements.sov:
    - syntax_stmt_lower's syntax_emit call -> _sov_emit_tw(tree, root, sx_tbl)
      with lazy sx_tbl_init()
    - tw_block_v2.sov appended at end + `include emit_native.sov`
  cx86_p3.sov:
    - nt_will_twin:      `if _sov_str_eq(tnm, "_sov_emit_tw") is 1 -> return 1`
    - try_native_body:   `if _sov_str_eq(tnm, "_sov_emit_tw") is 1 -> return emit_nt_syntax_emit_tw()`

--unland restores both files from the pristine checkpoint copies.
"""
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
ST = R / 'compilers/linux/statements.sov'
P3 = R / 'compilers/shared/cx86_p3.sov'
BLOCK = R / 'work/p4/tw_block_v2.sov'
PRISTINE_ST = Path('/tmp/statements.sov.fixedbase')
PRISTINE_P3 = Path('/tmp/cx86_p3.sov.fixedbase')

CALL_OLD = "    sx_result: syntax_emit(sx_tree, peek_i64(sx_tree, 48))\n"
CALL_NEW = ("    if sx_tbl is 0 -> sx_tbl_init()\n"
            "    sx_result: _sov_emit_tw(sx_tree, peek_i64(sx_tree, 48), sx_tbl)\n")
INCLUDE_LINE = "include emit_native.sov\n"

WT_OLD = '    if _sov_str_eq(tnm, "syntax_build") is 1 -> return 1\n'
WT_NEW = ('    if _sov_str_eq(tnm, "syntax_build") is 1 -> return 1\n'
          '    if _sov_str_eq(tnm, "_sov_emit_tw") is 1 -> return 1\n')
TB_OLD = '    if _sov_str_eq(tnm, "syntax_build") is 1 -> return emit_nt_syntax_build()\n'
TB_NEW = ('    if _sov_str_eq(tnm, "syntax_build") is 1 -> return emit_nt_syntax_build()\n'
          '    if _sov_str_eq(tnm, "_sov_emit_tw") is 1 -> return emit_nt_syntax_emit_tw()\n')

def land():
    st = ST.read_text()
    assert st.count(CALL_OLD) == 1, 'call site not found exactly once'
    assert INCLUDE_LINE not in st and 'sx_tbl_init' not in st, 'twin already landed'
    st = st.replace(CALL_OLD, CALL_NEW)
    block = BLOCK.read_text()
    if not block.endswith('\n'):
        block += '\n'
    st = st + '\n' + block + INCLUDE_LINE
    ST.write_text(st)
    p3 = P3.read_text()
    assert p3.count(WT_OLD) == 1 and p3.count(TB_OLD) == 1
    p3 = p3.replace(WT_OLD, WT_NEW).replace(TB_OLD, TB_NEW)
    P3.write_text(p3)
    print('landed: statements.sov (+%d B), cx86_p3.sov (+2 dispatch lines)' %
          (len(ST.read_text()) - len(PRISTINE_ST.read_text())))

def unland():
    import shutil
    shutil.copy(PRISTINE_ST, ST)
    shutil.copy(PRISTINE_P3, P3)
    print('unlanded: pristine statements.sov + cx86_p3.sov restored')

if __name__ == '__main__':
    {'land': land, 'unland': unland}[sys.argv[1]]()
