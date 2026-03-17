"""New screens for expanded game systems.

Provides FinanceScreen, BoardRoomScreen, YouthAcademyScreen,
PlayerDynamicsScreen, ContractScreen, AnalyticsScreen, and StaffScreen.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Button, DataTable, Label
from textual.screen import Screen
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel
from rich.table import Table as RichTable

from fm.db.database import get_session
from fm.db.models import (
    Club, Player, League, LeagueStanding, Season, Staff,
    Contract, YouthCandidate, Fixture, PlayerStats,
)


# ── Colour constants (matching app.py) ────────────────────────────────────

GREEN = "#2ECC71"
AMBER = "#F39C12"
RED = "#E74C3C"
ACCENT = "#58a6ff"
BORDER = "#30363d"
PANEL_BG = "#161b22"
SCREEN_BG = "#0d1117"


# ── Helper functions ──────────────────────────────────────────────────────

def _colour_value(value: float, thresholds: tuple = (70, 40)) -> str:
    """Return a Rich colour string based on value thresholds (high/mid)."""
    high, mid = thresholds
    if value >= high:
        return GREEN
    elif value >= mid:
        return AMBER
    return RED


def _fmt_currency(amount: float | None) -> str:
    """Format a monetary value for display."""
    if amount is None:
        return "N/A"
    if abs(amount) >= 1.0:
        return f"\u20ac{amount:.1f}M"
    return f"\u20ac{amount * 1000:.0f}K"


def _ordinal(n: int) -> str:
    """Return ordinal string for a number (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _bar(value: float, max_val: float = 100.0, width: int = 20) -> str:
    """Render a simple text bar."""
    ratio = max(0.0, min(1.0, value / max_val))
    filled = int(ratio * width)
    colour = _colour_value(value)
    return f"[{colour}]{'█' * filled}[/][dim]{'░' * (width - filled)}[/]"


def _get_current_season(session) -> Season | None:
    """Return the most recent Season row."""
    return session.query(Season).order_by(Season.year.desc()).first()


# ══════════════════════════════════════════════════════════════════════════
#  1. FinanceScreen
# ══════════════════════════════════════════════════════════════════════════

class FinanceScreen(Screen):
    """Detailed financial overview: revenue, expenses, P&L, wage ratio."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("FINANCE OVERVIEW", classes="section-title")
            with ScrollableContainer():
                yield Static(id="finance-summary")
                yield Static(id="revenue-panel")
                yield Static(id="expense-panel")
                yield Static(id="projection-panel")
                yield Static(id="ffp-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def _refresh(self) -> None:
        session = get_session()
        try:
            club = session.get(Club, self.club_id)
            if not club:
                return
            season = _get_current_season(session)
            season_year = season.year if season else 2024

            from fm.world.finance import (
                RevenueManager, ExpenseManager, FinancialHealthMonitor,
            )
            rev = RevenueManager(session)
            exp = ExpenseManager(session)
            health = FinancialHealthMonitor(session)

            report = health.get_financial_report(self.club_id, season_year)
            projection = health.project_finances(self.club_id, months=6)
            ffp = health.check_ffp_compliance(self.club_id, season_year)

            # -- Summary panel --
            budget = club.budget or 0
            budget_col = GREEN if budget > 0 else RED
            net = report.get("net_result", 0)
            net_col = GREEN if net >= 0 else RED
            wtr = report.get("wage_to_revenue_ratio", 0)
            wtr_col = GREEN if wtr < 0.60 else AMBER if wtr < 0.70 else RED

            summary_text = (
                f"[dim]Transfer Budget:[/]  [{budget_col}][bold]{_fmt_currency(budget)}[/][/]\n"
                f"[dim]Net Result (Season):[/]  [{net_col}][bold]{_fmt_currency(net)}[/][/]\n"
                f"[dim]Wage / Revenue Ratio:[/]  [{wtr_col}][bold]{wtr:.0%}[/][/]\n"
                f"[dim]Cash in Bank:[/]  [bold]{_fmt_currency(report.get('cash_in_bank', 0))}[/]"
            )
            self.query_one("#finance-summary", Static).update(Panel(
                summary_text,
                title=f"[bold]FINANCIAL SUMMARY  --  {club.name}[/]",
                border_style=ACCENT,
            ))

            # -- Revenue breakdown --
            rv = report.get("revenue", {})
            rev_table = RichTable(show_header=True, header_style=f"bold {ACCENT}",
                                  border_style=BORDER, expand=True)
            rev_table.add_column("Revenue Stream", style="bold")
            rev_table.add_column("Amount", justify="right")
            rev_table.add_column("% of Total", justify="right")

            total_rev = rv.get("total", 0) or 1
            for label, key in [
                ("Matchday Income", "matchday"),
                ("TV Money", "tv_money"),
                ("Sponsorship", "sponsorship"),
                ("Merchandise", "merchandise"),
                ("Prize Money", "prize_money"),
            ]:
                val = rv.get(key, 0)
                pct = val / total_rev * 100 if total_rev else 0
                rev_table.add_row(
                    label,
                    _fmt_currency(val),
                    f"{pct:.1f}%",
                )
            rev_table.add_row(
                f"[bold {GREEN}]TOTAL REVENUE[/]",
                f"[bold {GREEN}]{_fmt_currency(total_rev)}[/]",
                "[bold]100%[/]",
            )

            self.query_one("#revenue-panel", Static).update(Panel(
                rev_table,
                title="[bold]REVENUE[/]",
                border_style=BORDER,
            ))

            # -- Expense breakdown --
            ex = report.get("expenses", {})
            exp_table = RichTable(show_header=True, header_style=f"bold {ACCENT}",
                                  border_style=BORDER, expand=True)
            exp_table.add_column("Expense Category", style="bold")
            exp_table.add_column("Amount", justify="right")
            exp_table.add_column("% of Total", justify="right")

            total_exp = ex.get("total", 0) or 1
            for label, key in [
                ("Wages (Annual)", "wages"),
                ("Facility Maintenance", "facilities"),
                ("Transfer Amortization", "amortization"),
                ("Agent Fees", "agent_fees"),
                ("Operational Overhead", "overhead"),
                ("Performance Bonuses", "bonuses"),
            ]:
                val = ex.get(key, 0)
                pct = val / total_exp * 100 if total_exp else 0
                exp_table.add_row(
                    label,
                    _fmt_currency(val),
                    f"{pct:.1f}%",
                )
            exp_table.add_row(
                f"[bold {RED}]TOTAL EXPENSES[/]",
                f"[bold {RED}]{_fmt_currency(total_exp)}[/]",
                "[bold]100%[/]",
            )

            self.query_one("#expense-panel", Static).update(Panel(
                exp_table,
                title="[bold]EXPENSES[/]",
                border_style=BORDER,
            ))

            # -- Financial projection --
            monthly_net = projection.get("monthly_net", 0)
            months_neg = projection.get("months_until_negative", -1)
            proj_balance = projection.get("projected_balance", 0)
            net_col_m = GREEN if monthly_net >= 0 else RED

            if months_neg == -1:
                runway_text = f"[{GREEN}]Financially stable (positive cash flow)[/]"
            elif months_neg == 0:
                runway_text = f"[{RED}][bold]CRITICAL: Already in the red![/][/]"
            elif months_neg <= 3:
                runway_text = f"[{RED}][bold]WARNING: ~{months_neg} months until negative[/][/]"
            else:
                runway_text = f"[{AMBER}]~{months_neg} months until negative balance[/]"

            proj_text = (
                f"[dim]Monthly Income:[/]   {_fmt_currency(projection.get('monthly_income', 0))}\n"
                f"[dim]Monthly Expenses:[/] {_fmt_currency(projection.get('monthly_expenses', 0))}\n"
                f"[dim]Monthly Net:[/]      [{net_col_m}]{_fmt_currency(monthly_net)}[/]\n"
                f"[dim]6-Month Projected:[/] {_fmt_currency(proj_balance)}\n\n"
                f"{runway_text}"
            )
            self.query_one("#projection-panel", Static).update(Panel(
                proj_text,
                title="[bold]6-MONTH PROJECTION[/]",
                border_style=BORDER,
            ))

            # -- FFP compliance --
            compliant = ffp.get("compliant", True)
            comp_col = GREEN if compliant else RED
            comp_label = "COMPLIANT" if compliant else "NON-COMPLIANT"
            warnings = ffp.get("warnings", [])

            ffp_text = f"[{comp_col}][bold]FFP Status: {comp_label}[/][/]\n"
            ffp_text += f"[dim]Wage Ratio:[/] {ffp.get('wage_ratio', 0):.1%} "
            ffp_text += f"[{'dim' if ffp.get('wage_ratio_ok') else f'bold {RED}'}]"
            ffp_text += f"(limit 70%)[/]\n"
            ffp_text += f"[dim]3-Year Loss:[/] {_fmt_currency(abs(ffp.get('loss_3yr', 0)))} "
            ffp_text += f"[{'dim' if ffp.get('loss_3yr_ok') else f'bold {RED}'}]"
            ffp_text += f"(limit {_fmt_currency(30)})[/]"

            if warnings:
                ffp_text += "\n\n[bold]Warnings:[/]"
                for w in warnings:
                    ffp_text += f"\n  [{RED}]! {w}[/]"

            self.query_one("#ffp-panel", Static).update(Panel(
                ffp_text,
                title="[bold]FINANCIAL FAIR PLAY[/]",
                border_style=BORDER,
            ))
        finally:
            session.close()


# ══════════════════════════════════════════════════════════════════════════
#  2. BoardRoomScreen
# ══════════════════════════════════════════════════════════════════════════

class BoardRoomScreen(Screen):
    """Board confidence, expectations, fans, and stadium attendance."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("BOARD ROOM", classes="section-title")
            with ScrollableContainer():
                yield Static(id="board-confidence")
                yield Static(id="board-expectations")
                yield Static(id="fan-mood")
                yield Static(id="stadium-info")
                yield Static(id="board-message")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def _refresh(self) -> None:
        session = get_session()
        try:
            club = session.get(Club, self.club_id)
            if not club:
                return

            from fm.world.board import BoardManager, FanManager

            board_mgr = BoardManager(session)
            fan_mgr = FanManager(session)

            # Initialize board if needed
            board_mgr.initialise_board(self.club_id)
            season = _get_current_season(session)
            if season:
                board_mgr.set_expectations(self.club_id, season.year)

            # -- Board confidence --
            perf = board_mgr.evaluate_manager_performance(self.club_id)
            confidence = perf.get("confidence", 50)
            conf_col = _colour_value(confidence)
            status = perf.get("status", "Unknown")
            patience = perf.get("patience", 50)
            board_type = perf.get("board_type", "balanced")
            warning = perf.get("warning_issued", False)

            board_type_labels = {
                "sugar_daddy": "Sugar Daddy (High budget, patient)",
                "balanced": "Balanced (Moderate expectations)",
                "frugal": "Frugal (Low budget, patient)",
                "selling": "Selling Club (Youth focused, tight budget)",
            }
            board_label = board_type_labels.get(board_type, board_type.replace("_", " ").title())

            conf_bar = _bar(confidence)
            patience_bar = _bar(patience)

            warning_line = ""
            if warning:
                warning_line = f"\n[{RED}][bold]WARNING ISSUED - Results must improve![/][/]"

            conf_text = (
                f"[dim]Board Type:[/]  [bold]{board_label}[/]\n\n"
                f"[dim]Confidence:[/]  [{conf_col}][bold]{confidence:.0f}%[/][/]  ({status})\n"
                f"  {conf_bar}\n\n"
                f"[dim]Patience:[/]    [bold]{patience:.0f}[/] / 100\n"
                f"  {patience_bar}"
                f"{warning_line}"
            )
            self.query_one("#board-confidence", Static).update(Panel(
                conf_text,
                title="[bold]BOARD CONFIDENCE[/]",
                border_style=ACCENT,
            ))

            # -- Board expectations --
            expectations = board_mgr.get_expectations(self.club_id)
            if expectations:
                target_labels = {
                    "win_league": "Win the League",
                    "title_challenge": "Title Challenge",
                    "top_four": "Top 4 Finish",
                    "top_half": "Top Half Finish",
                    "mid_table": "Mid-Table",
                    "avoid_relegation": "Avoid Relegation",
                    "survive": "Survive",
                }
                cup_labels = {
                    "win": "Win the Cup",
                    "semi_final": "Reach Semi-Finals",
                    "quarter_final": "Reach Quarter-Finals",
                    "progress": "Progress in Cup",
                    "no_expectation": "No Expectation",
                }
                league_target = target_labels.get(
                    expectations.league_target.value,
                    expectations.league_target.value.replace("_", " ").title()
                )
                cup_target = cup_labels.get(
                    expectations.cup_target,
                    expectations.cup_target.replace("_", " ").title()
                )
                budget_stance = expectations.budget_stance.title()
                youth_focus = "Yes" if expectations.youth_focus else "No"
                net_spend = expectations.net_spend_limit

                net_col = GREEN if net_spend >= 0 else RED
                exp_text = (
                    f"[dim]League Target:[/]    [bold]{league_target}[/]\n"
                    f"[dim]Cup Target:[/]       [bold]{cup_target}[/]\n"
                    f"[dim]Budget Stance:[/]    [bold]{budget_stance}[/]\n"
                    f"[dim]Youth Focus:[/]      [bold]{youth_focus}[/]\n"
                    f"[dim]Net Spend Limit:[/]  [{net_col}][bold]{_fmt_currency(net_spend)}[/][/]"
                )

                # Current position vs target
                position = perf.get("position", 0)
                target_pos = perf.get("target_position", 0)
                ppg = perf.get("ppg", 0)
                target_ppg = perf.get("target_ppg", 0)

                if position > 0 and target_pos > 0:
                    pos_diff = target_pos - position
                    if pos_diff > 0:
                        pos_col = GREEN
                        pos_label = f"{pos_diff} places ahead"
                    elif pos_diff == 0:
                        pos_col = AMBER
                        pos_label = "On target"
                    else:
                        pos_col = RED
                        pos_label = f"{abs(pos_diff)} places behind"
                    exp_text += (
                        f"\n\n[dim]Current Position:[/]  [bold]{_ordinal(position)}[/]  "
                        f"(target: {_ordinal(target_pos)})\n"
                        f"[dim]Status:[/]  [{pos_col}][bold]{pos_label}[/][/]\n"
                        f"[dim]Points/Game:[/]  [bold]{ppg:.2f}[/]  "
                        f"(target: {target_ppg:.2f})"
                    )
            else:
                exp_text = "[dim]No expectations set yet.[/]"

            self.query_one("#board-expectations", Static).update(Panel(
                exp_text,
                title="[bold]BOARD EXPECTATIONS[/]",
                border_style=BORDER,
            ))

            # -- Fan mood --
            fan_mood = fan_mgr.get_fan_mood(self.club_id)
            happiness = fan_mood.get("happiness", 60)
            h_col = _colour_value(happiness)
            h_label = fan_mood.get("happiness_label", "Content")
            excitement = fan_mood.get("excitement", 50)
            loyalty = fan_mood.get("loyalty", 70)
            att_pct = fan_mood.get("recent_attendance_pct", 85)

            atmosphere = fan_mgr.get_stadium_atmosphere(self.club_id)
            atm_pct = atmosphere * 100

            fan_text = (
                f"[dim]Happiness:[/]   [{h_col}][bold]{h_label}[/]  ({happiness:.0f}/100)[/]\n"
                f"  {_bar(happiness)}\n\n"
                f"[dim]Excitement:[/]  [bold]{excitement:.0f}[/] / 100\n"
                f"  {_bar(excitement)}\n\n"
                f"[dim]Loyalty:[/]     [bold]{loyalty:.0f}[/] / 100\n"
                f"  {_bar(loyalty)}\n\n"
                f"[dim]Attendance:[/]  [bold]{att_pct:.0f}%[/] of capacity\n"
                f"[dim]Atmosphere:[/]  [bold]{atm_pct:.0f}%[/]"
            )
            self.query_one("#fan-mood", Static).update(Panel(
                fan_text,
                title="[bold]FAN MOOD[/]",
                border_style=BORDER,
            ))

            # -- Stadium info --
            capacity = club.stadium_capacity or 30000
            stadium_name = club.stadium_name or "Stadium"
            est_attendance = fan_mgr.calculate_attendance(self.club_id)

            stad_text = (
                f"[dim]Stadium:[/]         [bold]{stadium_name}[/]\n"
                f"[dim]Capacity:[/]        [bold]{capacity:,}[/]\n"
                f"[dim]Est. Attendance:[/] [bold]{est_attendance:,}[/]  "
                f"({est_attendance / max(capacity, 1) * 100:.0f}%)\n"
                f"[dim]Facilities:[/]      [bold]{club.facilities_level or 5}[/] / 10\n"
                f"[dim]Youth Academy:[/]   [bold]{club.youth_academy_level or 5}[/] / 10"
            )
            self.query_one("#stadium-info", Static).update(Panel(
                stad_text,
                title="[bold]STADIUM & FACILITIES[/]",
                border_style=BORDER,
            ))

            # -- Board message --
            message = board_mgr.get_board_message(self.club_id)
            self.query_one("#board-message", Static).update(Panel(
                f"[italic]{message}[/]",
                title="[bold]BOARD STATEMENT[/]",
                border_style=BORDER,
            ))
        finally:
            session.close()


# ══════════════════════════════════════════════════════════════════════════
#  3. YouthAcademyScreen
# ══════════════════════════════════════════════════════════════════════════

class YouthAcademyScreen(Screen):
    """Youth academy candidates, development, and promotion."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("YOUTH ACADEMY", classes="section-title")
            yield Static(id="academy-info")
            table = DataTable(id="youth-table")
            table.cursor_type = "row"
            yield table
            yield Static(id="youth-detail")
            with Horizontal():
                yield Button("Promote Selected", id="promote-btn",
                             variant="success")
                yield Button("Release Selected", id="release-btn",
                             variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "promote-btn":
            self._promote_selected()
        elif event.button.id == "release-btn":
            self._release_selected()

    def _refresh(self) -> None:
        session = get_session()
        try:
            club = session.get(Club, self.club_id)
            if not club:
                return

            academy_level = club.youth_academy_level or 5

            # Quality label
            if academy_level >= 8:
                quality_label = f"[{GREEN}]Elite[/]"
            elif academy_level >= 6:
                quality_label = f"[{GREEN}]Good[/]"
            elif academy_level >= 4:
                quality_label = f"[{AMBER}]Average[/]"
            else:
                quality_label = f"[{RED}]Poor[/]"

            # Youth coach quality
            youth_coaches = (
                session.query(Staff)
                .filter_by(club_id=self.club_id, role="youth_coach")
                .all()
            )
            if youth_coaches:
                avg_coaching = sum(
                    (s.coaching_technical or 50) for s in youth_coaches
                ) / len(youth_coaches)
                coach_text = f"[bold]{avg_coaching:.0f}[/] (from {len(youth_coaches)} coach(es))"
            else:
                coach_text = "[dim]No dedicated youth coach[/]"

            info_text = (
                f"[dim]Academy Level:[/]  [bold]{academy_level}[/] / 10  ({quality_label})\n"
                f"[dim]Youth Coach Quality:[/]  {coach_text}\n"
                f"[dim]Academy Bar:[/]  {_bar(academy_level * 10)}"
            )
            self.query_one("#academy-info", Static).update(Panel(
                info_text,
                title=f"[bold]{club.name} YOUTH ACADEMY[/]",
                border_style=ACCENT,
            ))

            # -- Candidates table --
            table = self.query_one("#youth-table", DataTable)
            table.clear(columns=True)
            table.add_columns(
                "Name", "Age", "Pos", "Ability", "Pot (Min)", "Pot (Max)",
                "Personality", "Ready", "Joined",
            )

            candidates = (
                session.query(YouthCandidate)
                .filter_by(club_id=self.club_id)
                .order_by(YouthCandidate.current_ability.desc())
                .all()
            )

            if not candidates:
                detail = self.query_one("#youth-detail", Static)
                detail.update(Panel(
                    "[dim]No youth candidates in the academy.\n"
                    "Youth intake occurs at the start of each season.[/]",
                    border_style=BORDER,
                ))
            else:
                self.query_one("#youth-detail", Static).update("")

            for cand in candidates:
                ca = cand.current_ability or 30
                pot_max = cand.potential_max or 80
                ready = cand.ready_to_promote or False

                # Ability colour
                if ca >= 60:
                    ca_col = GREEN
                elif ca >= 45:
                    ca_col = AMBER
                else:
                    ca_col = RED

                # Potential colour
                if pot_max >= 80:
                    pot_col = GREEN
                elif pot_max >= 65:
                    pot_col = AMBER
                else:
                    pot_col = RED

                ready_icon = f"[{GREEN}]YES[/]" if ready else f"[dim]No[/]"

                # Personality with colour coding
                personality = cand.personality_type or "balanced"
                good_personalities = {"determined", "professional", "perfectionist", "ambitious"}
                bad_personalities = {"lazy", "volatile"}
                if personality in good_personalities:
                    pers_display = f"[{GREEN}]{personality.title()}[/]"
                elif personality in bad_personalities:
                    pers_display = f"[{RED}]{personality.title()}[/]"
                else:
                    pers_display = personality.title()

                table.add_row(
                    cand.name or "Unknown",
                    str(cand.age or 16),
                    cand.position or "?",
                    Text(str(ca), style=f"bold {ca_col}"),
                    str(cand.potential_min or 50),
                    Text(str(pot_max), style=f"bold {pot_col}"),
                    Text.from_markup(pers_display),
                    Text.from_markup(ready_icon),
                    str(cand.season_joined or "?"),
                    key=str(cand.id),
                )
        finally:
            session.close()

    def _promote_selected(self) -> None:
        table = self.query_one("#youth-table", DataTable)
        row_key = table.cursor_row
        if row_key is None:
            return
        try:
            # Get the key from the row at cursor position
            keys = list(table.rows.keys())
            if row_key >= len(keys):
                return
            candidate_id = int(str(keys[row_key].value))
        except (ValueError, TypeError, IndexError):
            return

        session = get_session()
        try:
            from fm.world.youth_academy import YouthAcademyManager
            ya = YouthAcademyManager(session)
            season = _get_current_season(session)
            season_year = season.year if season else 2024

            cand = session.get(YouthCandidate, candidate_id)
            if not cand:
                self.query_one("#youth-detail", Static).update(Panel(
                    f"[{RED}]Candidate not found.[/]",
                    border_style=RED,
                ))
                return

            if not cand.ready_to_promote:
                self.query_one("#youth-detail", Static).update(Panel(
                    f"[{AMBER}]{cand.name} is not ready for promotion yet.[/]",
                    border_style=AMBER,
                ))
                return

            player = ya.promote_to_first_team(candidate_id, season_year)
            session.commit()

            if player:
                self.query_one("#youth-detail", Static).update(Panel(
                    f"[{GREEN}][bold]{player.name}[/] promoted to first team![/]\n"
                    f"[dim]Overall:[/] {player.overall}  "
                    f"[dim]Potential:[/] {player.potential}  "
                    f"[dim]Position:[/] {player.position}",
                    border_style=GREEN,
                ))
            else:
                self.query_one("#youth-detail", Static).update(Panel(
                    f"[{RED}]Failed to promote candidate.[/]",
                    border_style=RED,
                ))
        finally:
            session.close()
        self._refresh()

    def _release_selected(self) -> None:
        table = self.query_one("#youth-table", DataTable)
        row_key = table.cursor_row
        if row_key is None:
            return
        try:
            keys = list(table.rows.keys())
            if row_key >= len(keys):
                return
            candidate_id = int(str(keys[row_key].value))
        except (ValueError, TypeError, IndexError):
            return

        session = get_session()
        try:
            from fm.world.youth_academy import YouthAcademyManager
            ya = YouthAcademyManager(session)
            season = _get_current_season(session)
            season_year = season.year if season else 2024

            cand = session.get(YouthCandidate, candidate_id)
            name = cand.name if cand else "Unknown"

            success = ya.release_candidate(candidate_id, season_year)
            session.commit()

            if success:
                self.query_one("#youth-detail", Static).update(Panel(
                    f"[{AMBER}]{name} has been released from the academy.[/]",
                    border_style=AMBER,
                ))
            else:
                self.query_one("#youth-detail", Static).update(Panel(
                    f"[{RED}]Failed to release candidate.[/]",
                    border_style=RED,
                ))
        finally:
            session.close()
        self._refresh()


# ══════════════════════════════════════════════════════════════════════════
#  4. PlayerDynamicsScreen
# ══════════════════════════════════════════════════════════════════════════

class PlayerDynamicsScreen(Screen):
    """Squad happiness, relationships, cliques, and dressing room mood."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("PLAYER DYNAMICS", classes="section-title")
            with ScrollableContainer():
                yield Static(id="dressing-room")
                table = DataTable(id="dynamics-table")
                table.cursor_type = "row"
                yield table
                yield Static(id="cliques-panel")
                yield Static(id="mentors-panel")
                yield Static(id="leaders-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def _refresh(self) -> None:
        session = get_session()
        try:
            from fm.world.player_dynamics import (
                PlayerDynamicsManager, RelationshipManager,
                _happiness, _transfer_requests,
            )

            pdm = PlayerDynamicsManager(session)
            rm = RelationshipManager(session)

            # Build relationships if not yet done
            rm.build_relationships(self.club_id)

            # -- Dressing room overview --
            mood = rm.get_dressing_room_mood(self.club_id)
            spirit = mood.get("spirit", 50)
            spirit_label = mood.get("spirit_label", "Average")
            spirit_col = _colour_value(spirit, (70, 40))
            chem_avg = mood.get("chemistry_avg", 50)
            morale_avg = mood.get("morale_avg", 65)
            conflicts = mood.get("conflicts", 0)
            mentorships = mood.get("mentorships", 0)
            leaders = mood.get("leaders", 0)
            cliques = mood.get("cliques", 0)
            leader_names = mood.get("leader_names", [])

            conflicts_col = GREEN if conflicts == 0 else AMBER if conflicts <= 2 else RED

            dr_text = (
                f"[dim]Squad Spirit:[/]   [{spirit_col}][bold]{spirit_label}[/]  "
                f"({spirit:.0f}/100)[/]\n"
                f"  {_bar(spirit)}\n\n"
                f"[dim]Avg Chemistry:[/]  [bold]{chem_avg:.0f}[/] / 100\n"
                f"  {_bar(chem_avg)}\n\n"
                f"[dim]Avg Morale:[/]     [bold]{morale_avg:.0f}[/] / 100\n"
                f"  {_bar(morale_avg)}\n\n"
                f"[dim]Conflicts:[/]  [{conflicts_col}][bold]{conflicts}[/][/]    "
                f"[dim]Mentorships:[/]  [bold]{mentorships}[/]    "
                f"[dim]Leaders:[/]  [bold]{leaders}[/]    "
                f"[dim]Cliques:[/]  [bold]{cliques}[/]"
            )
            self.query_one("#dressing-room", Static).update(Panel(
                dr_text,
                title="[bold]DRESSING ROOM ATMOSPHERE[/]",
                border_style=ACCENT,
            ))

            # -- Player happiness table --
            table = self.query_one("#dynamics-table", DataTable)
            table.clear(columns=True)
            table.add_columns(
                "Name", "Pos", "OVR", "Morale", "Happiness", "Status",
            )

            players = (
                session.query(Player)
                .filter_by(club_id=self.club_id)
                .order_by(Player.overall.desc())
                .all()
            )

            for p in players:
                morale = p.morale or 65
                morale_col = _colour_value(morale, (70, 50))

                # Happiness factors
                factors = _happiness.get(p.id)
                if factors:
                    h_total = factors.total
                    if h_total >= 10:
                        h_label = f"[{GREEN}]Happy[/]"
                    elif h_total >= -10:
                        h_label = f"[{AMBER}]Content[/]"
                    else:
                        h_label = f"[{RED}]Unhappy[/]"
                else:
                    h_total = 0
                    h_label = "[dim]Unknown[/]"

                # Status
                statuses = []
                if p.id in _transfer_requests:
                    statuses.append(f"[{RED}]Transfer Req[/]")
                if (p.injured_weeks or 0) > 0:
                    statuses.append(f"[{RED}]Injured[/]")
                if factors and factors.transfer_request_pending:
                    if p.id not in _transfer_requests:
                        statuses.append(f"[{AMBER}]Wants Out[/]")
                status_text = ", ".join(statuses) if statuses else f"[{GREEN}]OK[/]"

                table.add_row(
                    (p.short_name or p.name)[:22],
                    p.position or "?",
                    str(p.overall or 50),
                    Text(f"{morale:.0f}", style=f"bold {morale_col}"),
                    Text.from_markup(h_label),
                    Text.from_markup(status_text),
                    key=str(p.id),
                )

            # -- Cliques panel --
            cliques_data = rm.get_squad_cliques(self.club_id)
            if cliques_data:
                clique_lines = []
                for clique in cliques_data:
                    nat = clique[0].get("nationality", "Unknown") if clique else "?"
                    names = [c.get("name", "?") for c in clique]
                    clique_lines.append(
                        f"[bold]{nat}[/] ({len(clique)} players): "
                        + ", ".join(names)
                    )
                cliques_text = "\n".join(clique_lines)
            else:
                cliques_text = "[dim]No significant nationality groups detected.[/]"

            self.query_one("#cliques-panel", Static).update(Panel(
                cliques_text,
                title="[bold]SQUAD CLIQUES[/]",
                border_style=BORDER,
            ))

            # -- Mentor pairs --
            mentors = rm.get_mentor_pairs(self.club_id)
            if mentors:
                mentor_lines = []
                for mp in mentors:
                    chem = mp.get("chemistry", 50)
                    chem_col = _colour_value(chem)
                    mentor_lines.append(
                        f"[bold]{mp['mentor_name']}[/] mentoring "
                        f"[bold]{mp['protege_name']}[/]  "
                        f"[dim]Chemistry:[/] [{chem_col}]{chem:.0f}[/]"
                    )
                mentors_text = "\n".join(mentor_lines)
            else:
                mentors_text = "[dim]No active mentor relationships.[/]"

            self.query_one("#mentors-panel", Static).update(Panel(
                mentors_text,
                title="[bold]MENTOR PAIRS[/]",
                border_style=BORDER,
            ))

            # -- Squad leaders --
            squad_leaders = rm.get_squad_leaders(self.club_id)
            if squad_leaders:
                leader_lines = []
                for i, ld in enumerate(squad_leaders[:5], 1):
                    score = ld.get("leadership_score", 0)
                    leader_lines.append(
                        f"  {i}. [bold]{ld['name']}[/]  "
                        f"[dim]Score:[/] {score:.0f}  "
                        f"[dim]Age:[/] {ld.get('age', '?')}  "
                        f"[dim]OVR:[/] {ld.get('overall', '?')}"
                    )
                leaders_text = "\n".join(leader_lines)
            else:
                leaders_text = "[dim]No natural leaders identified.[/]"

            self.query_one("#leaders-panel", Static).update(Panel(
                leaders_text,
                title="[bold]SQUAD LEADERS[/]",
                border_style=BORDER,
            ))
        finally:
            session.close()


# ══════════════════════════════════════════════════════════════════════════
#  5. ContractScreen
# ══════════════════════════════════════════════════════════════════════════

class ContractScreen(Screen):
    """Expiring contracts and renewal overview."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("CONTRACT MANAGEMENT", classes="section-title")
            yield Static(id="contract-overview")
            yield Label("Expiring Contracts (within 12 months):", classes="section-title")
            table = DataTable(id="contracts-table")
            table.cursor_type = "row"
            yield table
            yield Static(id="contract-detail")
            yield Label("Full Squad Contracts:", classes="section-title")
            table2 = DataTable(id="all-contracts-table")
            table2.cursor_type = "row"
            yield table2
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.data_table.id == "contracts-table":
            try:
                player_id = int(str(event.row_key.value))
                self._show_contract_detail(player_id)
            except (ValueError, TypeError):
                pass

    def _refresh(self) -> None:
        session = get_session()
        try:
            club = session.get(Club, self.club_id)
            if not club:
                return
            season = _get_current_season(session)
            current_year = season.year if season else 2024

            players = (
                session.query(Player)
                .filter_by(club_id=self.club_id)
                .order_by(Player.contract_expiry.asc())
                .all()
            )

            # -- Overview --
            total_wage = sum(p.wage or 0 for p in players)
            expiring_soon = [
                p for p in players
                if (p.contract_expiry or current_year + 5) <= current_year + 1
            ]
            expiring_count = len(expiring_soon)
            exp_col = GREEN if expiring_count == 0 else AMBER if expiring_count <= 3 else RED

            from fm.world.contracts import ContractNegotiator
            cn = ContractNegotiator(session)

            overview_text = (
                f"[dim]Total Squad Wage Bill:[/]  [bold]\u20ac{total_wage:.0f}K/wk[/]\n"
                f"[dim]Squad Size:[/]  [bold]{len(players)}[/]\n"
                f"[dim]Expiring Soon (<= 12 months):[/]  "
                f"[{exp_col}][bold]{expiring_count}[/][/] player(s)"
            )
            self.query_one("#contract-overview", Static).update(Panel(
                overview_text,
                title=f"[bold]{club.name} -- CONTRACT OVERVIEW[/]",
                border_style=ACCENT,
            ))

            # -- Expiring contracts table --
            table = self.query_one("#contracts-table", DataTable)
            table.clear(columns=True)
            table.add_columns(
                "Name", "Pos", "Age", "OVR", "Wage (K/wk)", "Expires",
                "Years Left", "Est. Demand",
            )

            if not expiring_soon:
                self.query_one("#contract-detail", Static).update(Panel(
                    f"[{GREEN}]No contracts expiring within 12 months.[/]",
                    border_style=GREEN,
                ))
            else:
                self.query_one("#contract-detail", Static).update("")

            for p in expiring_soon:
                expiry = p.contract_expiry or current_year
                years_left = expiry - current_year
                yr_col = RED if years_left <= 0 else AMBER

                # Estimate wage demand
                demand = cn.calculate_wage_demand(p)

                table.add_row(
                    (p.short_name or p.name)[:22],
                    p.position or "?",
                    str(p.age or 0),
                    str(p.overall or 50),
                    f"\u20ac{p.wage or 0:.0f}K",
                    str(expiry),
                    Text(str(years_left), style=f"bold {yr_col}"),
                    f"\u20ac{demand:.0f}K",
                    key=str(p.id),
                )

            # -- All contracts table --
            table2 = self.query_one("#all-contracts-table", DataTable)
            table2.clear(columns=True)
            table2.add_columns(
                "Name", "Pos", "Age", "OVR", "Wage (K/wk)", "Expires",
                "Value",
            )

            for p in players:
                expiry = p.contract_expiry or current_year
                years_left = expiry - current_year
                if years_left <= 0:
                    yr_display = f"[{RED}]EXPIRED[/]"
                elif years_left <= 1:
                    yr_display = f"[{RED}]{expiry}[/]"
                elif years_left <= 2:
                    yr_display = f"[{AMBER}]{expiry}[/]"
                else:
                    yr_display = str(expiry)

                table2.add_row(
                    (p.short_name or p.name)[:22],
                    p.position or "?",
                    str(p.age or 0),
                    str(p.overall or 50),
                    f"\u20ac{p.wage or 0:.0f}K",
                    Text.from_markup(yr_display),
                    _fmt_currency(p.market_value or 0),
                    key=f"all-{p.id}",
                )
        finally:
            session.close()

    def _show_contract_detail(self, player_id: int) -> None:
        session = get_session()
        try:
            player = session.get(Player, player_id)
            if not player:
                return

            from fm.world.contracts import ContractNegotiator
            cn = ContractNegotiator(session)
            demand = cn.calculate_wage_demand(player)

            season = _get_current_season(session)
            current_year = season.year if season else 2024
            expiry = player.contract_expiry or current_year
            years_left = expiry - current_year

            # Check for detailed Contract model
            contract = (
                session.query(Contract)
                .filter_by(player_id=player_id, club_id=self.club_id, is_active=True)
                .first()
            )

            detail_text = (
                f"[bold]{player.short_name or player.name}[/]  "
                f"({player.position}, Age {player.age})\n\n"
                f"[dim]Overall:[/]  [bold]{player.overall}[/]  "
                f"[dim]Potential:[/]  [bold]{player.potential}[/]\n"
                f"[dim]Current Wage:[/]  [bold]\u20ac{player.wage or 0:.0f}K/wk[/]\n"
                f"[dim]Contract Expires:[/]  [bold]{expiry}[/]  "
                f"({years_left} year{'s' if years_left != 1 else ''} remaining)\n"
                f"[dim]Market Value:[/]  [bold]{_fmt_currency(player.market_value or 0)}[/]\n\n"
                f"[dim]Estimated Renewal Demand:[/]  [{ACCENT}][bold]\u20ac{demand:.0f}K/wk[/][/]"
            )

            if contract:
                detail_text += "\n\n[bold]Contract Details:[/]\n"
                if contract.release_clause:
                    detail_text += f"  [dim]Release Clause:[/]  {_fmt_currency(contract.release_clause)}\n"
                if contract.appearance_bonus:
                    detail_text += f"  [dim]Appearance Bonus:[/]  \u20ac{contract.appearance_bonus:.0f}K\n"
                if contract.goal_bonus:
                    detail_text += f"  [dim]Goal Bonus:[/]  \u20ac{contract.goal_bonus:.0f}K\n"
                if contract.sell_on_clause_pct and contract.sell_on_clause_pct > 0:
                    detail_text += f"  [dim]Sell-On Clause:[/]  {contract.sell_on_clause_pct:.0f}%\n"
                if contract.squad_role_promised:
                    detail_text += f"  [dim]Promised Role:[/]  {contract.squad_role_promised}\n"

            # Willingness to renew (quick estimate via morale)
            morale = player.morale or 65
            if morale >= 70:
                will_text = f"[{GREEN}]Likely open to renewal[/]"
            elif morale >= 45:
                will_text = f"[{AMBER}]May consider renewal[/]"
            else:
                will_text = f"[{RED}]Unlikely to renew[/]"
            detail_text += f"\n[dim]Renewal Likelihood:[/]  {will_text}"

            self.query_one("#contract-detail", Static).update(Panel(
                detail_text,
                title="[bold]CONTRACT DETAILS[/]",
                border_style=ACCENT,
            ))
        finally:
            session.close()


# ══════════════════════════════════════════════════════════════════════════
#  6. AnalyticsScreen
# ══════════════════════════════════════════════════════════════════════════

class AnalyticsScreen(Screen):
    """Season analytics: form, trends, squad analysis, top performers."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("SEASON ANALYTICS", classes="section-title")
            with ScrollableContainer():
                yield Static(id="squad-analysis")
                yield Static(id="form-chart")
                yield Static(id="performance-trends")
                yield Static(id="top-performers")
                yield Static(id="position-chart")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def _refresh(self) -> None:
        session = get_session()
        try:
            club = session.get(Club, self.club_id)
            if not club or not club.league_id:
                return

            season = _get_current_season(session)
            if not season:
                return
            season_year = season.year
            league_id = club.league_id

            from fm.world.analytics import SeasonAnalytics

            sa = SeasonAnalytics(session)

            # -- Squad Analysis --
            squad = sa.get_squad_analysis(self.club_id)

            pos_depth_parts = []
            for pos, count in sorted(squad.position_depth.items()):
                avg = squad.position_avg_ovr.get(pos, 0)
                pos_depth_parts.append(f"  [bold]{pos}[/]: {count} players (avg {avg:.0f})")

            weakest_col = RED
            strongest_col = GREEN

            squad_text = (
                f"[dim]Total Players:[/]  [bold]{squad.total_players}[/]\n"
                f"[dim]Avg Overall:[/]    [bold]{squad.avg_overall:.1f}[/]\n"
                f"[dim]Avg Age:[/]        [bold]{squad.avg_age:.1f}[/]\n"
                f"[dim]Total Wages:[/]    [bold]\u20ac{squad.total_wage:.0f}K/wk[/]\n"
                f"[dim]Avg Fitness:[/]    [bold]{squad.avg_fitness:.0f}%[/]\n"
                f"[dim]Avg Morale:[/]     [bold]{squad.avg_morale:.0f}[/]\n"
                f"[dim]Injured:[/]        [bold]{squad.injury_count}[/]\n\n"
                f"[dim]Strongest:[/] [{strongest_col}][bold]{squad.strongest_position}[/][/]  "
                f"[dim]Weakest:[/] [{weakest_col}][bold]{squad.weakest_position}[/][/]\n\n"
                f"[bold]Position Depth:[/]\n" + "\n".join(pos_depth_parts)
            )
            self.query_one("#squad-analysis", Static).update(Panel(
                squad_text,
                title="[bold]SQUAD ANALYSIS[/]",
                border_style=ACCENT,
            ))

            # -- Form chart (text-based) --
            form_data = sa.get_form_curve(self.club_id, league_id, season_year)

            if form_data:
                # Build a text-based form chart
                chart_lines = []
                chart_lines.append("[dim]MD  Result  GF-GA  Pts  CumPts  Pos[/]")
                chart_lines.append("[dim]" + "-" * 48 + "[/]")

                for fp in form_data[-15:]:  # Last 15 matchdays
                    result = fp.result
                    r_col = GREEN if result == "W" else AMBER if result == "D" else RED
                    chart_lines.append(
                        f" {fp.matchday:>2}    [{r_col}][bold]{result}[/][/]     "
                        f"{fp.goals_for}-{fp.goals_against}    {fp.points}     "
                        f"{fp.cumulative_points:>3}    {_ordinal(fp.position):>4}"
                    )

                # Form summary line
                total_pts = form_data[-1].cumulative_points if form_data else 0
                total_games = len(form_data)
                ppg = total_pts / max(total_games, 1)
                wins = sum(1 for fp in form_data if fp.result == "W")
                draws = sum(1 for fp in form_data if fp.result == "D")
                losses = sum(1 for fp in form_data if fp.result == "L")

                chart_lines.append("")
                chart_lines.append(
                    f"[bold]Record:[/] [{GREEN}]{wins}W[/] [{AMBER}]{draws}D[/] "
                    f"[{RED}]{losses}L[/]  "
                    f"[bold]PPG:[/] {ppg:.2f}  "
                    f"[bold]Total Pts:[/] {total_pts}"
                )

                form_text = "\n".join(chart_lines)
            else:
                form_text = "[dim]No matches played yet this season.[/]"

            self.query_one("#form-chart", Static).update(Panel(
                form_text,
                title="[bold]SEASON FORM[/]",
                border_style=BORDER,
            ))

            # -- Performance trends --
            trends = sa.get_performance_trends(self.club_id, league_id, season_year)
            matchdays = trends.get("matchdays", [])

            if matchdays:
                gf_avg = trends.get("goals_for_avg", [])
                ga_avg = trends.get("goals_against_avg", [])
                xgf_avg = trends.get("xg_for_avg", [])
                xga_avg = trends.get("xg_against_avg", [])
                poss_avg = trends.get("possession_avg", [])

                # Show last 5 rolling averages
                last_n = min(5, len(matchdays))
                trend_lines = ["[dim]5-Match Rolling Averages (most recent):[/]\n"]

                if gf_avg:
                    trend_lines.append(
                        f"[dim]Goals Scored (avg):[/]    "
                        f"[{GREEN}][bold]{gf_avg[-1]:.2f}[/][/]"
                    )
                if ga_avg:
                    trend_lines.append(
                        f"[dim]Goals Conceded (avg):[/] "
                        f"[{RED}][bold]{ga_avg[-1]:.2f}[/][/]"
                    )
                if xgf_avg:
                    trend_lines.append(
                        f"[dim]xG For (avg):[/]         "
                        f"[bold]{xgf_avg[-1]:.2f}[/]"
                    )
                if xga_avg:
                    trend_lines.append(
                        f"[dim]xG Against (avg):[/]     "
                        f"[bold]{xga_avg[-1]:.2f}[/]"
                    )
                if poss_avg:
                    trend_lines.append(
                        f"[dim]Possession (avg):[/]     "
                        f"[bold]{poss_avg[-1]:.1f}%[/]"
                    )

                # xG comparison
                total_gf = sum(trends.get("goals_for", []))
                total_ga = sum(trends.get("goals_against", []))
                total_xgf = sum(trends.get("xg_for", []))
                total_xga = sum(trends.get("xg_against", []))

                overperform = total_gf - total_xgf
                op_col = GREEN if overperform > 0 else RED
                trend_lines.append("")
                trend_lines.append(
                    f"[dim]Season Totals:[/]\n"
                    f"  [dim]Goals:[/] {total_gf} scored, {total_ga} conceded\n"
                    f"  [dim]xG:[/]    {total_xgf:.1f} for, {total_xga:.1f} against\n"
                    f"  [dim]xG Performance:[/] [{op_col}]{overperform:+.1f}[/] "
                    f"({'overperforming' if overperform > 0 else 'underperforming'})"
                )

                trends_text = "\n".join(trend_lines)
            else:
                trends_text = "[dim]Not enough data for trends.[/]"

            self.query_one("#performance-trends", Static).update(Panel(
                trends_text,
                title="[bold]PERFORMANCE TRENDS[/]",
                border_style=BORDER,
            ))

            # -- Top performers --
            players = (
                session.query(Player)
                .filter_by(club_id=self.club_id)
                .all()
            )

            performer_table = RichTable(
                show_header=True, header_style=f"bold {ACCENT}",
                border_style=BORDER, expand=True,
            )
            performer_table.add_column("Name", style="bold")
            performer_table.add_column("Pos")
            performer_table.add_column("Apps", justify="right")
            performer_table.add_column("Goals", justify="right")
            performer_table.add_column("Assists", justify="right")
            performer_table.add_column("Rating", justify="right")

            player_perf = []
            for p in players:
                stats = (
                    session.query(PlayerStats)
                    .filter_by(player_id=p.id, season=season_year)
                    .first()
                )
                if stats and (stats.appearances or 0) > 0:
                    player_perf.append((p, stats))

            # Sort by rating descending
            player_perf.sort(
                key=lambda x: x[1].avg_rating or 6.0, reverse=True,
            )

            for p, stats in player_perf[:10]:
                rating = stats.avg_rating or 6.0
                r_col = GREEN if rating >= 7.5 else AMBER if rating >= 6.5 else RED
                performer_table.add_row(
                    (p.short_name or p.name)[:20],
                    p.position or "?",
                    str(stats.appearances or 0),
                    str(stats.goals or 0),
                    str(stats.assists or 0),
                    f"[{r_col}][bold]{rating:.1f}[/][/]",
                )

            if not player_perf:
                self.query_one("#top-performers", Static).update(Panel(
                    "[dim]No player stats available yet.[/]",
                    title="[bold]TOP PERFORMERS[/]",
                    border_style=BORDER,
                ))
            else:
                self.query_one("#top-performers", Static).update(Panel(
                    performer_table,
                    title="[bold]TOP PERFORMERS (by Rating)[/]",
                    border_style=BORDER,
                ))

            # -- League position trend (text chart) --
            if form_data and len(form_data) >= 2:
                # Simple text sparkline for position
                positions = [fp.position for fp in form_data]
                max_pos = max(positions) if positions else 20
                min_pos = min(positions) if positions else 1

                pos_lines = []
                pos_lines.append("[dim]League Position Over Time:[/]")
                pos_lines.append(
                    f"  [dim]Best: {_ordinal(min_pos)}  "
                    f"Current: {_ordinal(positions[-1])}  "
                    f"Worst: {_ordinal(max_pos)}[/]"
                )

                # Visual position chart (lower number = better = higher bar)
                chart_width = min(len(positions), 30)
                step = max(1, len(positions) // chart_width)
                sampled = positions[::step][-chart_width:]

                if max_pos > 0:
                    chart_row = "  "
                    for pos in sampled:
                        # Invert: position 1 = max height, position 20 = min height
                        height = max(1, int((1 - (pos - 1) / max(max_pos - 1, 1)) * 8))
                        bar_chars = ["_", "\u2581", "\u2582", "\u2583", "\u2584",
                                     "\u2585", "\u2586", "\u2587", "\u2588"]
                        char = bar_chars[min(height, 8)]
                        p_col = GREEN if pos <= 4 else AMBER if pos <= 10 else RED
                        chart_row += f"[{p_col}]{char}[/]"
                    pos_lines.append(chart_row)
                    pos_lines.append(f"  [dim]{''.join(str(fp.matchday % 10) for fp in form_data[::step][-chart_width:])}[/]")

                pos_text = "\n".join(pos_lines)
            else:
                pos_text = "[dim]Not enough data for position trend.[/]"

            self.query_one("#position-chart", Static).update(Panel(
                pos_text,
                title="[bold]LEAGUE POSITION TREND[/]",
                border_style=BORDER,
            ))
        finally:
            session.close()


# ══════════════════════════════════════════════════════════════════════════
#  7. StaffScreen
# ══════════════════════════════════════════════════════════════════════════

class StaffScreen(Screen):
    """Club staff listing with coaching quality breakdown."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, club_id: int):
        super().__init__()
        self.club_id = club_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="centered-content"):
            with Horizontal():
                yield Button("\u25c0 Back", id="back-btn", classes="back-btn")
                yield Label("STAFF OVERVIEW", classes="section-title")
            yield Static(id="staff-summary")
            table = DataTable(id="staff-table")
            table.cursor_type = "row"
            yield table
            yield Static(id="staff-detail")
            yield Static(id="coaching-impact")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key:
            try:
                staff_id = int(str(event.row_key.value))
                self._show_staff_detail(staff_id)
            except (ValueError, TypeError):
                pass

    def _refresh(self) -> None:
        session = get_session()
        try:
            club = session.get(Club, self.club_id)
            if not club:
                return

            staff = (
                session.query(Staff)
                .filter_by(club_id=self.club_id)
                .order_by(Staff.role, Staff.reputation.desc())
                .all()
            )

            # -- Summary --
            if staff:
                total_wage = sum(s.wage or 0 for s in staff)
                role_counts = {}
                for s in staff:
                    role_counts[s.role] = role_counts.get(s.role, 0) + 1

                role_text_parts = []
                for role, count in sorted(role_counts.items()):
                    label = role.replace("_", " ").title()
                    role_text_parts.append(f"  [bold]{label}:[/] {count}")

                # Calculate overall coaching quality
                coaching_attrs = [
                    "coaching_attacking", "coaching_defending",
                    "coaching_tactical", "coaching_technical",
                    "coaching_mental", "coaching_fitness",
                ]
                coaches = [s for s in staff if "coach" in (s.role or "").lower()
                           or s.role == "assistant"]
                if coaches:
                    avg_quality = sum(
                        sum(getattr(c, a, 50) or 50 for a in coaching_attrs) / len(coaching_attrs)
                        for c in coaches
                    ) / len(coaches)
                else:
                    avg_quality = 50

                q_col = _colour_value(avg_quality)

                summary_text = (
                    f"[dim]Total Staff:[/]  [bold]{len(staff)}[/]\n"
                    f"[dim]Staff Wages:[/]  [bold]\u20ac{total_wage:.0f}K/wk[/]\n"
                    f"[dim]Avg Coaching Quality:[/]  [{q_col}][bold]{avg_quality:.0f}[/][/]\n\n"
                    f"[bold]Staff by Role:[/]\n" + "\n".join(role_text_parts)
                )
            else:
                summary_text = (
                    "[dim]No staff records found.\n"
                    "Staff are auto-generated at game start or can be hired "
                    "through the board.[/]"
                )

            self.query_one("#staff-summary", Static).update(Panel(
                summary_text,
                title=f"[bold]{club.name} STAFF[/]",
                border_style=ACCENT,
            ))

            # -- Staff table --
            table = self.query_one("#staff-table", DataTable)
            table.clear(columns=True)
            table.add_columns(
                "Name", "Role", "Age", "Quality", "Wage (K/wk)",
                "Contract", "Rep",
            )

            if not staff:
                self.query_one("#staff-detail", Static).update(Panel(
                    "[dim]No staff members to display.[/]",
                    border_style=BORDER,
                ))
                self.query_one("#coaching-impact", Static).update("")
                return

            for s in staff:
                role_label = (s.role or "unknown").replace("_", " ").title()

                # Calculate quality rating based on role
                if "scout" in (s.role or ""):
                    quality = (
                        (s.scouting_ability or 50) * 0.6
                        + (s.scouting_potential_judge or 50) * 0.4
                    )
                elif "physio" in (s.role or ""):
                    quality = (
                        (s.physiotherapy or 50) * 0.6
                        + (s.sports_science or 50) * 0.4
                    )
                else:
                    # Coaching staff
                    quality = sum([
                        s.coaching_attacking or 50,
                        s.coaching_defending or 50,
                        s.coaching_tactical or 50,
                        s.coaching_technical or 50,
                        s.coaching_mental or 50,
                        s.coaching_fitness or 50,
                    ]) / 6

                q_col = _colour_value(quality)

                table.add_row(
                    (s.name or "Unknown")[:22],
                    role_label,
                    str(s.age or "?"),
                    Text(f"{quality:.0f}", style=f"bold {q_col}"),
                    f"\u20ac{s.wage or 0:.0f}K",
                    str(s.contract_expiry or "?"),
                    str(s.reputation or 50),
                    key=str(s.id),
                )

            # -- Coaching impact --
            # Show how coaching staff quality affects training
            if coaches:
                impact_lines = []

                # Per-category coaching quality
                categories = [
                    ("Attacking", "coaching_attacking"),
                    ("Defending", "coaching_defending"),
                    ("Tactical", "coaching_tactical"),
                    ("Technical", "coaching_technical"),
                    ("Mental", "coaching_mental"),
                    ("Fitness", "coaching_fitness"),
                ]

                for cat_name, attr in categories:
                    cat_avg = sum(
                        getattr(c, attr, 50) or 50 for c in coaches
                    ) / len(coaches)
                    c_col = _colour_value(cat_avg)
                    multiplier = 0.8 + (cat_avg / 100) * 0.4  # 0.8 to 1.2
                    impact_lines.append(
                        f"  [dim]{cat_name:12s}[/]  [{c_col}]{cat_avg:>3.0f}[/]  "
                        f"{_bar(cat_avg, width=15)}  "
                        f"[dim]Training mult:[/] [bold]{multiplier:.2f}x[/]"
                    )

                # GK coaching
                gk_coaches = [s for s in staff if s.role == "gk_coach"]
                if gk_coaches:
                    gk_avg = sum(
                        (c.coaching_gk or 50) for c in gk_coaches
                    ) / len(gk_coaches)
                    gk_col = _colour_value(gk_avg)
                    impact_lines.append(
                        f"  [dim]{'GK Coaching':12s}[/]  [{gk_col}]{gk_avg:>3.0f}[/]  "
                        f"{_bar(gk_avg, width=15)}"
                    )

                impact_text = (
                    "[bold]Coaching Quality by Category:[/]\n\n"
                    + "\n".join(impact_lines)
                    + "\n\n[dim]Higher quality coaching improves training effectiveness.\n"
                    "Training multiplier ranges from 0.8x (poor) to 1.2x (excellent).[/]"
                )
            else:
                impact_text = (
                    "[dim]No coaching staff found. Training effectiveness will be "
                    "at base level.[/]"
                )

            self.query_one("#coaching-impact", Static).update(Panel(
                impact_text,
                title="[bold]COACHING IMPACT ON TRAINING[/]",
                border_style=BORDER,
            ))
        finally:
            session.close()

    def _show_staff_detail(self, staff_id: int) -> None:
        session = get_session()
        try:
            staff = session.get(Staff, staff_id)
            if not staff:
                return

            role_label = (staff.role or "unknown").replace("_", " ").title()

            detail_text = (
                f"[bold]{staff.name}[/]  --  {role_label}\n\n"
                f"[dim]Age:[/]          {staff.age or '?'}\n"
                f"[dim]Nationality:[/]  {staff.nationality or '?'}\n"
                f"[dim]Reputation:[/]   {staff.reputation or 50}\n"
                f"[dim]Wage:[/]         \u20ac{staff.wage or 0:.0f}K/wk\n"
                f"[dim]Contract:[/]     Until {staff.contract_expiry or '?'}\n"
            )

            if "scout" in (staff.role or ""):
                detail_text += (
                    f"\n[bold]Scouting Attributes:[/]\n"
                    f"  [dim]Ability:[/]         {staff.scouting_ability or 50}\n"
                    f"  [dim]Potential Judge:[/]  {staff.scouting_potential_judge or 50}"
                )
            elif "physio" in (staff.role or ""):
                detail_text += (
                    f"\n[bold]Medical Attributes:[/]\n"
                    f"  [dim]Physiotherapy:[/]    {staff.physiotherapy or 50}\n"
                    f"  [dim]Sports Science:[/]   {staff.sports_science or 50}"
                )
            else:
                detail_text += (
                    f"\n[bold]Coaching Attributes:[/]\n"
                    f"  [dim]Attacking:[/]   {staff.coaching_attacking or 50}\n"
                    f"  [dim]Defending:[/]   {staff.coaching_defending or 50}\n"
                    f"  [dim]Tactical:[/]    {staff.coaching_tactical or 50}\n"
                    f"  [dim]Technical:[/]   {staff.coaching_technical or 50}\n"
                    f"  [dim]Mental:[/]      {staff.coaching_mental or 50}\n"
                    f"  [dim]Fitness:[/]     {staff.coaching_fitness or 50}\n"
                    f"  [dim]GK:[/]          {staff.coaching_gk or 50}\n\n"
                    f"[bold]Management:[/]\n"
                    f"  [dim]Motivation:[/]  {staff.motivation or 50}\n"
                    f"  [dim]Discipline:[/]  {staff.discipline or 50}\n"
                    f"  [dim]Man Mgmt:[/]    {staff.man_management or 50}"
                )

            self.query_one("#staff-detail", Static).update(Panel(
                detail_text,
                title="[bold]STAFF PROFILE[/]",
                border_style=ACCENT,
            ))
        finally:
            session.close()
