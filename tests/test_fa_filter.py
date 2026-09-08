"""
Unit tests for Free Agent injury filtering and multi-horizon stats.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
from src import ai_ranker


class TestFreeAgentFilter(unittest.TestCase):
    def test_filter_injured_free_agents(self):
        """
        Ensure free agents with any injury tag (IL, IL10, IL60, DTD, etc.)
        are excluded from the candidate pool.
        """
        all_fa = [
            {"player_id": "1", "name": "Casey Schmitt", "status": "IL60"},
            {"player_id": "2", "name": "Willy Adames", "status": "IL10"},
            {"player_id": "3", "name": "Shohei Ohtani (Pitcher)", "status": "IL"},
            {"player_id": "4", "name": "Day-to-Day Player", "status": "DTD"},
            {"player_id": "5", "name": "Jarren Duran", "status": ""},
            {"player_id": "6", "name": "Yainer Diaz", "status": ""},
        ]

        healthy_fa = [
            p for p in all_fa
            if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT", "DTD", "NA", "SUSP")
        ]

        self.assertEqual(len(healthy_fa), 2)
        healthy_names = [p["name"] for p in healthy_fa]
        self.assertIn("Jarren Duran", healthy_names)
        self.assertIn("Yainer Diaz", healthy_names)
        self.assertNotIn("Casey Schmitt", healthy_names)
        self.assertNotIn("Willy Adames", healthy_names)
        self.assertNotIn("Shohei Ohtani (Pitcher)", healthy_names)
        self.assertNotIn("Day-to-Day Player", healthy_names)

    def test_safety_post_filter_rejects_injured_add(self):
        """
        Ensure suggest_add_drops strips out any recommendation to add an injured player.
        """
        mock_client = MagicMock()
        ai_ranker._client = mock_client

        # Mock model returning an add suggestion for an injured player
        fake_response = MagicMock()
        fake_response.text = json.dumps([
            {
                "drop_player_id": 100,
                "add_player_id": 200,
                "drop_player_name": "Bench Batter",
                "add_player_name": "Injured Slugger",
                "rationale": "High upside when healthy",
                "expected_category_impact": "+HR"
            },
            {
                "drop_player_id": 101,
                "add_player_id": 201,
                "drop_player_name": "Fringe Pitcher",
                "add_player_name": "Healthy Ace",
                "rationale": "Strong recent strikeout pace",
                "expected_category_impact": "+K"
            }
        ])
        mock_client.models.generate_content.return_value = fake_response

        drop_candidates = [{"player_id": 100, "name": "Bench Batter"}, {"player_id": 101, "name": "Fringe Pitcher"}]
        free_agents = [
            {"player_id": 200, "name": "Injured Slugger", "status": "IL10"},
            {"player_id": 201, "name": "Healthy Ace", "status": ""},
        ]

        suggestions = ai_ranker.suggest_add_drops(
            drop_candidates,
            free_agents,
            category_gaps=[],
            recent_stats={}
        )

        # The injured slugger must be rejected by the safety post-filter!
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["add_player_name"], "Healthy Ace")


if __name__ == "__main__":
    unittest.main()
