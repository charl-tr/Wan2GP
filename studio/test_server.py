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
        for name in ('jobs','media','uploads','trash'):
            (self.data / name).mkdir()
        self.patch = patch.object(server, 'DATA', self.data)
        self.patch.start()
        self.bridge_patch=patch.object(server,'bridge',server.BridgeAuth(self.data/'sessions.json'))
        self.bridge_patch.start()
        self.client = TestClient(server.app, base_url='http://127.0.0.1')
        server.active.clear()
    def tearDown(self):
        server.active.clear()
        self.patch.stop()
        self.bridge_patch.stop()
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
        self.assertEqual(s['video_prompt_type'], 'I')
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

    def test_pairing_is_origin_bound_and_revocable(self):
        origin='https://studio.example'
        res=self.client.post('/api/local/pair',json={'origin':origin})
        self.assertEqual(res.status_code,200)
        token=res.json()['token']
        headers={'Origin':origin,'Authorization':'Bearer '+token}
        self.assertEqual(self.client.get('/api/jobs',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/jobs',headers={'Origin':origin}).status_code,401)
        self.assertEqual(self.client.get('/api/jobs',headers={**headers,'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/local/pair',json={'origin':'https://other.example'},headers=headers).status_code,403)
        self.assertEqual(self.client.delete('/api/local/connections',headers=headers).status_code,403)
        self.assertNotIn(token,(self.data/'sessions.json').read_text())
        self.client.delete('/api/local/connections')
        self.assertEqual(self.client.get('/api/jobs',headers=headers).status_code,403)

    def test_pairing_validation_and_preflight(self):
        for origin in ['http://example.com','https://example.com/path','https://user:pass@example.com','https://example.com?x=1','https://example.com:bad']:
            self.assertEqual(self.client.post('/api/local/pair',json={'origin':origin}).status_code,422)
        origin='https://studio.example'
        self.client.post('/api/local/pair',json={'origin':origin})
        res=self.client.options('/api/jobs',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Private-Network':'true'})
        self.assertEqual(res.status_code,200)
        self.assertEqual(res.headers['access-control-allow-origin'],origin)
        self.assertEqual(res.headers['access-control-allow-private-network'],'true')
        self.assertEqual(self.client.get('/api/jobs',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_expired_pairing_fails(self):
        with patch('studio.bridge.time.time',return_value=1):
            token=server.bridge.approve('https://studio.example')
        self.assertFalse(server.bridge.authorized('https://studio.example',token))

    def test_idempotent_submission_and_archive(self):
        original_start=server.threading.Thread.start
        def start_if_not_worker(thread):
            if thread._target is not server.run_job:
                return original_start(thread)
        with patch.object(server.threading.Thread,'start',start_if_not_worker):
            headers={'Idempotency-Key':'same-intent'}
            first=self.client.post('/api/jobs',json={'prompt':'hat'},headers=headers)
            second=self.client.post('/api/jobs',json={'prompt':'hat'},headers=headers)
            self.assertEqual(first.status_code,202)
            self.assertEqual(first.json(),second.json())
            self.assertEqual(self.client.post('/api/jobs',json={'prompt':'different'},headers=headers).status_code,409)
            key=first.json()['id']
            self.assertEqual(self.client.delete('/api/jobs/'+key).status_code,409)
            server.active.clear()
            self.assertEqual(self.client.delete('/api/jobs/'+key).status_code,200)
            self.assertTrue((self.data/'trash'/key/'request.json').is_file())
            self.assertEqual(self.client.get('/api/jobs').json(),[])

    def test_history_reports_actual_image_dimensions(self):
        folder=self.data/'jobs'/'one';folder.mkdir()
        Image.new('RGB',(576,576),'green').save(self.data/'media'/'one.png')
        (folder/'request.json').write_text(json.dumps({'created':0,'request':{'prompt':'hat'},'settings':{'resolution':'768x432'}}))
        (folder/'status.json').write_text(json.dumps({'state':'completed','files':[{'kind':'image','url':'/media/one.png'}]}))
        file=self.client.get('/api/jobs').json()[0]['files'][0]
        self.assertEqual((file['width'],file['height']),(576,576))

    def test_unknown_fields_rejected(self):
        self.assertEqual(self.client.post('/api/jobs',json={'prompt':'hat','command':'echo bad'}).status_code,422)

if __name__=='__main__':
    unittest.main()
