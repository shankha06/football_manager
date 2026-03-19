"""Premium Terminal Football Manager — Textual TUI Application.

Dark-themed, colour-coded, engaging terminal UI with live match stats,
formation displays, and post-match analytics dashboard.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Button, DataTable, Input, Label,
    Select, RichLog, ProgressBar, OptionList,
)
from textual.widgets.option_list import Option
from textual.screen import Screen
from textual.binding import Binding
from rich.text import Text
from rich.table import Table as RichTable
from rich.panel import Panel
from rich.columns import Columns
from rich.console import Group

from fm.db.database import init_db, get_session
from fm.db.models import (
    Club, Player, League, LeagueStanding, Fixture, Season,
    Manager, TacticalSetup, NewsItem, PlayerStats,
)
from fm.world.season import SeasonManager
from fm.config import (
    MENTALITY_LEVELS, STARTING_SEASON,
    TEMPO_LEVELS, PRESSING_LEVELS, PASSING_STYLES, WIDTH_LEVELS,
    DEFENSIVE_LINE_LEVELS,
)
from fm.engine.tactics import FORMATIONS
from fm.world.assistant import AssistantManager
from fm.ui.screens import (
    FinanceScreen, BoardRoomScreen, YouthAcademyScreen,
    PlayerDynamicsScreen, ContractScreen, AnalyticsScreen, StaffScreen,
)


# ── Colours & Constants ────────────────────────────────────────────────────

POS_COLOURS = {
    "GK": "#FFD700",   # gold
    "CB": "#4A90D9", "LB": "#4A90D9", "RB": "#4A90D9",
    "LWB": "#4A90D9", "RWB": "#4A90D9",
    "CDM": "#2ECC71", "CM": "#2ECC71", "CAM": "#2ECC71",
    "LM": "#2ECC71", "RM": "#2ECC71",
    "LW": "#E74C3C", "RW": "#E74C3C", "CF": "#E74C3C", "ST": "#E74C3C",
}

POS_GROUPS = {
    "GK": "GK", "CB": "DEF", "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
    "CDM": "MID", "CM": "MID", "CAM": "MID", "LM": "MID", "RM": "MID",
    "LW": "FWD", "RW": "FWD", "CF": "FWD", "ST": "FWD",
}

FORM_COLOURS = {"W": "#2ECC71", "D": "#F39C12", "L": "#E74C3C"}

ASCII_LOGO = (
    "[bold #58a6ff]"
    "\n  ╔══════════════════════════════════════════════╗"
    "\n  ║                                              ║"
    "\n  ║    ⚽  TERMINAL FOOTBALL MANAGER  ⚽         ║"
    "\n  ║       ═══════════════════════════            ║"
    "\n  ║                                              ║"
    "\n  ║      [/][bold #2ECC71]Manage[/] [bold #58a6ff]·[/] "
    "[bold #F39C12]Compete[/] [bold #58a6ff]·[/] "
    "[bold #E74C3C]Dominate[/]           [bold #58a6ff]║"
    "\n  ║                                              ║"
    "\n  ╚══════════════════════════════════════════════╝[/]"
)


def _pos_badge(pos: str) -> str:
    """Return a coloured position badge."""
    colour = POS_COLOURS.get(pos, "#999")
    return f"[bold {colour}]{pos:>3}[/]"


def _form_chips(form_str: str) -> str:
    """Render W/D/L as coloured chips."""
    if not form_str or form_str == "-----":
        return "[dim]─────[/]"
    chips = []
    for ch in form_str[-5:]:
        colour = FORM_COLOURS.get(ch, "#666")
        chips.append(f"[bold {colour}]{ch}[/]")
    return " ".join(chips)


def _stat_bar(label: str, home_val, away_val, fmt: str = "d") -> str:
    """Render a side-by-side stat comparison bar."""
    h = home_val if isinstance(home_val, str) else f"{home_val:{fmt}}"
    a = away_val if isinstance(away_val, str) else f"{away_val:{fmt}}"

    # Calculate bar widths (max 15 chars each side)
    total = (float(home_val) if not isinstance(home_val, str) else 0) + \
            (float(away_val) if not isinstance(away_val, str) else 0)
    if total > 0 and not isinstance(home_val, str):
        hw = int(float(home_val) / total * 15)
        aw = 15 - hw
    else:
        hw = aw = 7

    h_bar = "█" * max(hw, 1)
    a_bar = "█" * max(aw, 1)

    return (f"  [bold]{h:>6}[/] [#4A90D9]{h_bar:>15}[/]"
            f" [dim]{label:^14}[/] "
            f"[#E74C3C]{a_bar:<15}[/] [bold]{a:<6}[/]")


# ── CSS Styling ────────────────────────────────────────────────────────────

APP_CSS = """
Screen {
    background: #0d1117;
    color: #c9d1d9;
    align: center top;
}

Header {
    background: #161b22;
    color: #58a6ff;
}

Footer {
    background: #161b22;
}

/* ── Centering wrapper — constrains content and centres horizontally ── */
.centered-content {
    width: 100%;
    max-width: 120;

    padding: 1 2;
    height: auto;
}

.screen-title {
    color: #58a6ff;
    text-style: bold;
    text-align: center;
    width: 100%;
    padding: 0 0 1 0;
}

.header-row {
    height: auto;
    align: center middle;
    padding: 0 0 1 0;
    width: 100%;
}

/* ── Main Menu ── */
#main-menu {
    align: center middle;
    width: 56;
    height: auto;
    border: heavy #30363d;
    padding: 2 4;
    background: #161b22;
}

#main-menu Static {
    text-align: center;
    width: 100%;
    color: #58a6ff;
}

.menu-btn {
    width: 100%;
    margin: 1 0;
}

.menu-btn-primary {
    width: 100%;
    margin: 1 0;
    background: #238636;
}

.menu-btn-danger {
    width: 100%;
    margin: 1 0;
    background: #da3633;
}

/* ── Dashboard ── */
#dashboard {
    layout: grid;
    grid-size: 2 4;
    grid-gutter: 1;
    padding: 1 2;
    max-width: 140;

}

.panel {
    border: solid #30363d;
    padding: 1;
    height: auto;
    background: #161b22;
}

.panel-accent {
    border: solid #58a6ff;
    padding: 1;
    height: auto;
    background: #161b22;
}

.panel-gold {
    border: solid #FFD700;
    padding: 1;
    height: auto;
    background: #161b22;
}

.panel-green {
    border: solid #2ECC71;
    padding: 1;
    height: auto;
    background: #161b22;
}

.panel-purple {
    border: solid #9B59B6;
    padding: 1;
    height: auto;
    background: #161b22;
}

/* ── Match View ── */
#match-view {
    padding: 1 2;
    max-width: 120;

}

#scoreboard {
    background: #161b22;
    border: heavy #58a6ff;
    padding: 1;
    text-align: center;
    height: auto;
}

#match-stats-panel {
    background: #161b22;
    border: solid #30363d;
    padding: 1;
    height: auto;
}

/* ── Match Prep ── */
#match-prep-view {
    max-width: 120;

    padding: 1 2;
}

.prep-row {
    height: auto;
    width: 100%;
}

.prep-row > Static {
    width: 1fr;
}

/* ── Data Table ── */
DataTable {
    height: auto;
    max-height: 35;
    background: #0d1117;
}

DataTable > .datatable--header {
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1f6feb;
}

DataTable > .datatable--even-row {
    background: #0d1117;
}

DataTable > .datatable--odd-row {
    background: #161b22;
}

/* ── Widgets ── */
RichLog {
    background: #0d1117;
    border: solid #30363d;
    height: auto;
    max-height: 20;
}

Input {
    background: #161b22;
    border: solid #30363d;
}

Input:focus {
    border: solid #58a6ff;
}

Select {
    background: #161b22;
    border: solid #30363d;
}

Select:focus {
    border: solid #58a6ff;
}

Button {
    background: #21262d;
    color: #c9d1d9;
    border: solid #30363d;
    margin: 0 1;
}

.back-btn {
    border: none;
    background: transparent;
    color: #58a6ff;
    min-width: 10;
    margin-right: 2;
}
.back-btn:hover {
    background: #21262d;
}

Button:hover {
    background: #30363d;
}

Button.-primary {
    background: #238636;
    border: solid #2ea043;
}

Button.-primary:hover {
    background: #2ea043;
}

Button.-success {
    background: #1f6feb;
    border: solid #58a6ff;
}

Label {
    color: #c9d1d9;
}

.section-title {
    color: #58a6ff;
    text-style: bold;
    text-align: center;
    padding: 0 0 1 0;
    width: 100%;
}

.dim-text {
    color: #484f58;
}

ScrollableContainer {
    height: auto;
    max-height: 50;
}

/* ── Team Talk ── */
#pre-talk-container, #post-talk-container {
    padding: 1 2;
    height: auto;
    max-width: 100;

}

#talk-options {
    height: auto;
    max-height: 12;
    background: #161b22;
    border: solid #30363d;
    margin: 1 0;
}

#talk-options > .option-list--option-highlighted {
    background: #1f6feb;
}

#talk-options > .option-list--option-hover {
    background: #30363d;
}

/* ── Button Row ── */
.btn-row {
    height: auto;
    align: center middle;
    padding: 1 0;
    width: 100%;
}

ResourceWidget {
    dock: top;
    color: #8b949e;
    text-align: right;
    width: 100%;
    height: 1;
    padding: 0 2;
    background: transparent;
}
"""


# ── Resource Widget ────────────────────────────────────────────────────────
class ResourceWidget(Static):
    """Displays system CPU load and RAM usage."""
    def on_mount(self) -> None:
        self.update_stats()
        self.set_interval(2.0, self.update_stats)

    def update_stats(self) -> None:
        ram_usage = "N/A"
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem_total = next(int(line.split()[1]) for line in lines if line.startswith("MemTotal:"))
            mem_avail = next(int(line.split()[1]) for line in lines if line.startswith("MemAvailable:"))
            if mem_total:
                ram_usage = f"{((mem_total - mem_avail) / mem_total) * 100:.1f}%"
        except Exception:
            pass
        cpu_load = "N/A"
        try:
            with open("/proc/loadavg", "r") as f:
                cpu_load = f.read().split()[0]
        except Exception:
            pass
        self.update(f"💻 CPU Load: [bold]{cpu_load}[/] | 🧠 RAM: [bold]{ram_usage}[/]")

# ── Main Menu Screen ──────────────────────────────────────────────────────

class MainMenuScreen(Screen):
    """The game's main menu."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ResourceWidget()
        with Container(id="main-menu"):
            yield Static(ASCII_LOGO)
            yield Static("")
            yield Button("🆕  New Game", id="new-game",
                         classes="menu-btn", variant="primary")
            yield Button("📂  Continue", id="continue",
                         classes="menu-btn", variant="success")
            yield Button("❌  Quit", id="quit",
                         classes="menu-btn", variant="error")
            yield Static("[dim]v0.3.0 — AI Assistant Edition[/]")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-game":
            self.app.push_screen(NewGameScreen())
        elif event.button.id == "continue":
            self.app.push_screen(ClubSelectScreen(continue_game=True))
        elif event.button.id == "quit":
            self.app.exit()


# ── New Game Screen ────────────────────────────────────────────────────────

class NewGameScreen(Screen):
    """New game setup — data ingestion then club selection."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield ResourceWidget()
        with Container(id="main-menu"):
            yield Static("[bold #58a6ff]🆕 NEW GAME SETUP[/]")
            yield Static("━" * 40)
            yield Static("Initialising database and loading player data...",
                         id="status")
            yield Button("▶ Start Data Load", id="start-load",
                         classes="menu-btn", variant="primary")
            yield Button("◀ Back", id="back", classes="menu-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "start-load":
            status = self.query_one("#status", Static)
            status.update("[#F39C12]Loading data... This may take a moment.[/]")
            self.set_timer(0.1, self._do_load)

    def _do_load(self):
        from fm.db.ingestion import ingest_all
        from fm.db.database import reset_db

        status = self.query_one("#status", Static)
        try:
            reset_db()
            stats = ingest_all()
            status.update(
                f"[#2ECC71]✅ Loaded {stats['players']} players, {stats['clubs']} clubs, "
                f"{stats['leagues']} leagues, {stats['fixtures']} fixtures.[/]\n\n"
                f"Select your club to begin!"
            )
            self.set_timer(1.5, lambda: self.app.push_screen(ClubSelectScreen()))
        except Exception as e:
            status.update(f"[#E74C3C]❌ Error: {e}[/]")


# ── Club Selection ─────────────────────────────────────────────────────────

class ClubSelectScreen(Screen):
    """Select which club to manage."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, continue_game: bool = False):
        super().__init__()
        self.continue_game = continue_game

    def compose(self) -> ComposeResult:
        yield Header()
        yield ResourceWidget()
        with Vertical(classes="centered-content"):
            yield Label("⚽ SELECT YOUR CLUB", classes="section-title")
            yield Static("[dim center]Use ↑↓ to navigate, Enter to select.[/]")
            table = DataTable(id="clubs-table")
            table.cursor_type = "row"
            yield table
        yield Footer()

    def on_mount(self) -> None:
        if self.continue_game:
            init_db()
        session = get_session()
        table = self.query_one("#clubs-table", DataTable)
        table.add_columns("League", "Club", "⭐ Rep", "Budget (€M)", "Squad")

        leagues = session.query(League).order_by(League.tier, League.name).all()
        for league in leagues:
            clubs = session.query(Club).filter_by(
                league_id=league.id
            ).order_by(Club.reputation.desc()).all()
            for club in clubs:
                player_count = session.query(Player).filter_by(
                    club_id=club.id).count()
                stars = "⭐" * min((club.reputation or 50) // 20, 5)
                table.add_row(
                    league.name,
                    club.name,
                    stars,
                    f"€{club.budget or 0:.1f}M",
                    str(player_count),
                    key=str(club.id),
                )
        session.close()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        club_id = int(str(event.row_key.value))
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        if season:
            season.human_club_id = club_id
        mgr = session.query(Manager).filter_by(club_id=club_id).first()
        if mgr:
            mgr.is_human = True
        session.commit()
        session.close()
        self.app.push_screen(DashboardScreen(club_id))


# ── Dashboard ──────────────────────────────────────────────────────────────

class DashboardScreen(Screen):
    """Main game dashboard after selecting a club."""

    BINDINGS = [
        Binding("s", "show_squad", "Squad"),
        Binding("t", "show_tactics", "Tactics"),
        Binding("l", "show_league", "League"),
        Binding("m", "play_match", "Match Day"),
        Binding("r", "show_transfers", "Transfers"),
        Binding("o", "show_scout", "Scout"),
        Binding("n", "show_news", "News"),
        Binding("g", "show_league_stats", "Golden Boot"),
        Binding("f", "show_fixtures", "Fixtures"),
        Binding("x", "show_training", "Training"),
        Binding("$", "show_finance", "Finance"),
        Binding("b", "show_boardroom", "Board"),
        Binding("y", "show_youth", "Youth"),
        Binding("d", "show_dynamics", "Dynamics"),
        Binding("c", "show_contracts", "Contracts"),
        Binding("a", "show_analytics", "Analytics"),
        Binding("w", "show_staff", "Staff"),
        Binding("p", "show_match_prep", "Match Prep"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield ResourceWidget()
        with Container(id="dashboard"):
            yield Static(id="club-info", classes="panel-accent")
            yield Static(id="next-match", classes="panel")
            yield Static(id="league-pos", classes="panel")
            yield Static(id="finances", classes="panel")
            yield Static(id="squad-summary", classes="panel")
            yield Static(id="team-morale", classes="panel")
            yield Static(id="training-status", classes="panel")
            yield Static(id="recent-news", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_dashboard()

    def on_screen_resume(self) -> None:
        """Re-fetch data whenever the user returns to this screen."""
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        session = get_session()
        club = session.query(Club).get(self.club_id)
        season = session.query(Season).order_by(Season.year.desc()).first()
        league = session.query(League).get(club.league_id) if club.league_id else None

        # ─ Club info ─
        player_count = session.query(Player).filter_by(club_id=self.club_id).count()
        stars = "⭐" * min((club.reputation or 50) // 20, 5)
        info = self.query_one("#club-info", Static)
        info.update(Panel(
            f"[bold #58a6ff]{club.name}[/]\n"
            f"[dim]League:[/] {league.name if league else 'N/A'}\n"
            f"[dim]Squad:[/] {player_count} players\n"
            f"[dim]Reputation:[/] {stars}\n"
            f"[dim]Season:[/] {season.year}/{season.year + 1 if season else '?'}",
            title="🏟️ [bold]YOUR CLUB[/]",
            border_style="#58a6ff",
        ))

        # ─ Next match ─
        next_md = (season.current_matchday or 0) + 1
        fixture = session.query(Fixture).filter(
            Fixture.season == season.year,
            Fixture.matchday == next_md,
            Fixture.played == False,
            (Fixture.home_club_id == self.club_id) |
            (Fixture.away_club_id == self.club_id),
        ).first()

        next_match = self.query_one("#next-match", Static)
        if fixture:
            home = session.query(Club).get(fixture.home_club_id)
            away = session.query(Club).get(fixture.away_club_id)
            is_home = fixture.home_club_id == self.club_id
            venue = "[#2ECC71]HOME[/]" if is_home else "[#E74C3C]AWAY[/]"
            next_match.update(Panel(
                f"[dim]Matchday {next_md}[/]  {venue}\n\n"
                f"[bold]{home.name}[/]  vs  [bold]{away.name}[/]\n\n"
                f"[dim]Press[/] [bold #FFD700]P[/] [dim]for AI Match Prep[/]  |  "
                f"[dim]Press[/] [bold #58a6ff]M[/] [dim]to simulate[/]",
                title="📅 [bold]NEXT FIXTURE[/]",
                border_style="#30363d",
            ))
        else:
            next_match.update(Panel("No upcoming fixtures", title="📅 Next Fixture"))

        # ─ League position ─
        if league:
            standings = session.query(LeagueStanding).filter_by(
                league_id=league.id, season=season.year
            ).order_by(
                LeagueStanding.points.desc(),
                LeagueStanding.goal_difference.desc()
            ).all()

            pos = 1
            my_st = None
            for i, st in enumerate(standings):
                if st.club_id == self.club_id:
                    pos = i + 1
                    my_st = st
                    break

            league_pos = self.query_one("#league-pos", Static)
            if my_st:
                form_display = _form_chips(my_st.form)
                league_pos.update(Panel(
                    f"[bold #58a6ff]#{pos}[/] / {len(standings)}\n"
                    f"[dim]P:[/] {my_st.played}  [#2ECC71]W:[/] {my_st.won}  "
                    f"[#F39C12]D:[/] {my_st.drawn}  [#E74C3C]L:[/] {my_st.lost}\n"
                    f"[dim]GD:[/] {my_st.goal_difference:+d}  "
                    f"[dim]Pts:[/] [bold]{my_st.points}[/]\n"
                    f"[dim]Form:[/] {form_display}",
                    title="📊 [bold]LEAGUE[/]",
                    border_style="#30363d",
                ))
            else:
                league_pos.update(Panel("No standings data", title="📊 League"))
        else:
            self.query_one("#league-pos", Static).update(
                Panel("No league assigned", title="📊 League"))

        # ─ Finances ─
        budget = club.budget or 0
        wage_budget = club.wage_budget or 0
        wages = club.total_wages or 0
        wage_pct = min(wages / max(wage_budget * 1000 / 52, 1) * 100, 100) if wage_budget else 0
        wage_colour = "#2ECC71" if wage_pct < 70 else "#F39C12" if wage_pct < 90 else "#E74C3C"
        finances = self.query_one("#finances", Static)
        finances.update(Panel(
            f"[dim]Transfer Budget:[/] [bold]€{budget:.1f}M[/]\n"
            f"[dim]Wage Budget:[/] €{wage_budget:.1f}M/yr\n"
            f"[dim]Current Wages:[/] [{wage_colour}]€{wages:.0f}K/wk[/] ({wage_pct:.0f}%)",
            title="💰 [bold]FINANCES[/]",
            border_style="#30363d",
        ))

        # ─ Squad summary ─
        players = session.query(Player).filter_by(club_id=self.club_id).all()
        gk = sum(1 for p in players if p.position == "GK")
        defs = sum(1 for p in players if POS_GROUPS.get(p.position) == "DEF")
        mids = sum(1 for p in players if POS_GROUPS.get(p.position) == "MID")
        fwds = sum(1 for p in players if POS_GROUPS.get(p.position) == "FWD")
        avg_ovr = sum(p.overall or 0 for p in players) / max(len(players), 1)
        injured = sum(1 for p in players if (p.injured_weeks or 0) > 0)
        # Morale
        avg_morale = sum(p.morale or 65 for p in players) / max(len(players), 1)
        if avg_morale >= 80:
            morale_label, morale_col = "Superb", "#2ECC71"
        elif avg_morale >= 65:
            morale_label, morale_col = "Good", "#2ECC71"
        elif avg_morale >= 50:
            morale_label, morale_col = "Decent", "#F39C12"
        else:
            morale_label, morale_col = "Poor", "#E74C3C"

        # Training focus
        training_focus = club.training_focus or "match_prep"
        focus_labels = {
            "attacking": "Attacking", "defending": "Defending",
            "physical": "Physical", "tactical": "Tactical",
            "set_pieces": "Set Pieces", "match_prep": "Match Prep",
        }
        training_label = focus_labels.get(training_focus, training_focus.replace("_", " ").title())

        # Upcoming fixtures (next 3)
        upcoming_text = ""
        if season:
            next_md_start = (season.current_matchday or 0) + 1
            upcoming_fixtures = session.query(Fixture).filter(
                Fixture.season == season.year,
                Fixture.played == False,
                Fixture.matchday >= next_md_start,
                (Fixture.home_club_id == self.club_id) |
                (Fixture.away_club_id == self.club_id),
            ).order_by(Fixture.matchday).limit(3).all()
            if upcoming_fixtures:
                upcoming_text = "\n[dim]Upcoming:[/] "
                fix_parts = []
                for uf in upcoming_fixtures:
                    opp_id = uf.away_club_id if uf.home_club_id == self.club_id else uf.home_club_id
                    opp = session.query(Club).get(opp_id)
                    venue = "H" if uf.home_club_id == self.club_id else "A"
                    opp_name = (opp.short_name or opp.name)[:12] if opp else "?"
                    fix_parts.append(f"{opp_name}({venue})")
                upcoming_text += "  ".join(fix_parts)

        squad_summary = self.query_one("#squad-summary", Static)
        squad_summary.update(Panel(
            f"[#FFD700]GK:[/] {gk}  [#4A90D9]DEF:[/] {defs}  "
            f"[#2ECC71]MID:[/] {mids}  [#E74C3C]FWD:[/] {fwds}\n"
            f"[dim]Avg OVR:[/] [bold]{avg_ovr:.0f}[/]  "
            f"[dim]Injured:[/] {'[#E74C3C]' + str(injured) + '[/]' if injured else '0'}\n"
            f"[dim]Morale:[/] [{morale_col}]{morale_label} ({avg_morale:.0f})[/]  "
            f"[dim]Training:[/] [bold]{training_label}[/]"
            f"{upcoming_text}",
            title="📋 [bold]SQUAD[/]",
            border_style="#30363d",
        ))

        # ─ Team morale ─
        very_happy = sum(1 for p in players if (p.morale or 65) >= 85)
        happy = sum(1 for p in players if 70 <= (p.morale or 65) < 85)
        content = sum(1 for p in players if 50 <= (p.morale or 65) < 70)
        unhappy = sum(1 for p in players if 30 <= (p.morale or 65) < 50)
        very_unhappy = sum(1 for p in players if (p.morale or 65) < 30)
        morale_bar = (
            f"[#2ECC71]{'█' * very_happy}[/]"
            f"[#8BC34A]{'█' * happy}[/]"
            f"[#F39C12]{'█' * content}[/]"
            f"[#E67E22]{'█' * unhappy}[/]"
            f"[#E74C3C]{'█' * very_unhappy}[/]"
        )
        morale_panel = self.query_one("#team-morale", Static)
        morale_panel.update(Panel(
            f"[dim]Overall:[/] [{morale_col}][bold]{morale_label}[/] ({avg_morale:.0f})[/]\n"
            f"{morale_bar}\n"
            f"[#2ECC71]😄 {very_happy}[/]  [#8BC34A]🙂 {happy}[/]  "
            f"[#F39C12]😐 {content}[/]  [#E67E22]😟 {unhappy}[/]  "
            f"[#E74C3C]😠 {very_unhappy}[/]",
            title="😊 [bold]MORALE[/]",
            border_style="#30363d",
        ))

        # ─ Training status ─
        focus_emoji = {
            "attacking": "⚽", "defending": "🛡️", "physical": "💪",
            "tactical": "🧠", "set_pieces": "🎯", "match_prep": "📋",
        }
        avg_fitness = sum(p.fitness or 100 for p in players) / max(len(players), 1)
        fit_col = "#2ECC71" if avg_fitness >= 85 else "#F39C12" if avg_fitness >= 70 else "#E74C3C"
        injured_players = [p for p in players if (p.injured_weeks or 0) > 0]
        inj_text = ""
        if injured_players:
            inj_text = "\n[#E74C3C]Injured:[/] " + ", ".join(
                f"{(p.short_name or p.name)[:10]}({p.injured_weeks}w)"
                for p in injured_players[:3]
            )
            if len(injured_players) > 3:
                inj_text += f" +{len(injured_players)-3} more"

        training_panel = self.query_one("#training-status", Static)
        training_panel.update(Panel(
            f"[dim]Focus:[/] {focus_emoji.get(training_focus, '📋')} [bold]{training_label}[/]\n"
            f"[dim]Squad Fitness:[/] [{fit_col}]{avg_fitness:.0f}%[/]\n"
            f"[dim]Press[/] [bold #58a6ff]X[/] [dim]to change training[/]"
            f"{inj_text}",
            title="🏋️ [bold]TRAINING[/]",
            border_style="#30363d",
        ))

        # ─ Recent news ─
        news = session.query(NewsItem).order_by(NewsItem.id.desc()).limit(3).all()
        news_text = ""
        if news:
            for item in news:
                emoji = {"transfer": "💼", "match": "⚽", "injury": "🏥",
                         "manager": "👔", "finance": "💰"}.get(item.category, "📰")
                news_text += f"{emoji} {item.headline}\n"
        else:
            news_text = "[dim]No news yet. Play some matches![/]"
        recent_news = self.query_one("#recent-news", Static)
        recent_news.update(Panel(
            news_text.strip(),
            title="📰 [bold]NEWS[/]",
            border_style="#30363d",
        ))

        session.close()

    def action_show_squad(self) -> None:
        self.app.push_screen(SquadScreen(self.club_id))

    def action_show_tactics(self) -> None:
        self.app.push_screen(TacticsScreen(self.club_id))

    def action_show_league(self) -> None:
        self.app.push_screen(LeagueTableScreen(self.club_id))

    def action_play_match(self) -> None:
        self.app.push_screen(MatchDayScreen(self.club_id))

    def action_show_transfers(self) -> None:
        self.app.push_screen(TransferScreen(self.club_id))

    def action_show_news(self) -> None:
        self.app.push_screen(NewsScreen(self.club_id))

    def action_show_scout(self) -> None:
        self.app.push_screen(ScoutScreen(self.club_id))

    def action_show_league_stats(self) -> None:
        self.app.push_screen(LeagueStatsScreen(self.club_id))

    def action_show_fixtures(self) -> None:
        self.app.push_screen(FixtureResultsScreen(self.club_id))

    def action_show_training(self) -> None:
        self.app.push_screen(TrainingScreen(self.club_id))

    def action_show_finance(self) -> None:
        self.app.push_screen(FinanceScreen(self.club_id))

    def action_show_boardroom(self) -> None:
        self.app.push_screen(BoardRoomScreen(self.club_id))

    def action_show_youth(self) -> None:
        self.app.push_screen(YouthAcademyScreen(self.club_id))

    def action_show_dynamics(self) -> None:
        self.app.push_screen(PlayerDynamicsScreen(self.club_id))

    def action_show_contracts(self) -> None:
        self.app.push_screen(ContractScreen(self.club_id))

    def action_show_analytics(self) -> None:
        self.app.push_screen(AnalyticsScreen(self.club_id))

    def action_show_staff(self) -> None:
        self.app.push_screen(StaffScreen(self.club_id))

    def action_show_match_prep(self) -> None:
        self.app.push_screen(MatchPrepScreen(self.club_id))

    def action_quit(self) -> None:
        self.app.exit()


# ── Squad Screen ───────────────────────────────────────────────────────────

class SquadScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal(classes="header-row", id="squad-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("📋 SQUAD OVERVIEW", classes="section-title")
            table = DataTable(id="squad-table")
            table.cursor_type = "row"
            yield table
            yield Static(id="player-detail")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        table = self.query_one("#squad-table", DataTable)
        table.add_columns(
            "Pos", "Name", "Age", "OVR", "POT",
            "PAC", "SHO", "PAS", "DRI", "DEF", "PHY",
            "Wage", "Fit", "Form",
        )

        players = session.query(Player).filter_by(
            club_id=self.club_id
        ).order_by(Player.position, Player.overall.desc()).all()

        for p in players:
            pos_col = POS_COLOURS.get(p.position, "#999")

            # Fitness indicator
            fit = p.fitness or 0
            if (p.injured_weeks or 0) > 0:
                fit_icon = "🏥"
            elif fit > 80:
                fit_icon = "🟢"
            elif fit > 50:
                fit_icon = "🟡"
            else:
                fit_icon = "🔴"

            # OVR colour
            ovr = p.overall or 0
            if ovr >= 80:
                ovr_display = f"[bold #2ECC71]{ovr}[/]"
            elif ovr >= 70:
                ovr_display = f"[#F39C12]{ovr}[/]"
            else:
                ovr_display = f"{ovr}"

            table.add_row(
                Text(p.position, style=f"bold {pos_col}"),
                (p.short_name or p.name)[:22],
                str(p.age),
                Text(str(ovr), style="bold" if ovr >= 80 else ""),
                str(p.potential),
                str(p.pace), str(p.shooting), str(p.passing),
                str(p.dribbling), str(p.defending), str(p.physical),
                f"€{p.wage:.0f}K",
                fit_icon,
                f"{p.form:.0f}" if p.form else "65",
                key=str(p.id),
            )
        session.close()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key:
            try:
                player_id = int(str(event.row_key.value))
                self.app.push_screen(PlayerDetailScreen(player_id))
            except (ValueError, TypeError):
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()


# ── Player Detail Screen ───────────────────────────────────────────────────

class PlayerDetailScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, player_id: int):
        super().__init__()
        self.player_id = player_id

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="centered-content"):
            with Horizontal(classes="header-row"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("PLAYER DETAILS", classes="section-title")
            yield Static(id="player-header")
            yield Static(id="player-attrs")
            yield Static(id="player-stats")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        p = session.query(Player).get(self.player_id)
        if not p:
            session.close()
            return

        club = session.query(Club).get(p.club_id) if p.club_id else None

        # Header
        pos_col = POS_COLOURS.get(p.position, "#999")
        header = self.query_one("#player-header", Static)

        morale_val = p.morale or 65
        morale_label = (
            "Superb" if morale_val >= 85
            else "Good" if morale_val >= 70
            else "Decent" if morale_val >= 55
            else "Poor" if morale_val >= 40
            else "Very Poor"
        )
        morale_col = "#2ECC71" if morale_val >= 70 else "#F39C12" if morale_val >= 50 else "#E74C3C"

        header.update(Panel(
            f"[bold {pos_col}]{p.position}[/]  [bold]{p.name}[/]  "
            f"[dim]Age:[/] {p.age}  [dim]Nationality:[/] {p.nationality or '?'}\n"
            f"[dim]Club:[/] {club.name if club else 'Free Agent'}  "
            f"[dim]OVR:[/] [bold]{p.overall}[/]  [dim]POT:[/] [bold]{p.potential}[/]\n"
            f"[dim]Value:[/] €{p.market_value:.1f}M  [dim]Wage:[/] €{p.wage:.0f}K/w  "
            f"[dim]Contract:[/] {p.contract_expiry}\n"
            f"[dim]Fitness:[/] {p.fitness:.0f}%  "
            f"[dim]Morale:[/] [{morale_col}]{morale_label}[/]  "
            f"[dim]Form:[/] {p.form:.0f}",
            title=f"👤 {p.short_name or p.name}",
            border_style=pos_col,
        ))

        # Attributes
        def attr_bar(name, val, max_val=99):
            val = val or 0
            filled = int(val / max_val * 15)
            bar = "█" * filled + "░" * (15 - filled)
            col = "#2ECC71" if val >= 80 else "#F39C12" if val >= 60 else "#E74C3C" if val >= 40 else "#666"
            return f"  {name:<18} [{col}]{bar}[/] [bold]{val:>2}[/]"

        if p.position == "GK":
            attrs_text = "[bold #FFD700]Goalkeeping[/]\n"
            attrs_text += "\n".join([
                attr_bar("Diving", p.gk_diving),
                attr_bar("Handling", p.gk_handling),
                attr_bar("Kicking", p.gk_kicking),
                attr_bar("Positioning", p.gk_positioning),
                attr_bar("Reflexes", p.gk_reflexes),
            ])
        else:
            attrs_text = "[bold #E74C3C]Attacking[/]\n"
            attrs_text += "\n".join([
                attr_bar("Finishing", p.finishing),
                attr_bar("Shot Power", p.shot_power),
                attr_bar("Long Shots", p.long_shots),
                attr_bar("Volleys", p.volleys),
                attr_bar("Penalties", p.penalties),
            ])
            attrs_text += "\n\n[bold #2ECC71]Passing[/]\n"
            attrs_text += "\n".join([
                attr_bar("Short Passing", p.short_passing),
                attr_bar("Long Passing", p.long_passing),
                attr_bar("Vision", p.vision),
                attr_bar("Crossing", p.crossing),
                attr_bar("Curve", p.curve),
            ])
            attrs_text += "\n\n[bold #F39C12]Dribbling[/]\n"
            attrs_text += "\n".join([
                attr_bar("Dribbling", p.dribbling),
                attr_bar("Ball Control", p.ball_control),
                attr_bar("Agility", p.agility),
                attr_bar("Balance", p.balance),
            ])
            attrs_text += "\n\n[bold #4A90D9]Defending[/]\n"
            attrs_text += "\n".join([
                attr_bar("Marking", p.marking),
                attr_bar("Stand Tackle", p.standing_tackle),
                attr_bar("Slide Tackle", p.sliding_tackle),
                attr_bar("Interceptions", p.interceptions),
                attr_bar("Heading", p.heading_accuracy),
            ])
            attrs_text += "\n\n[bold #9B59B6]Physical[/]\n"
            attrs_text += "\n".join([
                attr_bar("Pace", p.pace),
                attr_bar("Acceleration", p.acceleration),
                attr_bar("Sprint Speed", p.sprint_speed),
                attr_bar("Stamina", p.stamina),
                attr_bar("Strength", p.strength),
                attr_bar("Jumping", p.jumping),
                attr_bar("Aggression", p.aggression),
            ])
            attrs_text += "\n\n[bold #58a6ff]Mental[/]\n"
            attrs_text += "\n".join([
                attr_bar("Composure", p.composure),
                attr_bar("Reactions", p.reactions),
                attr_bar("Positioning", p.positioning),
            ])

        self.query_one("#player-attrs", Static).update(Panel(
            attrs_text, title="📊 ATTRIBUTES", border_style="#30363d",
        ))

        # Season stats
        stats = session.query(PlayerStats).filter_by(
            player_id=self.player_id
        ).order_by(PlayerStats.season.desc()).first()

        if stats:
            stats_text = (
                f"[dim]Apps:[/] {stats.appearances}  "
                f"[dim]Goals:[/] {stats.goals}  "
                f"[dim]Assists:[/] {stats.assists}\n"
                f"[dim]Yellow:[/] {stats.yellow_cards}  "
                f"[dim]Red:[/] {stats.red_cards}  "
                f"[dim]Avg Rating:[/] {stats.avg_rating:.1f}\n"
                f"[dim]Minutes:[/] {stats.minutes_played}"
            )
        else:
            stats_text = "[dim]No stats recorded yet this season[/]"

        self.query_one("#player-stats", Static).update(Panel(
            stats_text, title="📈 SEASON STATS", border_style="#30363d",
        ))

        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()


# ── Training Screen ───────────────────────────────────────────────────────

class TrainingScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="centered-content"):
            with Horizontal(classes="header-row"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("🏋️ TRAINING", classes="section-title")
            yield Static(id="training-info")
            yield Static(id="squad-fitness")
            yield Label("\n[dim]Training Focus:[/]")
            yield Select(
                [
                    ("⚽ Attacking — Finishing, Shooting, Positioning", "attacking"),
                    ("🛡️ Defending — Marking, Tackling, Interceptions", "defending"),
                    ("💪 Physical — Stamina, Strength, Pace", "physical"),
                    ("🧠 Tactical — Positioning, Vision, Composure", "tactical"),
                    ("🎯 Set Pieces — Free Kicks, Penalties, Heading", "set_pieces"),
                    ("📋 Match Prep — Fitness & Form Recovery", "match_prep"),
                ],
                id="training-select",
            )
            yield Button("💾 Set Training Focus", id="save-training", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self):
        session = get_session()
        club = session.query(Club).get(self.club_id)

        # Current focus
        focus = club.training_focus or "match_prep"
        info = self.query_one("#training-info", Static)

        focus_descriptions = {
            "attacking": "⚽ [bold]Attacking[/] — Develops finishing, shooting, positioning, long shots",
            "defending": "🛡️ [bold]Defending[/] — Develops marking, tackling, interceptions, heading",
            "physical": "💪 [bold]Physical[/] — Develops stamina, strength, pace, acceleration, jumping",
            "tactical": "🧠 [bold]Tactical[/] — Develops positioning, vision, composure, reactions",
            "set_pieces": "🎯 [bold]Set Pieces[/] — Develops free kicks, penalties, heading, curve",
            "match_prep": "📋 [bold]Match Prep[/] — Boosts fitness and form (no attribute growth)",
        }
        desc = focus_descriptions.get(focus, focus)
        info.update(Panel(
            f"Current Focus: {desc}\n\n"
            f"[dim]Training affects all players weekly. Young players (< 24) develop faster.\n"
            f"Harder training drains more fitness. Match Prep recovers fitness.[/]",
            title="🏋️ TRAINING REGIME",
            border_style="#58a6ff",
        ))

        # Pre-populate select
        try:
            self.query_one("#training-select", Select).value = focus
        except Exception:
            pass

        # Squad fitness overview
        players = session.query(Player).filter_by(club_id=self.club_id).all()
        if players:
            avg_fitness = sum(p.fitness or 100 for p in players) / len(players)
            avg_morale = sum(p.morale or 65 for p in players) / len(players)
            injured = [p for p in players if (p.injured_weeks or 0) > 0]
            low_fitness = [p for p in players if (p.fitness or 100) < 70]

            fitness_color = "#2ECC71" if avg_fitness >= 85 else "#F39C12" if avg_fitness >= 70 else "#E74C3C"
            morale_color = "#2ECC71" if avg_morale >= 70 else "#F39C12" if avg_morale >= 50 else "#E74C3C"

            squad_text = (
                f"[dim]Avg Fitness:[/] [{fitness_color}]{avg_fitness:.0f}%[/]    "
                f"[dim]Avg Morale:[/] [{morale_color}]{avg_morale:.0f}[/]\n"
            )
            if injured:
                squad_text += f"\n[#E74C3C]Injured ({len(injured)}):[/]\n"
                for p in injured[:5]:
                    squad_text += f"  🏥 {p.short_name or p.name} — {p.injured_weeks}w remaining\n"
            if low_fitness:
                squad_text += f"\n[#F39C12]Low Fitness ({len(low_fitness)}):[/]\n"
                for p in sorted(low_fitness, key=lambda x: x.fitness or 100)[:5]:
                    squad_text += f"  ⚠️ {p.short_name or p.name} — {p.fitness:.0f}%\n"

            sf = self.query_one("#squad-fitness", Static)
            sf.update(Panel(squad_text.strip(), title="📋 SQUAD STATUS", border_style="#30363d"))

        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-training":
            sel = self.query_one("#training-select", Select)
            if sel.value and sel.value != Select.BLANK:
                session = get_session()
                from fm.world.training import TrainingManager
                tm = TrainingManager(session)
                tm.set_focus(self.club_id, str(sel.value))
                session.commit()
                session.close()
                self._refresh()
        elif event.button.id == "back-btn":
            self.app.pop_screen()


# ── Tactics Screen ─────────────────────────────────────────────────────────

FORMATION_DISPLAY = {
    "4-4-2":     "         ST    ST\n     LM   CM   CM   RM\n     LB   CB   CB   RB\n              GK",
    "4-3-3":     "     LW    ST    RW\n         CM   CM   CM\n     LB   CB   CB   RB\n              GK",
    "4-2-3-1":   "             ST\n     LW   CAM  CAM   RW\n         CDM   CDM\n     LB   CB   CB   RB\n              GK",
    "3-5-2":     "         ST    ST\n     LM  CM  CM  CM  RM\n         CB   CB   CB\n              GK",
    "5-3-2":     "         ST    ST\n         CM   CM   CM\n    LWB  CB  CB  CB  RWB\n              GK",
    "4-1-4-1":   "             ST\n     LM   CM   CM   RM\n            CDM\n     LB   CB   CB   RB\n              GK",
    "3-4-3":     "     LW    ST    RW\n     LM   CM   CM   RM\n         CB   CB   CB\n              GK",
    "4-5-1":     "             ST\n     LM  CM  CM  CM  RM\n     LB   CB   CB   RB\n              GK",
}


class TacticsScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="centered-content"):
            with Horizontal(classes="header-row", id="tactics-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("⚙️ TACTICAL SETUP", classes="section-title")
            yield Static(id="current-tactics")
            yield Static(id="formation-display")
            yield Label("\n[dim]Formation:[/]")
            yield Select(
                [(f, f) for f in FORMATIONS.keys()],
                id="formation-select",
            )
            yield Label("[dim]Mentality:[/]")
            yield Select(
                [(m.replace("_", " ").title(), m) for m in MENTALITY_LEVELS],
                id="mentality-select",
            )
            yield Label("[dim]Tempo:[/]")
            yield Select(
                [(t.replace("_", " ").title(), t) for t in TEMPO_LEVELS],
                id="tempo-select",
            )
            yield Label("[dim]Pressing:[/]")
            yield Select(
                [(p.replace("_", " ").title(), p) for p in PRESSING_LEVELS],
                id="pressing-select",
            )
            yield Label("[dim]Passing Style:[/]")
            yield Select(
                [(ps.replace("_", " ").title(), ps) for ps in PASSING_STYLES],
                id="passing-select",
            )
            yield Label("[dim]Width:[/]")
            yield Select(
                [(w.replace("_", " ").title(), w) for w in WIDTH_LEVELS],
                id="width-select",
            )
            yield Label("[dim]Defensive Line:[/]")
            yield Select(
                [(dl.replace("_", " ").title(), dl) for dl in DEFENSIVE_LINE_LEVELS],
                id="defline-select",
            )
            yield Button("💾 Save Tactics", id="save-tactics", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        setup = session.query(TacticalSetup).filter_by(club_id=self.club_id).first()
        if setup:
            info = self.query_one("#current-tactics", Static)
            info.update(Panel(
                f"[bold]{setup.formation}[/]  │  "
                f"{setup.mentality}  │  {setup.tempo} tempo  │  "
                f"{setup.pressing} press  │  {setup.passing_style} passing",
                title="📋 Current Setup",
                border_style="#30363d",
            ))

            # Show formation diagram
            diagram = FORMATION_DISPLAY.get(setup.formation, "")
            if diagram:
                fd = self.query_one("#formation-display", Static)
                fd.update(Panel(
                    f"[#2ECC71]{diagram}[/]",
                    title=f"⚽ {setup.formation}",
                    border_style="#58a6ff",
                ))

            # Pre-populate selects with current values
            try:
                self.query_one("#formation-select", Select).value = setup.formation
                self.query_one("#mentality-select", Select).value = setup.mentality
                self.query_one("#tempo-select", Select).value = setup.tempo
                self.query_one("#pressing-select", Select).value = setup.pressing
                self.query_one("#passing-select", Select).value = setup.passing_style
                self.query_one("#width-select", Select).value = setup.width
                self.query_one("#defline-select", Select).value = setup.defensive_line
            except Exception:
                pass
        session.close()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "formation-select" and event.value != Select.BLANK:
            diagram = FORMATION_DISPLAY.get(str(event.value), "")
            if diagram:
                fd = self.query_one("#formation-display", Static)
                fd.update(Panel(
                    f"[#2ECC71]{diagram}[/]",
                    title=f"⚽ {event.value}",
                    border_style="#58a6ff",
                ))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-tactics":
            session = get_session()
            setup = session.query(TacticalSetup).filter_by(
                club_id=self.club_id).first()
            if setup:
                _selects = {
                    "formation-select": "formation",
                    "mentality-select": "mentality",
                    "tempo-select": "tempo",
                    "pressing-select": "pressing",
                    "passing-select": "passing_style",
                    "width-select": "width",
                    "defline-select": "defensive_line",
                }
                for widget_id, attr in _selects.items():
                    sel = self.query_one(f"#{widget_id}", Select)
                    if sel.value and sel.value != Select.BLANK:
                        setattr(setup, attr, str(sel.value))
                session.commit()
                info = self.query_one("#current-tactics", Static)
                info.update(Panel(
                    f"[#2ECC71]✅ Saved:[/] [bold]{setup.formation}[/] │ "
                    f"{setup.mentality} │ {setup.tempo} tempo │ "
                    f"{setup.pressing} press │ {setup.passing_style} passing │ "
                    f"{setup.width} width │ {setup.defensive_line} line",
                    title="📋 Current Setup",
                    border_style="#2ECC71",
                ))
            session.close()
        elif event.button.id == "back-btn":
            self.app.pop_screen()


# ── League Table ───────────────────────────────────────────────────────────

class LeagueTableScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal(classes="header-row", id="league-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("📊 LEAGUE TABLE", classes="section-title")
            table = DataTable(id="league-table")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        club = session.query(Club).get(self.club_id)
        season = session.query(Season).order_by(Season.year.desc()).first()

        table = self.query_one("#league-table", DataTable)
        table.add_columns("#", "Club", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Form")

        if club.league_id and season:
            league = session.query(League).get(club.league_id)
            num_teams = 20  # default
            promo = 0
            releg = 3
            from fm.config import LEAGUES_CONFIG
            for lc in LEAGUES_CONFIG:
                if lc["name"] == league.name:
                    num_teams = lc["num_teams"]
                    promo = lc["promo"]
                    releg = lc["releg"]
                    break

            standings = session.query(LeagueStanding).filter_by(
                league_id=club.league_id, season=season.year
            ).order_by(
                LeagueStanding.points.desc(),
                LeagueStanding.goal_difference.desc(),
                LeagueStanding.goals_for.desc(),
            ).all()

            for i, st in enumerate(standings, 1):
                c = session.query(Club).get(st.club_id)
                name = c.name if c else "Unknown"

                # Zone colouring
                if i <= promo:
                    zone_char = "🟢"  # promotion
                elif i > len(standings) - releg:
                    zone_char = "🔴"  # relegation
                else:
                    zone_char = "  "

                # Highlight user's club
                if st.club_id == self.club_id:
                    name = f"[bold #58a6ff]▸ {name}[/]"

                gd = st.goal_difference
                gd_str = f"[#2ECC71]+{gd}[/]" if gd > 0 else f"[#E74C3C]{gd}[/]" if gd < 0 else "0"
                pts_str = f"[bold]{st.points}[/]"
                form_display = _form_chips(st.form)

                table.add_row(
                    f"{zone_char}{i}",
                    name,
                    str(st.played), str(st.won), str(st.drawn), str(st.lost),
                    str(st.goals_for), str(st.goals_against),
                    gd_str, pts_str, form_display,
                )
        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()


# ── Match Preparation Screen ───────────────────────────────────────────────

class MatchPrepScreen(Screen):
    """AI Assistant match preparation report."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("a", "apply_tactics", "Apply Recommended"),
    ]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id
        self._report = None

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="match-prep-view"):
            yield Static(id="prep-header")
            with Horizontal(classes="prep-row"):
                yield Static(id="prep-h2h")
                yield Static(id="prep-opponent")
            with Horizontal(classes="prep-row"):
                yield Static(id="prep-tactics")
                yield Static(id="prep-prediction")
            yield Static(id="prep-form-analysis")
            yield Static(id="prep-opp-recent")
            yield Static(id="prep-lineup")
            yield Static(id="prep-warnings")
            yield Static(id="prep-plan")
            with Horizontal(classes="btn-row"):
                yield Button("📋 Apply Recommended Tactics", id="apply-btn", variant="primary")
                yield Button("◀ Back", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        if not season:
            self.query_one("#prep-header", Static).update(
                Panel("[bold red]No season active[/]", border_style="red")
            )
            return

        next_md = (season.current_matchday or 0) + 1
        fixture = session.query(Fixture).filter(
            Fixture.season == season.year,
            Fixture.matchday == next_md,
            Fixture.played == False,
            (Fixture.home_club_id == self.club_id) |
            (Fixture.away_club_id == self.club_id),
        ).first()

        if not fixture:
            self.query_one("#prep-header", Static).update(
                Panel("[bold #F39C12]No upcoming fixture found[/]",
                      border_style="#F39C12")
            )
            return

        is_home = fixture.home_club_id == self.club_id
        opp_id = fixture.away_club_id if is_home else fixture.home_club_id

        assistant = AssistantManager(session)
        report = assistant.prepare_match_report(
            self.club_id, opp_id, is_home, "league",
        )
        self._report = report
        opp = report.opponent

        # ── Header ──
        venue_badge = "[bold #2ECC71]HOME[/]" if is_home else "[bold #E74C3C]AWAY[/]"
        club = session.get(Club, self.club_id)
        club_name = club.name if club else "Your Team"
        imp_col = {"must_win": "#E74C3C", "high": "#F39C12", "normal": "#58a6ff", "low": "#484f58"}
        self.query_one("#prep-header", Static).update(Panel(
            f"[bold #FFD700]{'━' * 18} MATCH PREPARATION {'━' * 18}[/]\n\n"
            f"  [bold #58a6ff]{club_name}[/]  vs  [bold #E74C3C]{opp.club_name}[/]    {venue_badge}\n"
            f"  Matchday {next_md}  |  "
            f"Importance: [bold {imp_col.get(report.importance, '#58a6ff')}]"
            f"{report.importance.upper()}[/]",
            title="🤖 [bold]AI MATCH ASSISTANT[/]",
            border_style="#FFD700",
        ))

        # ── Head-to-Head ──
        h2h = getattr(report, "head_to_head", None)
        if h2h and h2h.total_matches > 0:
            h2h_text = (
                f"[bold]Record vs {opp.club_name}[/]\n\n"
                f"  Played: [bold]{h2h.total_matches}[/]\n"
                f"  [#2ECC71]Wins: {h2h.wins}[/]  "
                f"[#F39C12]Draws: {h2h.draws}[/]  "
                f"[#E74C3C]Losses: {h2h.losses}[/]\n"
                f"  GF: {h2h.goals_for}  GA: {h2h.goals_against}\n"
            )
            if h2h.recent_results:
                h2h_text += "\n[bold]Recent Meetings:[/]\n"
                for r in h2h.recent_results[:3]:
                    res_col = {"W": "#2ECC71", "D": "#F39C12", "L": "#E74C3C"}.get(r.get("result", ""), "#999")
                    h2h_text += (
                        f"  [{res_col}]{r.get('result', '?')}[/] "
                        f"{r.get('score', '?')}  "
                        f"[dim]{r.get('venue', '')} MD{r.get('matchday', '')}[/]\n"
                    )
        else:
            h2h_text = f"[dim]No previous meetings with {opp.club_name}[/]"

        self.query_one("#prep-h2h", Static).update(Panel(
            h2h_text,
            title="🏆 HEAD TO HEAD",
            border_style="#9B59B6",
        ))

        # ── Opponent profile ──
        form_chips = " ".join(
            f"[bold {'#2ECC71' if c == 'W' else '#E74C3C' if c == 'L' else '#F39C12'}]{c}[/]"
            for c in opp.recent_form
        )
        key_str = "\n".join(
            f"  ⚡ {kp['name']} ({kp['position']}, {kp['overall']}) — {kp['threat']}"
            for kp in opp.key_players[:3]
        )
        strengths_str = "\n".join(f"  [#2ECC71]+ {s}[/]" for s in opp.strengths[:3])
        weak_str = "\n".join(f"  [#E74C3C]- {w}[/]" for w in opp.weaknesses[:3])

        self.query_one("#prep-opponent", Static).update(Panel(
            f"[bold]{opp.club_name}[/] — {_ordinal(opp.league_position)} place\n"
            f"Form: {form_chips}\n"
            f"Formation: [bold]{opp.formation}[/]  |  {opp.mentality} / {opp.pressing}\n"
            f"GF: {opp.goals_scored}  GA: {opp.goals_conceded}\n\n"
            f"[bold]Key Threats:[/]\n{key_str}\n\n"
            f"[bold]Strengths:[/]\n{strengths_str}\n\n"
            f"[bold]Weaknesses:[/]\n{weak_str}",
            title="📊 OPPONENT SCOUTING",
            border_style="#58a6ff",
        ))

        # ── Tactical recommendation ──
        self.query_one("#prep-tactics", Static).update(Panel(
            f"[bold #FFD700]Recommended Setup:[/]\n\n"
            f"  [bold]Formation:[/]   [bold #FFD700]{report.recommended_formation}[/]\n"
            f"  [bold]Mentality:[/]   {report.recommended_mentality}\n"
            f"  [bold]Pressing:[/]    {report.recommended_pressing}\n"
            f"  [bold]Passing:[/]     {report.recommended_passing}\n"
            f"  [bold]Width:[/]       {report.recommended_width}\n"
            f"  [bold]Tempo:[/]       {report.recommended_tempo}\n"
            f"  [bold]Def. Line:[/]   {report.recommended_defensive_line}\n\n"
            f"[bold]Key Battle:[/]\n  {report.key_battle}\n\n"
            f"[bold]Set Pieces:[/]\n  {report.set_piece_advice}",
            title="🎯 TACTICAL PLAN",
            border_style="#2ECC71",
        ))

        # ── Prediction (with visual probability bar) ──
        w_bar = int(report.win_probability * 30)
        d_bar = int(report.draw_probability * 30)
        l_bar = max(0, 30 - w_bar - d_bar)
        prob_bar = (
            f"[#2ECC71]{'█' * w_bar}[/]"
            f"[#F39C12]{'█' * d_bar}[/]"
            f"[#E74C3C]{'█' * l_bar}[/]"
        )
        self.query_one("#prep-prediction", Static).update(Panel(
            f"[bold]Win Probability:[/]\n"
            f"  {prob_bar}\n"
            f"  [#2ECC71]Win {report.win_probability*100:.0f}%[/]  "
            f"[#F39C12]Draw {report.draw_probability*100:.0f}%[/]  "
            f"[#E74C3C]Loss {report.loss_probability*100:.0f}%[/]\n\n"
            f"[bold]Predicted Score:[/] [bold #FFD700]{report.predicted_score}[/]\n\n"
            f"[bold]Team Talk:[/]\n  {report.team_talk_advice}",
            title="🔮 PREDICTION",
            border_style="#9B59B6",
        ))

        # ── Player form analysis ──
        form_data = getattr(report, "player_form_analysis", {})
        in_form = form_data.get("in_form", [])
        out_of_form = form_data.get("out_of_form", [])
        form_text = ""
        if in_form:
            form_text += "[bold #2ECC71]In Form:[/]\n"
            for pf in in_form[:3]:
                form_text += (
                    f"  [#2ECC71]▲[/] {pf.get('name', '?')} ({pf.get('position', '?')}) "
                    f"OVR:{pf.get('overall', 0)}  "
                    f"Morale:{pf.get('morale', 0):.0f}  "
                    f"Fit:{pf.get('fitness', 0):.0f}%\n"
                )
        if out_of_form:
            form_text += "\n[bold #E74C3C]Out of Form:[/]\n"
            for pf in out_of_form[:3]:
                form_text += (
                    f"  [#E74C3C]▼[/] {pf.get('name', '?')} ({pf.get('position', '?')}) "
                    f"OVR:{pf.get('overall', 0)}  "
                    f"Morale:{pf.get('morale', 0):.0f}  "
                    f"Fit:{pf.get('fitness', 0):.0f}%\n"
                )
        if not form_text:
            form_text = "[dim]No form data available yet.[/]"

        self.query_one("#prep-form-analysis", Static).update(Panel(
            form_text.strip(),
            title="📈 SQUAD FORM ANALYSIS",
            border_style="#58a6ff",
        ))

        # ── Opponent recent matches ──
        opp_recent = getattr(report, "opponent_recent_matches", [])
        if opp_recent:
            opp_recent_text = "[bold]Their Last 5 Results:[/]\n"
            for m in opp_recent[:5]:
                res_col = {"W": "#2ECC71", "D": "#F39C12", "L": "#E74C3C"}.get(m.get("result", ""), "#999")
                opp_recent_text += (
                    f"  [{res_col}]{m.get('result', '?')}[/] "
                    f"{m.get('score', '?'):<6} "
                    f"vs {m.get('opponent', '?'):<20} "
                    f"[dim]{m.get('venue', '')}[/]\n"
                )
        else:
            opp_recent_text = "[dim]No recent match data available.[/]"

        self.query_one("#prep-opp-recent", Static).update(Panel(
            opp_recent_text.strip(),
            title=f"📋 {opp.club_name.upper()} RECENT RESULTS",
            border_style="#30363d",
        ))

        # ── Lineup suggestion ──
        if report.suggested_xi:
            xi_lines = "\n".join(
                f"  {_pos_badge(p['position'])} {p['name']:<20} "
                f"OVR:{p['overall']}  Fit:{p['fitness']}%  "
                f"[dim]{p['reason']}[/]"
                for p in report.suggested_xi
            )
            rest_lines = "\n".join(
                f"  ⚠️ {r}" for r in report.rest_recommendations
            )
            lineup_text = f"[bold]Suggested Starting XI:[/]\n{xi_lines}"
            if rest_lines:
                lineup_text += f"\n\n[bold]Rotation Advice:[/]\n{rest_lines}"
        else:
            lineup_text = "[dim]No lineup data available[/]"

        self.query_one("#prep-lineup", Static).update(Panel(
            lineup_text,
            title="👥 LINEUP SUGGESTION",
            border_style="#30363d",
        ))

        # ── Warnings ──
        if report.warnings:
            warn_text = "\n".join(f"  ⚠️ {w}" for w in report.warnings)
        else:
            warn_text = "  [#2ECC71]No concerns — squad looks ready![/]"
        self.query_one("#prep-warnings", Static).update(Panel(
            warn_text,
            title="⚠️ WARNINGS & ALERTS",
            border_style="#F39C12",
        ))

        # ── Full tactical plan narrative ──
        self.query_one("#prep-plan", Static).update(Panel(
            report.tactical_plan,
            title="📝 ASSISTANT'S MATCH BRIEFING",
            border_style="#1f6feb",
        ))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "apply-btn":
            self._apply_recommended()

    def action_apply_tactics(self) -> None:
        self._apply_recommended()

    def _apply_recommended(self) -> None:
        if not self._report:
            return
        r = self._report
        session = get_session()
        ts = session.query(TacticalSetup).filter_by(club_id=self.club_id).first()
        if not ts:
            ts = TacticalSetup(club_id=self.club_id)
            session.add(ts)
        ts.formation = r.recommended_formation
        ts.mentality = r.recommended_mentality
        ts.pressing = r.recommended_pressing
        ts.passing_style = r.recommended_passing
        ts.width = r.recommended_width
        ts.defensive_line = r.recommended_defensive_line
        ts.tempo = r.recommended_tempo
        session.commit()

        btn = self.query_one("#apply-btn", Button)
        btn.label = "✅ Tactics Applied!"
        btn.disabled = True


def _ordinal(n: int) -> str:
    if n == 0:
        return "unranked"
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = suffixes.get(n % 10, "th")
    return f"{n}{suffix}"


# ── Match Day Screen ───────────────────────────────────────────────────────

TEAM_TALK_OPTIONS = [
    ("🔥 Motivate — Fire up the team!", "motivate"),
    ("😌 Calm — Ease the pressure", "calm"),
    ("🎯 Focus — Demand concentration", "focus"),
    ("🙏 No Pressure — Remove expectations", "no_pressure"),
    ("👏 Praise — Show confidence in them", "praise"),
    ("😤 Criticize — Demand more from them", "criticize"),
]

TEAM_TALK_DESCRIPTIONS = {
    "motivate": (
        "[bold #E74C3C]🔥 MOTIVATE[/]\n\n"
        "Fire up the squad and demand intensity!\n\n"
        "[dim]Best when:[/] Morale is middling, big match atmosphere\n"
        "[dim]Risk:[/] Slight fitness cost from adrenaline\n"
        "[dim]Worst when:[/] Team is already fired up"
    ),
    "calm": (
        "[bold #58a6ff]😌 CALM[/]\n\n"
        "Settle nerves and focus on the game plan.\n\n"
        "[dim]Best when:[/] Morale very high (overconfidence) or very low (nerves)\n"
        "[dim]Risk:[/] Low — safe choice\n"
        "[dim]Worst when:[/] Team needs firing up"
    ),
    "focus": (
        "[bold #F39C12]🎯 FOCUS[/]\n\n"
        "Demand total concentration from every player.\n\n"
        "[dim]Best when:[/] Any situation — reliable option\n"
        "[dim]Risk:[/] None\n"
        "[dim]Worst when:[/] Never truly bad"
    ),
    "no_pressure": (
        "[bold #2ECC71]🙏 NO PRESSURE[/]\n\n"
        "Tell them to go out and enjoy the game.\n\n"
        "[dim]Best when:[/] Underdogs, low morale, high-pressure match\n"
        "[dim]Risk:[/] Low\n"
        "[dim]Worst when:[/] You're the favourites and should be winning"
    ),
    "praise": (
        "[bold #9B59B6]👏 PRAISE[/]\n\n"
        "Express confidence in the squad's ability.\n\n"
        "[dim]Best when:[/] After a win, good form\n"
        "[dim]Risk:[/] Low\n"
        "[dim]Worst when:[/] After a bad loss (feels hollow)"
    ),
    "criticize": (
        "[bold #da3633]😤 CRITICIZE[/]\n\n"
        "Demand more effort — no excuses!\n\n"
        "[dim]Best when:[/] After poor performance, complacency\n"
        "[dim]Risk:[/] HIGH — can backfire badly and tank morale\n"
        "[dim]Worst when:[/] After a win, or when morale is fragile"
    ),
}


class PreMatchTalkScreen(Screen):
    """Pre-match team talk — player chooses how to address the squad."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Skip/Continue", show=True),
        Binding("enter", "confirm", "Select/Continue", show=False),
        Binding("c", "dismiss_screen", "Continue", show=False),
    ]

    def __init__(self, club_id: int, home_name: str, away_name: str,
                 is_home: bool, opponent_rep: int):
        super().__init__()
        self.club_id = club_id
        self.home_name = home_name
        self.away_name = away_name
        self.is_home = is_home
        self.opponent_rep = opponent_rep
        self._talk_delivered = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="pre-talk-container"):
            yield Static(id="talk-header")
            yield Static(id="morale-summary")
            yield Static(id="talk-description")
            yield Label("[dim]Choose your team talk (Enter to select):[/]")
            yield OptionList(
                Option("🔥 Motivate — Fire up the team!", id="motivate"),
                Option("😌 Calm — Ease the pressure", id="calm"),
                Option("🎯 Focus — Demand concentration", id="focus"),
                Option("🙏 No Pressure — Remove expectations", id="no_pressure"),
                Option("👏 Praise — Show confidence in them", id="praise"),
                Option("😤 Criticize — Demand more from them", id="criticize"),
                id="talk-options",
            )
            yield Button("⏭ Skip — Say Nothing", id="skip-btn")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        club = session.query(Club).get(self.club_id)
        players = session.query(Player).filter_by(club_id=self.club_id).all()

        avg_morale = sum(p.morale or 65 for p in players) / max(len(players), 1)
        avg_fitness = sum(p.fitness or 100 for p in players) / max(len(players), 1)

        morale_label = (
            "Superb" if avg_morale >= 85 else "Good" if avg_morale >= 70
            else "Decent" if avg_morale >= 55 else "Poor" if avg_morale >= 40
            else "Very Poor"
        )
        morale_col = "#2ECC71" if avg_morale >= 70 else "#F39C12" if avg_morale >= 50 else "#E74C3C"

        venue = "[#2ECC71]HOME[/]" if self.is_home else "[#E74C3C]AWAY[/]"
        opp = self.away_name if self.is_home else self.home_name

        club_rep = club.reputation or 50
        if self.opponent_rep > club_rep + 15:
            matchup = "[#E74C3C]Underdog[/]"
        elif self.opponent_rep < club_rep - 15:
            matchup = "[#2ECC71]Favourite[/]"
        else:
            matchup = "[#F39C12]Even Match[/]"

        header = self.query_one("#talk-header", Static)
        header.update(Panel(
            f"[bold #FFD700]PRE-MATCH TEAM TALK[/]\n\n"
            f"[bold]{self.home_name}[/]  vs  [bold]{self.away_name}[/]\n"
            f"{venue}  |  {matchup}\n\n"
            f"[dim]Address the squad in the dressing room before kickoff.[/]",
            title="🎤 DRESSING ROOM",
            border_style="#FFD700",
        ))

        morale_summary = self.query_one("#morale-summary", Static)
        morale_summary.update(Panel(
            f"[dim]Team Morale:[/] [{morale_col}]{morale_label} ({avg_morale:.0f})[/]\n"
            f"[dim]Squad Fitness:[/] {avg_fitness:.0f}%\n"
            f"[dim]Opponent:[/] {opp} (Rep: {self.opponent_rep})",
            title="📋 SQUAD STATE",
            border_style="#30363d",
        ))
        session.close()

        # Focus the option list so user can immediately interact
        self.query_one("#talk-options", OptionList).focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "talk-options" and event.option.id:
            desc = TEAM_TALK_DESCRIPTIONS.get(event.option.id, "")
            self.query_one("#talk-description", Static).update(Panel(
                desc, title="ℹ️ TALK DETAILS", border_style="#58a6ff",
            ))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Triggered on Enter/double-click on an option — deliver the talk."""
        if event.option_list.id == "talk-options" and event.option.id:
            self._apply_talk(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip-btn":
            self.dismiss()

    def action_dismiss_screen(self) -> None:
        """Escape or 'c' key — always works to leave this screen."""
        self.dismiss()

    def action_confirm(self) -> None:
        """Enter key — select option if not yet delivered, otherwise leave."""
        if self._talk_delivered:
            self.dismiss()
            return
        ol = self.query_one("#talk-options", OptionList)
        if not ol.disabled and ol.highlighted is not None:
            opt = ol.get_option_at_index(ol.highlighted)
            if opt and opt.id:
                self._apply_talk(opt.id)

    def _apply_talk(self, talk_type: str):
        if self._talk_delivered:
            return
        self._talk_delivered = True

        try:
            from fm.world.morale import MoraleManager, TeamTalkType
            session = get_session()
            mm = MoraleManager(session)
            mm.give_team_talk(self.club_id, TeamTalkType(talk_type), context="pre_match")
            session.commit()

            # Show feedback
            players = session.query(Player).filter_by(club_id=self.club_id).all()
            avg_morale = sum(p.morale or 65 for p in players) / max(len(players), 1)
            morale_col = "#2ECC71" if avg_morale >= 70 else "#F39C12" if avg_morale >= 50 else "#E74C3C"
            session.close()
        except Exception:
            avg_morale = 65.0
            morale_col = "#F39C12"

        # Remove the option list entirely so it can't capture keyboard input
        try:
            ol = self.query_one("#talk-options", OptionList)
            ol.remove()
        except Exception:
            pass

        header = self.query_one("#talk-header", Static)
        header.update(Panel(
            f"[bold #2ECC71]Team talk delivered![/]\n\n"
            f"[dim]New morale:[/] [{morale_col}]{avg_morale:.0f}[/]\n\n"
            f"[bold]Press Enter, Escape, or click Head to Pitch[/]",
            title="🎤 DRESSING ROOM",
            border_style="#2ECC71",
        ))

        # Change skip button to continue (always enabled)
        btn = self.query_one("#skip-btn", Button)
        btn.label = "✅ Head to Pitch"
        btn.disabled = False
        btn.focus()


# ── Post-Match Team Talk Screen ───────────────────────────────────────────

class PostMatchTalkScreen(Screen):
    """Post-match team talk — react to the result."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Skip/Continue", show=True),
        Binding("enter", "confirm", "Select/Continue", show=False),
        Binding("c", "dismiss_screen", "Continue", show=False),
    ]

    def __init__(self, club_id: int, goals_for: int, goals_against: int,
                 home_name: str, away_name: str, was_home: bool):
        super().__init__()
        self.club_id = club_id
        self.goals_for = goals_for
        self.goals_against = goals_against
        self.home_name = home_name
        self.away_name = away_name
        self.was_home = was_home
        self._morale_before: float = 0.0
        self._talk_delivered = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="post-talk-container"):
            yield Static(id="result-header")
            yield Static(id="talk-description")
            yield Label("[dim]Address the squad after the match (Enter to select):[/]")
            yield OptionList(
                Option("🔥 Motivate — Fire up the team!", id="motivate"),
                Option("😌 Calm — Ease the pressure", id="calm"),
                Option("🎯 Focus — Demand concentration", id="focus"),
                Option("🙏 No Pressure — Remove expectations", id="no_pressure"),
                Option("👏 Praise — Show confidence in them", id="praise"),
                Option("😤 Criticize — Demand more from them", id="criticize"),
                id="talk-options",
            )
            yield Button("⏭ Skip — Say Nothing", id="skip-btn")
        yield Footer()

    def on_mount(self) -> None:
        gf, ga = self.goals_for, self.goals_against
        if gf > ga:
            result_text = f"[bold #2ECC71]WIN {gf}-{ga}[/]"
            mood = "The players are in good spirits!"
        elif gf < ga:
            result_text = f"[bold #E74C3C]LOSS {gf}-{ga}[/]"
            mood = "Heads are down in the dressing room."
        else:
            result_text = f"[bold #F39C12]DRAW {gf}-{ga}[/]"
            mood = "A mixed atmosphere in the dressing room."

        # Record morale before talk
        session = get_session()
        players = session.query(Player).filter_by(club_id=self.club_id).all()
        self._morale_before = sum(p.morale or 65 for p in players) / max(len(players), 1)
        morale_col = "#2ECC71" if self._morale_before >= 70 else "#F39C12" if self._morale_before >= 50 else "#E74C3C"
        session.close()

        header = self.query_one("#result-header", Static)
        header.update(Panel(
            f"[bold #FFD700]POST-MATCH TEAM TALK[/]\n\n"
            f"{self.home_name}  {result_text}  {self.away_name}\n\n"
            f"[dim]{mood}[/]\n"
            f"[dim]Current morale:[/] [{morale_col}]{self._morale_before:.0f}[/]",
            title="🎤 POST-MATCH",
            border_style="#FFD700",
        ))

        # Focus the option list so user can immediately interact
        self.query_one("#talk-options", OptionList).focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "talk-options" and event.option.id:
            desc = TEAM_TALK_DESCRIPTIONS.get(event.option.id, "")
            self.query_one("#talk-description", Static).update(Panel(
                desc, title="ℹ️ TALK DETAILS", border_style="#58a6ff",
            ))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Triggered on Enter/double-click on an option — deliver the talk."""
        if event.option_list.id == "talk-options" and event.option.id:
            self._apply_talk(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip-btn":
            self.dismiss()

    def action_dismiss_screen(self) -> None:
        """Escape or 'c' key — always works to leave this screen."""
        self.dismiss()

    def action_confirm(self) -> None:
        """Enter key — select option if not yet delivered, otherwise leave."""
        if self._talk_delivered:
            self.dismiss()
            return
        ol = self.query_one("#talk-options", OptionList)
        if not ol.disabled and ol.highlighted is not None:
            opt = ol.get_option_at_index(ol.highlighted)
            if opt and opt.id:
                self._apply_talk(opt.id)

    def _apply_talk(self, talk_type: str):
        if self._talk_delivered:
            return
        self._talk_delivered = True

        try:
            from fm.world.morale import MoraleManager, TeamTalkType
            session = get_session()
            mm = MoraleManager(session)

            if self.goals_for > self.goals_against:
                context = "post_match_win"
            elif self.goals_for < self.goals_against:
                context = "post_match_loss"
            else:
                context = "post_match_draw"

            mm.give_team_talk(self.club_id, TeamTalkType(talk_type), context=context)
            session.commit()

            players = session.query(Player).filter_by(club_id=self.club_id).all()
            avg_morale_after = sum(p.morale or 65 for p in players) / max(len(players), 1)
            morale_col = "#2ECC71" if avg_morale_after >= 70 else "#F39C12" if avg_morale_after >= 50 else "#E74C3C"

            delta = avg_morale_after - self._morale_before
            if delta > 0:
                delta_str = f"[#2ECC71]+{delta:.1f}[/]"
                reaction = "The squad responded well!"
            elif delta < -2:
                delta_str = f"[#E74C3C]{delta:.1f}[/]"
                reaction = "That didn't go down well..."
            else:
                delta_str = f"[#F39C12]{delta:+.1f}[/]"
                reaction = "The players seem unmoved."

            session.close()
        except Exception:
            avg_morale_after = self._morale_before
            morale_col = "#F39C12"
            delta_str = "[#F39C12]+0.0[/]"
            reaction = "The players seem unmoved."

        # Remove the option list entirely so it can't capture keyboard input
        try:
            ol = self.query_one("#talk-options", OptionList)
            ol.remove()
        except Exception:
            pass

        header = self.query_one("#result-header", Static)
        header.update(Panel(
            f"[bold #2ECC71]Team talk delivered![/]\n\n"
            f"[dim]Morale:[/] {self._morale_before:.0f} → [{morale_col}]{avg_morale_after:.0f}[/]  ({delta_str})\n"
            f"[dim]{reaction}[/]\n\n"
            f"[bold]Press Enter, Escape, or click Continue[/]",
            title="🎤 POST-MATCH",
            border_style="#2ECC71",
        ))

        # Change skip button to continue button (always visible and enabled)
        btn = self.query_one("#skip-btn", Button)
        btn.label = "✅ Continue"
        btn.disabled = False
        btn.focus()


# ── Match Day Screen ───────────────────────────────────────────────────────

class MatchDayScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id
        self._commentary_lines: list[str] = []
        self._commentary_index: int = 0
        self._match_result = None
        self._advance_result = None
        self._pre_talk_done = False
        self._post_talk_info = None
        self._post_talk_pending = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ResourceWidget()
        with Vertical(id="match-view"):
            with Horizontal(classes="header-row", id="match-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
            yield Static(id="scoreboard")
            yield Button("▶ Simulate Matchday", id="sim-btn",
                         variant="primary")
            yield Static(id="match-stats-panel")
            yield ScrollableContainer(
                RichLog(id="commentary-log", highlight=True, markup=True),
                id="commentary-container",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._load_fixture_info()

    def _load_fixture_info(self):
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        next_md = (season.current_matchday or 0) + 1

        fixture = session.query(Fixture).filter(
            Fixture.season == season.year,
            Fixture.matchday == next_md,
            Fixture.played == False,
            (Fixture.home_club_id == self.club_id) |
            (Fixture.away_club_id == self.club_id),
        ).first()

        scoreboard = self.query_one("#scoreboard", Static)
        if fixture:
            home = session.query(Club).get(fixture.home_club_id)
            away = session.query(Club).get(fixture.away_club_id)
            scoreboard.update(Panel(
                f"[dim]Matchday {next_md}[/]\n\n"
                f"[bold #58a6ff]{home.name}[/]  [dim]vs[/]  [bold #E74C3C]{away.name}[/]\n\n"
                f"[dim]Press ▶ to begin[/]",
                title="⚽ MATCH DAY",
                border_style="#58a6ff",
            ))
        else:
            sm = SeasonManager(session)
            if sm.is_season_complete():
                session.close()
                self.app.push_screen(SeasonSummaryScreen(self.club_id))
                return
            else:
                scoreboard.update(Panel(
                    f"Matchday {next_md} ready",
                    title="⚽ MATCH DAY",
                ))
        session.close()

    def on_screen_resume(self) -> None:
        """Called when returning from pre/post-match talk screens."""
        if self._pre_talk_done and self._match_result is None:
            # Returning from pre-match talk — start simulation
            self._pre_talk_done = False
            btn = self.query_one("#sim-btn", Button)
            btn.disabled = True
            self.set_timer(0.1, self._simulate)
        elif self._post_talk_pending:
            # Returning from post-match talk — reset for next match
            self._post_talk_pending = False
            self._reset_for_next_match()

    def _reset_for_next_match(self):
        """Reset state and load next fixture."""
        self._match_result = None
        self._advance_result = None
        self._post_talk_info = None
        self._pre_talk_done = False
        self._post_talk_pending = False
        self._commentary_lines = []
        self._commentary_index = 0
        self.query_one("#commentary-log", RichLog).clear()
        self.query_one("#match-stats-panel", Static).update("")
        self._load_fixture_info()
        btn = self.query_one("#sim-btn", Button)
        btn.label = "▶ Simulate Matchday"
        btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "sim-btn":
            if self._match_result is not None:
                # Match done — show post-match talk or go to next match
                info = getattr(self, "_post_talk_info", None)
                if info:
                    self._post_talk_pending = True
                    self._post_talk_info = None
                    self.app.push_screen(PostMatchTalkScreen(
                        self.club_id, info["gf"], info["ga"],
                        info["h_name"], info["a_name"], info["is_home"],
                    ))
                else:
                    # No post-talk info (already done or skipped)
                    self._reset_for_next_match()
                return

            # First click — show pre-match team talk
            event.button.disabled = True
            self._show_pre_match_talk()

    def _show_pre_match_talk(self):
        """Push the pre-match team talk screen before simulating."""
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        if not season:
            session.close()
            btn = self.query_one("#sim-btn", Button)
            btn.disabled = False
            return

        next_md = (season.current_matchday or 0) + 1

        fixture = session.query(Fixture).filter(
            Fixture.season == season.year,
            Fixture.matchday == next_md,
            Fixture.played == False,
            (Fixture.home_club_id == self.club_id) |
            (Fixture.away_club_id == self.club_id),
        ).first()

        if fixture:
            home = session.query(Club).get(fixture.home_club_id)
            away = session.query(Club).get(fixture.away_club_id)
            is_home = fixture.home_club_id == self.club_id
            opp_id = fixture.away_club_id if is_home else fixture.home_club_id
            opp = session.query(Club).get(opp_id)
            opp_rep = opp.reputation or 50 if opp else 50

            self._pre_talk_done = True
            session.close()
            self.app.push_screen(PreMatchTalkScreen(
                self.club_id, home.name, away.name, is_home, opp_rep,
            ))
        else:
            # No human fixture — skip pre-talk and go straight to simulation
            session.close()
            self._pre_talk_done = True
            self.set_timer(0.1, self._simulate)

    def _simulate(self):
        session = get_session()
        sm = SeasonManager(session)
        log = self.query_one("#commentary-log", RichLog)
        scoreboard = self.query_one("#scoreboard", Static)

        log.write("[bold #58a6ff]⚽ Match underway...[/]\n")

        try:
            result = sm.advance_matchday(human_club_id=self.club_id)
        except Exception as e:
            log.write(f"[bold #E74C3C]Error during simulation: {e}[/]\n")
            session.close()
            btn = self.query_one("#sim-btn", Button)
            btn.disabled = False
            btn.label = "▶ Retry Matchday"
            return

        self._advance_result = result

        if result["matches"] == 0:
            # No fixtures to simulate — auto-advance
            log.write("[dim]No fixtures this matchday. Auto-advancing...[/]\n")
            session.close()
            self._reset_for_next_match()
            return

        if result["human_result"]:
            hr = result["human_result"]
            self._match_result = hr

            # Get team names
            hfix = result.get("human_fixture")
            h_name = "Home"
            a_name = "Away"
            if hfix:
                h_club = session.query(Club).get(hfix.home_club_id)
                a_club = session.query(Club).get(hfix.away_club_id)
                h_name = h_club.name if h_club else "Home"
                a_name = a_club.name if a_club else "Away"

            # Store for progressive reveal
            self._commentary_lines = hr.commentary[:]
            self._commentary_index = 0
            self._h_name = h_name
            self._a_name = a_name

            session.close()

            # Show live scoreboard
            scoreboard.update(Panel(
                f"[bold #F39C12]LIVE[/]\n\n"
                f"[bold #58a6ff]{h_name}[/]  "
                f"[bold white on #1f6feb]  {hr.home_goals}  [/]"
                f" — "
                f"[bold white on #da3633]  {hr.away_goals}  [/]"
                f"  [bold #E74C3C]{a_name}[/]",
                title="⚽ MATCH",
                border_style="#F39C12",
            ))

            log.write(f"\n[bold]{'━' * 50}[/]\n")

            # Start progressive commentary reveal
            self._reveal_commentary()
        else:
            log.write(f"Matchday {result['matchday']}: "
                      f"{result['matches']} matches simulated.\n")
            self._show_other_results(session, result)
            session.close()
            btn = self.query_one("#sim-btn", Button)
            btn.disabled = False
            btn.label = "▶ Next Matchday"

    def _reveal_commentary(self):
        """Reveal commentary lines progressively with delays."""
        log = self.query_one("#commentary-log", RichLog)

        # Reveal a batch of lines
        batch_size = 4
        lines_shown = 0

        while (self._commentary_index < len(self._commentary_lines)
               and lines_shown < batch_size):
            line = self._commentary_lines[self._commentary_index]
            log.write(line)
            self._commentary_index += 1
            lines_shown += 1

        if self._commentary_index < len(self._commentary_lines):
            # More lines — schedule next batch with variable delay
            next_line = self._commentary_lines[self._commentary_index]
            if "GOAL" in next_line or "RED CARD" in next_line:
                delay = 0.6
            elif "HALF TIME" in next_line or "FULL TIME" in next_line:
                delay = 0.4
            else:
                delay = 0.15
            self.set_timer(delay, self._reveal_commentary)
        else:
            # All commentary shown — finalize
            self._finalize_match()

    def _finalize_match(self):
        """Show final stats, ratings, and other results after commentary."""
        hr = self._match_result
        result = self._advance_result
        if not hr or not result:
            return

        session = get_session()
        log = self.query_one("#commentary-log", RichLog)
        scoreboard = self.query_one("#scoreboard", Static)
        stats_panel = self.query_one("#match-stats-panel", Static)

        h_name = getattr(self, "_h_name", "Home")
        a_name = getattr(self, "_a_name", "Away")
        hs = hr.home_stats
        aws = hr.away_stats

        # Final scoreboard
        scoreboard.update(Panel(
            f"[bold #FFD700]FULL TIME[/]\n\n"
            f"[bold #58a6ff]{h_name}[/]  "
            f"[bold white on #1f6feb]  {hr.home_goals}  [/]"
            f" — "
            f"[bold white on #da3633]  {hr.away_goals}  [/]"
            f"  [bold #E74C3C]{a_name}[/]\n\n"
            f"[dim]xG: {hr.home_xg:.2f} — {hr.away_xg:.2f}[/]"
            + (f"\n[#FFD700]⭐ MOTM: {hr.motm.name} ({hr.motm.avg_rating:.1f})[/]"
               if hr.motm else ""),
            title="⚽ RESULT",
            border_style="#FFD700",
        ))

        # Stats bars
        stats_lines = "\n".join([
            _stat_bar("Possession", f"{hs.possession:.0f}%", f"{aws.possession:.0f}%"),
            _stat_bar("Shots", hs.shots, aws.shots),
            _stat_bar("On Target", hs.shots_on_target, aws.shots_on_target),
            _stat_bar("xG", f"{hs.xg:.2f}", f"{aws.xg:.2f}"),
            _stat_bar("Passes", hs.passes, aws.passes),
            _stat_bar("Pass Acc", f"{hs.pass_accuracy:.0f}%", f"{aws.pass_accuracy:.0f}%"),
            _stat_bar("Tackles", hs.tackles_won, aws.tackles_won),
            _stat_bar("Corners", hs.corners, aws.corners),
            _stat_bar("Fouls", hs.fouls, aws.fouls),
            _stat_bar("Woodwork", hs.woodwork, aws.woodwork) if hs.woodwork or aws.woodwork else "",
            _stat_bar("Offsides", hs.offsides, aws.offsides) if hs.offsides or aws.offsides else "",
            _stat_bar("Saves", hs.saves, aws.saves),
        ])
        stats_panel.update(Panel(
            stats_lines.strip(),
            title="📊 MATCH STATS",
            border_style="#30363d",
        ))

        # Player ratings
        log.write(f"\n[bold #58a6ff]Player Ratings:[/]\n")
        for side_label, lineup in [(h_name, hr.home_lineup), (a_name, hr.away_lineup)]:
            log.write(f"\n[bold]{side_label}[/]\n")
            rated = sorted(lineup, key=lambda p: p.avg_rating, reverse=True)
            for p in rated[:11]:
                r = p.avg_rating
                col = "#2ECC71" if r >= 7.5 else "#F39C12" if r >= 6.5 else "#E74C3C"
                stats_str = ""
                if p.goals:
                    stats_str += f" ⚽{p.goals}"
                if p.assists:
                    stats_str += f" 🅰️{p.assists}"
                if p.yellow_cards:
                    stats_str += " 🟨"
                log.write(
                    f"  {_pos_badge(p.position)} {p.name:<15} "
                    f"[{col}]{r:.1f}[/]{stats_str}\n"
                )

        # Other results
        self._show_other_results(session, result)

        session.close()

        btn = self.query_one("#sim-btn", Button)
        btn.disabled = False
        btn.label = "🎤 Post-Match Talk"

        # Store info for post-match talk
        hfix = result.get("human_fixture")
        if hfix:
            is_home = hfix.home_club_id == self.club_id
            self._post_talk_info = {
                "gf": hr.home_goals if is_home else hr.away_goals,
                "ga": hr.away_goals if is_home else hr.home_goals,
                "h_name": h_name,
                "a_name": a_name,
                "is_home": is_home,
            }
        else:
            self._post_talk_info = None

    def _show_other_results(self, session, result):
        """Display results from other matches this matchday."""
        log = self.query_one("#commentary-log", RichLog)
        md = result["matchday"]
        season_obj = session.query(Season).order_by(Season.year.desc()).first()
        other_fixtures = session.query(Fixture).filter(
            Fixture.season == season_obj.year,
            Fixture.matchday == md,
            Fixture.played == True,
        ).all()

        if other_fixtures:
            other_lines = []
            for f in other_fixtures:
                if f.home_club_id == self.club_id or f.away_club_id == self.club_id:
                    continue
                h_club = session.query(Club).get(f.home_club_id)
                a_club = session.query(Club).get(f.away_club_id)
                h_name_short = (h_club.short_name or h_club.name)[:15] if h_club else "?"
                a_name_short = (a_club.short_name or a_club.name)[:15] if a_club else "?"
                other_lines.append(
                    f"{h_name_short} {f.home_goals}-{f.away_goals} {a_name_short}"
                )
            if other_lines:
                rows = []
                for i in range(0, len(other_lines), 3):
                    rows.append(" | ".join(other_lines[i:i+3]))
                other_text = "\n".join(rows)
                log.write(f"\n[bold #58a6ff]Other Results:[/]\n{other_text}\n")


# ── Transfer Screen ────────────────────────────────────────────────────────

class TransferScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal(classes="header-row", id="transfers-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("💼 TRANSFER MARKET", classes="section-title")
            with Horizontal():
                yield Input(placeholder="Search player name...", id="search-input")
                yield Select(
                    [("All Positions", "all"), ("GK", "GK"),
                     ("DEF", "DEF"), ("MID", "MID"), ("FWD", "FWD")],
                    id="pos-filter", value="all",
                )
                yield Button("🔍 Search", id="search-btn", variant="primary")
            table = DataTable(id="transfer-table")
            table.cursor_type = "row"
            yield table
            yield Static(id="transfer-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#transfer-table", DataTable)
        table.add_columns("Pos", "Name", "Age", "OVR", "Club", "Value", "Wage")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-btn":
            self._search()
        elif event.button.id == "back-btn":
            self.app.pop_screen()

    def _search(self):
        search_input = self.query_one("#search-input", Input)
        pos_filter = self.query_one("#pos-filter", Select)
        query = search_input.value.strip()
        pos_val = str(pos_filter.value) if pos_filter.value != Select.BLANK else "all"

        session = get_session()
        table = self.query_one("#transfer-table", DataTable)
        table.clear()

        q = session.query(Player).filter(Player.club_id != self.club_id)
        if query:
            q = q.filter(Player.name.ilike(f"%{query}%"))
        if pos_val != "all":
            if pos_val == "DEF":
                q = q.filter(Player.position.in_(["CB", "LB", "RB", "LWB", "RWB"]))
            elif pos_val == "MID":
                q = q.filter(Player.position.in_(["CDM", "CM", "CAM", "LM", "RM"]))
            elif pos_val == "FWD":
                q = q.filter(Player.position.in_(["LW", "RW", "CF", "ST"]))
            else:
                q = q.filter(Player.position == pos_val)

        players = q.order_by(Player.overall.desc()).limit(50).all()

        for p in players:
            club = session.query(Club).get(p.club_id) if p.club_id else None
            pos_col = POS_COLOURS.get(p.position, "#999")
            table.add_row(
                Text(p.position, style=f"bold {pos_col}"),
                (p.short_name or p.name)[:25],
                str(p.age),
                str(p.overall),
                (club.name if club else "Free Agent")[:20],
                f"€{p.market_value:.1f}M" if p.market_value else "€0.0M",
                f"€{p.wage:.0f}K" if p.wage else "€0K",
                key=str(p.id),
            )
        session.close()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        player_id = int(str(event.row_key.value))
        session = get_session()
        from fm.world.transfer_market import TransferMarket
        tm = TransferMarket(session)
        player = session.query(Player).get(player_id)
        if player:
            value = tm.calculate_market_value(player)
            bid = value * 1.1
            season_obj = session.query(Season).order_by(Season.year.desc()).first()
            success = tm.make_bid(self.club_id, player_id, bid,
                                  season_obj.year if season_obj else STARTING_SEASON)
            status = self.query_one("#transfer-status", Static)
            if success:
                session.commit()
                status.update(
                    f"[#2ECC71]✅ Signed {player.name} for €{bid:.1f}M![/]"
                )
            else:
                status.update(
                    f"[#E74C3C]❌ Bid of €{bid:.1f}M rejected for {player.name}[/]"
                )
        session.close()


# ── News Screen ────────────────────────────────────────────────────────────

class NewsScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal(classes="header-row", id="news-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("📰 NEWS FEED", classes="section-title")
            yield ScrollableContainer(
                RichLog(id="news-log", highlight=True, markup=True),
            )
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        log = self.query_one("#news-log", RichLog)

        news = session.query(NewsItem).order_by(NewsItem.id.desc()).limit(30).all()
        if not news:
            log.write("[dim]No news yet. Play some matches![/]")
        else:
            for item in news:
                category_emoji = {
                    "transfer": "💼", "match": "⚽", "injury": "🏥",
                    "manager": "👔", "finance": "💰", "general": "📰",
                    "award": "🏆",
                }.get(item.category, "📰")
                log.write(f"{category_emoji} [bold]{item.headline}[/]")
                if item.body:
                    log.write(f"   [dim]{item.body}[/]\n")
                log.write("")
        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()


# ── Scout Screen ───────────────────────────────────────────────────────────

class ScoutScreen(Screen):
    """Scouting and player discovery."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id
        self._last_reports: list = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal(classes="header-row", id="scout-header"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("🔎 SCOUTING NETWORK", classes="section-title")
            with Horizontal():
                yield Button("⭐ Wonderkids", id="search-wonderkids",
                             variant="primary")
                yield Button("💰 Bargains", id="search-bargains",
                             variant="success")
                yield Button("📋 Free Agents", id="search-free-agents",
                             variant="warning")
                yield Select(
                    [("By Position...", "none"),
                     ("GK", "GK"),
                     ("CB", "CB"), ("LB", "LB"), ("RB", "RB"),
                     ("CDM", "CDM"), ("CM", "CM"), ("CAM", "CAM"),
                     ("LW", "LW"), ("RW", "RW"), ("ST", "ST"), ("CF", "CF"),
                     ("DEF (all)", "DEF"), ("MID (all)", "MID"),
                     ("FWD (all)", "FWD")],
                    id="pos-scout-filter", value="none",
                )
                yield Button("🔍 Search Position", id="search-position")
            table = DataTable(id="scout-table")
            table.cursor_type = "row"
            yield table
            yield Static(id="scout-detail")
            yield Static(id="scout-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#scout-table", DataTable)
        table.add_columns(
            "Pos", "Name", "Age", "OVR*", "POT*", "Club",
            "Value*", "Recommendation",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "search-wonderkids":
            self._do_search("wonderkids")
        elif event.button.id == "search-bargains":
            self._do_search("bargains")
        elif event.button.id == "search-free-agents":
            self._do_search("free_agents")
        elif event.button.id == "search-position":
            pos_filter = self.query_one("#pos-scout-filter", Select)
            pos_val = str(pos_filter.value) if pos_filter.value != Select.BLANK else "none"
            if pos_val != "none":
                self._do_search("position", position=pos_val)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Auto-search when a position is selected from the dropdown."""
        if event.select.id == "pos-scout-filter" and event.value != Select.BLANK:
            pos_val = str(event.value)
            if pos_val != "none":
                self._do_search("position", position=pos_val)

    def _do_search(self, search_type: str, position: str = "") -> None:
        from fm.world.scouting import ScoutingManager

        session = get_session()
        sm = ScoutingManager(session)

        # Calculate squad average for recommendations
        players = session.query(Player).filter_by(club_id=self.club_id).all()
        squad_avg = (
            sum(p.overall or 0 for p in players) / max(len(players), 1)
        )

        if search_type == "wonderkids":
            reports = sm.search_wonderkids(
                max_age=21, min_potential=80, max_results=25,
                scout_quality=70, squad_avg=squad_avg,
            )
        elif search_type == "bargains":
            reports = sm.search_bargains(
                max_value=10.0, min_overall=68, max_results=25,
                scout_quality=70, squad_avg=squad_avg,
            )
        elif search_type == "free_agents":
            reports = sm.search_free_agents(
                min_overall=55, max_results=25,
                scout_quality=70, squad_avg=squad_avg,
            )
        elif search_type == "position":
            reports = sm.search_by_position(
                position=position, min_overall=60, max_results=25,
                scout_quality=70, squad_avg=squad_avg,
            )
        else:
            reports = []

        self._last_reports = reports
        self._populate_table(reports)
        session.close()

    def _populate_table(self, reports) -> None:
        table = self.query_one("#scout-table", DataTable)
        table.clear()

        for r in reports:
            pos_col = POS_COLOURS.get(r.position, "#999")

            # Colour-code OVR estimate
            ovr = r.overall_estimate
            if ovr >= 80:
                ovr_style = "bold #2ECC71"
            elif ovr >= 70:
                ovr_style = "#F39C12"
            else:
                ovr_style = ""

            # Colour-code recommendation
            rec = r.recommendation
            if "immediately" in rec.lower() or "major upgrade" in rec.lower():
                rec_col = "#2ECC71"
            elif "good" in rec.lower() or "strong" in rec.lower() or "great" in rec.lower():
                rec_col = "#58a6ff"
            elif "not worth" in rec.lower() or "below" in rec.lower():
                rec_col = "#E74C3C"
            else:
                rec_col = "#c9d1d9"

            table.add_row(
                Text(r.position, style=f"bold {pos_col}"),
                r.player_name[:25],
                str(r.age),
                Text(str(ovr), style=ovr_style),
                str(r.potential_estimate),
                (r.club_name or "Free Agent")[:20],
                f"€{r.estimated_value:.1f}M",
                Text(rec[:35], style=rec_col),
                key=str(r.player_id),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        player_id = int(str(event.row_key.value))

        # Find the report from our cached list
        report = None
        for r in self._last_reports:
            if r.player_id == player_id:
                report = r
                break

        if not report:
            return

        detail = self.query_one("#scout-detail", Static)

        # Format strengths and weaknesses
        strengths_str = ", ".join(report.key_strengths) if report.key_strengths else "None identified"
        weaknesses_str = ", ".join(report.key_weaknesses) if report.key_weaknesses else "None identified"

        # Accuracy indicator
        acc = report.accuracy
        if acc >= 0.8:
            acc_label = "[#2ECC71]High[/]"
        elif acc >= 0.5:
            acc_label = "[#F39C12]Medium[/]"
        else:
            acc_label = "[#E74C3C]Low[/]"

        pos_col = POS_COLOURS.get(report.position, "#999")

        # Colour the recommendation
        rec = report.recommendation
        if "immediately" in rec.lower() or "major upgrade" in rec.lower():
            rec_display = f"[bold #2ECC71]{rec}[/]"
        elif "not worth" in rec.lower() or "below" in rec.lower():
            rec_display = f"[#E74C3C]{rec}[/]"
        else:
            rec_display = f"[#58a6ff]{rec}[/]"

        detail.update(Panel(
            f"[bold {pos_col}]{report.position}[/]  "
            f"[bold]{report.player_name}[/]  "
            f"Age {report.age}\n\n"
            f"[dim]Club:[/] {report.club_name}    "
            f"[dim]Wage:[/] €{report.wage:.0f}K/wk\n"
            f"[dim]Est. Overall:[/] [bold]{report.overall_estimate}[/]    "
            f"[dim]Est. Potential:[/] [bold]{report.potential_estimate}[/]    "
            f"[dim]Est. Value:[/] [bold]€{report.estimated_value:.1f}M[/]\n"
            f"[dim]Report Accuracy:[/] {acc_label}\n\n"
            f"[#2ECC71]Strengths:[/] {strengths_str}\n"
            f"[#E74C3C]Weaknesses:[/] {weaknesses_str}\n\n"
            f"[dim]Recommendation:[/] {rec_display}\n\n"
            f"[dim]Select again (Enter) to make a bid.[/]",
            title="🔎 SCOUT REPORT",
            border_style="#58a6ff",
        ))

        # If detail is already showing for this player, make a bid on second select
        status = self.query_one("#scout-status", Static)
        if hasattr(self, "_selected_player_id") and self._selected_player_id == player_id:
            self._make_bid(player_id, report)
        else:
            self._selected_player_id = player_id
            status.update(
                f"[dim]Press Enter again on {report.player_name} to make a bid.[/]"
            )

    def _make_bid(self, player_id: int, report) -> None:
        """Attempt to sign the selected player."""
        from fm.world.transfer_market import TransferMarket

        session = get_session()
        tm = TransferMarket(session)
        player = session.query(Player).get(player_id)
        status = self.query_one("#scout-status", Static)

        if not player:
            status.update("[#E74C3C]Player not found.[/]")
            session.close()
            return

        if player.club_id is None:
            # Free agent signing
            season_obj = session.query(Season).order_by(Season.year.desc()).first()
            wage = player.wage if player.wage else 5.0
            success = tm.sign_free_agent(
                self.club_id, player_id, wage,
                season_obj.year if season_obj else STARTING_SEASON,
            )
            if success:
                session.commit()
                status.update(
                    f"[#2ECC71]Signed {report.player_name} on a free transfer! "
                    f"Wage: €{wage:.0f}K/wk[/]"
                )
            else:
                status.update(
                    f"[#E74C3C]Could not sign {report.player_name}.[/]"
                )
        else:
            # Make a bid at 110% of estimated value
            bid = report.estimated_value * 1.1
            season_obj = session.query(Season).order_by(Season.year.desc()).first()
            success = tm.make_bid(
                self.club_id, player_id, bid,
                season_obj.year if season_obj else STARTING_SEASON,
            )
            if success:
                session.commit()
                status.update(
                    f"[#2ECC71]Signed {report.player_name} for "
                    f"€{bid:.1f}M![/]"
                )
            else:
                status.update(
                    f"[#E74C3C]Bid of €{bid:.1f}M rejected for "
                    f"{report.player_name}.[/]"
                )

        # Reset selection so next Enter re-shows detail
        self._selected_player_id = None
        session.close()


# ── League Stats Screen (Golden Boot) ─────────────────────────────────

class LeagueStatsScreen(Screen):
    """Top scorers, assists, clean sheets for the league."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="centered-content"):
            with Horizontal(classes="header-row"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("🏆 LEAGUE STATS", classes="section-title")
            yield Static(id="top-scorers-panel")
            yield Static(id="top-assists-panel")
            yield Static(id="top-rated-panel")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        if not season:
            session.close()
            return

        # Top 20 Scorers
        scorers = (session.query(PlayerStats, Player)
                   .join(Player, PlayerStats.player_id == Player.id)
                   .filter(PlayerStats.season == season.year,
                           PlayerStats.goals > 0)
                   .order_by(PlayerStats.goals.desc())
                   .limit(20).all())

        scorer_lines = []
        for i, (ps, p) in enumerate(scorers, 1):
            club = session.query(Club).get(p.club_id) if p.club_id else None
            club_name = (club.short_name or club.name)[:15] if club else "?"
            scorer_lines.append(
                f"  {i:>2}. {_pos_badge(p.position)} {(p.short_name or p.name):<20} "
                f"[dim]{club_name:<15}[/] [bold #FFD700]{ps.goals} goals[/]"
            )
        scorers_panel = self.query_one("#top-scorers-panel", Static)
        scorers_panel.update(Panel(
            "\n".join(scorer_lines) if scorer_lines else "[dim]No goals scored yet[/]",
            title="⚽ TOP SCORERS",
            border_style="#FFD700",
        ))

        # Top 20 Assists
        assisters = (session.query(PlayerStats, Player)
                     .join(Player, PlayerStats.player_id == Player.id)
                     .filter(PlayerStats.season == season.year,
                             PlayerStats.assists > 0)
                     .order_by(PlayerStats.assists.desc())
                     .limit(20).all())

        assist_lines = []
        for i, (ps, p) in enumerate(assisters, 1):
            club = session.query(Club).get(p.club_id) if p.club_id else None
            club_name = (club.short_name or club.name)[:15] if club else "?"
            assist_lines.append(
                f"  {i:>2}. {_pos_badge(p.position)} {(p.short_name or p.name):<20} "
                f"[dim]{club_name:<15}[/] [bold #2ECC71]{ps.assists} assists[/]"
            )
        assists_panel = self.query_one("#top-assists-panel", Static)
        assists_panel.update(Panel(
            "\n".join(assist_lines) if assist_lines else "[dim]No assists yet[/]",
            title="🅰️ TOP ASSISTS",
            border_style="#2ECC71",
        ))

        # Top 20 Rated
        rated = (session.query(PlayerStats, Player)
                 .join(Player, PlayerStats.player_id == Player.id)
                 .filter(PlayerStats.season == season.year,
                         PlayerStats.appearances >= 3)
                 .order_by(PlayerStats.avg_rating.desc())
                 .limit(20).all())

        rated_lines = []
        for i, (ps, p) in enumerate(rated, 1):
            club = session.query(Club).get(p.club_id) if p.club_id else None
            club_name = (club.short_name or club.name)[:15] if club else "?"
            r = ps.avg_rating or 0
            col = "#2ECC71" if r >= 7.5 else "#F39C12" if r >= 6.5 else "#E74C3C"
            rated_lines.append(
                f"  {i:>2}. {_pos_badge(p.position)} {(p.short_name or p.name):<20} "
                f"[dim]{club_name:<15}[/] [{col}]{r:.2f}[/]"
            )
        rated_panel = self.query_one("#top-rated-panel", Static)
        rated_panel.update(Panel(
            "\n".join(rated_lines) if rated_lines else "[dim]Not enough data yet[/]",
            title="⭐ TOP RATED PLAYERS",
            border_style="#58a6ff",
        ))

        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()


# ── Fixture Results Screen ────────────────────────────────────────────

class FixtureResultsScreen(Screen):
    """View played fixtures and results."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal(classes="header-row"):
                yield Button("◀ Back", id="back-btn", classes="back-btn")
                yield Label("📅 FIXTURE RESULTS", classes="section-title")
            yield ScrollableContainer(
                Static(id="fixtures-content"),
            )
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        club = session.query(Club).get(self.club_id)
        if not season or not club:
            session.close()
            return

        current_md = season.current_matchday or 0
        content_parts = []

        # Show last 5 matchdays of results
        start_md = max(1, current_md - 4)
        for md in range(current_md, start_md - 1, -1):
            fixtures = session.query(Fixture).filter(
                Fixture.season == season.year,
                Fixture.matchday == md,
                Fixture.played == True,
                Fixture.league_id == club.league_id,
            ).all()

            if not fixtures:
                continue

            result_lines = []
            for f in fixtures:
                h_club = session.query(Club).get(f.home_club_id)
                a_club = session.query(Club).get(f.away_club_id)
                h_name = (h_club.name if h_club else "?")[:20]
                a_name = (a_club.name if a_club else "?")[:20]
                is_user = (f.home_club_id == self.club_id
                           or f.away_club_id == self.club_id)
                prefix = "[bold #58a6ff]▸ " if is_user else "  "
                suffix = "[/]" if is_user else ""
                result_lines.append(
                    f"{prefix}{h_name:<20} {f.home_goals:>2} - {f.away_goals:<2} "
                    f"{a_name}{suffix}"
                )

            content_parts.append(Panel(
                "\n".join(result_lines),
                title=f"Matchday {md}",
                border_style="#30363d",
            ))

        widget = self.query_one("#fixtures-content", Static)
        if content_parts:
            widget.update(Group(*content_parts))
        else:
            widget.update(Panel(
                "[dim]No played fixtures yet[/]",
                title="📅 Results",
                border_style="#30363d",
            ))

        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()


# ── Season Summary Screen ────────────────────────────────────────────

class SeasonSummaryScreen(Screen):
    """End-of-season summary: winner, relegation, top scorer, your position."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="centered-content"):
            yield Static(id="season-summary")
            yield Button("▶ Continue to Next Season", id="continue-btn",
                         variant="primary")
            yield Button("◀ Back to Dashboard", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        session = get_session()
        season = session.query(Season).order_by(Season.year.desc()).first()
        club = session.query(Club).get(self.club_id)
        league = session.query(League).get(club.league_id) if club and club.league_id else None

        parts = []
        parts.append(f"[bold #FFD700]🏆 SEASON {season.year}/{season.year + 1} SUMMARY[/]\n")

        if league:
            standings = session.query(LeagueStanding).filter_by(
                league_id=league.id, season=season.year
            ).order_by(
                LeagueStanding.points.desc(),
                LeagueStanding.goal_difference.desc(),
            ).all()

            if standings:
                champ = session.query(Club).get(standings[0].club_id)
                parts.append(f"[bold #FFD700]🥇 Champion:[/] {champ.name if champ else '?'} "
                             f"({standings[0].points} pts)\n")

                from fm.config import LEAGUES_CONFIG
                releg = 3
                for lc in LEAGUES_CONFIG:
                    if lc["name"] == league.name:
                        releg = lc["releg"]
                        break
                if releg > 0:
                    relegated = standings[-releg:]
                    rel_names = []
                    for st in relegated:
                        c = session.query(Club).get(st.club_id)
                        rel_names.append(c.name if c else "?")
                    parts.append(f"[#E74C3C]🔻 Relegated:[/] {', '.join(rel_names)}\n")

                my_pos = None
                my_st = None
                for i, st in enumerate(standings, 1):
                    if st.club_id == self.club_id:
                        my_pos = i
                        my_st = st
                        break
                if my_pos and my_st:
                    parts.append(
                        f"\n[bold #58a6ff]📊 Your finish: #{my_pos}[/]  "
                        f"P: {my_st.played}  W: {my_st.won}  D: {my_st.drawn}  "
                        f"L: {my_st.lost}  GD: {my_st.goal_difference:+d}  "
                        f"Pts: [bold]{my_st.points}[/]\n"
                    )

        top_scorer = (session.query(PlayerStats, Player)
                      .join(Player, PlayerStats.player_id == Player.id)
                      .filter(PlayerStats.season == season.year,
                              PlayerStats.goals > 0)
                      .order_by(PlayerStats.goals.desc())
                      .first())
        if top_scorer:
            ps, p = top_scorer
            sc_club = session.query(Club).get(p.club_id) if p.club_id else None
            parts.append(
                f"\n[bold #FFD700]⚽ Top Scorer:[/] {p.name} "
                f"({sc_club.name if sc_club else '?'}) — {ps.goals} goals"
            )

        top_assist = (session.query(PlayerStats, Player)
                      .join(Player, PlayerStats.player_id == Player.id)
                      .filter(PlayerStats.season == season.year,
                              PlayerStats.assists > 0)
                      .order_by(PlayerStats.assists.desc())
                      .first())
        if top_assist:
            ps, p = top_assist
            as_club = session.query(Club).get(p.club_id) if p.club_id else None
            parts.append(
                f"[bold #2ECC71]🅰️ Top Assists:[/] {p.name} "
                f"({as_club.name if as_club else '?'}) — {ps.assists} assists"
            )

        summary = self.query_one("#season-summary", Static)
        summary.update(Panel(
            "\n".join(parts),
            title="🏆 SEASON SUMMARY",
            border_style="#FFD700",
        ))
        session.close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "continue-btn":
            session = get_session()
            sm = SeasonManager(session)
            sm.end_season()
            session.commit()
            session.close()
            self.app.pop_screen()


# ── The App ────────────────────────────────────────────────────────────────

class FootballManagerApp(App):
    """The main Textual TUI application."""

    CSS = APP_CSS
    TITLE = "Terminal Football Manager"
    SUB_TITLE = "⚽ Season 2024/25 — Enhanced Stats"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())
