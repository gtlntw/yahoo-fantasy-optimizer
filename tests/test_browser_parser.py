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

    def test_no_start_active_players_button_click(self):
        """
        Regression test: ensure apply_lineup_changes never queries or clicks
        Yahoo's 'Start Active Players' button, which triggers a blocking modal.
        """
        import inspect
        source = inspect.getsource(YahooBrowserClient.apply_lineup_changes)
        self.assertNotIn("has-text('Start Active Players')", source)
        self.assertNotIn('has-text("Start Active Players")', source)

    def test_parse_free_agent_status_and_stats(self):
        """
        Verify that Free Agent parsing detects injury status badges (e.g. IL60)
        and properly extracts stat columns without trailing-cell offset.
        """
        from bs4 import BeautifulSoup
        html = '''
        <table class="Table">
            <tbody>
                <tr>
                    <td>icon</td><td>icon</td>
                    <td>
                        <a class="Nowrap" data-ys-playerid="12544" href="/players/12544">Casey Schmitt</a>
                        <span class="status">IL60</span>
                        <span class="ysf-player-meta">SF - 1B,2B,3B,OF</span>
                    </td>
                    <td>STL</td><td>W</td><td>-</td><td>82</td><td>-</td><td>20%</td>
                    <td>105/387</td><td>47</td><td>21</td><td>55</td><td>9</td><td>11</td><td>187</td><td>.271</td><td></td>
                </tr>
                <tr>
                    <td>icon</td><td>icon</td>
                    <td>
                        <a class="Nowrap" data-ys-playerid="11735" href="/players/11735">Jarren Duran</a>
                        <span class="ysf-player-meta">BOS - OF</span>
                    </td>
                    <td>TOR</td><td>W</td><td>-</td><td>35</td><td>-</td><td>84%</td>
                    <td>135/470</td><td>80</td><td>15</td><td>60</td><td>25</td><td>45</td><td>210</td><td>.287</td><td></td>
                </tr>
            </tbody>
        </table>
        '''
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find("tbody").find_all("tr")

        # Row 0: Schmitt (IL60)
        r0 = rows[0]
        status_tag = r0.find(class_="status")
        status0 = status_tag.get_text(strip=True) if status_tag else ""
        self.assertEqual(status0, "IL60")

        # Extract stats from r0
        cells0 = [td.get_text(strip=True) for td in r0.find_all("td")]
        while cells0 and not cells0[-1].strip():
            cells0.pop()
        labels = ["H/AB", "R", "HR", "RBI", "SB", "BB", "TB", "AVG"]
        stats0 = {}
        for i, l in enumerate(reversed(labels)):
            stats0[l] = float(cells0[-1 - i]) if l != "H/AB" else cells0[-1 - i]
        self.assertEqual(stats0["AVG"], 0.271)
        self.assertEqual(stats0["TB"], 187.0)
        self.assertEqual(stats0["HR"], 21.0)

        # Row 1: Duran (Healthy)
        r1 = rows[1]
        status_tag1 = r1.find(class_="status")
        status1 = status_tag1.get_text(strip=True) if status_tag1 else ""
        self.assertEqual(status1, "")


if __name__ == "__main__":
    unittest.main()
