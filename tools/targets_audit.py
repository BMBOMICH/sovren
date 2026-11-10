#!/usr/bin/env python3
"""Audit retained file identities. Missing driver binaries fail this gate."""
import json
from backend_support import load,integrity,layout_integrity
failures={e['id']:err for e in load() if (err:=integrity(e,views=True))}
if (errors:=layout_integrity()):failures['layout']=errors
print(json.dumps(failures,indent=2) if failures else 'Retained file identities PASS; not execution certification')
raise SystemExit(bool(failures))
