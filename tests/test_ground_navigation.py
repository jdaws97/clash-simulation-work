"""Pure grid reuse must preserve BFS ties and react to live geometry changes."""

import unittest

from clashlab.spatial import _ground_navigation, _ground_route
from test_spatial import synthetic_structure, synthetic_unit


class GroundNavigationTests(unittest.TestCase):
    def test_reuses_grid_with_live_goal_range_position_and_exit_cells(self):
        _ground_navigation.cache_clear()
        actor = synthetic_unit(x=0.5, y=0.5, range=0.1)
        target = synthetic_structure(x=2.5, y=2.5, width=0, height=0)
        blocked = {(1, 1)}
        self.assertEqual(
            _ground_route(actor, target, blocked, 4, 4),
            [(0.5, 1.5), (0.5, 2.5), (1.5, 2.5), (2.5, 2.5)],
        )
        target.update(x=2.5, y=0.5)
        self.assertEqual(
            _ground_route(actor, target, blocked, 4, 4), [(1.5, 0.5), (2.5, 0.5)]
        )
        actor.update(x=0.6, range=1.1)
        self.assertEqual(
            _ground_route(actor, target, blocked, 4, 4), [(0.5, 0.5), (1.5, 0.5)]
        )
        self.assertEqual(
            _ground_route(actor, None, blocked, 4, 4, exit_cells={(0, 0)}),
            [(0.5, 0.5), (0.5, 1.5)],
        )
        self.assertEqual(_ground_navigation.cache_info().misses, 1)
        self.assertEqual(_ground_navigation.cache_info().hits, 3)

    def test_obstacle_mutation_board_bounds_and_returned_route_are_isolated(self):
        actor = synthetic_unit(x=0.5, y=0.5, range=0.1)
        target = synthetic_structure(x=2.5, y=0.5, width=0, height=0)
        blocked = {(1, 0)}
        self.assertIsNone(_ground_route(actor, target, blocked, 3, 1))
        route = _ground_route(actor, target, blocked, 3, 2)
        self.assertEqual(route, [(0.5, 1.5), (1.5, 1.5), (2.5, 1.5), (2.5, 0.5)])
        route.clear()
        self.assertEqual(len(_ground_route(actor, target, blocked, 3, 2)), 4)
        blocked.clear()
        self.assertEqual(
            _ground_route(actor, target, blocked, 3, 1), [(1.5, 0.5), (2.5, 0.5)]
        )
        blocked.add((1, 0))
        self.assertIsNone(_ground_route(actor, target, blocked, 3, 1))


if __name__ == "__main__":
    unittest.main()
