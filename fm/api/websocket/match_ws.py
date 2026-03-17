"""WebSocket endpoint for live match simulation with real-time updates."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from fm.db.database import get_session
from fm.db.models import (
    Club, Fixture, MatchEvent, Player, Season, TacticalSetup,
)
from fm.world.season import SeasonManager

router = APIRouter()


@router.websocket("/ws/match")
async def match_websocket(ws: WebSocket):
    """WebSocket for live match simulation.

    Client sends: {"type": "start"}
    Server pushes: commentary, goal, stats_update, match_end
    """
    await ws.accept()

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "text": "Invalid JSON"})
                continue

            if msg.get("type") == "start":
                await _run_live_match(ws)
            else:
                await ws.send_json({"type": "error", "text": f"Unknown type: {msg.get('type')}"})
    except WebSocketDisconnect:
        pass


async def _run_live_match(ws: WebSocket):
    """Simulate the human club's next match with live commentary."""

    # 1. Read pre-match info
    session = get_session()
    try:
        season = session.query(Season).order_by(Season.year.desc()).first()
        if season is None or season.human_club_id is None:
            await ws.send_json({"type": "error", "text": "No active season or human club."})
            return

        human_club_id = season.human_club_id
        season_year = season.year
        next_md = season.current_matchday + 1

        fixture = (
            session.query(Fixture)
            .filter(
                Fixture.season == season_year,
                Fixture.matchday == next_md,
                Fixture.played.is_(False),
                (Fixture.home_club_id == human_club_id) | (Fixture.away_club_id == human_club_id),
            )
            .first()
        )
        if fixture is None:
            await ws.send_json({"type": "error", "text": "No upcoming fixture found."})
            return

        fixture_id = fixture.id
        home_club = session.get(Club, fixture.home_club_id)
        away_club = session.get(Club, fixture.away_club_id)
        home_name = home_club.name if home_club else "Home"
        away_name = away_club.name if away_club else "Away"
    finally:
        session.close()

    # 2. Send match_start
    await ws.send_json({
        "type": "match_start",
        "home": home_name,
        "away": away_name,
        "matchday": next_md,
    })

    # 3. Run simulation (separate session to avoid locks)
    sm_session = get_session()
    try:
        sm = SeasonManager(sm_session)
        sm.advance_matchday(human_club_id=human_club_id)
        sm_session.commit()
    except Exception as e:
        sm_session.rollback()
        await ws.send_json({"type": "error", "text": f"Simulation failed: {e}"})
        return
    finally:
        sm_session.close()

    # 4. Send kickoff
    await ws.send_json({"type": "commentary", "minute": 0, "text": "The referee blows the whistle. Kick off!"})

    # 5. Stream events from DB
    read_session = get_session()
    try:
        fixture = read_session.get(Fixture, fixture_id)
        events = (
            read_session.query(MatchEvent)
            .filter_by(fixture_id=fixture_id)
            .order_by(MatchEvent.minute)
            .all()
        )

        last_minute = 0
        home_goals = 0
        away_goals = 0
        sent_halftime = False

        for event in events:
            # Time delay
            if event.minute > last_minute:
                delay = min((event.minute - last_minute) * 0.3, 3.0)
                await asyncio.sleep(delay)
                last_minute = event.minute

            # Half-time
            if event.minute >= 45 and not sent_halftime:
                sent_halftime = True
                await ws.send_json({
                    "type": "commentary", "minute": 45,
                    "text": "Half time! The referee blows for the break.",
                })
                await ws.send_json({
                    "type": "stats_update", "minute": 45,
                    "data": _build_stats_dict(fixture, home_goals, away_goals),
                })
                await asyncio.sleep(2.0)

            # Track goals
            if event.event_type == "goal":
                if event.team_side == "home":
                    home_goals += 1
                else:
                    away_goals += 1
                scorer = event.player.name if event.player else "Unknown"
                await ws.send_json({
                    "type": "goal", "minute": event.minute,
                    "text": f"GOAL! {scorer} scores! {home_name} {home_goals} - {away_goals} {away_name}",
                    "data": {"scorer": scorer, "team_side": event.team_side, "score": f"{home_goals}-{away_goals}",
                             "home_goals": home_goals, "away_goals": away_goals},
                })
                await asyncio.sleep(1.5)

            # Commentary for all events
            await ws.send_json({
                "type": "commentary", "minute": event.minute,
                "text": event.description or f"{event.event_type} at {event.minute}'",
                "data": {"event_type": event.event_type, "team_side": event.team_side},
            })

            # Cards
            if event.event_type in ("yellow_card", "red_card"):
                await asyncio.sleep(0.5)

            # Periodic stats
            if event.minute > 0 and event.minute % 15 == 0:
                await ws.send_json({
                    "type": "stats_update", "minute": event.minute,
                    "data": _build_stats_dict(fixture, home_goals, away_goals),
                })

        # 6. Full time
        await ws.send_json({
            "type": "commentary", "minute": 90,
            "text": "Full time! The referee blows the final whistle.",
        })
        await ws.send_json({
            "type": "stats_update", "minute": 90,
            "data": _build_stats_dict(fixture, fixture.home_goals or 0, fixture.away_goals or 0),
        })

        # MOTM
        motm_name = None
        if fixture.motm_player_id:
            motm = read_session.get(Player, fixture.motm_player_id)
            if motm:
                motm_name = motm.name

        end_data = _build_stats_dict(fixture, fixture.home_goals or 0, fixture.away_goals or 0)
        end_data.update({
            "fixture_id": fixture_id,
            "home_club": home_name,
            "away_club": away_name,
            "attendance": fixture.attendance,
            "weather": fixture.weather,
            "motm": motm_name,
        })
        await ws.send_json({
            "type": "match_end",
            "data": end_data,
        })
    finally:
        read_session.close()


def _build_stats_dict(fixture: Fixture, home_goals: int, away_goals: int) -> dict:
    """Build a comprehensive stats dict for stats_update messages."""
    home_passes = fixture.home_passes or 0
    away_passes = fixture.away_passes or 0
    home_passes_completed = fixture.home_passes_completed or 0
    away_passes_completed = fixture.away_passes_completed or 0
    return {
        "home_goals": home_goals,
        "away_goals": away_goals,
        # Attacking
        "home_possession": round(fixture.home_possession or 50, 1),
        "away_possession": round(100 - (fixture.home_possession or 50), 1),
        "home_shots": fixture.home_shots or 0,
        "away_shots": fixture.away_shots or 0,
        "home_shots_on_target": fixture.home_shots_on_target or 0,
        "away_shots_on_target": fixture.away_shots_on_target or 0,
        "home_xg": round(fixture.home_xg or 0, 2),
        "away_xg": round(fixture.away_xg or 0, 2),
        "home_big_chances": fixture.home_big_chances or 0,
        "away_big_chances": fixture.away_big_chances or 0,
        "home_key_passes": fixture.home_key_passes or 0,
        "away_key_passes": fixture.away_key_passes or 0,
        # Passing
        "home_passes": home_passes,
        "away_passes": away_passes,
        "home_passes_completed": home_passes_completed,
        "away_passes_completed": away_passes_completed,
        "home_pass_accuracy": round(home_passes_completed / home_passes * 100, 1) if home_passes else 0,
        "away_pass_accuracy": round(away_passes_completed / away_passes * 100, 1) if away_passes else 0,
        "home_crosses": fixture.home_crosses or 0,
        "away_crosses": fixture.away_crosses or 0,
        # Defending
        "home_tackles": fixture.home_tackles_won or 0,
        "away_tackles": fixture.away_tackles_won or 0,
        "home_interceptions": fixture.home_interceptions or 0,
        "away_interceptions": fixture.away_interceptions or 0,
        "home_clearances": fixture.home_clearances or 0,
        "away_clearances": fixture.away_clearances or 0,
        "home_aerials_won": fixture.home_aerials_won or 0,
        "away_aerials_won": fixture.away_aerials_won or 0,
        # Discipline
        "home_fouls": fixture.home_fouls or 0,
        "away_fouls": fixture.away_fouls or 0,
        "home_offsides": fixture.home_offsides or 0,
        "away_offsides": fixture.away_offsides or 0,
        "home_yellow_cards": fixture.home_yellow_cards or 0,
        "away_yellow_cards": fixture.away_yellow_cards or 0,
        "home_red_cards": fixture.home_red_cards or 0,
        "away_red_cards": fixture.away_red_cards or 0,
        # GK
        "home_saves": fixture.home_saves or 0,
        "away_saves": fixture.away_saves or 0,
    }
