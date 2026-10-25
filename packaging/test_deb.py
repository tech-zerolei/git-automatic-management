#!/usr/bin/python3
"""Install/remove in a temporary dpkg root and launch at installed paths."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout[-4000:] + result.stderr[-4000:])
    return result.stdout


def check(package):
    package = Path(package).resolve()
    host_status_before = hashlib.sha256(Path('/var/lib/dpkg/status').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='planner-deb-smoke-') as temporary:
        base = Path(temporary)
        root = base / 'root'
        admin = root / 'var/lib/dpkg'
        (admin / 'info').mkdir(parents=True)
        # Real installed dependency versions, isolated records and no host dpkg writes.
        dependencies = ['python3', 'git', 'bubblewrap', 'zenity', 'xdg-utils']
        records = run(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${Architecture}\n', *dependencies])
        status = []
        for record in records.splitlines():
            name, version, arch = record.split('\t')
            status.append(f'Package: {name}\nStatus: install ok installed\nArchitecture: {arch}\nVersion: {version}\nDescription: Existing host dependency\n')
            (admin / 'info' / f'{name}.list').write_text('')
        (admin / 'status').write_text('\n'.join(status) + '\n')
        sandbox = ['/usr/bin/bwrap', '--ro-bind', '/', '/', '--bind', str(base), str(base),
                   '--unshare-net', '--unshare-pid', '--proc', '/proc', '--dev', '/dev',
                   '--uid', '0', '--gid', '0', '--']
        dpkg = ['/usr/bin/dpkg', '--root=' + str(root), '--log=' + str(base / 'dpkg.log')]
        run([*sandbox, *dpkg, '--install', str(package)])
        state = run(['dpkg-query', '--admindir=' + str(admin), '-W', '-f=${Status}', 'git-version-planner'])
        assert state == 'install ok installed', state
        assert (root / 'usr/bin/git-version-planner').stat().st_mode & 0o111
        run(['desktop-file-validate', str(root / 'usr/share/applications/git-version-planner.desktop')])
        assert not any((admin / 'info' / ('git-version-planner.' + suffix)).exists()
                       for suffix in ['preinst', 'postinst', 'prerm', 'postrm'])
        for name in ['semver-LICENSE.txt', 'LUCIDE-LICENSE', 'copyright']:
            assert (root / 'usr/share/doc/git-version-planner' / name).is_file()
        # /usr/share is replaced only inside this namespace. The command uses its
        # real absolute installed app path, rather than testing source code again.
        launch = ['/usr/bin/bwrap', '--ro-bind', '/', '/', '--bind', str(base), str(base),
                  '--tmpfs', '/usr/share', '--ro-bind', str(root / 'usr/share'), '/usr/share',
                  '--proc', '/proc', '--dev', '/dev', '--die-with-parent', '--',
                  str(root / 'usr/bin/git-version-planner'), '--no-browser']
        log = (base / 'launch.log').open('w+')
        process = subprocess.Popen(launch, stdout=log, stderr=log)
        try:
            url = ''
            for _ in range(100):
                log.flush(); log.seek(0)
                url = log.readline().strip()
                if url.startswith('http://'): break
                if process.poll() is not None: raise RuntimeError(log.read())
                time.sleep(0.05)
            assert url.startswith('http://'), 'Installed launcher did not become ready'
            parts = urlsplit(url)
            origin = parts.scheme + '://' + parts.netloc
            with urllib.request.urlopen(origin, timeout=5) as response:
                assert response.status == 200
            def api(action, data):
                request = urllib.request.Request(origin + '/api/' + action,
                    data=json.dumps(data).encode(), headers={'Content-Type': 'application/json',
                    'Origin': origin, 'X-Planner-Token': parts.fragment})
                try:
                    with urllib.request.urlopen(request, timeout=10) as response:
                        return json.load(response)
                except urllib.error.HTTPError as error:
                    raise RuntimeError(error.read().decode()) from error
            assert api('state', {}) == {'snapshot': None, 'plan': None}
            assert api('quit', {})['closed']
            assert process.wait(timeout=10) == 0
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=10)
            log.close()
        # The host denies nested user namespaces. Test the installed-path
        # launcher above without bypassing that policy, then test package payload
        # as the normal user so the app uses only its usual single sandbox.
        process = subprocess.Popen(
            ['/usr/bin/python3', '-B', str(root / 'usr/share/git-version-planner/local_app/server.py'), '--no-browser'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            url = process.stdout.readline().strip()
            assert url.startswith('http://'), 'Package payload did not become ready'
            parts = urlsplit(url)
            origin = parts.scheme + '://' + parts.netloc
            repo = base / 'synthetic'; repo.mkdir()
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(base), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
            def git(*args):
                run(['/usr/bin/git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args], cwd=repo, env=env)
            git('init', '--initial-branch=main')
            git('commit', '--allow-empty', '-m', 'feat: initial')
            git('tag', 'v1.0.0')
            git('commit', '--allow-empty', '-m', 'fix: packaged build')
            api('open', {'path': str(repo)})
            plan = api('plan', {'confirmed': True, 'baseline': 'refs/tags/v1.0.0'})['plan']
            assert plan['candidateVersion'] == '1.0.1'
            api('export', {'format': 'json', 'path': str(base / 'report.json'), 'planFingerprint': plan['planFingerprint']})
            assert json.loads((base / 'report.json').read_text())['candidateVersion'] == '1.0.1'
            assert api('quit', {})['closed']
            assert process.wait(timeout=10) == 0
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=10)
            process.stdout.close(); process.stderr.close()
        run([*sandbox, *dpkg, '--remove', 'git-version-planner'])
        assert not (root / 'usr/bin/git-version-planner').exists()
        assert not (root / 'usr/share/git-version-planner/local_app/server.py').exists()
        assert not (root / 'usr/share/applications/git-version-planner.desktop').exists()
    assert hashlib.sha256(Path('/var/lib/dpkg/status').read_bytes()).hexdigest() == host_status_before
    return {'status': 'PASS', 'checks': ['isolated dpkg install with real dependency versions',
            'installed package state', 'desktop entry validation', 'bundled licenses', 'no maintainer scripts',
            'installed-path launcher and HTTP 200', 'extracted payload synthetic Git plan 1.0.1', 'packaged JSON export',
            'authenticated exit', 'isolated dpkg remove', 'host dpkg status unchanged'],
            'systemInstall': False,
            'limitations': ['Host denies nested user namespaces: repository plan/export tested as normal-user package payload outside installed-path namespace'],
            'scope': 'Isolated dpkg root and installed-path startup plus extracted-payload functional test; not a privileged host install'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('--evidence')
    args = parser.parse_args()
    result = check(args.package)
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.evidence: Path(args.evidence).write_text(content)
    print(content)
