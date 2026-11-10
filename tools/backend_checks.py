#!/usr/bin/env python3
"""Installed retained-backend correctness job. No speed certification."""
import argparse,json,subprocess,sys
from pathlib import Path
from backend_support import ROOT,source_snapshot
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('/tmp/ci'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
commands=[['tests/integration/physical_layout.py','--output',str(a.output/'physical-layout.json')],['tests/regression/constant_eval.py','--output',str(a.output/'constant-evaluation.json')],['tools/backend.py','verify'],['tests/conformance/native.py','--output',str(a.output/'conformance.json')],['tests/conformance/output_safety.py','--output',str(a.output/'output-safety.json')]]
for command in commands:subprocess.run([sys.executable,*command],cwd=ROOT,check=True)
result=json.loads((a.output/'conformance.json').read_text(encoding='utf-8'));assert result['implementation_sources_sha256']==source_snapshot();print('Retained backend correctness PASS; not full-language certification')
