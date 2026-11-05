"""Run the single-file EXE outside the project with Python removed from PATH."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from generate_sample import generate

root = Path(__file__).resolve().parents[1]
portable = root / 'qa-output' / '独立运行验证'
portable.mkdir(parents=True, exist_ok=True)
exe = portable / 'ScreenshotOCR.exe'
shutil.copy2(root / 'dist' / 'ScreenshotOCR.exe', exe)
sample = generate(root / 'qa-output' / 'screenshot-sample.png')
second = generate(root / 'qa-output' / 'second-sample.png', second=True)
env = os.environ.copy()
for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_QPA_PLATFORM'):
    env.pop(key, None)
windows = Path(os.environ.get('SYSTEMROOT', 'C:/Windows'))
env['PATH'] = str(windows / 'System32')
output = root / 'qa-output' / 'packaged-result.json'
output.unlink(missing_ok=True)
started = time.perf_counter()
result = subprocess.run([str(exe), str(sample), str(second), '--diagnostic-output', str(output)], cwd=portable, env=env, timeout=50, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
seconds = round(time.perf_counter() - started, 2)
print('exit_code:', result.returncode)
print('launch_and_ocr_seconds:', seconds)
print('exe_size_mb:', round(exe.stat().st_size / 1024 / 1024, 1))
if result.stderr:
    print(result.stderr.decode(errors='replace'))
assert result.returncode == 0, 'Frozen executable failed'
report = json.loads(output.read_text(encoding='utf-8'))
print(json.dumps(report, ensure_ascii=False, indent=2))
assert not report['error']
assert report['clipboard_matches']
assert report['current_clipboard_matches']
assert len(report['items']) == 2
assert all(item['state'] == '已完成' for item in report['items'])
assert '67890' in report['items'][1]['text']
assert report['all_text'] == '\n\n'.join(item['text'] for item in report['items'])
for expected in ('本地截图文字识别', 'Hello', '12345', '2026', '128.50'):
    assert expected in report['text'], expected
(root / 'qa-output' / 'portable-verification.json').write_text(json.dumps({'exit_code': result.returncode, 'seconds': seconds, 'bytes': exe.stat().st_size, 'isolated_directory': str(portable), 'python_in_path': False}, ensure_ascii=False, indent=2), encoding='utf-8')
