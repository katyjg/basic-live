import io
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings




class CollectAssetsCleanTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.assets_root = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _mock_download(self, src_url, path, sri=None):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("dummy asset content")

    def test_default_preserves_obsolete_files(self):
        obsolete_file = self.assets_root / "obsolete" / "stale.js"
        obsolete_file.parent.mkdir(parents=True, exist_ok=True)
        obsolete_file.write_text("old version")

        with override_settings(BASICLIVE_ASSETS_ROOT=str(self.assets_root)):
            with patch(
                "basiclive.core.lims.management.commands.collectassets.download_asset",
                side_effect=self._mock_download,
            ):
                call_command("collectassets")

        self.assertTrue(obsolete_file.exists())

    def test_clean_removes_obsolete_files_and_empty_dirs(self):
        obsolete_file = self.assets_root / "obsolete" / "subdir" / "stale.js"
        obsolete_file.parent.mkdir(parents=True, exist_ok=True)
        obsolete_file.write_text("old version")

        with override_settings(BASICLIVE_ASSETS_ROOT=str(self.assets_root)):
            with patch(
                "basiclive.core.lims.management.commands.collectassets.download_asset",
                side_effect=self._mock_download,
            ):
                call_command("collectassets", clean=True)

        self.assertFalse(obsolete_file.exists())
        self.assertFalse((self.assets_root / "obsolete" / "subdir").exists())
        self.assertFalse((self.assets_root / "obsolete").exists())
        self.assertTrue(self.assets_root.exists())

    def test_clean_preserves_hidden_files_and_their_dirs(self):
        root_gitkeep = self.assets_root / ".gitkeep"
        root_gitkeep.write_text("")

        keep_dir = self.assets_root / "vendor_keep"
        keep_dir.mkdir(parents=True, exist_ok=True)
        dir_gitkeep = keep_dir / ".gitkeep"
        dir_gitkeep.write_text("")

        stale_file = keep_dir / "stale.css"
        stale_file.write_text("stale css")

        with override_settings(BASICLIVE_ASSETS_ROOT=str(self.assets_root)):
            with patch(
                "basiclive.core.lims.management.commands.collectassets.download_asset",
                side_effect=self._mock_download,
            ):
                call_command("collectassets", clean=True)

        self.assertTrue(root_gitkeep.exists())
        self.assertTrue(dir_gitkeep.exists())
        self.assertFalse(stale_file.exists())
        self.assertTrue(keep_dir.exists())

    def test_clean_dry_run_reports_without_deleting(self):
        obsolete_file = self.assets_root / "obsolete" / "stale.js"
        obsolete_file.parent.mkdir(parents=True, exist_ok=True)
        obsolete_file.write_text("old version")

        out = io.StringIO()
        with override_settings(BASICLIVE_ASSETS_ROOT=str(self.assets_root)):
            with patch(
                "basiclive.core.lims.management.commands.collectassets.download_asset",
                side_effect=self._mock_download,
            ):
                call_command("collectassets", clean=True, dry_run=True, stdout=out)

        output = out.getvalue()
        self.assertTrue(obsolete_file.exists())
        self.assertIn("Would remove obsolete asset:", output)
        self.assertIn("stale.js", output)

    def test_clean_empty_or_nonexistent_root(self):
        nonexistent = self.assets_root / "nonexistent_sub"
        with override_settings(BASICLIVE_ASSETS_ROOT=str(nonexistent)):
            with patch(
                "basiclive.core.lims.management.commands.collectassets.download_asset",
                side_effect=self._mock_download,
            ):
                call_command("collectassets", clean=True)
