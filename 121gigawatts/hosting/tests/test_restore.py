import importlib.util
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('restore', Path(__file__).parents[1] / 'ansible/files/restore.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class Archive:
    def __init__(self, members):
        self.members = members
    def getmembers(self):
        return self.members


class RestoreArchiveTests(unittest.TestCase):
    def test_content_file_allowed(self):
        restore.validate_archive(Archive([tarfile.TarInfo('images/2026/photo.jpg')]))

    def test_parent_and_absolute_paths_rejected(self):
        for name in ['../config.production.json', '/etc/passwd', 'images/../../config.production.json']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                restore.validate_archive(Archive([tarfile.TarInfo(name)]))

    def test_site_backup_not_content_archive(self):
        with self.assertRaises(ValueError):
            restore.validate_archive(Archive([tarfile.TarInfo('config.production.json')]))

    def test_links_and_devices_rejected(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE]:
            member = tarfile.TarInfo('images/escape')
            member.type = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                restore.validate_archive(Archive([member]))


class TargetTests(unittest.TestCase):
    def test_nonempty_target_is_refused_before_import(self):
        with patch.object(restore.subprocess, 'run', return_value=Mock(stdout='18\n')), \
             patch.object(restore.subprocess, 'Popen') as importer:
            with self.assertRaisesRegex(ValueError, 'nonempty database'):
                restore.restore()
            importer.assert_not_called()

if __name__ == '__main__':
    unittest.main()
