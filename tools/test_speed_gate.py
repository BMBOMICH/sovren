import unittest
import tempfile
from pathlib import Path
import sys
from speed_gate import Command, checked, run_interleaved

class SpeedGateTests(unittest.TestCase):
    def test_named_ownership_and_order(self):
        order=[]
        commands={'sovren':Command(['slow'],Path('s')), 'sa':Command(['fast'],Path('a'))}
        def fake(command, cwd):
            order.append(command.argv[0]);return 10.0 if command.argv[0]=='slow' else 1.0
        result=run_interleaved(commands,4,runner=fake)
        self.assertEqual(result['sovren'].samples_seconds,[10]*4)
        self.assertEqual(result['sa'].samples_seconds,[1]*4)
        self.assertEqual(order,['slow','fast','fast','slow','slow','fast','fast','slow'])
    def test_reject_failed_translation_and_stale_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'artifact';p.write_text('stale')
            with self.assertRaises(RuntimeError):
                checked(Command([sys.executable,'-c','raise SystemExit(7)'],p))
            self.assertFalse(p.exists())
    def test_reject_missing_or_empty_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'artifact'
            for script in ['pass', f'open({str(p)!r},"w").close()']:
                with self.assertRaises(RuntimeError):checked(Command([sys.executable,'-c',script],p))
    def test_failed_cell_aborts(self):
        def fail(command,cwd):raise RuntimeError('bad compile')
        with self.assertRaises(RuntimeError):run_interleaved({'sovren':Command([],Path('s'))},1,runner=fail)
    def test_positive_round_count(self):
        with self.assertRaises(ValueError):run_interleaved({},0)

if __name__=='__main__':unittest.main()
