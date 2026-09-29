"""Run: python3 -m unittest discover -s test/deck-talk -p 'test_*.py' -v"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'crews/content-producer/skills/expert-video/tools'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deck = load('deck', TOOLS / 'deck-render/scripts/deck-render.py')
pip = load('pip_compose', TOOLS / 'video-producer/scripts/pip-compose.py')
liveportrait = load('liveportrait', TOOLS / 'liveportrait/scripts/liveportrait.py')
from font_policy import font_available, font_css, font_family


class DeckTests(unittest.TestCase):
    def test_platform_font_policy(self):
        self.assertEqual(font_family('linux'), 'Noto Sans CJK SC')
        self.assertEqual(font_family('win32'), 'Microsoft YaHei')
        self.assertIn('Noto Sans CJK SC Bold', font_css('linux'))
        self.assertIn('Microsoft YaHei Light', font_css('win32'))
        with tempfile.TemporaryDirectory() as tmp:
            fonts = Path(tmp) / 'Fonts'
            fonts.mkdir()
            self.assertFalse(font_available('win32', Path(tmp)))
            for name in ('msyhl.ttc', 'msyh.ttc', 'msyhbd.ttc'):
                (fonts / name).touch()
            self.assertTrue(font_available('win32', Path(tmp)))

    @unittest.skipUnless(os.environ.get('DECK_RENDER_BROWSER_TEST') == '1', 'opt-in Chrome test')
    def test_dark_image_page_in_browser(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp/'source.png'
            Image.new('RGB', (400, 300), '#376e9c').save(source)
            spec = tmp/'spec.json'
            spec.write_text(json.dumps({'theme': 'dark', 'pip': 'top-left', 'scenes': [
                {'type': 'image', 'title': '中文图片测试', 'duration': 3, 'image': str(source), 'source': '测试夹具', 'points': ['图片与文字']}
            ]}, ensure_ascii=False))
            project = tmp/'project'
            deck.scaffold(spec, project)
            self.assertEqual((project/'assets/scene-01.png').read_bytes(), source.read_bytes())
            result = subprocess.run([str(TOOLS/'deck-render/deck-render.sh'), 'preview', str(project), '--output', str(tmp/'preview')], text=True, capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((tmp/'preview/contact-sheet.jpg').is_file())

    def test_workflow_scripts_keep_baseline_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project/'brief.md').write_text('- workflow：deck-talk\n')
            voiceover = '锁定的甲方口播，不能为了版式改变事实。\n'
            (project/'voiceover.md').write_text(voiceover)
            wrapper = TOOLS/'video-producer/video-producer.sh'
            for command in ('script-write', 'script-self-eval'):
                result = subprocess.run([str(wrapper), command, str(project)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(voiceover, (project/'script/deck-script.md').read_text())
            self.assertFalse((project/'script/script.md').exists())
            evaluation = json.loads((project/'script/self-eval.json').read_text())
            self.assertEqual(evaluation['workflow'], 'deck-talk')
            self.assertIn('page_timing', [x['key'] for x in evaluation['dims']])
            stages = (
                ('storyboard-build', 'storyboard/storyboard.json'),
                ('shot-decompose', 'storyboard/shot_decompose.json'),
                ('character-register', 'characters/registry.json'),
                ('slot-plan', 'slots/slot-plan.json'),
                ('asset-resolve', 'slots/asset-resolve.json'),
                ('slideshow-risk', 'slots/slideshow-risk.json'),
                ('delivery-promise-lock', 'slots/delivery-promise.json'),
                ('render-shot', 'render/deck-render-plan.json'),
            )
            for number, (command, artifact) in enumerate(stages, start=3):
                result = subprocess.run([str(wrapper), command, str(project)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'[done] Stage {number} deck-talk', result.stdout)
                payload = json.loads((project/artifact).read_text())
                self.assertEqual(payload['stage'], number)
                self.assertEqual(payload['workflow'], 'deck-talk')
            self.assertEqual(json.loads((project/'characters/registry.json').read_text())['presenter_source'], None)
            result = subprocess.run([str(wrapper), 'mix-audio', str(project)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            audio_plan = json.loads((project/'audio/deck-audio-plan.json').read_text())
            self.assertEqual(audio_plan['stage'], 11)
            self.assertFalse((project/'audio/subtitles.srt').exists())

            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'color=c=blue:s=320x180:r=12:d=1', '-c:v', 'libx264',
                            '-threads', '1', str(project/'video.mp4')], check=True)
            result = subprocess.run([str(wrapper), 'motion-audit', str(project)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            audit = json.loads((project/'review/deck-motion-audit.json').read_text())
            self.assertEqual(audit['workflow'], 'deck-talk')
            self.assertNotIn('motion_led', audit)

    def test_removed_narration_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project/'brief.md').write_text('- workflow：narration-video\n')
            result = subprocess.run([str(TOOLS/'video-producer/video-producer.sh'), 'script-write', str(project)],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('narration-video 已移除', result.stderr + result.stdout)
            self.assertFalse((project/'script/script.md').exists())

    def test_untyped_fullscreen_voiceover_keeps_locked_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project/'brief.md').write_text('- form：人物全屏口播\n')
            original = '甲方口播逐字保留。\n'
            (project/'voiceover.md').write_text(original)
            wrapper = TOOLS/'video-producer/video-producer.sh'
            for command in ('script-write', 'script-self-eval'):
                result = subprocess.run([str(wrapper), command, str(project)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((project/'script/script.md').read_text(), original)
            evaluation = json.loads((project/'script/self-eval.json').read_text())
            self.assertIsNone(evaluation['workflow'])
            self.assertIn('verbatim', [item['key'] for item in evaluation['dims']])

    def test_deck_stage_requires_previous_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project/'brief.md').write_text('- workflow：deck-talk\n')
            result = subprocess.run([str(TOOLS/'video-producer/video-producer.sh'), 'shot-decompose', str(project)],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Stage 4 前置缺失', result.stderr + result.stdout)
            self.assertFalse((project/'storyboard/shot_decompose.json').exists())

    def test_audio_broll_brief_gets_segment_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project/'brief.md').write_text(
                '- workflow：deck-talk\n- presenter_source：audio\n- visual_source：broll\n'
                '- audio_origin：recorded\n- audio：/tmp/user-voice.wav\n', encoding='utf-8')
            result = subprocess.run([str(TOOLS/'video-producer/video-producer.sh'), 'script-write', str(project)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            script = (project/'script/deck-script.md').read_text()
            self.assertIn('## 第 1 段', script)
            self.assertIn('presenter_source: audio', script)
            self.assertIn('audio: /tmp/user-voice.wav', script)
            self.assertIn('素材来源', script)
            result = subprocess.run([str(TOOLS/'video-producer/video-producer.sh'), 'script-self-eval', str(project)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            evaluation = json.loads((project/'script/self-eval.json').read_text())
            self.assertIn('segment_timing', [item['key'] for item in evaluation['dims']])
            self.assertNotIn('page_timing', [item['key'] for item in evaluation['dims']])

    def test_invalid_chart_data_and_duration(self):
        for value in (float('nan'), float('inf'), -1, 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                deck.validate_spec({'scenes': [{'title': 'test', 'duration': 5, 'type': 'chart', 'source': 'fixture',
                                               'caption': 'fixture', 'data': [{'label': 'a', 'value': value}]}]})
        with self.assertRaisesRegex(ValueError, 'caption'):
            deck.validate_spec({'scenes': [{'title': 'test', 'duration': 5, 'type': 'chart',
                                            'source': 'internal record', 'data': [{'label': 'a', 'value': 1}]}]})
        with self.assertRaises(ValueError):
            deck.validate_spec({'scenes': [{'title': 'test', 'duration': 1}]})

    def test_scaffold_timeline_escape_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec = tmp / 'spec.json'
            spec.write_text(json.dumps({'scenes': [{'title': '<script>bad</script>', 'duration': 3}, {'title': '中文第二页', 'duration': 7}]}))
            project = tmp / 'project'
            deck.scaffold(spec, project)
            self.assertEqual(deck.metadata(project)['duration'], 10)
            self.assertIn('data-start="3"', (project / 'index.html').read_text())
            scene = (project / 'compositions/scene-01.html').read_text()
            self.assertIn('&lt;script&gt;', scene)
            self.assertIn('@font-face', scene)
            with self.assertRaises(ValueError):
                deck.scaffold(spec, project)

    def test_portrait_scaffold_uses_native_canvas_and_hides_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec = tmp/'spec.json'
            spec.write_text(json.dumps({'width': 1080, 'height': 1920, 'pip': 'bottom-right',
                                        'scenes': [{'title': '竖屏中文标题', 'duration': 5,
                                                    'source': '内部制作备注', 'caption': '观众可见图注'}]}, ensure_ascii=False))
            project = tmp/'project'
            deck.scaffold(spec, project)
            scene = (project/'compositions/scene-01.html').read_text()
            self.assertIn('width:1080px; height:1920px', scene)
            self.assertNotIn('transform:scale(', scene)
            self.assertIn('观众可见图注', scene)
            self.assertNotIn('内部制作备注', scene)
            self.assertIn('内部制作备注', (project/'deck-spec.json').read_text())
            scene_path = project/'compositions/scene-01.html'
            scene_path.write_text(scene.replace('background:#f7f5f0', 'transform:scale(0.5625,1.7778); background:#f7f5f0'))
            with mock.patch.object(deck, 'run', side_effect=AssertionError('HF must not run')):
                with self.assertRaisesRegex(ValueError, '非等比'):
                    deck.check('unused', project)


class PiPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        for name, color, freq, seconds in [('base', 'blue', 220, 2), ('presenter', 'red', 880, 2), ('short', 'red', 880, 1)]:
            fps = 30 if name == 'base' else 24
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color={color}:s=640x360:r={fps}:d={seconds}', '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration={seconds}', '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(cls.work / f'{name}.mp4')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', str(cls.work/'audio.wav')], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def command(self, *extra):
        return subprocess.run(['python3', str(TOOLS/'video-producer/scripts/pip-compose.py'), '--base', str(self.work/'base.mp4'), '--output', str(self.work/'out.mp4'), '--force', *map(str, extra)], text=True, capture_output=True)

    def test_four_corners_and_dry_run(self):
        for corner in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
            result = self.command('--presenter', self.work/'presenter.mp4', '--subtitle-safe', '40', '--corner', corner, '--dry-run')
            self.assertEqual(result.returncode, 0, result.stderr)
            box = json.loads(result.stdout)['pip']
            self.assertLessEqual(box['y']+box['height'], 320)

    def test_bad_inputs_fail_without_output(self):
        for extra in [('--presenter', self.work/'short.mp4'), ('--presenter', self.work/'presenter.mp4', '--subtitle-safe', 350), ('--presenter', self.work/'presenter.mp4', '--size', 'nan'), ('--audio', self.work/'short.mp4'), ('--output', self.work/'base.mp4')]:
            with self.subTest(extra=extra):
                result = self.command(*extra)
                self.assertEqual(result.returncode, 1, result.stderr)

    def test_duration_error_lists_media_durations(self):
        result = self.command('--presenter', self.work/'short.mp4')
        for label in ('base=', 'audio=', 'presenter=', '容差='):
            self.assertIn(label, result.stderr)

    def test_composition_geometry_and_unique_audio(self):
        result = self.command('--presenter', self.work/'presenter.mp4', '--audio', self.work/'audio.wav', '--subtitle-safe', 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        box = report['pip']
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '1', '-i', str(self.work/'out.mp4'), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-threads', '1', '-'])
        def pixel(x, y):
            pos = (y*640+x)*3
            return raw[pos:pos+3]
        self.assertGreater(pixel(box['x']+box['width']//2, box['y']+box['height']//2)[0], 200)
        self.assertGreater(pixel(box['x'], box['y'])[2], 200)  # Rounded corner exposes blue base.
        self.assertGreater(pixel(320, 350)[2], 200)  # Subtitle band untouched.
        # Count zero crossings: external 440Hz, never base 220 or presenter 880.
        import array
        samples = array.array('h', subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '0.5', '-i', str(self.work/'out.mp4'), '-t', '1', '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-']))
        crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
        self.assertTrue(435 < crossings < 445, crossings)

    def test_narration_only_and_default_base_audio(self):
        for extra in (('--audio', self.work/'audio.wav'), ()):
            result = self.command(*extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            media = pip.probe(self.work/'out.mp4')
            self.assertIsNotNone(pip.stream(media, 'audio'))
            self.assertEqual(pip.stream(media, 'video')['width'], 640)

    def test_deck_compose_three_modes_keep_one_audio(self):
        source_audio = self.work/'audio.wav'
        avatar_job = self.work/'avatar.liveportrait.json'
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        avatar_job.write_text(json.dumps({
            'status': 'SUCCEEDED', 'timing_pass': True,
            'video_file': str(self.work/'presenter.mp4'), 'audio_file': str(source_audio),
            'video_sha256': sha(self.work/'presenter.mp4'), 'audio_sha256': sha(source_audio),
        }))
        inputs = {
            'footage': ['--presenter', str(self.work/'presenter.mp4')],
            'avatar': ['--avatar-job', str(avatar_job)],
            'audio': ['--audio', str(source_audio)],
        }
        for mode, extra in inputs.items():
            with self.subTest(mode=mode):
                output = self.work/f'deck-{mode}.mp4'
                result = subprocess.run([str(TOOLS/'video-producer/video-producer.sh'), 'deck-compose',
                                         '--mode', mode, '--base', str(self.work/'base.mp4'),
                                         '--output', str(output), '--subtitle-safe', '40', *extra],
                                        capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(output.with_suffix('.deck-talk.json').read_text())
                self.assertEqual(report['mode'], mode)
                self.assertEqual(report['audio_sha256'], sha(Path(report['audio'])))
                media = pip.probe(output)
                self.assertEqual(pip.stream(media, 'video')['width'], 640)
                self.assertIsNotNone(pip.stream(media, 'audio'))
                self.assertEqual(bool(json.loads(output.with_suffix('.pip.json').read_text())['pip']), mode != 'audio')

    def test_liveportrait_resume_accepts_verified_local_success(self):
        audio = self.work/'audio.wav'
        video = self.work/'presenter.mp4'
        job_path = self.work/'resume.liveportrait.json'
        job_path.write_text(json.dumps({
            'base_url': 'https://test.example/api/v1', 'task_id': 'expired-task',
            'status': 'SUCCEEDED', 'timing_pass': True,
            'audio_file': str(audio), 'audio_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
            'video_file': str(video), 'video_duration': 2.0,
        }))
        with (mock.patch.object(liveportrait, 'workspace', return_value=('https://test.example/api/v1', 'test-key')),
              mock.patch.object(liveportrait, 'request', side_effect=AssertionError('remote task expired'))):
            liveportrait.finish(job_path)
        job = json.loads(job_path.read_text())
        self.assertEqual(job['video_sha256'], hashlib.sha256(video.read_bytes()).hexdigest())
        self.assertEqual(job['status'], 'SUCCEEDED')


if __name__ == '__main__':
    unittest.main()
