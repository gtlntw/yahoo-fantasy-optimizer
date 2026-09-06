"""
Unit tests for Yahoo Fantasy browser client HTML parsing.
"""

import unittest
from src.browser_client import YahooBrowserClient


SAMPLE_ROSTER_HTML = """
<html>
<body>
<div id="team-roster">
    <table id="statTable0" class="Table">
        <thead>
            <tr><th>Pos</th><th>Edit</th><th>Batters</th><th>Opp</th><th>Pre-Season</th><th>% Start</th></tr>
        </thead>
        <tbody>
            <tr>
                <td class="pos-label">C</td>
                <td class="edit">
                    <select name="10542">
                        <option value="C" selected>C</option>
                        <option value="Util">Util</option>
                        <option value="BN">BN</option>
                    </select>
                </td>
                <td class="ysf-player-name">
                    <a class="Nowrap name F-link" data-ys-playerid="10542" href="https://sports.yahoo.com/mlb/players/10542">Will Smith</a>
                    <span class="Fz-xxs">LAD - C</span>
                </td>
                <td>@ SF 7:15 pm</td>
                <td>221</td>
                <td>35%</td>
            </tr>
            <tr>
                <td class="pos-label">1B</td>
                <td class="edit">
                    <select name="9876">
                        <option value="1B" selected>1B</option>
                        <option value="Util">Util</option>
                        <option value="BN">BN</option>
                    </select>
                </td>
                <td class="ysf-player-name">
                    <a class="Nowrap name F-link" data-ys-playerid="9876" href="https://sports.yahoo.com/mlb/players/9876">Freddie Freeman</a>
                    <span class="Fz-xxs">LAD - 1B</span>
                    <span class="status DTD">DTD</span>
                </td>
                <td>@ SF 7:15 pm</td>
                <td>25</td>
                <td>93%</td>
            </tr>
            <tr>
                <td class="pos-label">BN</td>
                <td class="edit">
                    <select name="11234">
                        <option value="OF">OF</option>
                        <option value="Util">Util</option>
                        <option value="BN" selected>BN</option>
                    </select>
                </td>
                <td class="ysf-player-name">
                    <a class="Nowrap name F-link" data-ys-playerid="11234" href="https://sports.yahoo.com/mlb/players/11234">Jackson Chourio</a>
                    <span class="Fz-xxs">MIL - OF</span>
                </td>
                <td>-</td>
                <td>90</td>
                <td>73%</td>
            </tr>
        </tbody>
    </table>
    <table id="statTable1" class="Table">
        <thead>
            <tr><th>Pos</th><th>Edit</th><th>Pitchers</th><th>Opp</th><th>Pre-Season</th><th>% Start</th></tr>
        </thead>
        <tbody>
            <tr>
                <td class="pos-label">SP</td>
                <td class="edit">
                    <select name="8888">
                        <option value="SP" selected>SP</option>
                        <option value="P">P</option>
                        <option value="BN">BN</option>
                    </select>
                </td>
                <td class="ysf-player-name">
                    <a class="Nowrap name F-link" data-ys-playerid="8888" href="https://sports.yahoo.com/mlb/players/8888">Tarik Skubal</a>
                    <span class="Fz-xxs">DET - SP</span>
                </td>
                <td>vs CWS 1:10 pm ^</td>
                <td>156</td>
                <td>67%</td>
            </tr>
        </tbody>
    </table>
</div>
</body>
</html>
"""

SAMPLE_STANDINGS_HTML = """
<html>
<body>
<table id="standingstable" class="Table">
    <thead>
        <tr>
            <th>Rank</th><th>Team Name</th><th>Pts</th><th>R</th><th>HR</th><th>RBI</th><th>SB</th><th>AVG</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>1</td>
            <td><a href="https://baseball.fantasysports.yahoo.com/b1/12345/1">Bronx Bombers</a></td>
            <td>75.5</td><td>450</td><td>120</td><td>430</td><td>55</td><td>.265</td>
        </tr>
        <tr>
            <td>2</td>
            <td><a href="https://baseball.fantasysports.yahoo.com/b1/12345/2">Dodger Blue</a></td>
            <td>72.0</td><td>440</td><td>115</td><td>425</td><td>62</td><td>.261</td>
        </tr>
    </tbody>
</table>
</body>
</html>
"""


class TestBrowserParser(unittest.TestCase):
    def test_parse_roster_html(self):
        roster = YahooBrowserClient.parse_roster_html(SAMPLE_ROSTER_HTML)
        self.assertEqual(len(roster), 4)

        # Player 1: Will Smith
        smith = roster[0]
        self.assertEqual(smith["name"], "Will Smith")
        self.assertEqual(smith["player_id"], "10542")
        self.assertEqual(smith["selected_position"], "C")
        self.assertEqual(smith["position_type"], "B")
        self.assertIn("C", smith["eligible_positions"])
        self.assertEqual(smith["team"], "LAD")
        self.assertTrue(smith["has_game"])
        self.assertEqual(smith["status"], "")
        self.assertEqual(smith["preseason_rank"], 221)

        # Player 2: Freddie Freeman (DTD)
        freeman = roster[1]
        self.assertEqual(freeman["name"], "Freddie Freeman")
        self.assertEqual(freeman["selected_position"], "1B")
        self.assertEqual(freeman["status"], "DTD")
        self.assertEqual(freeman["preseason_rank"], 25)

        # Player 3: Jackson Chourio (BN, no game)
        chourio = roster[2]
        self.assertEqual(chourio["name"], "Jackson Chourio")
        self.assertEqual(chourio["selected_position"], "BN")
        self.assertFalse(chourio["has_game"])

        # Player 4: Tarik Skubal (SP, starting)
        skubal = roster[3]
        self.assertEqual(skubal["name"], "Tarik Skubal")
        self.assertEqual(skubal["selected_position"], "SP")
        self.assertEqual(skubal["position_type"], "P")
        self.assertTrue(skubal["is_starting_pitcher"])

    def test_parse_standings_html(self):
        standings = YahooBrowserClient.parse_standings_html(SAMPLE_STANDINGS_HTML)
        self.assertEqual(len(standings), 2)

        team1 = standings[0]
        self.assertEqual(team1["name"], "Bronx Bombers")
        self.assertEqual(team1["team_key"], "1")
        self.assertEqual(team1["points"], 75.5)
        self.assertEqual(team1["stats"]["HR"], 120.0)
        self.assertEqual(team1["stats"]["SB"], 55.0)


if __name__ == "__main__":
    unittest.main()
