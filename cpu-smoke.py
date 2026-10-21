"""Prove ComfyUI starts and exposes every backend class used in our workflows."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request

process = subprocess.Popen([
    '/opt/venv/bin/python', '/ComfyUI/main.py', '--cpu',
    '--listen', '127.0.0.1', '--port', '8188', '--disable-auto-launch',
], cwd='/ComfyUI')
try:
    deadline = time.monotonic() + 180
    while True:
        if process.poll() is not None:
            raise RuntimeError('ComfyUI exited during CPU startup')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8188/object_info', timeout=5) as response:
                classes = json.load(response)
            break
        except OSError:
            if time.monotonic() > deadline:
                raise RuntimeError('ComfyUI startup timed out')
            time.sleep(2)
    required = set()
    for path in Path('/opt/combined').glob('workflow-*.json'):
        required.update(n['type'] for n in json.loads(path.read_text())['nodes'])
    missing = required - set(classes) - {'Note', 'MarkdownNote'}
    if missing:
        raise RuntimeError('Workflow classes unavailable: ' + ', '.join(sorted(missing)))
    print('ComfyUI CPU startup and all personal workflow classes passed.', flush=True)
finally:
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
