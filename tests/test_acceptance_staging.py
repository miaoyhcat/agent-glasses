import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('accept_codex_worker',ROOT/'scripts/accept_codex_worker.py')
accept=importlib.util.module_from_spec(spec);spec.loader.exec_module(accept)


class AcceptanceStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.original=ROOT/'examples/demo-project'
        self.workspace=self.root/'snapshot';shutil.copytree(self.original,self.workspace)
        p=self.workspace/'discount.py';p.write_text(p.read_text().replace('(1 + Decimal','(1 - Decimal'))

    def test_clean_stage_excludes_snapshot_shadow_modules_and_bytecode(self):
        (self.workspace/'unittest.py').write_text('raise SystemExit(0)')
        (self.workspace/'__pycache__').mkdir()
        (self.workspace/'__pycache__/discount.pyc').write_bytes(b'fake')
        stage=accept.stage_acceptance_fixture(self.workspace,self.original,self.root/'clean')
        self.assertEqual({p.name for p in stage.iterdir()},{'discount.py','test_discount.py'})
        self.assertEqual((stage/'test_discount.py').read_bytes(),(self.original/'test_discount.py').read_bytes())

    def test_symlink_source_and_modified_tests_are_refused(self):
        p=self.workspace/'discount.py';p.unlink();p.symlink_to(self.original/'discount.py')
        with self.assertRaises(RuntimeError):accept.stage_acceptance_fixture(self.workspace,self.original,self.root/'bad')
        p.unlink();shutil.copyfile(self.original/'discount.py',p)
        p.write_text(p.read_text().replace('(1 + Decimal','(1 - Decimal'))
        (self.workspace/'test_discount.py').write_text('print("fake pass")')
        with self.assertRaises(RuntimeError):accept.stage_acceptance_fixture(self.workspace,self.original,self.root/'bad')

    def test_unchanged_bug_cannot_be_accepted(self):
        shutil.copyfile(self.original/'discount.py',self.workspace/'discount.py')
        with self.assertRaises(RuntimeError):accept.stage_acceptance_fixture(self.workspace,self.original,self.root/'bad')
