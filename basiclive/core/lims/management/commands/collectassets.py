# Modified from https://github.com/jochenklar/django-vendor-files/
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

import httpx2
from django.apps import apps as django_apps
from django.conf import settings
from django.core.management.base import BaseCommand

from basiclive.core.lims.icons import get_icon_backend


def get_assets_root() -> Path:
    assets_root = getattr(settings, "BASICLIVE_ASSETS_ROOT", None)
    if assets_root:
        return Path(assets_root)
    static_root = getattr(settings, "STATIC_ROOT", None) or Path("static")
    return Path(static_root) / "assets"


ASSETS_ROOT = get_assets_root()


def download_asset(src_url, path: Path | str, sri: str | None = None):
    """
    Download an asset from the given URL and save it to the given path and verify it's checksum
    if SRI is provided
    :param src_url: Source URL
    :param path: Target path to save the file
    :param sri: SRI string for verification
    """

    # if file exists, check SRI and only download if new
    download_pending = True
    if Path(path).exists() and sri:
        algorithm, file_hash = sri.split('-')
        h = hashlib.new(algorithm)
        with open(path, 'rb') as f:
            content = f.read()
            h.update(content)
            if base64.b64encode(h.digest()).decode() == file_hash:
                print(f'{path} is up to date!')
                download_pending = False

    if download_pending:
        # fetch the file from the url
        response = httpx2.get(src_url, follow_redirects=True)
        response.raise_for_status()

        # check the integrity of the file if an SRI was supplied
        if sri is not None:
            algorithm, file_hash = sri.split('-')
            h = hashlib.new(algorithm)
            h.update(response.content)
            if base64.b64encode(h.digest()).decode() != file_hash:
                print(f'File integrity mismatch: {path}!!!')
                return

        # Save the file
        with open(path, 'wb') as f:
            print(f'{src_url} -> {path}')
            f.write(response.content)


class Command(BaseCommand):
    help = 'Fetches static asset files from CDNs defined in `assets.json` files and the active icon backend'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Remove obsolete files and empty directories from the asset root folder.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report obsolete files that would be removed without deleting them.',
        )

    def process_assets(self, assets: dict, assets_root: Path) -> set[Path]:
        collected_files: set[Path] = set()
        for key, asset_conf in assets.items():
            conf = dict(asset_conf)
            url = conf.pop('url', '')
            for kind in conf.keys():
                for asset in conf[kind]:
                    # get the directory and the file_name
                    filename = asset.get('file', Path(asset['path']).name)
                    file_path = assets_root / key / kind / filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    collected_files.add(file_path.resolve())

                    # get the full url of the file
                    file_url = urljoin(url, asset['path'])
                    download_asset(file_url, file_path, sri=asset.get('sri'))
        return collected_files

    def clean_obsolete_assets(
        self,
        assets_root: Path,
        expected_files: set[Path],
        dry_run: bool = False,
        verbosity: int = 1,
    ) -> list[Path]:
        """
        Identify and remove files in assets_root that are not in expected_files.
        Hidden files and directories (names starting with '.') are preserved.
        Empty directories left behind are also pruned up to assets_root.
        """
        if not assets_root.exists():
            return []

        resolved_root = assets_root.resolve()
        obsolete_files: list[Path] = []

        for path in assets_root.rglob('*'):
            rel_parts = path.relative_to(assets_root).parts
            if any(part.startswith('.') for part in rel_parts):
                continue
            if path.is_file() or path.is_symlink():
                if path.resolve() not in expected_files:
                    obsolete_files.append(path)

        for path in obsolete_files:
            if dry_run:
                if verbosity >= 1:
                    self.stdout.write(f'Would remove obsolete asset: {path}')
            else:
                if verbosity >= 1:
                    self.stdout.write(f'Removing obsolete asset: {path}')
                path.unlink()

        # Prune empty directories bottom-up
        if not dry_run:
            dirs = [p for p in assets_root.rglob('*') if p.is_dir()]
            # Sort by length of parts descending (deepest first)
            dirs.sort(key=lambda p: len(p.parts), reverse=True)
            for d in dirs:
                if d == assets_root or d.resolve() == resolved_root:
                    continue
                rel_parts = d.relative_to(assets_root).parts
                if any(part.startswith('.') for part in rel_parts):
                    continue
                # Check if directory is empty
                if d.exists() and not any(d.iterdir()):
                    try:
                        d.rmdir()
                        if verbosity >= 2:
                            self.stdout.write(f'Removed empty directory: {d}')
                    except OSError:
                        pass

        return obsolete_files

    def handle(self, *args, **options):
        clean = options.get('clean', False)
        dry_run = options.get('dry_run', False)
        verbosity = options.get('verbosity', 1)

        apps = django_apps.get_app_configs()
        assets_root = get_assets_root()
        expected_files: set[Path] = set()

        for app in apps:
            asset_path = None
            # read spec file. Prefer 'assets.json' and fallback to 'vendor.json'
            for spec_file in ['assets.json', 'vendor.json']:
                asset_path = Path(app.path) / 'static' / app.label / spec_file
                if asset_path.exists():
                    break
            else:
                continue

            with open(asset_path, 'r') as f:
                assets = json.load(f)

            app_files = self.process_assets(assets, assets_root)
            if app_files:
                expected_files.update(app_files)

        # Process assets from configured IconBackend and run post_collect hook
        backend = get_icon_backend()
        backend_assets = backend.get_assets()
        if backend_assets:
            backend_files = self.process_assets(backend_assets, assets_root)
            if backend_files:
                expected_files.update(backend_files)

        if clean:
            self.clean_obsolete_assets(
                assets_root,
                expected_files,
                dry_run=dry_run,
                verbosity=verbosity,
            )

        backend.post_collect(assets_root)

