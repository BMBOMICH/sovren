#!/usr/bin/env python3
from retained_inventory import ROOT,document
(ROOT/'COMPILER_COMPLETENESS.md').write_text(document('Retained compiler availability'),encoding='utf-8')
print('Wrote current retained inventory; no completeness or speed certification')
