#!/usr/bin/env python3
"""Installed shared-backend correctness job, deliberately without benchmarks."""
import argparse,json,subprocess,sys
from pathlib import Path
from backend_support import ROOT,source_snapshot
p=argparse.ArgumentParser();p.add_argument('--tsc',required=True);p.add_argument('--output',type=Path,default='/tmp/ci');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
commands=[['tests/integration/physical_layout.py','--output',str(a.output/'physical-layout.json')],['tests/regression/constant_eval.py','--output',str(a.output/'constant-evaluation.json')],['tools/backend.py','verify'],['tests/conformance/transpilers.py','--require-native','--require-ts','--tsc',a.tsc,'--output',str(a.output/'conformance.json')],['tests/integration/shared_ir.py','--output',str(a.output/'shared-ir.json')],['tests/conformance/output_safety.py','--output',str(a.output/'output-safety.json')]]
for command in commands:subprocess.run([sys.executable,*command],cwd=ROOT,check=True)
result=json.loads((a.output/'conformance.json').read_text());assert result['implementation_sources_sha256']==source_snapshot();print('Installed shared backend correctness PASS; not full-language certification')
