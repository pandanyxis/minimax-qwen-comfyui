import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
    'downloader', Path(__file__).resolve().parents[1] / 'download-civitai.py')
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


class DownloaderTests(unittest.TestCase):
    def test_exact_file_is_selected_instead_of_primary(self):
        session = MagicMock()
        session.get.return_value.json.return_value = {'files': [
            {'id': 10, 'primary': True}, {'id': 20, 'primary': False}]}
        result = downloader.resolve(
            'https://civitai.com/models/1?modelVersionId=2&fileId=20', session)
        self.assertEqual(result['id'], 20)
        session.get.assert_called_once_with(
            'https://civitai.com/api/v1/model-versions/2', timeout=60)

    def test_other_hosts_and_tokens_in_urls_are_rejected(self):
        for url in ('https://example.com/models/1',
                    'https://civitai.com/models/1?token=secret'):
            with self.assertRaises(ValueError):
                downloader.resolve(url, MagicMock())

    def test_resumed_download_and_corrupt_data(self):
        content = b'complete model data'
        item = {'name': 'model.safetensors',
                'hashes': {'SHA256': hashlib.sha256(content).hexdigest()},
                'downloadUrl': 'https://civitai.com/api/download/models/1'}
        session = MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.status_code = 206
        response.headers = {'Content-Range': 'bytes 5-18/19'}
        response.iter_content.return_value = [content[5:]]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / item['name']
            partial = target.with_name(target.name + '.part')
            partial.write_bytes(content[:5])
            with patch.object(downloader.requests, 'Session', return_value=session), \
                    patch.object(downloader, 'resolve', return_value=item):
                downloader.download('version:1', directory)
                self.assertEqual(target.read_bytes(), content)
                self.assertFalse(partial.exists())
                target.unlink()
                response.status_code = 200
                response.iter_content.return_value = [b'corrupt']
                with self.assertRaises(ValueError):
                    downloader.download('version:1', directory)
                self.assertFalse(target.exists())
                self.assertFalse(partial.exists())


if __name__ == '__main__':
    unittest.main()
