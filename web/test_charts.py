from datetime import date

from django.test import SimpleTestCase

from .charts import HEIGHT, PAD_BOTTOM, PAD_TOP, WIDTH, build_chart


class BuildChartTests(SimpleTestCase):
    def test_no_points_means_no_chart(self):
        self.assertIsNone(build_chart([]))

    def test_a_single_point_is_a_dot_in_the_middle(self):
        chart = build_chart([(date(2026, 1, 1), 2500)])
        self.assertEqual((chart.line, chart.area, chart.count), ("", "", 1))
        self.assertGreater(chart.last_x, 0)
        self.assertLess(chart.last_x, WIDTH)
        self.assertEqual(chart.first_date, chart.last_date)

    def test_higher_ratings_are_drawn_higher_up(self):
        chart = build_chart([(date(2026, 1, 1), 2400), (date(2026, 7, 1), 2500)])
        self.assertTrue(chart.line.startswith("M"))
        first_y, last_y = [float(p.split()[1]) for p in chart.line[1:].split(" L")]
        self.assertGreater(first_y, last_y)  # SVG's y grows downwards
        self.assertEqual(chart.last_y, last_y)

    def test_points_are_sorted_by_date_and_spaced_by_time(self):
        chart = build_chart(
            [(date(2026, 3, 1), 2450), (date(2026, 1, 1), 2400), (date(2026, 1, 2), 2410)]
        )
        xs = [float(p.split()[0]) for p in chart.line[1:].split(" L")]
        self.assertEqual(xs, sorted(xs))
        self.assertLess(xs[1] - xs[0], (xs[2] - xs[1]) / 10)  # one day vs two months
        self.assertEqual((chart.first_date, chart.last_date), (date(2026, 1, 1), date(2026, 3, 1)))

    def test_the_range_always_contains_every_rating(self):
        for ratings in ([2400, 2500], [2400, 2405], [1000, 3000], [2450, 2450]):
            with self.subTest(ratings=ratings):
                points = [(date(2026, 1 + i, 1), r) for i, r in enumerate(ratings)]
                chart = build_chart(points)
                self.assertLess(chart.y_min, min(ratings))
                self.assertGreater(chart.y_max, max(ratings))

    def test_all_coordinates_stay_inside_the_drawing(self):
        points = [(date(2026, 1 + i, 1), 2300 + 37 * i % 90) for i in range(12)]
        chart = build_chart(points)
        for pair in chart.line[1:].split(" L"):
            x, y = (float(v) for v in pair.split())
            self.assertTrue(0 <= x <= WIDTH)
            self.assertTrue(PAD_TOP <= y <= HEIGHT - PAD_BOTTOM)

    def test_constant_ratings_give_a_flat_line(self):
        chart = build_chart([(date(2026, 1, 1), 2450), (date(2026, 2, 1), 2450)])
        ys = {p.split()[1] for p in chart.line[1:].split(" L")}
        self.assertEqual(len(ys), 1)

    def test_axis_labels_go_from_bottom_to_top(self):
        chart = build_chart([(date(2026, 1, 1), 2400), (date(2026, 2, 1), 2500)])
        values = [value for _, value in chart.y_ticks]
        self.assertEqual(values, sorted(values))
        pixels = [pixel for pixel, _ in chart.y_ticks]
        self.assertEqual(pixels, sorted(pixels, reverse=True))
