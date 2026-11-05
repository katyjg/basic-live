import json
from pathlib import Path

from django.apps import apps
from django.test import TestCase



class NotebooksAssetsTestCase(TestCase):
    def setUp(self):
        app_config = apps.get_app_config("notebooks")
        self.static_dir = Path(app_config.path) / "static" / "notebooks"
        self.assets_file = self.static_dir / "assets.json"

    def test_assets_json_exists_and_parses(self):
        """Verify notebooks/assets.json exists and is valid JSON."""
        self.assertTrue(self.assets_file.exists(), "notebooks/assets.json must exist")
        with open(self.assets_file, "r") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_required_vendor_libraries_defined(self):
        """Verify all required vendor packages are defined with valid structure and SRIs."""
        expected_libraries = [
            "simplemde",
            "katex",
            "dropzone",
            "atrament",
            "papaparse",
            "d3",
            "clndr",
            "moment",
            "tinycolorpicker",
            "html5sortable",
            "highlight",
            "markjs",
        ]
        with open(self.assets_file, "r") as f:
            data = json.load(f)

        for lib in expected_libraries:
            self.assertIn(lib, data, f"Missing vendor library '{lib}' in assets.json")
            conf = data[lib]
            self.assertIn("url", conf, f"Library '{lib}' missing 'url' key")
            has_assets = False
            for kind in ["js", "css", "fonts"]:
                if kind in conf:
                    has_assets = True
                    for entry in conf[kind]:
                        self.assertIn("path", entry, f"Asset entry in '{lib}' missing 'path'")
                        self.assertIn("sri", entry, f"Asset entry in '{lib}' missing 'sri'")
                        self.assertTrue(
                            entry["sri"].startswith(("sha256-", "sha384-", "sha512-")),
                            f"Invalid SRI prefix for '{lib}': {entry['sri']}"
                        )
            self.assertTrue(has_assets, f"Library '{lib}' has no assets defined")

    def test_native_assets_exist(self):
        """Verify native CSS/SCSS, icons, fonts, images, and JS files exist."""
        required_files = [
            self.static_dir / "icons" / "style.css",
            self.static_dir / "icons" / "fonts" / "Myeln-Icons.eot",
            self.static_dir / "icons" / "fonts" / "Myeln-Icons.svg",
            self.static_dir / "icons" / "fonts" / "Myeln-Icons.ttf",
            self.static_dir / "icons" / "fonts" / "Myeln-Icons.woff",
            self.static_dir / "img" / "text-color.png",
            self.static_dir / "notebooks.scss",
            self.static_dir / "notebooks.min.css",
            self.static_dir / "calendar.min.css",
            self.static_dir / "notebooks.js",
            self.static_dir / "notebooks.min.js",
        ]
        for f in required_files:
            self.assertTrue(f.exists(), f"Required native asset '{f.name}' not found at {f}")

    def test_relative_asset_paths_clean(self):
        """Verify native SCSS/CSS does not contain dead /static/ext references."""
        scss_file = self.static_dir / "notebooks.scss"
        with open(scss_file, "r") as f:
            scss_content = f.read()
        self.assertNotIn("/static/ext/tinycolorpicker/text-color.png", scss_content)
        self.assertIn("../img/text-color.png", scss_content)

        default_css = self.static_dir / "notebooks.min.css"
        with open(default_css, "r") as f:
            css_content = f.read()
        self.assertNotIn("/static/ext/", css_content)
