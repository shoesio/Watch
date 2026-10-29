import hashlib
import io
from PIL import Image
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tmdb_logos import TMDB, normal, sync, atomic

class LogosTest(unittest.TestCase):
    def test_absent_token_never_connects(self):
        with tempfile.TemporaryDirectory() as root, patch('tmdb_logos.TMDB') as client:
            self.assertFalse(sync(root, [])['connected'])
            client.assert_not_called()

    def test_match_rejects_ambiguity_and_prefers_british(self):
        client = TMDB('read-token')
        results = [{'id':1,'name':'Taskmaster','origin_country':['US']}, {'id':2,'name':'Taskmaster','origin_country':['GB']}]
        with patch.object(client, 'get', side_effect=lambda route, **kw: {'results':results} if route.startswith('search/') else {'id':2,'name':'Taskmaster'}):
            self.assertEqual(client.match('Taskmaster Bleeped')['id'], 2)
            results.append({'id':3,'name':'Taskmaster','origin_country':['GB']})
            self.assertIsNone(client.match('Taskmaster'))

    def test_cache_and_private_file(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            atomic(root/'tmdb-token', b'read-token')
            self.assertEqual((root/'tmdb-token').stat().st_mode & 0o777, 0o600)
            programmes = [{'title':'QI XL'}, {'title':'BBC One','live':True}]
            with patch.object(TMDB,'match',return_value={'id':1,'name':'QI'}) as match, patch.object(TMDB,'logo',return_value=(b'png','/abc.png')):
                self.assertEqual(sync(root,programmes)['downloaded'],1)
                self.assertEqual(sync(root,programmes)['downloaded'],0)
                self.assertEqual(match.call_count,1)
            ident=hashlib.sha256(normal('QI XL').encode()).hexdigest()[:20]
            self.assertEqual((root/'show-logos'/(ident+'.png')).read_bytes(), b'png')

    def test_logo_trims_transparency_without_stretching(self):
        image=Image.new('RGBA',(200,100),(0,0,0,0))
        image.paste((255,255,255,255),(20,30,180,70))
        encoded=io.BytesIO(); image.save(encoded,'PNG')
        client=TMDB('read-token')
        with patch.object(client,'get',return_value={'logos':[{'file_path':'/abc.png','iso_639_1':'en','width':200}]}), patch('tmdb_logos.requests.get') as request:
            response=request.return_value.__enter__.return_value
            response.status_code=200
            response.iter_content.return_value=[encoded.getvalue()]
            data,path=client.logo(1)
        with Image.open(io.BytesIO(data)) as result:
            self.assertEqual(result.size,(160,40))
        self.assertNotIn('headers',request.call_args.kwargs)

    def test_errors_do_not_expose_credential(self):
        client=TMDB('a'*32)
        with patch.object(client.session,'get') as get:
            get.return_value.status_code=401
            with self.assertRaisesRegex(RuntimeError, r'^TMDB request failed \(HTTP 401\)\.$'):
                client.get('configuration')

if __name__ == '__main__': unittest.main()
