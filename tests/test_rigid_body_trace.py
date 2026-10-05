"""Reject incomplete or divergent rigid-body arithmetic evidence."""
import copy
from pathlib import Path
import tempfile
import unittest

from rigid_body_trace_check import records, compare


class RigidBodyTrace(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'console.txt'
            path.write_text(text)
            return records(path)

    def test_wrapped_vectors_and_exponents(self):
        text = 'RB_TRACE phase=collision entity=486 frame=182 field=velocity v=-0.000541,-337.750549,4.07628021e+02\n'
        wrapped = text.replace('velocity', 'velo\ncity').replace('e+02', 'e+\n02')
        self.assertEqual(self.read(text), self.read(wrapped))
        self.assertEqual(self.read(text), self.read(text.replace('4.07628021e+02', '4.076\n28021e+02')))

    def test_incomplete_or_absent(self):
        for text in ('', 'RB_TRACE phase=begin entity=486 frame=182 field=velocity v=1,2',
                     'RB_TRACE phase=begin entity=486 frame=182 field=velocity v=nan,2,3'):
            with self.assertRaises(ValueError):
                self.read(text)

    def test_exact_value_difference(self):
        rows = self.read('RB_TRACE phase=collision entity=486 frame=182 field=velocity v=0,0,407.628021\n')
        web = copy.deepcopy(rows)
        web[0]['value'] = (0., 0., 407.628113)
        with self.assertRaisesRegex(ValueError, 'frame=182.*velocity'):
            compare(rows, web)
        self.assertEqual(compare(rows, rows), 1)

    def test_identity_order_and_count(self):
        rows = self.read('RB_TRACE phase=begin entity=486 frame=181 field=position v=1,2,3\n'
                         'RB_TRACE phase=begin entity=486 frame=182 field=position v=1,2,3\n')
        for field, value in [('entity', 487), ('phase', 'motion'), ('field', 'linearMomentum')]:
            web = copy.deepcopy(rows)
            web[0][field] = value
            with self.assertRaisesRegex(ValueError, field):
                compare(rows, web)
        with self.assertRaisesRegex(ValueError, 'frame'):
            compare(rows, list(reversed(rows)))
        with self.assertRaisesRegex(ValueError, 'count'):
            compare(rows, rows[:-1])


if __name__ == '__main__':
    unittest.main()
