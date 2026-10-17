import os
from pathlib import Path
import stat
import tempfile
import unittest
from agentglass.security import prepare_worker_tree


class WorkerTreeTests(unittest.TestCase):
    def test_model_created_symlinks_cannot_chmod_host_target(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);outside=root/'private';outside.write_text('private');outside.chmod(0o600)
            work=root/'work';work.mkdir();(work/'escape').symlink_to(outside)
            with self.assertRaises(ValueError):prepare_worker_tree(work,writable=True)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode),0o600)
            self.assertEqual(outside.read_text(),'private')

    def test_hardlinks_and_special_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);outside=root/'private';outside.write_text('private');outside.chmod(0o600)
            work=root/'work';work.mkdir();os.link(outside,work/'hardlink')
            with self.assertRaises(ValueError):prepare_worker_tree(work,writable=True)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode),0o600)
            (work/'hardlink').unlink()
            if hasattr(os,'mkfifo'):
                os.mkfifo(work/'pipe')
                with self.assertRaises(ValueError):prepare_worker_tree(work,writable=True)

    def test_regular_tree_permissions_and_budget(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td);(work/'data').write_text('public');(work/'dir').mkdir()
            self.assertEqual(prepare_worker_tree(work,writable=False),{'files':1,'bytes':6})
            if os.name!='nt':self.assertEqual(stat.S_IMODE((work/'data').stat().st_mode),0o644)
            with self.assertRaises(ValueError):prepare_worker_tree(work,writable=True,max_bytes=5)
