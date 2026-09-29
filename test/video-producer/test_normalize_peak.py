import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[2]/'crews/content-producer/skills/expert-video/tools/video-producer/scripts/normalize.py'
spec = importlib.util.spec_from_file_location('video_normalize', MODULE)
normalize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalize)


class PeakGuardTests(unittest.TestCase):
    def test_target_loudness_does_not_skip_hot_peak(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'in.mp4'
            dest = Path(tmp)/'out.mp4'
            source.write_bytes(b'fixture')
            measurement = {'input_i': '-14.0', 'input_tp': '-0.5', 'input_lra': '2',
                           'input_thresh': '-24', 'normalization_i': '0',
                           'output_i': '-14', 'output_tp': '-2', 'output_lra': '2'}
            with mock.patch.object(normalize, 'ffprobe_loudness', return_value=measurement), \
                    mock.patch.object(normalize, 'run', return_value=(0, '', '')) as run:
                result = normalize.normalize(str(source), str(dest), -14, -2, 11)
            self.assertFalse(result['skipped'])
            self.assertIn('TP=-2', run.call_args.args[0][run.call_args.args[0].index('-af')+1])


if __name__ == '__main__':
    unittest.main()
