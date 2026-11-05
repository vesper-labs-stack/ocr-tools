"""Include license notices already shipped in dependency wheels."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

out = Path(__file__).resolve().parents[1] / 'third_party'
out.mkdir(exist_ok=True)
lines = ['Bundled third-party components', '']
for dist in sorted(distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = dist.metadata['Name']
    if name.lower() in {'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'pefile', 'setuptools', 'pywin32-ctypes', 'packaging'}:
        continue
    lines.append(f'{name} {dist.version}')
    for file in dist.files or []:
        if any(word in file.name.lower() for word in ('license', 'copying', 'copyright', 'notice')):
            source = Path(dist.locate_file(file))
            if source.is_file():
                target = out / name / Path(*[part for part in file.parts if part != '..'])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
(out / 'COMPONENTS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
