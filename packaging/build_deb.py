#!/usr/bin/python3
"""Build the local edition without sudo, downloads or maintainer scripts."""

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'git-version-planner'
VERSION = '0.1.0-1'


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'{PACKAGE}_{VERSION}_all.deb'
    if destination.exists():
        raise SystemExit('目标包已存在；请使用新的输出目录，避免覆盖已发布文件。')
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH') or subprocess.check_output(
        ['git', '-C', str(ROOT), 'log', '-1', '--format=%ct'], text=True).strip())
    with tempfile.TemporaryDirectory(prefix='git-planner-deb-') as temporary:
        stage = Path(temporary) / 'root'
        app = stage / 'usr/share' / PACKAGE
        docs = stage / 'usr/share/doc' / PACKAGE
        controls = stage / 'DEBIAN'
        controls.mkdir(parents=True)
        docs.mkdir(parents=True)
        app.mkdir(parents=True)
        shutil.copytree(ROOT / 'local_app', app / 'local_app',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        # Source-only per-user installer is not used by the system package.
        (app / 'local_app/install_launcher.py').unlink()
        shutil.copyfile(ROOT / 'start.sh', app / 'start.sh')
        files = {
            'packaging/debian/control': controls / 'control',
            'packaging/debian/git-version-planner': stage / 'usr/bin' / PACKAGE,
            'packaging/debian/git-version-planner.desktop': stage / 'usr/share/applications' / f'{PACKAGE}.desktop',
            'local_app/static/icon.svg': stage / 'usr/share/icons/hicolor/scalable/apps' / f'{PACKAGE}.svg',
            'packaging/debian/copyright': docs / 'copyright',
            'local_app/vendor/semver-3.0.4.dist-info/LICENSE.txt': docs / 'semver-LICENSE.txt',
            'local_app/static/vendor/LUCIDE-LICENSE': docs / 'LUCIDE-LICENSE',
            'README.md': docs / 'README.md',
            'SECURITY.md': docs / 'SECURITY.md',
            'docs/USER-GUIDE.md': docs / 'USER-GUIDE.md',
            'docs/FEATURES.md': docs / 'FEATURES.md',
            'docs/DEB.md': docs / 'DEB.md',
        }
        for source, target in files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, target)
        with (docs / 'changelog.gz').open('wb') as stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=epoch) as archive:
                archive.write((ROOT / 'CHANGELOG.md').read_bytes())
        checksums = []
        for file in sorted(stage.rglob('*')):
            if file.is_symlink():
                raise SystemExit('拒绝将符号链接加入包。')
            if file.is_file() and controls not in file.parents:
                checksums.append(hashlib.md5(file.read_bytes()).hexdigest() + '  ' + str(file.relative_to(stage)))
        (controls / 'md5sums').write_text('\n'.join(checksums) + '\n')
        size = sum(file.stat().st_size for file in stage.rglob('*') if file.is_file() and controls not in file.parents)
        with (controls / 'control').open('a') as stream:
            stream.write(f'Installed-Size: {(size + 1023) // 1024}\n')
        for path in stage.rglob('*'):
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.utime(path, (epoch, epoch))
        for path in [app / 'start.sh', stage / 'usr/bin' / PACKAGE]:
            path.chmod(0o755)
        os.utime(stage, (epoch, epoch))
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', str(stage), str(destination)],
                       env={**os.environ, 'SOURCE_DATE_EPOCH': str(epoch)}, check=True)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    (output / 'SHA256SUMS').write_text(checksum + '  ' + destination.name + '\n')
    print(destination)
    print('SHA256: ' + checksum)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'dist'))
    build(parser.parse_args().output)
