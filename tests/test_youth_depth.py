import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fm.db.models import Base, Club, League, Manager, Staff, YouthCandidate, Player, NewsItem
from fm.world.youth_academy import YouthAcademyManager

# Setup dummy DB
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Mock data
league = League(name="Premier League", country="England", tier=1, num_teams=20)
session.add(league)
session.flush()

club = Club(name="Test FC", league_id=league.id, youth_academy_level=8, scouting_network_level=5)
session.add(club)
session.flush()

manager = Manager(name="Boss", club_id=club.id, youth_development=85)
session.add(manager)
session.flush()

coach = Staff(name="Coach", club_id=club.id, role="youth_coach", coaching_mental=75, coaching_technical=80)
session.add(coach)
session.flush()

ya = YouthAcademyManager(session)

print("--- Testing Youth Intake ---")
candidates = ya.generate_youth_intake(club.id, 2024)
for c in candidates:
    print(f"Name: {c.name}, Pos: {c.position}, Arch: {c.archetype}, Pot: {c.potential_min}-{c.potential_max}, Det: {c.determination}")

print("\n--- Testing Promotion ---")
if candidates:
    cand = candidates[0]
    cand_id = cand.id
    player = ya.promote_to_first_team(cand_id, 2024)
    if player:
        print(f"Promoted: {player.name}")
        print(f"Archetype: {player.squad_role if hasattr(player, 'squad_role') else 'N/A'}")
        print(f"Determination: {player.determination} (Expected same as cand: {cand.determination})")
        print(f"Professionalism: {player.professionalism}")
        print(f"Strength: {player.strength}")
        print(f"Finishing: {player.finishing}")
    else:
        print("Promotion failed")
else:
    print("No candidates generated")
