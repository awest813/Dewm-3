"""Check that rendering evidence cannot silently accept simulation divergence."""
from pathlib import Path
import tempfile
import unittest

from render_state_parity_check import compare, compare_traces, draw_offset, states, traces


class RenderStateParity(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'console.txt'
            path.write_text(text)
            return states(path)

    def test_native_wrapping_and_web_match(self):
        native = self.read('noise\nRENDER_STATE game_time=176 render_time=176 frame=11 random_s\need=-471451794\n')
        web = self.read('RENDER_STATE game_time=176 render_time=176 frame=11 random_seed=-471451794\n')
        self.assertEqual(compare(native, web), 1)

    def test_missing_and_truncated_evidence(self):
        for text in ('noise', 'RENDER_STATE game_time=176',
                     'RENDER_STATE game_time=176\nRENDER_STATE game_time=192'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.read(text)

    def test_wrap_inside_seed_digits(self):
        rows = self.read('RENDER_STATE game_time=176 render_time=176 frame=11 random_seed=-471\n451794\nwriting screenshot\n')
        self.assertEqual(rows[0]['random_seed'], -471451794)

    def test_each_field_must_match(self):
        row = dict(game_time=176, render_time=176, frame=11, random_seed=-471451794)
        for field in row:
            changed = dict(row)
            changed[field] += 1
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                compare([row], [changed])

    def test_count_and_schema_must_match(self):
        for native, web in (([], []), ([{}], []), ([{}], [{}])):
            with self.subTest(native=native, web=web), self.assertRaises(ValueError):
                compare(native, web)

    def test_recorded_campaign_offsets(self):
        for native, web in ((-471451794, 1286920474),
                            (-2008849762, -392712374),
                            (-787973119, 630802013)):
            self.assertEqual(draw_offset(native, web), 4)
            self.assertEqual(draw_offset(web, native), -4)
        self.assertEqual(draw_offset(-1, -1), 0)
        self.assertIsNone(draw_offset(0, 2, limit=10))

    def test_offset_diagnosis_does_not_accept_mismatch(self):
        native = dict(game_time=176, render_time=176, frame=11, random_seed=-471451794)
        web = dict(native, random_seed=1286920474)
        with self.assertRaisesRegex(ValueError, 'web 4 random draws ahead'):
            compare([native], [web])

    def test_trace_wrap_and_first_divergence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.txt'
            path.write_text('RANDOM_STATE phase=think_entity index=34 frame=1 se\ned=-471451794\n')
            native = traces(path)
        self.assertEqual(compare_traces(native, native), 1)
        with self.assertRaisesRegex(ValueError, 'phase=think_entity index=34 frame=1.*4 random draws ahead'):
            compare_traces(native, [dict(native[0], seed=1286920474)])

    def test_trace_entity_order_is_required(self):
        native = [dict(phase='think_entity', index=34, frame=1, seed=0)]
        with self.assertRaisesRegex(ValueError, 'index 34 / 35'):
            compare_traces(native, [dict(native[0], index=35)])
        with self.assertRaisesRegex(ValueError, 'count differs'):
            compare_traces(native, native * 2)


if __name__ == '__main__':
    unittest.main()
