"""Template-based match commentary generator.

Rich, varied commentary with context-awareness for dramatic moments,
late goals, comebacks, and tactical situations.
"""
from __future__ import annotations

import random


class Commentary:
    """Generates human-readable commentary strings for match events."""

    # ── Goal templates ─────────────────────────────────────────────────────

    _GOAL_TEMPLATES = [
        "⚽ GOAL! {scorer} scores for {team}!",
        "⚽ GOAL! {scorer} finds the back of the net! {team} celebrate!",
        "⚽ GOAL! Brilliant finish from {scorer}!",
        "⚽ GOAL! {scorer} makes no mistake and scores for {team}!",
        "⚽ GOAL! Clinical finishing from {scorer}! That's a quality strike.",
        "⚽ GOAL! {scorer} wheels away in celebration! {team} are jubilant!",
        "⚽ GOAL! You won't see a better finish than that! {scorer} for {team}!",
        "⚽ GOAL! Cool as you like from {scorer}. Nerves of steel.",
        "⚽ GOAL! The net bulges! {scorer} has done it for {team}!",
        "⚽ GOAL! What a moment! {scorer} fires {team} ahead!",
    ]

    _LATE_GOAL_TEMPLATES = [
        "⚽ LATE DRAMA! {scorer} scores in the dying minutes for {team}!",
        "⚽ HEARTBREAK AND ECSTASY! {scorer} with a last-gasp goal!",
        "⚽ INCREDIBLE! {scorer} pops up when it matters most! {team} go wild!",
        "⚽ RIGHT AT THE DEATH! {scorer} rescues {team}!",
        "⚽ STOPPAGE TIME GOAL! {scorer}! You couldn't write this!",
    ]

    _EQUALISER_TEMPLATES = [
        "⚽ EQUALISER! {scorer} levels it up for {team}! Game on!",
        "⚽ BACK IN IT! {scorer} scores to draw {team} level!",
        "⚽ THEY'RE LEVEL! {scorer} brings {team} back into the match!",
    ]

    _GOAL_ASSIST_TEMPLATES = [
        " Assisted by {assister}.",
        " Great ball from {assister} to set it up.",
        " {assister} with the key pass.",
        " {assister} provided the assist.",
        " Lovely through ball from {assister} makes the goal.",
        " {assister}'s vision opens up the defence.",
        " {assister} delivers the perfect pass. Clinical from both.",
    ]

    _HEADER_GOAL_TEMPLATES = [
        "⚽ GOAL! {scorer} heads it in from {crosser}'s cross!",
        "⚽ GOAL! Powerful header from {scorer}! {crosser} delivered a pinpoint cross.",
        "⚽ GOAL! {scorer} rises highest and heads home!",
        "⚽ GOAL! Bullet header! {scorer} meets {crosser}'s delivery perfectly!",
        "⚽ GOAL! {scorer} gets above the defence and nods home from {crosser}'s cross!",
    ]

    _PENALTY_GOAL_TEMPLATES = [
        "⚽ GOAL! {scorer} sends the keeper the wrong way from the spot!",
        "⚽ GOAL! {scorer} converts the penalty! Cool and composed.",
        "⚽ GOAL! Right into the corner! {scorer} makes no mistake from twelve yards.",
        "⚽ GOAL! Unstoppable penalty from {scorer}! The keeper had no chance.",
    ]

    _FREE_KICK_GOAL_TEMPLATES = [
        "⚽ WHAT A FREE KICK! {scorer} curls it into the top corner!",
        "⚽ GOAL! {scorer} bends the free kick over the wall and in!",
        "⚽ SENSATIONAL! {scorer} scores directly from the free kick!",
    ]

    _SAVE_TEMPLATES = [
        "🧤 Great save by {keeper}! {shooter}'s effort is denied.",
        "🧤 {keeper} pulls off a fine stop to keep out {shooter}'s shot.",
        "🧤 Excellent reflexes from {keeper} to save {shooter}'s attempt.",
        "🧤 {keeper} gets down well to save from {shooter}.",
        "🧤 Superb stop! {keeper} tips {shooter}'s effort away.",
        "🧤 {keeper} stands tall and blocks {shooter}'s shot!",
        "🧤 What a save! {keeper} somehow keeps {shooter}'s effort out!",
        "🧤 {keeper} at full stretch to deny {shooter}! Outstanding goalkeeping.",
    ]

    _YELLOW_TEMPLATES = [
        "🟨 Yellow card — {fouler} is booked for a foul on {victim}.",
        "🟨 Caution for {fouler} ({team}) after bringing down {victim}.",
        "🟨 The referee shows {fouler} a yellow card. Reckless challenge on {victim}.",
        "🟨 {fouler} goes into the book for a late tackle on {victim}.",
        "🟨 The referee reaches for his pocket — yellow for {fouler} ({team}).",
    ]

    _RED_TEMPLATES = [
        "🟥 RED CARD! {fouler} is sent off for a dangerous challenge on {victim}!",
        "🟥 Straight red for {fouler} ({team})! That's a terrible tackle on {victim}.",
        "🟥 {fouler} sees red! {team} are down to {count} men.",
        "🟥 OFF HE GOES! {fouler} shown a straight red for that horror tackle on {victim}!",
    ]

    _SECOND_YELLOW_TEMPLATES = [
        "🟨🟥 Second yellow for {fouler}! {team} are down to {count} men.",
        "🟨🟥 {fouler} picks up a second booking and is sent off! {team} in trouble.",
        "🟨🟥 That's a second yellow! {fouler} walks. {team} must dig in with {count}.",
    ]

    _INTERCEPTION_TEMPLATES = [
        "🔄 {interceptor} reads the play and intercepts!",
        "🔄 Good reading of the game by {interceptor}, picks off {passer}'s pass.",
        "🔄 {interceptor} steps in to cut out {passer}'s ball.",
        "🔄 Alert defending from {interceptor} — {passer}'s pass is cut out.",
    ]

    _INJURY_TEMPLATES = [
        "🏥 {player} ({team}) goes down injured and has to come off.",
        "🏥 Bad news for {team} — {player} appears to have picked up an injury.",
        "🏥 {player} is in real discomfort. The physios are on. This doesn't look good for {team}.",
        "🏥 Concern for {team} as {player} pulls up holding their leg.",
    ]

    _SUB_TEMPLATES = [
        "🔄 Substitution ({team}): {off} ➜ {on}",
        "🔄 {team} make a change: {off} is replaced by {on}.",
        "🔄 Fresh legs for {team}: {on} comes on for {off}.",
    ]

    _WOODWORK_TEMPLATES = [
        "💥 {shooter} hits the woodwork! So close for {team}!",
        "💥 Off the post! {shooter} rattles the frame of the goal!",
        "💥 {shooter}'s effort crashes against the crossbar! Agonising for {team}!",
        "💥 It comes back off the woodwork! {shooter} can't believe it!",
        "💥 PING! {shooter}'s shot cannons off the post! What a let-off!",
    ]

    _OFFSIDE_TEMPLATES = [
        "🚩 Offside! {player} is flagged. Free kick to the defending side.",
        "🚩 The flag goes up — {player} ({team}) caught offside.",
        "🚩 {player} timed the run wrong. Offside.",
    ]

    _BIG_CHANCE_MISSED_TEMPLATES = [
        "😱 Big chance missed! {player} should have scored there for {team}!",
        "😱 {player} wastes a golden opportunity! {team} will rue that miss.",
        "😱 How has {player} not scored?! A huge chance goes begging for {team}.",
        "😱 {player} blazes it over from close range! {team} can't believe it.",
        "😱 Head in hands! {player} misses a sitter for {team}!",
    ]

    _CORNER_TEMPLATES = [
        "🚩 Corner kick to {team}.",
        "🚩 {team} win a corner. The ball is swung in...",
    ]

    _CLEARANCE_TEMPLATES = [
        "🛡️ Important clearance by {player}.",
        "🛡️ {player} clears the danger for {team}.",
        "🛡️ Last-ditch clearance from {player}! That was vital.",
    ]

    _PENALTY_AWARDED_TEMPLATES = [
        "🔴 PENALTY! {team} are awarded a penalty kick!",
        "🔴 The referee points to the spot! Penalty to {team}!",
        "🔴 PENALTY! There's contact in the box and the referee has no hesitation!",
    ]

    _PENALTY_MISS_TEMPLATES = [
        "❌ MISSED! {taker} blazes the penalty over the bar!",
        "❌ The penalty is saved! Great stop by the goalkeeper!",
        "❌ Off the post! {taker} hits the woodwork from the spot!",
    ]

    _DRIBBLE_TEMPLATES = [
        "💨 Brilliant run from {player}! Leaves the defender for dead!",
        "💨 {player} dances past the challenge with a lovely piece of skill!",
        "💨 {player} shows great feet to beat the defender!",
    ]

    _TACKLE_TEMPLATES = [
        "🦶 Crunching tackle from {player}! Wins the ball cleanly.",
        "🦶 Great challenge by {player} to stop the attack.",
        "🦶 {player} times the tackle perfectly to dispossess the attacker.",
    ]

    _ATMOSPHERE_TEMPLATES = [
        "The crowd are on their feet!",
        "The stadium is rocking!",
        "What an atmosphere here!",
        "The fans are making themselves heard!",
        "The noise levels have gone up a notch!",
    ]

    _HALF_TIME_TEMPLATES = [
        "45' ── HALF TIME ── {home} {hg}-{ag} {away}",
    ]

    _FULL_TIME_TEMPLATES = [
        "90' ── FULL TIME ── {home} {hg}-{ag} {away}",
    ]

    # ── Public methods ─────────────────────────────────────────────────────

    def goal(
        self, minute: int, scorer: str, team: str, *,
        assist_name: str | None = None,
        score_home: int = 0, score_away: int = 0,
        home_name: str = "Home", away_name: str = "Away",
        is_equaliser: bool = False,
        detail: str = "",
    ) -> str:
        # Pick template based on context
        if detail == "penalty_goal":
            templates = self._PENALTY_GOAL_TEMPLATES
        elif detail == "free_kick_goal":
            templates = self._FREE_KICK_GOAL_TEMPLATES
        elif minute >= 85:
            templates = self._LATE_GOAL_TEMPLATES
        elif is_equaliser:
            templates = self._EQUALISER_TEMPLATES
        else:
            templates = self._GOAL_TEMPLATES

        text = f"{minute}' " + random.choice(templates).format(
            scorer=scorer, team=team
        )
        if assist_name:
            text += random.choice(self._GOAL_ASSIST_TEMPLATES).format(
                assister=assist_name
            )
        text += f"\n    {home_name} {score_home}-{score_away} {away_name}"

        # Atmosphere for important goals
        if minute >= 85 or is_equaliser or score_home == score_away:
            text += f"\n    {random.choice(self._ATMOSPHERE_TEMPLATES)}"

        return text

    def header_goal(
        self, minute: int, scorer: str, crosser: str, team: str,
        score_home: int, score_away: int,
        home_name: str, away_name: str,
    ) -> str:
        text = f"{minute}' " + random.choice(self._HEADER_GOAL_TEMPLATES).format(
            scorer=scorer, crosser=crosser, team=team
        )
        text += f"\n    {home_name} {score_home}-{score_away} {away_name}"
        return text

    def save(self, minute: int, keeper: str, shooter: str) -> str:
        return f"{minute}' " + random.choice(self._SAVE_TEMPLATES).format(
            keeper=keeper, shooter=shooter
        )

    def yellow_card(self, minute: int, fouler: str, victim: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._YELLOW_TEMPLATES).format(
            fouler=fouler, victim=victim, team=team
        )

    def red_card(self, minute: int, fouler: str, victim: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._RED_TEMPLATES).format(
            fouler=fouler, victim=victim, team=team, count="10"
        )

    def second_yellow(self, minute: int, fouler: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._SECOND_YELLOW_TEMPLATES).format(
            fouler=fouler, team=team, count="10"
        )

    def interception(self, minute: int, interceptor: str, passer: str,
                     team: str) -> str:
        return f"{minute}' " + random.choice(self._INTERCEPTION_TEMPLATES).format(
            interceptor=interceptor, passer=passer, team=team
        )

    def injury(self, minute: int, player: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._INJURY_TEMPLATES).format(
            player=player, team=team
        )

    def substitution(self, minute: int, off: str, on: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._SUB_TEMPLATES).format(
            off=off, on=on, team=team
        )

    def woodwork(self, minute: int, shooter: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._WOODWORK_TEMPLATES).format(
            shooter=shooter, team=team
        )

    def offside(self, minute: int, player: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._OFFSIDE_TEMPLATES).format(
            player=player, team=team
        )

    def big_chance_missed(self, minute: int, player: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._BIG_CHANCE_MISSED_TEMPLATES).format(
            player=player, team=team
        )

    def corner(self, minute: int, team: str) -> str:
        return f"{minute}' " + random.choice(self._CORNER_TEMPLATES).format(
            team=team
        )

    def clearance(self, minute: int, player: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._CLEARANCE_TEMPLATES).format(
            player=player, team=team
        )

    def penalty_awarded(self, minute: int, team: str) -> str:
        return f"{minute}' " + random.choice(self._PENALTY_AWARDED_TEMPLATES).format(
            team=team
        )

    def penalty_missed(self, minute: int, taker: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._PENALTY_MISS_TEMPLATES).format(
            taker=taker, team=team
        )

    def dribble_success(self, minute: int, player: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._DRIBBLE_TEMPLATES).format(
            player=player, team=team
        )

    def tackle_success(self, minute: int, player: str, team: str) -> str:
        return f"{minute}' " + random.choice(self._TACKLE_TEMPLATES).format(
            player=player, team=team
        )

    def half_time(self, home_name: str, away_name: str,
                  home_goals: int, away_goals: int) -> str:
        return random.choice(self._HALF_TIME_TEMPLATES).format(
            home=home_name, away=away_name, hg=home_goals, ag=away_goals
        )

    def full_time(self, home_name: str, away_name: str,
                  home_goals: int, away_goals: int) -> str:
        return random.choice(self._FULL_TIME_TEMPLATES).format(
            home=home_name, away=away_name, hg=home_goals, ag=away_goals
        )

    def atmosphere(self) -> str:
        return random.choice(self._ATMOSPHERE_TEMPLATES)

    def passage_of_play(self, minute: int, team: str) -> str:
        """Generate ambient commentary for periods without major events."""
        templates = [
            f"{minute}' {team} keep possession, probing for an opening.",
            f"{minute}' Patient build-up play from {team} here.",
            f"{minute}' {team} looking to create something on the break.",
            f"{minute}' The ball is recycled by {team}, looking for the gap.",
            f"{minute}' {team} with some nice passing moves in midfield.",
            f"{minute}' Tight defensive battle in midfield right now.",
            f"{minute}' The game has settled into a rhythm.",
        ]
        return random.choice(templates)

    # ── V2 Engine: New Action Commentary ─────────────────────────────────

    _THROUGH_BALL_TEMPLATES = [
        "⚡ {passer} plays a brilliant through ball for {runner}!",
        "⚡ What vision from {passer}! {runner} is through on goal!",
        "⚡ {passer} threads the needle! {runner} is in behind the defence!",
        "⚡ Incisive pass from {passer} splits the defence for {runner}!",
        "⚡ {passer} picks out {runner} with a perfectly weighted through ball!",
        "⚡ Exquisite vision from {passer}! {runner} races onto the pass!",
    ]

    _THROUGH_BALL_FAIL_TEMPLATES = [
        "{passer} tries a through ball but the defence reads it well.",
        "{passer}'s attempted through ball is overhit. Goal kick.",
        "Nice idea from {passer} but the pass is too heavy for {runner}.",
        "{passer} looks for {runner} but the gap isn't there.",
    ]

    _SWITCH_PLAY_TEMPLATES = [
        "🔄 {passer} switches the play to the opposite flank!",
        "🔄 Excellent crossfield ball from {passer} to {target}!",
        "🔄 {passer} opens up the pitch with a sweeping pass to {target}!",
        "🔄 {passer} changes the point of attack — the ball goes wide to {target}.",
        "🔄 Great awareness from {passer} to switch to the open side for {target}.",
    ]

    _ONE_TWO_TEMPLATES = [
        "🔁 Lovely one-two between {player1} and {player2}!",
        "🔁 Quick wall pass! {player1} and {player2} combine brilliantly!",
        "🔁 {player1} plays it to {player2} and gets it straight back!",
        "🔁 Slick interchange between {player1} and {player2}! The defender is left flat-footed.",
        "🔁 {player1} and {player2} with a beautiful give-and-go!",
    ]

    _HOLD_UP_TEMPLATES = [
        "💪 {player} holds up the ball well, waiting for support.",
        "💪 Good strength from {player} to shield the ball from the defender.",
        "💪 {player} receives with back to goal and brings others into play.",
        "💪 {player} muscles the defender off and lays it off for {target}.",
    ]

    _LONG_BALL_TEMPLATES = [
        "🎯 Long ball forward from {passer}! {target} goes to meet it.",
        "🎯 {passer} bypasses the midfield with a direct ball to {target}!",
        "🎯 Route one football! {passer} hits it long for {target} to chase.",
        "🎯 {passer} launches it forward — {target} wins the aerial duel!",
    ]

    _OVERLAP_TEMPLATES = [
        "🏃 {player} makes an overlapping run down the flank!",
        "🏃 The full-back {player} bombs forward in support!",
        "🏃 {player} overlap! Creating an overload on the wing.",
        "🏃 {player} surges past the winger, making a darting run!",
    ]

    _LAY_OFF_TEMPLATES = [
        "🎯 {player} lays it off for {target} on the edge of the box!",
        "🎯 Neat lay-off from {player} — {target} has space to shoot!",
        "🎯 {player} with a clever touch back for the onrushing {target}.",
    ]

    _BUILD_UP_TEMPLATES = [
        "{team} build patiently from the back.",
        "{team} play out from defence, keeping possession.",
        "The goalkeeper starts the move, rolling it out to the centre-back.",
        "Patient play from {team}, working the ball through the thirds.",
        "{team} move the ball through midfield with short, crisp passing.",
    ]

    _PRESSING_TEMPLATES = [
        "🔥 {team} press high immediately after losing the ball!",
        "🔥 Intense pressing from {team}! They want the ball back NOW.",
        "🔥 {player} leads the press, harrying the defender into a mistake!",
        "🔥 {team} swarm the ball carrier! No time on the ball.",
    ]

    _COUNTER_COMMENTARY = [
        "⚡ Counter-attack! {team} break at pace!",
        "⚡ {team} spring forward on the break! Numbers going forward!",
        "⚡ Quick transition from {team}! They've caught the defence out!",
        "⚡ The ball is won and {team} launch a devastating counter!",
    ]

    _SET_PIECE_CORNER_NEAR = [
        "🚩 Near-post corner from {taker}. {target} attacks it!",
        "🚩 Whipped to the near post by {taker}! {target} gets a flick on!",
    ]

    _SET_PIECE_CORNER_FAR = [
        "🚩 {taker} floats it to the far post. {target} rises!",
        "🚩 Deep corner from {taker} — {target} at the back post!",
    ]

    _SET_PIECE_CORNER_SHORT = [
        "🚩 Short corner. {taker} plays it to {target} nearby.",
        "🚩 {taker} goes short. Clever variation here.",
    ]

    _THROW_IN_LONG = [
        "📏 Long throw-in from {player}! It's like a corner kick!",
        "📏 {player} launches a long throw into the box!",
    ]

    _GK_DISTRIBUTION = [
        "{keeper} rolls it out to the centre-back to start the move.",
        "{keeper} sends a long kick forward, looking for the striker.",
        "{keeper} takes it short, playing out from the back.",
        "{keeper} throws it out quickly to launch the counter!",
    ]

    _TACTICAL_CHANGE = [
        "📋 Tactical change! {team} switch to a more {style} approach.",
        "📋 {team} are reorganising — the manager wants changes.",
        "📋 Instructions from the bench! {team} are shifting shape.",
    ]

    _MOMENTUM_SURGE = [
        "🔥 {team} are really building momentum now!",
        "🔥 The crowd can sense it — {team} are on top!",
        "🔥 All the pressure is from {team}! Can they capitalize?",
        "🔥 {team} are turning the screw here!",
    ]

    _MOMENTUM_DROP = [
        "{team} have lost their way a bit here.",
        "{team} are struggling to get a foothold in the game.",
        "A frustrating spell for {team}. Nothing is coming off for them.",
    ]

    _VAR_CHECK = [
        "⏸️ Hold on — the referee is checking with the assistant...",
        "⏸️ There's been a stoppage. The referee wants another look.",
    ]

    _TIME_WASTING = [
        "⏰ {team} are taking their time here. Slowing the game down.",
        "⏰ The ball goes out and {team} aren't in any hurry to restart.",
        "⏰ The goalkeeper takes an age over this goal kick. The referee is not impressed.",
    ]

    _CROWD_REACTIONS = [
        "The home fans are getting restless...",
        "A chorus of boos from the home supporters.",
        "The crowd rise to their feet in appreciation!",
        "The away fans are in full voice!",
        "The atmosphere is electric inside the stadium!",
        "A standing ovation as {player} is substituted.",
        "The fans are singing the name of {player}!",
    ]

    _INJURY_DETAILED = [
        "🏥 {player} goes down clutching their hamstring. This could be serious.",
        "🏥 {player} has turned their ankle after that challenge. The physio is on.",
        "🏥 {player} pulls up with what looks like a muscular problem.",
        "🏥 {player} takes a knock to the knee. They're trying to run it off...",
        "🏥 {player} is stretchered off. A worrying sight for {team}.",
    ]

    # ── V2 Commentary Methods ────────────────────────────────────────────

    def through_ball(self, minute: int, passer: str, runner: str,
                     success: bool) -> str:
        if success:
            return f"{minute}' " + random.choice(self._THROUGH_BALL_TEMPLATES).format(
                passer=passer, runner=runner)
        return f"{minute}' " + random.choice(self._THROUGH_BALL_FAIL_TEMPLATES).format(
            passer=passer, runner=runner)

    def switch_play(self, minute: int, passer: str, target: str) -> str:
        return f"{minute}' " + random.choice(self._SWITCH_PLAY_TEMPLATES).format(
            passer=passer, target=target)

    def one_two(self, minute: int, player1: str, player2: str) -> str:
        return f"{minute}' " + random.choice(self._ONE_TWO_TEMPLATES).format(
            player1=player1, player2=player2)

    def hold_up_play(self, minute: int, player: str,
                     target: str | None = None) -> str:
        templates = self._HOLD_UP_TEMPLATES
        if target:
            templates = [t for t in templates if "{target}" in t]
            if not templates:
                templates = self._HOLD_UP_TEMPLATES[:2]
        t = random.choice(templates)
        return f"{minute}' " + t.format(player=player, target=target or "")

    def long_ball(self, minute: int, passer: str, target: str) -> str:
        return f"{minute}' " + random.choice(self._LONG_BALL_TEMPLATES).format(
            passer=passer, target=target)

    def overlap_run(self, minute: int, player: str) -> str:
        return f"{minute}' " + random.choice(self._OVERLAP_TEMPLATES).format(
            player=player)

    def lay_off(self, minute: int, player: str, target: str) -> str:
        return f"{minute}' " + random.choice(self._LAY_OFF_TEMPLATES).format(
            player=player, target=target)

    def build_up(self, minute: int, team: str) -> str:
        return f"{minute}' " + random.choice(self._BUILD_UP_TEMPLATES).format(
            team=team)

    def pressing_event(self, minute: int, team: str,
                       player: str | None = None) -> str:
        templates = self._PRESSING_TEMPLATES
        if player:
            templates = [t for t in templates if "{player}" in t]
        if not templates:
            templates = self._PRESSING_TEMPLATES[:2]
        t = random.choice(templates)
        return f"{minute}' " + t.format(team=team, player=player or "")

    def counter_attack(self, minute: int, team: str) -> str:
        return f"{minute}' " + random.choice(self._COUNTER_COMMENTARY).format(
            team=team)

    def corner_variation(self, minute: int, taker: str, target: str,
                         variant: str = "near") -> str:
        if variant == "near":
            templates = self._SET_PIECE_CORNER_NEAR
        elif variant == "far":
            templates = self._SET_PIECE_CORNER_FAR
        else:
            templates = self._SET_PIECE_CORNER_SHORT
        return f"{minute}' " + random.choice(templates).format(
            taker=taker, target=target)

    def gk_distribution(self, minute: int, keeper: str) -> str:
        return f"{minute}' " + random.choice(self._GK_DISTRIBUTION).format(
            keeper=keeper)

    def tactical_change(self, minute: int, team: str,
                        style: str = "attacking") -> str:
        return f"{minute}' " + random.choice(self._TACTICAL_CHANGE).format(
            team=team, style=style)

    def momentum_shift(self, minute: int, team: str, positive: bool) -> str:
        templates = self._MOMENTUM_SURGE if positive else self._MOMENTUM_DROP
        return f"{minute}' " + random.choice(templates).format(team=team)

    def time_wasting(self, minute: int, team: str) -> str:
        return f"{minute}' " + random.choice(self._TIME_WASTING).format(
            team=team)

    def crowd_reaction(self, minute: int,
                       player: str | None = None) -> str:
        templates = self._CROWD_REACTIONS
        if player:
            templates = [t for t in templates if "{player}" in t]
        if not templates:
            templates = self._CROWD_REACTIONS[:3]
        return f"{minute}' " + random.choice(templates).format(
            player=player or "")

    def detailed_injury(self, minute: int, player: str,
                        team: str) -> str:
        return f"{minute}' " + random.choice(self._INJURY_DETAILED).format(
            player=player, team=team)
