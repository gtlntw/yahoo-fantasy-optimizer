"""
Unit tests for lineup optimization logic.
"""

import unittest
from src.optimizer import optimize_lineup


class TestOptimizer(unittest.TestCase):
    def test_injured_player_in_active_slot_is_force_benched(self):
        """
        An injured player (IL10) occupying an active slot (1B) must be benched
        so that an active starter can take 1B without collision.
        """
        roster = [
            {
                "player_id": "10166",
                "name": "Willson Contreras",
                "selected_position": "1B",
                "eligible_positions": ["1B", "Util", "BN", "IL"],
                "position_type": "B",
                "status": "IL10",
                "has_game": True,
                "ai_rank": 8,
            },
            {
                "player_id": "8875",
                "name": "Bryce Harper",
                "selected_position": "OF",
                "eligible_positions": ["1B", "OF", "Util", "BN"],
                "position_type": "B",
                "status": "",
                "has_game": True,
                "ai_rank": 1,
            },
            {
                "player_id": "12582",
                "name": "Daylen Lile",
                "selected_position": "Util",
                "eligible_positions": ["OF", "Util", "BN"],
                "position_type": "B",
                "status": "",
                "has_game": True,
                "ai_rank": 2,
            },
            {
                "player_id": "9999",
                "name": "Active OF 1",
                "selected_position": "OF",
                "eligible_positions": ["OF", "Util", "BN"],
                "position_type": "B",
                "status": "",
                "has_game": True,
                "ai_rank": 3,
            },
            {
                "player_id": "9998",
                "name": "Active OF 2",
                "selected_position": "OF",
                "eligible_positions": ["OF", "Util", "BN"],
                "position_type": "B",
                "status": "",
                "has_game": True,
                "ai_rank": 4,
            },
        ]

        changes = optimize_lineup(roster)

        # There should be a change benching Contreras
        contreras_change = next((c for c in changes if c["player_name"] == "Willson Contreras"), None)
        self.assertIsNotNone(contreras_change, "Expected Contreras to be benched")
        self.assertEqual(contreras_change["from"], "1B")
        self.assertEqual(contreras_change["to"], "BN")
        self.assertIn("Injured/inactive", contreras_change["reason"])

        # Harper should be assigned to 1B
        harper_change = next((c for c in changes if c["player_name"] == "Bryce Harper"), None)
        self.assertIsNotNone(harper_change, "Expected Harper to move to 1B")
        self.assertEqual(harper_change["to"], "1B")

        # Lile should move to OF
        lile_change = next((c for c in changes if c["player_name"] == "Daylen Lile"), None)
        self.assertIsNotNone(lile_change, "Expected Lile to move to OF")
        self.assertEqual(lile_change["to"], "OF")

    def test_no_game_healthy_player_cosmetic_retention(self):
        """
        A healthy player with no game should remain in their slot if the slot
        remains unfilled by any active player.
        """
        roster = [
            {
                "player_id": "8996",
                "name": "Jose Altuve",
                "selected_position": "2B",
                "eligible_positions": ["2B", "Util", "BN"],
                "position_type": "B",
                "status": "",
                "has_game": False,  # No game
                "ai_rank": 5,
            },
            {
                "player_id": "8875",
                "name": "Bryce Harper",
                "selected_position": "1B",
                "eligible_positions": ["1B", "Util", "BN"],
                "position_type": "B",
                "status": "",
                "has_game": True,
                "ai_rank": 1,
            },
        ]

        changes = optimize_lineup(roster)
        # Altuve should NOT be moved to BN because 2B is completely empty
        altuve_change = next((c for c in changes if c["player_name"] == "Jose Altuve"), None)
        self.assertIsNone(altuve_change, "Altuve should stay in 2B since nobody else can fill 2B")


if __name__ == "__main__":
    unittest.main()
