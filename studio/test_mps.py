"""Regression checks for the Mac memory fences, isolated from API tests."""
import subprocess
import sys
import unittest

@unittest.skipUnless(sys.platform == 'darwin', 'Apple Silicon compatibility')
class MpsFenceTests(unittest.TestCase):
    def test_fences_and_idempotent_installation(self):
        script = '''
import torch
from unittest.mock import patch
from shared.mps.device_patch import apply_mps_patch
first_to = torch.Tensor.to
first_seed = torch.manual_seed
apply_mps_patch()
assert torch.Tensor.to is first_to
assert torch.manual_seed is first_seed
with patch.object(torch.mps, 'synchronize') as sync:
    event = torch.cuda.Event()
    event.record()
    event.synchronize()
    stream = torch.cuda.Stream()
    stream.synchronize()
    stream.wait_stream(stream)
    stream.wait_event(event)
    torch.cuda.current_stream().wait_stream(stream)
    torch.cuda.current_stream().wait_event(event)
    assert sync.call_count == 7, sync.call_count
if torch.backends.mps.is_available():
    from models.flux.modules.autoencoder_flux2 import AutoencoderKLFlux2
    model = AutoencoderKLFlux2.__new__(AutoencoderKLFlux2)
    torch.nn.Module.__init__(model)
    model.bn_eps = 1e-4
    model.bn = torch.nn.BatchNorm2d(128, eps=model.bn_eps, affine=False).eval()
    x = torch.randn(1, 128, 4, 4).to(torch.bfloat16)
    model.bn.running_mean.copy_(torch.randn(128))
    model.bn.running_var.copy_(torch.rand(128) + 0.1)
    expected = model.bn(x.float()).to(torch.bfloat16)
    model.bn.to('mps')
    actual = model.normalize(x.to('mps')).cpu()
    assert torch.isfinite(actual).all()
    torch.testing.assert_close(actual, expected, rtol=0.01, atol=0.02)
print('MPS fences, idempotence and BF16 normalization verified')
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

if __name__ == '__main__':
    unittest.main()
