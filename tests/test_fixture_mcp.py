import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_mcp', ROOT / 'scripts/fixture_mcp.py')
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class FixtureMcpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        for name in ['discount.py', 'test_discount.py']:
            shutil.copyfile(ROOT / 'examples/demo-project' / name, self.directory / name)
        self.tools = mcp.FixtureTools(self.directory)

    def test_actual_negative_and_fixed_tests(self):
        original = self.tools.invoke('read_fixture', {})['discount.py']
        self.assertNotEqual(self.tools.invoke('test_fixture', {})['exit_code'], 0)
        self.tools.invoke('write_fixture', {'source': original.replace('(1 + Decimal', '(1 - Decimal')})
        self.assertEqual(self.tools.invoke('test_fixture', {})['exit_code'], 0)

    def test_harmless_documentation_change_is_accepted(self):
        source = self.tools.original.replace('(1 + Decimal', '(1 - Decimal').replace('Exercise: a 10% discount on 100 should produce 90, not 110.', 'Apply a proportional discount.')
        self.tools.invoke('write_fixture', {'source': source})
        self.assertEqual(self.tools.invoke('test_fixture', {})['exit_code'], 0)

    def test_arbitrary_code_paths_and_commands_refused(self):
        for name, args in [('write_fixture', {'source': "import os;os.system('false')"}), ('read_fixture', {'path': '/etc/passwd'}), ('shell', {'command': 'true'})]:
            with self.assertRaises(ValueError):
                self.tools.invoke(name, args)

    def test_changed_tests_and_symlinks_refused(self):
        (self.directory / 'test_discount.py').write_text('print("fake pass")')
        with self.assertRaises(ValueError):
            self.tools.invoke('test_fixture', {})
        shutil.copyfile(ROOT / 'examples/demo-project/test_discount.py', self.directory / 'test_discount.py')
        (self.directory / 'unexpected').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            self.tools.invoke('read_fixture', {})

    def test_call_budget(self):
        for _ in range(24):
            self.tools.invoke('read_fixture', {})
        with self.assertRaises(ValueError):
            self.tools.invoke('read_fixture', {})
