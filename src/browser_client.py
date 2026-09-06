"""
Yahoo Fantasy Baseball — Playwright Browser Automation Client.

Provides browser-based interaction with Yahoo Fantasy web pages without
requiring Yahoo Developer API credentials.

Features:
- Persistent browser session (stored in .yahoo_browser_profile/)
- Interactive one-time login with 2FA support
- Headless scraping of team roster, statuses, game times, and opponents
- Headless scraping of league standings and category stats
- Automated lineup adjustment and submission ("Start Active Players" and position changes)
"""

import datetime
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path(__file__).parent.parent / ".yahoo_browser_profile"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "browser_screenshots"

BATTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF", "Util"}
PITCHER_POSITIONS = {"SP", "RP", "P"}
INACTIVE_POSITIONS = {"BN", "IL", "IL+", "NA", "DL"}


class YahooBrowserClient:
    """Manages Playwright browser automation for Yahoo Fantasy Baseball."""

    def __init__(self, profile_dir: Optional[Path] = None, headless: bool = True):
        self.profile_dir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self._playwright = None
        self._context: Optional[BrowserContext] = None

    def start(self, headless: Optional[bool] = None) -> BrowserContext:
        """Launch persistent browser context."""
        if headless is not None:
            self.headless = headless

        if self._context is not None:
            return self._context

        logger.info(f"Launching Playwright Chromium (profile: {self.profile_dir}, headless: {self.headless})...")
        self._playwright = sync_playwright().start()

        launch_kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "viewport": {"width": 1440, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "args": [
                "--disable-blink-features=AutomationControlled",
            ],
        }

        if Path("/Applications/Google Chrome.app").exists():
            launch_kwargs["channel"] = "chrome"

        try:
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            logger.warning(f"Failed launching with channel='chrome' ({e}), falling back to bundled Chromium...")
            launch_kwargs.pop("channel", None)
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        return self._context

    def close(self):
        """Close browser context and stop Playwright."""
        if self._context:
            try:
                self._context.close()
            except Exception as e:
                logger.debug(f"Error closing context: {e}")
            self._context = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.debug(f"Error stopping playwright: {e}")
            self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def is_logged_in(self, page: Page) -> bool:
        """Check if current page shows an active Yahoo login."""
        try:
            # Check for sign-in button or user profile indicator
            sign_in_link = page.query_selector("a[data-redirect-params*='login'], a:has-text('Sign in')")
            if sign_in_link and sign_in_link.is_visible():
                return False
            # Check if fantasy content / user team navigation is visible
            fantasy_nav = page.query_selector("#yfs-nav, #team-roster, a[href*='/b1/']")
            return fantasy_nav is not None
        except Exception:
            return False

    def login_interactive(self, league_id: Optional[str] = None):
        """
        Open a visible browser window for the user to log in manually.
        Waits until the user completes 2FA/login and visits their fantasy page.
        """
        print("\n" + "=" * 65)
        print("🌐 YAHOO BROWSER LOGIN")
        print("=" * 65)
        print("Opening Chromium browser window for Yahoo login...")
        print("Please log into your Yahoo account in the opened browser window.")
        print("Once you finish logging in, the script will auto-detect your session.")
        print("=" * 65 + "\n")

        self.close()
        context = self.start(headless=False)
        page = context.new_page()

        target_url = f"https://baseball.fantasysports.yahoo.com/b1/{league_id}" if league_id else "https://baseball.fantasysports.yahoo.com/"
        page.goto(target_url, wait_until="domcontentloaded")

        print("Waiting for Yahoo login to complete in the browser (timeout: 10 minutes)...")
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < 600:
            page.wait_for_timeout(3000)
            try:
                if self.is_logged_in(page):
                    logged_in = True
                    print("\n✅ Successful Yahoo Fantasy login detected!")
                    break
            except Exception:
                pass

        if not logged_in:
            print("⚠️ Login timeout reached or session not confirmed.")
        else:
            time.sleep(2)
            SCREENSHOTS_DIR.mkdir(exist_ok=True)
            screenshot_path = SCREENSHOTS_DIR / "login_verification.png"
            page.screenshot(path=str(screenshot_path))
            print(f"✅ Session saved in: {self.profile_dir}")
            print(f"📷 Verification screenshot: {screenshot_path}\n")

        self.close()

    def _resolve_team_url(self, page: Page, league_id: str, team_id: Optional[str] = None) -> str:
        """Resolve full team URL. If team_id is not given, inspects league home to find user's team."""
        if team_id:
            return f"https://baseball.fantasysports.yahoo.com/b1/{league_id}/{team_id}"

        league_url = f"https://baseball.fantasysports.yahoo.com/b1/{league_id}"
        logger.info(f"Navigating to league home {league_url} to detect user's team ID...")
        page.goto(league_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Look for links matching /b1/<league_id>/<team_id>
        team_links = page.query_selector_all(f"a[href*='/b1/{league_id}/']")
        user_team_id = None

        # Look for "My Team" or links in the subnav
        for link in team_links:
            href = link.get_attribute("href") or ""
            text = (link.inner_text() or "").strip().lower()
            match = re.search(rf"/b1/{league_id}/(\d+)", href)
            if match:
                tid = match.group(1)
                # Avoid non-team links like /standings, /players
                if "my team" in text or "roster" in text:
                    user_team_id = tid
                    break

        if not user_team_id:
            # Fallback to first numbered team link if found
            for link in team_links:
                href = link.get_attribute("href") or ""
                match = re.search(rf"/b1/{league_id}/(\d+)", href)
                if match:
                    user_team_id = match.group(1)
                    break

        if not user_team_id:
            logger.warning(f"Could not automatically detect team ID for league {league_id}. Defaulting to team 1.")
            user_team_id = "1"

        logger.info(f"Detected Team ID: {user_team_id}")
        return f"https://baseball.fantasysports.yahoo.com/b1/{league_id}/{user_team_id}"

    def get_roster(
        self,
        league_id: str,
        team_id: Optional[str] = None,
        date: Optional[datetime.date] = None,
    ) -> list[dict]:
        """
        Fetch team roster from Yahoo Fantasy web page using Playwright.
        Returns roster in the exact dictionary format expected by the optimizer.
        """
        if date is None:
            date = datetime.date.today()

        context = self.start()
        page = context.new_page()

        team_base_url = self._resolve_team_url(page, league_id, team_id)
        target_url = f"{team_base_url}?date={date.strftime('%Y-%m-%d')}"

        logger.info(f"Navigating to roster page: {target_url}")
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Ensure page content is rendered
        try:
            page.wait_for_selector("table#statTable0, table#statTable1, #team-roster", timeout=10000)
        except PlaywrightTimeoutError:
            logger.warning("Roster table selector timed out. Checking if login is required...")
            if not self.is_logged_in(page):
                raise RuntimeError(
                    "Yahoo session is not logged in or has expired. "
                    "Please run: python -m src.browser_client --login"
                )

        html_content = page.content()
        roster = self.parse_roster_html(html_content)
        logger.info(f"Parsed {len(roster)} players from web roster.")
        return roster

    @staticmethod
    def parse_roster_html(html: str) -> list[dict]:
        """
        Parse players from Yahoo Fantasy HTML markup.
        Compatible with desktop Yahoo Fantasy tables (statTable0 for batters, statTable1 for pitchers).
        """
        soup = BeautifulSoup(html, "html.parser")
        roster = []

        tables = soup.find_all("table", id=lambda x: x in ("statTable0", "statTable1"))
        if not tables:
            tables = soup.find_all("table", class_=re.compile(r"ysf-rosterswapper|Table"))

        for table in tables:
            table_id = table.get("id", "")
            table_type = "P" if table_id == "statTable1" else ("B" if table_id == "statTable0" else None)
            rows = table.find_all("tr")
            for row in rows:
                player = YahooBrowserClient._parse_player_row(row, default_position_type=table_type)
                if player:
                    roster.append(player)

        return roster

    @staticmethod
    def _parse_player_row(row, default_position_type: Optional[str] = None) -> Optional[dict]:
        """Parse a single player row in a Yahoo roster table."""
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        # Look for the player link with data-ys-playerid or in .ysf-player-name / a.name
        player_link = row.find("a", attrs={"data-ys-playerid": True})
        if not player_link:
            player_link = row.find("a", class_=re.compile(r"Nowrap|name|playernote"))
        if not player_link:
            player_link = row.find("a", href=re.compile(r"/players/|/player/"))

        if not player_link:
            return None

        name = player_link.get_text(strip=True)
        href = player_link.get("href", "")
        pid = player_link.get("data-ys-playerid")
        if not pid:
            match = re.search(r"/players/(\d+)", href)
            pid = match.group(1) if match else name.lower().replace(" ", "_")

        # Position selection and eligible positions from <select> or pos-label
        select = row.find("select")
        selected_pos = ""
        eligible_positions = []

        if select:
            if not pid or pid == name.lower().replace(" ", "_"):
                select_name = select.get("name", "")
                if select_name.isdigit():
                    pid = select_name

            for opt in select.find_all("option"):
                val = opt.get("value", "").strip().upper()
                if val:
                    eligible_positions.append(val)
                if opt.get("selected") is not None or opt.has_attr("selected"):
                    selected_pos = val

        if not selected_pos:
            pos_label = row.find(class_=re.compile(r"pos-label|pos"))
            if pos_label:
                selected_pos = pos_label.get_text(strip=True).upper()
            else:
                selected_pos = cells[0].get_text(strip=True).upper()

        if not selected_pos or selected_pos in ("POS", "POSITION", "SLOT", "EDIT"):
            return None

        # Status badge (DTD, IL, IL10, IL15, IL60, NA, DL, SUSP, etc.)
        status = ""
        status_tag = row.find(class_=re.compile(r"\bstatus\b|player-status"))
        if status_tag:
            status = status_tag.get_text(strip=True)
            if "note" in status.lower():
                status = ""
        if not status:
            status_span = row.find(
                lambda tag: tag.name in ("span", "abbr")
                and tag.get_text(strip=True) in ("DTD", "IL", "IL10", "IL15", "IL60", "NA", "DL", "SUSP")
            )
            if status_span:
                status = status_span.get_text(strip=True)

        # Team abbreviation & real-life positions
        meta = row.find(class_=re.compile(r"Fz-xxs|ysf-player-meta|F-sub"))
        team_abbr = ""
        if meta:
            meta_text = meta.get_text(strip=True)
            if "-" in meta_text:
                parts = meta_text.split("-")
                team_abbr = parts[0].strip()
                if not eligible_positions and len(parts) > 1:
                    eligible_positions = [p.strip().upper() for p in parts[1].split(",") if p.strip()]
            else:
                team_abbr = meta_text.strip()

        # Opponent & Game status
        opp_text = ""
        is_starting_pitcher = False
        has_game = True

        game_status_tag = row.find(class_=re.compile(r"game-status|ysf-game-status"))
        if game_status_tag:
            opp_text = game_status_tag.get_text(strip=True)
        elif len(cells) > 3:
            opp_text = cells[3].get_text(strip=True)

        if not opp_text or opp_text in ("-", "No Game"):
            has_game = False
            opp_text = "No Game"
        else:
            has_game = True

        # Check for starting pitcher indicator (caret in Yahoo)
        if "^" in opp_text:
            is_starting_pitcher = True

        # Determine B vs P
        if any(p in PITCHER_POSITIONS for p in eligible_positions) or selected_pos in ("SP", "RP", "P"):
            position_type = "P"
        elif any(p in BATTER_POSITIONS for p in eligible_positions) or selected_pos in BATTER_POSITIONS:
            position_type = "B"
        elif default_position_type:
            position_type = default_position_type
        else:
            position_type = "B"

        if not eligible_positions:
            eligible_positions = [selected_pos] if selected_pos not in ("BN", "IL", "IL+", "NA") else ["Util"]

        # Parse Pre-Season Rank and % Start if available
        preseason_rank = 999
        percent_started = 0.0
        if len(cells) > 5:
            rank_str = cells[4].get_text(strip=True).replace(",", "")
            if rank_str.isdigit():
                preseason_rank = int(rank_str)
            start_str = cells[5].get_text(strip=True).replace("%", "").strip()
            try:
                percent_started = float(start_str)
            except ValueError:
                pass

        if "BN" not in eligible_positions:
            eligible_positions.append("BN")

        return {
            "player_id": pid,
            "name": name,
            "position_type": position_type,
            "eligible_positions": eligible_positions,
            "selected_position": selected_pos,
            "status": status,
            "team": team_abbr,
            "editorial_team_full_name": team_abbr,
            "opponent": opp_text,
            "has_game": has_game,
            "is_starting_pitcher": is_starting_pitcher,
            "preseason_rank": preseason_rank,
            "percent_started": percent_started,
        }

    @staticmethod
    def _parse_stats_table(table, position_type: str) -> dict[str, dict]:
        """
        Parse stat columns for each player from a Yahoo roster stat table.
        Returns dict: {player_id: {stat_name: value}}
        """
        results = {}
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 10:
                continue

            name_tag = row.find("a", attrs={"data-ys-playerid": True})
            if not name_tag:
                name_tag = row.find("a", class_=re.compile(r"Nowrap|name|playernote"))
            if not name_tag:
                continue

            pid = name_tag.get("data-ys-playerid")
            if not pid:
                href = name_tag.get("href", "")
                m = re.search(r"/players/(\d+)", href)
                pid = m.group(1) if m else name_tag.get_text(strip=True).lower().replace(" ", "_")

            cell_texts = [td.get_text(strip=True) for td in cells]
            stats = {}

            if position_type == "B":
                # Typical batter stat columns:
                # [Pos, Edit, Name, Opp, Pre-Season, Current, % Start, % Ros, H/AB, R, HR, RBI, SB, BB, TB, AVG]
                # Match stats from the tail of the row
                stat_labels = ["H/AB", "R", "HR", "RBI", "SB", "BB", "TB", "AVG"]
                for i, label in enumerate(reversed(stat_labels)):
                    idx = len(cell_texts) - 1 - i
                    if idx >= 0:
                        val_str = cell_texts[idx]
                        if "/" in val_str or label == "H/AB":
                            stats[label] = val_str
                        else:
                            try:
                                stats[label] = float(val_str.replace(",", ""))
                            except ValueError:
                                stats[label] = val_str
            else:
                # Typical pitcher stat columns:
                # [Pos, Edit, Name, Opp, Pre-Season, Current, % Start, % Ros, IP, W, SV, K, ERA, WHIP, QS]
                stat_labels = ["IP", "W", "SV", "K", "ERA", "WHIP", "QS"]
                for i, label in enumerate(reversed(stat_labels)):
                    idx = len(cell_texts) - 1 - i
                    if idx >= 0:
                        val_str = cell_texts[idx]
                        try:
                            stats[label] = float(val_str.replace(",", ""))
                        except ValueError:
                            stats[label] = val_str

            results[str(pid)] = stats

        return results

    def get_player_stats(self, league_id: str, team_id: str) -> dict:
        """
        Fetch Season, L7, L14, and L30 stats for all players on the roster.
        Returns dict: {player_id: {'season': {...}, 'lastweek': {...}, 'last14': {...}, 'lastmonth': {...}}}
        """
        context = self.start()
        page = context.new_page()
        base_url = f"https://baseball.fantasysports.yahoo.com/b1/{league_id}/{team_id}"

        stats_by_player: dict[str, dict] = {}

        # Views to fetch:
        # stat2=S: Season
        # stat2=L7: Last 7 Days (hitters)
        # stat2=L14: Last 14 Days (pitchers & hitters)
        # stat2=L30: Last 30 Days (pitchers)
        view_mappings = [
            ("season", "stat1=S&stat2=S"),
            ("lastweek", "stat1=S&stat2=L7"),
            ("last14", "stat1=S&stat2=L14"),
            ("lastmonth", "stat1=S&stat2=L30"),
        ]

        for window_name, query in view_mappings:
            target_url = f"{base_url}?{query}"
            logger.info(f"Fetching {window_name} stats via browser: {target_url}")
            try:
                page.goto(target_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                soup = BeautifulSoup(page.content(), "html.parser")

                t0 = soup.find("table", id="statTable0")
                if t0:
                    batter_stats = self._parse_stats_table(t0, "B")
                    for pid, s in batter_stats.items():
                        if pid not in stats_by_player:
                            stats_by_player[pid] = {}
                        stats_by_player[pid][window_name] = s

                t1 = soup.find("table", id="statTable1")
                if t1:
                    pitcher_stats = self._parse_stats_table(t1, "P")
                    for pid, s in pitcher_stats.items():
                        if pid not in stats_by_player:
                            stats_by_player[pid] = {}
                        stats_by_player[pid][window_name] = s

            except Exception as e:
                logger.warning(f"Failed to fetch {window_name} stats via browser: {e}")

        return stats_by_player

    def get_standings(self, league_id: str) -> list[dict]:
        """
        Fetch league category standings table from Yahoo web page.
        """
        context = self.start()
        page = context.new_page()

        standings_url = f"https://baseball.fantasysports.yahoo.com/b1/{league_id}/standings"
        logger.info(f"Navigating to standings page: {standings_url}")
        page.goto(standings_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        html_content = page.content()
        standings = self.parse_standings_html(html_content)
        logger.info(f"Parsed {len(standings)} teams from standings.")
        return standings

    @staticmethod
    def parse_standings_html(html: str) -> list[dict]:
        """Parse standings table from Yahoo Fantasy standings page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        standings = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue

            header_row = None
            for r in rows[:3]:
                txts = [c.get_text(strip=True) for c in r.find_all(["th", "td"])]
                if "Team Name" in txts:
                    header_row = txts
                    break

            if not header_row:
                continue

            for r in rows:
                cells = r.find_all("td")
                if len(cells) < len(header_row) - 4:
                    continue

                team_link = r.find("a", href=re.compile(r"/b1/\d+/\d+"))
                if not team_link:
                    continue

                team_name = team_link.get_text(strip=True)
                team_href = team_link.get("href", "")
                tid_match = re.search(r"/b1/\d+/(\d+)", team_href)
                team_key = tid_match.group(1) if tid_match else team_name

                stats = {}
                total_pts = 0.0
                cell_txts = [c.get_text(strip=True) for c in cells]

                for h, val in zip(header_row, cell_txts):
                    if h in ("R", "HR", "RBI", "SB", "BB", "TB", "AVG", "OBP", "W", "SV", "K", "ERA", "WHIP", "QS"):
                        try:
                            stats[h] = float(val.replace(",", ""))
                        except ValueError:
                            stats[h] = val
                    elif h in ("Total Points", "Pts", "Points"):
                        try:
                            total_pts = float(val.replace(",", ""))
                        except ValueError:
                            pass

                standings.append({
                    "name": team_name,
                    "team_key": team_key,
                    "points": total_pts,
                    "stats": stats,
                })
            break

        return standings

    def get_top_free_agents(
        self,
        league_id: str,
        position_type: str = "B",
        count: int = 25,
    ) -> list[dict]:
        """
        Fetch top available free agents sorted by ownership percentage via browser.
        position_type: 'B' for batters, 'P' for pitchers
        """
        context = self.start()
        page = context.new_page()

        # Yahoo FA URL sorted by % Rostered (sort=OR)
        url = f"https://baseball.fantasysports.yahoo.com/b1/{league_id}/players?status=A&pos={position_type}&sort=OR"
        logger.info(f"Fetching top free agents ({position_type}) via browser: {url}")

        free_agents = []
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            soup = BeautifulSoup(page.content(), "html.parser")

            table = soup.find("table", class_=re.compile(r"Table|players"))
            if table:
                rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
                for r in rows:
                    name_tag = r.find("a", attrs={"data-ys-playerid": True})
                    if not name_tag:
                        name_tag = r.find("a", class_=re.compile(r"Nowrap|name|playernote"))
                    if not name_tag:
                        continue

                    name = name_tag.get_text(strip=True)
                    pid = name_tag.get("data-ys-playerid")
                    if not pid:
                        href = name_tag.get("href", "")
                        m = re.search(r"/players/(\d+)", href)
                        pid = m.group(1) if m else name.lower().replace(" ", "_")

                    # Pos / Meta
                    meta = r.find(class_=re.compile(r"Fz-xxs|ysf-player-meta|F-sub"))
                    eligible_positions = []
                    if meta:
                        parts = meta.get_text(strip=True).split("-")
                        if len(parts) > 1:
                            eligible_positions = [p.strip().upper() for p in parts[1].split(",") if p.strip()]

                    # Percent owned and counting stats
                    cells = [td.get_text(strip=True) for td in r.find_all("td")]
                    pct_owned = 0.0
                    for c in cells:
                        if "%" in c:
                            try:
                                pct_owned = float(c.replace("%", "").strip())
                                break
                            except ValueError:
                                pass

                    # Parse stats from row
                    stats = {}
                    if position_type == "B":
                        stat_labels = ["H/AB", "R", "HR", "RBI", "SB", "BB", "TB", "AVG"]
                        for i, label in enumerate(reversed(stat_labels)):
                            idx = len(cells) - 1 - i
                            if idx >= 0:
                                val_str = cells[idx]
                                if "/" in val_str or label == "H/AB":
                                    stats[label] = val_str
                                else:
                                    try:
                                        stats[label] = float(val_str.replace(",", ""))
                                    except ValueError:
                                        stats[label] = val_str
                    else:
                        stat_labels = ["IP", "W", "SV", "K", "ERA", "WHIP", "QS"]
                        for i, label in enumerate(reversed(stat_labels)):
                            idx = len(cells) - 1 - i
                            if idx >= 0:
                                val_str = cells[idx]
                                try:
                                    stats[label] = float(val_str.replace(",", ""))
                                except ValueError:
                                    stats[label] = val_str

                    free_agents.append({
                        "player_id": str(pid),
                        "name": name,
                        "position_type": position_type,
                        "eligible_positions": eligible_positions,
                        "status": "",
                        "percent_owned": pct_owned,
                        "stats": stats,
                    })
                    if len(free_agents) >= count:
                        break
        except Exception as e:
            logger.warning(f"Failed to fetch free agents via browser: {e}")

        logger.info(f"Parsed {len(free_agents)} top free agents for {position_type}.")
        return free_agents

    def apply_lineup_changes(
        self,
        league_id: str,
        changes: list[dict],
        team_id: Optional[str] = None,
        date: Optional[datetime.date] = None,
    ) -> bool:
        """
        Execute lineup changes directly on the Yahoo Fantasy team web page.
        """
        if not changes:
            logger.info("No lineup changes to apply.")
            return True

        if date is None:
            date = datetime.date.today()

        context = self.start(headless=self.headless)
        page = context.new_page()

        team_base_url = self._resolve_team_url(page, league_id, team_id)
        target_url = f"{team_base_url}?date={date.strftime('%Y-%m-%d')}"

        logger.info(f"Opening team page for lineup updates: {target_url}")
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 1. Try Yahoo's "Start Active Players" button if applicable
        start_active_btn = page.query_selector("a:has-text('Start Active Players'), button:has-text('Start Active Players')")
        if start_active_btn and start_active_btn.is_visible():
            logger.info("Found 'Start Active Players' button. Clicking it to baseline active roster...")
            try:
                start_active_btn.click()
                page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"Could not click 'Start Active Players': {e}")

        # 2. Iterate through changes and adjust position dropdowns / swaps
        for change in changes:
            pname = change["player_name"]
            to_pos = change["to"]
            logger.info(f"Setting {pname} to {to_pos}...")

            try:
                # Find the row containing this player's name
                row = page.locator(f"tr:has-text('{pname}')").first
                if not row.count():
                    logger.warning(f"Could not locate row for player {pname}")
                    continue

                # Look for position select dropdown in the row
                pos_select = row.locator("select").first
                if pos_select.count():
                    try:
                        pos_select.select_option(value=to_pos)
                    except Exception:
                        pos_select.select_option(label=to_pos)
                    page.wait_for_timeout(500)
                else:
                    # Some Yahoo layouts use position toggle buttons or swap modals
                    pos_btn = row.locator("button, a.pos-label").first
                    if pos_btn.count():
                        pos_btn.click()
                        page.wait_for_timeout(500)
                        # Look for target position option in the popup
                        target_opt = page.locator(f"button:has-text('{to_pos}'), a:has-text('{to_pos}')").first
                        if target_opt.count():
                            target_opt.click()
                            page.wait_for_timeout(500)
            except Exception as e:
                logger.error(f"Failed setting position for {pname}: {e}")

        # 3. Click "Save Changes" or "Submit Changes"
        save_btn = page.query_selector("input[value='Save Changes'], button:has-text('Save Changes')")
        if save_btn and save_btn.is_visible():
            logger.info("Clicking 'Save Changes' button...")
            save_btn.click()
            page.wait_for_timeout(3000)
            logger.info("✅ Lineup changes saved successfully!")
        else:
            logger.info("No 'Save Changes' button required (changes auto-saved or confirmed).")

        # Capture verification screenshot
        SCREENSHOTS_DIR.mkdir(exist_ok=True)
        screenshot_file = SCREENSHOTS_DIR / f"lineup_{date.strftime('%Y%m%d')}.png"
        page.screenshot(path=str(screenshot_file))
        logger.info(f"📷 Lineup confirmation screenshot saved to {screenshot_file}")

        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Yahoo Fantasy Browser Client")
    parser.add_argument("--login", action="store_true", help="Launch interactive browser login to Yahoo")
    parser.add_argument("--league-id", type=str, default=os.environ.get("YAHOO_LEAGUE_ID", ""), help="Yahoo League ID")
    parser.add_argument("--team-id", type=str, default=None, help="Team ID (optional)")
    parser.add_argument("--test-roster", action="store_true", help="Test fetching and parsing roster")
    args = parser.parse_args()

    client = YahooBrowserClient()
    if args.login:
        client.login_interactive(args.league_id)
    elif args.test_roster:
        if not args.league_id:
            print("❌ --league-id is required.")
        else:
            with client:
                r = client.get_roster(args.league_id, args.team_id)
                print(f"\nFetched {len(r)} players:")
                for p in r:
                    print(f"  [{p['selected_position']:4s}] {p['name']:25s} ({p['team']}) - Eligible: {p['eligible_positions']} - Status: {p['status']}")
    else:
        parser.print_help()
