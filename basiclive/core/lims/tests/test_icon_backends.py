from django.test import SimpleTestCase, override_settings


from basiclive.core.lims.icons import (
    BaseIconBackend,
    ThemifyBackend,
    get_icon_backend,
)


class DummyIconBackend(BaseIconBackend):
    name = "dummy"

    def resolve_icon_name(self, icon: str) -> str:
        return f"dummy-{icon}"

    def get_css_classes(self, icon: str, size: str = None, extra_class: str = "") -> str:
        classes = ["dummy", self.resolve_icon_name(icon)]
        size_cls = self.format_size_class(size)
        if size_cls:
            classes.append(size_cls)
        if extra_class:
            classes.append(extra_class)
        return " ".join(classes)

    def get_stylesheet_urls(self) -> list[str]:
        return ["dummy/dummy.css"]

    def get_assets(self) -> dict:
        return {
            "dummy-icons": {
                "url": "https://example.com/dummy/",
                "css": [{"path": "dummy.css", "sri": "sha256-dummy"}]
            }
        }

    def cleanup_assets(self, assets_root):
        DummyIconBackend.cleanup_invoked = True


class IconBackendTests(SimpleTestCase):
    def test_default_backend_resolution(self):
        backend = get_icon_backend()
        self.assertIsInstance(backend, ThemifyBackend)
        self.assertEqual(backend.name, "themify")

    @override_settings(BASICLIVE_ICON_BACKEND="basiclive.core.lims.tests.test_icon_backends.DummyIconBackend")
    def test_custom_backend_setting(self):
        backend = get_icon_backend()
        self.assertIsInstance(backend, DummyIconBackend)
        self.assertEqual(backend.name, "dummy")
        self.assertEqual(backend.get_css_classes("test", size="lg"), "dummy dummy-test bl-icon-lg")

    def test_themify_get_css_classes_plain_icon(self):
        backend = ThemifyBackend()
        self.assertEqual(backend.get_css_classes("home"), "ti ti-home")
        self.assertEqual(backend.get_css_classes("calendar", size="md"), "ti ti-calendar bl-icon-md")
        self.assertEqual(
            backend.get_css_classes("alert", size="sm", extra_class="text-danger"),
            "ti ti-alert bl-icon-sm text-danger"
        )

    def test_themify_allowed_sizes(self):
        backend = ThemifyBackend()
        for size in ("xs", "sm", "md", "lg", "xl"):
            classes = backend.get_css_classes("star", size=size)
            self.assertEqual(classes, f"ti ti-star bl-icon-{size}")

    def test_themify_invalid_size_raises(self):
        backend = ThemifyBackend()
        with self.assertRaises(ValueError) as ctx:
            backend.get_css_classes("star", size="2x")
        self.assertIn("Invalid icon size '2x'", str(ctx.exception))

    def test_themify_empty_or_whitespace_icon(self):
        backend = ThemifyBackend()
        self.assertEqual(backend.get_css_classes(""), "")
        self.assertEqual(backend.get_css_classes("   "), "")

    def test_themify_stylesheet_urls(self):
        backend = ThemifyBackend()
        self.assertEqual(backend.get_stylesheet_urls(), ["themify-icons/css/themify-icons.css"])

    def test_render_icon_helper(self):
        from basiclive.core.lims.icons import render_icon
        self.assertEqual(render_icon("home"), '<i class="ti ti-home"></i>')
        self.assertEqual(render_icon(name="home"), '<i class="ti ti-home"></i>')
        self.assertEqual(render_icon(icon="home"), '<i class="ti ti-home"></i>')
        self.assertEqual(
            render_icon("download", size="md", extra_class="text-primary"),
            '<i class="ti ti-download bl-icon-md text-primary"></i>'
        )
        self.assertEqual(render_icon("move", extra_class="movable"), '<i class="ti ti-move movable"></i>')
        self.assertEqual(render_icon("minus"), '<i class="ti ti-minus"></i>')
        self.assertEqual(render_icon("plus"), '<i class="ti ti-plus"></i>')
        self.assertEqual(render_icon(""), "")
        self.assertEqual(render_icon(None), "")

    @override_settings(BASICLIVE_ICON_BACKEND="basiclive.core.lims.tests.test_icon_backends.DummyIconBackend")
    def test_render_icon_with_custom_backend(self):
        from basiclive.core.lims.icons import render_icon
        self.assertEqual(render_icon("plus"), '<i class="dummy dummy-plus"></i>')
        self.assertEqual(
            render_icon("move", size="sm", extra_class="movable"),
            '<i class="dummy dummy-move bl-icon-sm movable"></i>'
        )

    def test_base_backend_abstract_methods(self):
        backend = BaseIconBackend()
        with self.assertRaises(NotImplementedError):
            backend.get_stylesheet_urls()

    def test_framework_icon_sizing_classes_in_scss_and_css(self):
        from pathlib import Path
        from django.apps import apps
        lims_static = Path(apps.get_app_config("lims").path) / "static" / "lims" / "css"
        scss_content = (lims_static / "basiclive.scss").read_text()
        css_content = (lims_static / "basiclive.min.css").read_text()

        for size in ("xs", "sm", "md", "lg", "xl"):
            self.assertIn(f".bl-icon-{size}", scss_content)
            self.assertIn(f".bl-icon-{size}", css_content)

    def test_show_icon_template_tag_plain_icon(self):
        from django.template import Template, Context
        tmpl = Template('{% load bl_icons %}{% show_icon icon="home" %}')
        rendered = tmpl.render(Context({})).strip()
        self.assertRegex(rendered, r'class="ti ti-[^\s]+? position-relative"')

    def test_show_icon_template_tag_with_size(self):
        from django.template import Template, Context
        tmpl = Template('{% load bl_icons %}{% show_icon icon="calendar" size="md" %}')
        rendered = tmpl.render(Context({})).strip()
        self.assertRegex(rendered, r'class="ti ti-[^\s]+? bl-icon-md position-relative"')

    def test_show_icon_template_tag_with_extra_class(self):
        from django.template import Template, Context
        tmpl = Template('{% load bl_icons %}{% show_icon icon="alert" size="sm" extra_class="text-danger" %}')
        rendered = tmpl.render(Context({})).strip()
        self.assertRegex(rendered, r'class="ti ti-[^\s]+? bl-icon-sm text-danger position-relative"')

    def test_show_icon_template_tag_with_label_and_tooltip(self):
        from django.template import Template, Context
        tmpl = Template(
            '{% load bl_icons %}{% show_icon label="Calendar" icon="calendar" size="md" tooltip="View calendar" %}'
        )
        rendered = tmpl.render(Context({})).strip()
        self.assertIn('title="View calendar"', rendered)
        self.assertRegex(rendered, r'<div class="icon-label .+?">Calendar</div>')

    def test_show_icon_template_tag_with_badge_and_color(self):
        from django.template import Template, Context
        tmpl = Template('{% load bl_icons %}{% show_icon icon="headphone-alt" badge="+" color="primary" %}')
        rendered = tmpl.render(Context({})).strip()
        self.assertIn('rounded-pill', rendered)
        self.assertIn('position-absolute', rendered)
        self.assertIn('>+</span>', rendered)

    def test_show_icon_template_tag_invalid_size_raises(self):
        from django.template import Template, Context
        tmpl = Template('{% load bl_icons %}{% show_icon icon="star" size="invalid_size" %}')
        with self.assertRaises(ValueError) as ctx:
            tmpl.render(Context({}))
        self.assertIn("Invalid icon size 'invalid_size'", str(ctx.exception))

    def test_show_icon_css_template_tag(self):
        from django.template import Template, Context
        from django.templatetags.static import static
        tmpl = Template('{% load bl_icons %}{% show_icon_css %}')
        rendered = tmpl.render(Context({})).strip()
        expected = f'<link rel="stylesheet" href="{static("themify-icons/css/themify-icons.css")}">'
        self.assertEqual(rendered, expected)

    @override_settings(BASICLIVE_ICON_BACKEND="basiclive.core.lims.tests.test_icon_backends.DummyIconBackend")
    def test_show_icon_css_custom_backend(self):
        from django.template import Template, Context
        from django.templatetags.static import static
        tmpl = Template('{% load bl_icons %}{% show_icon_css %}')
        rendered = tmpl.render(Context({})).strip()
        expected = f'<link rel="stylesheet" href="{static("dummy/dummy.css")}">'
        self.assertEqual(rendered, expected)

    def test_lims_base_html_uses_show_icon_css(self):
        from django.template.loader import get_template
        from django.templatetags.static import static
        tmpl = get_template("lims/base.html")
        rendered = tmpl.render({"user": None, "APP_NAME": "BasicLIVE"})
        expected = f'<link rel="stylesheet" href="{static("themify-icons/css/themify-icons.css")}">'
        self.assertIn(expected, rendered)

    def test_no_hardcoded_ti_icons_in_python_and_templates(self):
        import re
        from pathlib import Path
        import basiclive

        base_dir = Path(basiclive.__file__).parent
        # Search for raw HTML icon tags referencing ti or ti-
        raw_icon_pattern = re.compile(r'<i\s+class=[\'"][^\'"]*\bti[-\s][^\'"]*[\'"]')

        violations = []
        for path in base_dir.rglob("*"):
            if path.suffix in (".py", ".html"):
                # Skip icons.py itself where render_icon generates <i class="...">
                if path.name == "icons.py" or "/tests/" in path.as_posix():
                    continue
                content = path.read_text(errors="ignore")
                matches = raw_icon_pattern.findall(content)
                if matches:
                    violations.append((str(path.relative_to(base_dir)), matches))

        self.assertEqual(violations, [], f"Found hardcoded icon HTML in codebase: {violations}")

    def test_base_backend_asset_defaults(self):
        backend = BaseIconBackend()
        self.assertEqual(backend.get_assets(), {})
        # Verify default cleanup and post_collect do not raise
        from pathlib import Path
        backend.cleanup_assets(Path("/tmp"))
        backend.post_collect(Path("/tmp"))

    def test_collectassets_command_integrates_icon_backend(self):
        from unittest.mock import patch
        from django.core.management import call_command

        with patch("basiclive.core.lims.management.commands.collectassets.download_asset") as mock_download:
            call_command("collectassets")
            # Verify download_asset was called for Themify assets provided by backend
            called_urls = [call.args[0] for call in mock_download.call_args_list]
            self.assertTrue(
                any("themify-icons.css" in url for url in called_urls),
                f"Expected themify-icons.css in download calls, got: {called_urls}"
            )
            self.assertTrue(
                any("themify" in url for url in called_urls),
                f"Expected themify in download calls, got: {called_urls}"
            )

    @override_settings(BASICLIVE_ICON_BACKEND="basiclive.core.lims.tests.test_icon_backends.DummyIconBackend")
    def test_collectassets_command_with_custom_backend_and_cleanup(self):
        from unittest.mock import patch
        from django.core.management import call_command

        DummyIconBackend.cleanup_invoked = False
        with patch("basiclive.core.lims.management.commands.collectassets.download_asset") as mock_download:
            call_command("collectassets")
            called_urls = [call.args[0] for call in mock_download.call_args_list]
            self.assertTrue(
                any("dummy.css" in url for url in called_urls),
                f"Expected dummy.css in download calls, got: {called_urls}"
            )
            self.assertTrue(
                DummyIconBackend.cleanup_invoked,
                "Expected DummyIconBackend.cleanup_assets to be called during collectassets"
            )






