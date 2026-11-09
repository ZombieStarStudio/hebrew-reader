"""dsp.py against librosa itself. Needs librosa (the HebrewSpeaker venv has it); skipped when it is missing."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor"))
from zipvoice_onnx import dsp  # noqa: E402

try:
    import librosa
except ImportError:  # pragma: no cover
    librosa = None


@unittest.skipIf(librosa is None, "librosa not installed")
class Dsp(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        t = np.arange(24000 * 2) / 24000
        self.y = (0.3 * np.sin(2 * np.pi * 220 * t) * (t > 0.4) * (t < 1.5) + 0.01 * rng.standard_normal(t.size)).astype(np.float32)

    def test_mel(self):
        a = librosa.filters.mel(sr=24000, n_fft=1024, n_mels=100, norm=None, htk=True)
        np.testing.assert_allclose(dsp.mel_filters(24000, 1024, 100), a, atol=1e-6)

    def test_stft(self):
        a = librosa.stft(self.y, n_fft=1024, hop_length=256, center=True, window="hann")
        np.testing.assert_allclose(dsp.stft(self.y, 1024, 256), a, atol=1e-3)

    def test_istft(self):
        spec = librosa.stft(self.y, n_fft=1024, hop_length=256)
        a = librosa.istft(spec, hop_length=256, win_length=1024, window="hann", center=True)
        b = dsp.istft(spec, 256, 1024)
        self.assertEqual(a.shape, b.shape)
        np.testing.assert_allclose(b, a, atol=1e-5)

    def test_trim_split(self):
        _, a = librosa.effects.trim(self.y, top_db=30, ref=1.0, frame_length=512, hop_length=128)
        _, b = dsp.trim(self.y, top_db=30, frame_length=512, hop_length=128)
        self.assertEqual(tuple(int(x) for x in a), b)
        np.testing.assert_array_equal(librosa.effects.split(self.y, top_db=30, ref=1.0), dsp.split(self.y, top_db=30))

    def test_resample_length(self):
        a = librosa.resample(self.y, orig_sr=24000, target_sr=16000)
        b = dsp.resample(self.y, 24000, 16000)
        self.assertLessEqual(abs(len(a) - len(b)), 1)


if __name__ == "__main__":
    unittest.main()
