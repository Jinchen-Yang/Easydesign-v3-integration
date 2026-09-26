#!/usr/bin/env python3
"""Package the complete committed frontend, build and untouched reviewer input pack."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

project = Path(__file__).resolve().parents[1]
input_pack = project.parent / 'input-pack'
output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project.parent.parent / 'deliverables/EasyDesign-Workbench-full-review-20260913.zip'
prefix = output.stem

def git(*args):
    return subprocess.check_output(['git', '-C', str(project), *args], text=True).strip()

if git('status', '--porcelain'):
    raise SystemExit('Commit all frontend changes before creating the review archive.')
if not (project / 'dist/index.html').is_file() or not input_pack.is_dir():
    raise SystemExit('Build dist and retain the complete sibling input-pack before packaging.')
output.parent.mkdir(parents=True, exist_ok=True)
commit = git('rev-parse', 'HEAD')
branch = git('branch', '--show-current')
tracked = git('ls-files', '-z').split('\0')
entries = {f'ui-workbench/{name}': project / name for name in tracked if name}
entries.update({f'ui-workbench/{p.relative_to(project)}': p for p in (project / 'dist').rglob('*') if p.is_file()})
entries.update({f'input-pack/{p.relative_to(input_pack)}': p for p in input_pack.rglob('*') if p.is_file()})
with tempfile.TemporaryDirectory(prefix='easydesign-review-bundle-') as temp:
    bundle = Path(temp) / 'ui-workbench.git.bundle'
    subprocess.run(['git', '-C', str(project), 'bundle', 'create', str(bundle), '--all'], check=True)
    subprocess.run(['git', '-C', str(project), 'bundle', 'verify', str(bundle)], check=True, capture_output=True)
    entries[bundle.name] = bundle
    note = Path(temp) / 'REVIEW_PACKAGE.md'
    note.write_text(f'''# Complete EasyDesign Workbench review package

Source commit: `{commit}`

Branch: `{branch}`

- `ui-workbench/`: complete frontend source, lockfile, tests, docs, screenshots, validation logs, structure data and production build.
- `input-pack/`: complete original supplied specification/reference pack, unchanged and separate from the runnable app.
- `ui-workbench.git.bundle`: self-contained Git history. To restore a Git checkout: `git clone ui-workbench.git.bundle editable-workbench`.
- `PACKAGE_MANIFEST.json`: SHA-256 and size for every other archive file.

Start with `ui-workbench/README.md`, then `ui-workbench/docs/REPORT.md` and `ui-workbench/docs/ACCEPTANCE.md`.

To run: `cd ui-workbench`, `pnpm install --frozen-lockfile`, `pnpm dev` (Node 22+, pnpm 11.19.0). Open http://127.0.0.1:13180/.

This is the full standalone frontend repository, not a partial patch or a scientific backend snapshot. No dependencies on an unshipped EasyDesign checkout exist. Reinstallable node_modules, private environment files, local Git configuration, browser caches and ephemeral test output are excluded. The complete source history is preserved by the bundle. Input reference screenshots are supplied only for collaborator review and are never loaded by the application.
''')
    entries[note.name] = note
    manifest = {'version': 1, 'commit': commit, 'branch': branch, 'file_count_excluding_manifest': len(entries), 'files': []}
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(entries.items()):
            data = path.read_bytes()
            manifest['files'].append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            archive.writestr(f'{prefix}/{name}', data)
        archive.writestr(f'{prefix}/PACKAGE_MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for record in manifest['files']:
            data = archive.read(f"{prefix}/{record['path']}")
            assert len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256']
sha = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix('.zip.sha256').write_text(f'{sha}  {output.name}\n')
print(json.dumps({'archive': str(output), 'bytes': output.stat().st_size, 'files': len(entries) + 1, 'sha256': sha, 'commit': commit, 'verified': True}, indent=2))
