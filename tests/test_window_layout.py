import unittest

import window_layout


class LayoutTests(unittest.TestCase):
    def test_wide_window_keeps_one_row(self):
        plan = window_layout.arrange(460, 78)
        row = [item for item in plan["buttons"] if item[0] in window_layout.TRANSPORT]
        ys = {item[2] for item in row}
        self.assertEqual(len(ys), 1)
        self.assertGreater(ys.pop(), plan["status"][1])
        gear = next(item for item in plan["buttons"] if item[0] == "gear")
        power = next(item for item in plan["buttons"] if item[0] == "power")
        self.assertLess(gear[2], row[0][2])
        self.assertGreater(power[1], gear[1])

    def test_skinny_window_stacks(self):
        plan = window_layout.arrange(72, 400)
        xs = {item[1] for item in plan["buttons"]}
        ys = {item[2] for item in plan["buttons"]}
        self.assertEqual(len(xs), 1)
        self.assertGreater(len(ys), 1)
        self.assertGreater(plan["height"], 200)

    def test_medium_window_wraps(self):
        plan = window_layout.arrange(180, 220)
        xs = {item[1] for item in plan["buttons"]}
        ys = {item[2] for item in plan["buttons"]}
        self.assertGreater(len(xs), 1)
        self.assertGreater(len(ys), 1)

    def test_minimum_size_and_saved_place(self):
        self.assertEqual(window_layout.clamp_size(20, 20)[0], window_layout.MIN_W)
        wide_w, wide_h = window_layout.clamp_size(500, 10)
        self.assertGreaterEqual(wide_h, window_layout.min_height(500))
        narrow_w, narrow_h = window_layout.clamp_size(80, 74)
        self.assertGreater(narrow_h, 74)
        x, y = window_layout.clamp_origin(-400, 5000, 200, 80, 800, 600)
        self.assertGreater(x + 200, 0)
        self.assertLess(y, 600)
