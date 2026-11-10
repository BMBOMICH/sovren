#!/usr/bin/env python3
from retained_inventory import ROOT,document
(ROOT/'IMPLEMENTATION_LEDGER.md').write_text(document('Retained compiler implementation ledger'),encoding='utf-8')
print('Wrote current retained inventory; no completeness or speed certification')
