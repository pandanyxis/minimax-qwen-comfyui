"""Resolve Civitai identifiers and verify downloads without logging credentials."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlparse

import requests
from download_progress import progress_line


def resolve(identifier, session):
    selected = None
    if identifier.startswith('version:'):
        version_id = int(identifier.split(':', 1)[1])
    else:
        if identifier.startswith('model:'):
            model_id = int(identifier.split(':', 1)[1])
            query = {}
        else:
            url = urlparse(identifier)
            if url.scheme != 'https' or url.hostname not in ('civitai.com', 'www.civitai.com'):
                raise ValueError('Use a Civitai HTTPS model URL or model:ID / version:ID')
            query = parse_qs(url.query)
            if 'token' in query:
                raise ValueError('Keep tokens in environment variables')
            model_id = int(url.path.strip('/').split('/')[1])
        selected = int(query['fileId'][0]) if 'fileId' in query else None
        if 'modelVersionId' in query:
            version_id = int(query['modelVersionId'][0])
        else:
            response = session.get(f'https://civitai.com/api/v1/models/{model_id}', timeout=60)
            response.raise_for_status()
            version_id = response.json()['modelVersions'][0]['id']
    response = session.get(f'https://civitai.com/api/v1/model-versions/{version_id}', timeout=60)
    response.raise_for_status()
    files = response.json()['files']
    if selected is not None:
        return next(f for f in files if f['id'] == selected)
    return next((f for f in files if f.get('primary')), files[0])


def download(identifier, output, filename=None):
    session = requests.Session()
    token = os.environ.get('CIVITAI_TOKEN') or os.environ.get('civitai_token')
    if token:
        session.headers['Authorization'] = 'Bearer ' + token
    print('[models] Resolving Civitai file metadata...', flush=True)
    item = resolve(identifier, session)
    name = filename or item['name']
    if Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Unsafe filename')
    target = Path(output) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = item.get('hashes', {}).get('SHA256', '').lower()
    if not digest:
        raise ValueError('Civitai file has no SHA256 metadata')
    print('[models] Preparing Civitai file: ' + name, flush=True)
    if target.is_file():
        print('[models] Checking existing SHA-256: ' + name, flush=True)
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == digest:
                print('[models] Already verified: ' + name, flush=True)
                return
    partial = target.with_name(target.name + '.part')
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {'Range': f'bytes={offset}-'} if offset else {}
    # Requests strips Authorization when following a redirect to a different host.
    with session.get(item['downloadUrl'], headers=headers, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        append = offset and response.status_code == 206
        if append and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
            raise ValueError('Unexpected download range')
        received = offset if append else 0
        remaining = int(response.headers.get('Content-Length', 0))
        total = remaining + received if remaining else 0
        content_range = response.headers.get('Content-Range', '')
        if append and '/' in content_range:
            size = content_range.rsplit('/', 1)[1]
            if size.isdigit():
                total = int(size)
        started = last_report = time.monotonic()
        initial = received
        print(f'[models] Downloading {name}; starting at {received / 1024**3:.2f} GiB', flush=True)
        with partial.open('ab' if append else 'wb') as stream:
            for chunk in response.iter_content(8 * 1024 * 1024):
                stream.write(chunk)
                received += len(chunk)
                now = time.monotonic()
                if now - last_report >= 15:
                    print(progress_line(name, received, total, now - started,
                                        received - initial), flush=True)
                    last_report = now
    print(progress_line(name, received, total, time.monotonic() - started,
                        received - initial), flush=True)
    print(f'[models] Download complete: {name}; checking SHA-256...', flush=True)
    with partial.open('rb') as stream:
        valid = hashlib.file_digest(stream, 'sha256').hexdigest() == digest
    if not valid:
        partial.unlink()
        raise ValueError('Downloaded file checksum mismatch')
    partial.replace(target)
    print('[models] Verified ' + target.name, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identifier', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--filename')
    args = parser.parse_args()
    try:
        download(args.identifier, args.output, args.filename)
    except Exception as error:
        # HTTP exceptions can include signed URLs: do not print their message.
        print('[models] Civitai download failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
