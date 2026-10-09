"""API boundary checks; no model downloads and no real generations."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
from studio import server

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        for name in ('jobs','media','uploads'):
            (self.data / name).mkdir()
        self.patch = patch.object(server, 'DATA', self.data)
        self.patch.start()
        self.client = TestClient(server.app, base_url='http://127.0.0.1')
        server.active.clear()
    def tearDown(self):
        server.active.clear()
        self.patch.stop()
        self.tmp.cleanup()
    def test_lazy_ignores_advanced_values(self):
        s = server.settings_for(server.GenerationRequest(prompt='Hat', model='unknown', steps=50, seed=99))
        self.assertEqual((s['model_type'],s['num_inference_steps'],s['seed']),('flux2_klein_4b',4,-1))
    def test_custom_preserves_values(self):
        s=server.settings_for(server.GenerationRequest(prompt='Hat',mode='custom',model='z_image',steps=9,seed=42,aspect='9:16'))
        self.assertEqual((s['model_type'],s['seed'],s['resolution']),('z_image',42,'432x768'))
    def test_rejects_invalid_model_and_empty_prompt(self):
        for payload in ({'prompt':'  '},{'prompt':'hat','mode':'custom','model':'../../secret'},{'prompt':'hat','steps':0},{'prompt':'hat','kind':'video','mode':'custom','model':'flux2_klein_4b'}):
            self.assertEqual(self.client.post('/api/jobs',json=payload).status_code,422)
    def test_no_parallel_generations(self):
        server.active['one']=None
        self.assertEqual(self.client.post('/api/jobs',json={'prompt':'hat'}).status_code,409)
    def test_cross_origin_and_untrusted_host_rejected(self):
        self.assertEqual(self.client.post('/api/jobs',json={'prompt':'hat'},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/config',headers={'Host':'evil.example'}).status_code,400)
    def test_reference_upload_and_invalid_file(self):
        im=io.BytesIO();Image.new('RGB',(20,20)).save(im,format='PNG')
        res=self.client.post('/api/uploads',files={'file':('ref.png',im.getvalue(),'image/png')})
        self.assertEqual(res.status_code,200)
        key=res.json()['id']
        s=server.settings_for(server.GenerationRequest(prompt='hat',reference=key))
        self.assertTrue(Path(s['image_refs'][0]).is_file())
        self.assertEqual(self.client.post('/api/uploads',files={'file':('bad.png',b'not an image','image/png')}).status_code,422)
        self.assertEqual(self.client.post('/api/jobs',json={'prompt':'hat','reference':'../../secret'}).status_code,422)
    def test_interrupted_history_is_not_stuck_running(self):
        folder=self.data/'jobs'/'one';folder.mkdir()
        (folder/'request.json').write_text(json.dumps({'created':0,'request':{'prompt':'hat'},'settings':{}}))
        (folder/'status.json').write_text(json.dumps({'state':'running'}))
        self.assertEqual(self.client.get('/api/jobs').json()[0]['state'],'failed')
    def test_rejects_black_output_but_accepts_color(self):
        from studio.worker import validate_image
        path=self.data/'test.png'
        Image.new('RGB',(16,16),'black').save(path)
        with self.assertRaises(RuntimeError):
            validate_image(path)
        Image.new('RGB',(16,16),'red').save(path)
        validate_image(path)
    def test_cancel_before_worker_start(self):
        folder=self.data/'jobs'/'one';folder.mkdir()
        server.active['one']=None
        self.assertEqual(self.client.post('/api/jobs/one/cancel').status_code,200)
        server.run_job('one',folder)
        self.assertEqual(json.loads((folder/'status.json').read_text())['state'],'cancelled')
        self.assertNotIn('one',server.active)

if __name__=='__main__':
    unittest.main()
