import os
import requests
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fm.config import SAVE_DIR, DB_NAME
from fm.db.models import Club, League

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CLUBS_DIR = ASSETS_DIR / "clubs"
LEAGUES_DIR = ASSETS_DIR / "leagues"

# Create directories
CLUBS_DIR.mkdir(parents=True, exist_ok=True)
LEAGUES_DIR.mkdir(parents=True, exist_ok=True)

# Major Club Logo URLs (Wikimedia Commons or similar)
# Note: These are example URLs. In a real scenario, you'd use a more robust search or a dedicated API.
CLUB_LOGOS = {
    # England
    "Manchester City": "https://upload.wikimedia.org/wikipedia/en/e/eb/Manchester_City_FC_badge.svg",
    "Manchester United": "https://upload.wikimedia.org/wikipedia/en/7/7a/Manchester_United_FC_crest.svg",
    "Liverpool": "https://upload.wikimedia.org/wikipedia/en/0/0c/Liverpool_FC.svg",
    "Arsenal": "https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg",
    "Chelsea": "https://upload.wikimedia.org/wikipedia/en/c/cc/Chelsea_FC.svg",
    "Tottenham Hotspur": "https://upload.wikimedia.org/wikipedia/en/b/b4/Tottenham_Hotspur_badge.svg",
    "Newcastle United": "https://upload.wikimedia.org/wikipedia/commons/5/5a/Newcastle_United_FC_logo.svg",
    "Aston Villa": "https://upload.wikimedia.org/wikipedia/commons/f/f9/Aston_Villa_FC_logo.svg",
    # Spain
    "Real Madrid": "https://upload.wikimedia.org/wikipedia/en/5/56/Real_Madrid_CF.svg",
    "FC Barcelona": "https://upload.wikimedia.org/wikipedia/en/4/47/FC_Barcelona_%28crest%29.svg",
    "Atlético Madrid": "https://upload.wikimedia.org/wikipedia/commons/f/fc/Atl%C3%A9tico_Madrid_logo.svg",
    "Sevilla": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Sevilla_FC_logo.svg",
    "Real Sociedad": "https://upload.wikimedia.org/wikipedia/commons/2/2d/Real_Sociedad_logo.svg",
    "Villarreal": "https://upload.wikimedia.org/wikipedia/commons/7/7b/Villarreal_CF_logo.svg",
    "Athletic Club": "https://upload.wikimedia.org/wikipedia/commons/9/92/Athletic_Club_logo.svg",
    # Germany
    "FC Bayern München": "https://upload.wikimedia.org/wikipedia/commons/1/1b/FC_Bayern_M%C3%BCnchen_logo_%282017%29.svg",
    "Borussia Dortmund": "https://upload.wikimedia.org/wikipedia/commons/6/67/Borussia_Dortmund_logo.svg",
    "Bayer 04 Leverkusen": "https://upload.wikimedia.org/wikipedia/commons/b/b3/Logo_TSV_Bayer_04_Leverkusen.svg",
    "RB Leipzig": "https://upload.wikimedia.org/wikipedia/commons/0/04/Rb-Leipzig.svg",
    "Eintracht Frankfurt": "https://upload.wikimedia.org/wikipedia/commons/0/04/Eintracht_Frankfurt_Logo.svg",
    # Italy
    "Inter": "https://upload.wikimedia.org/wikipedia/commons/0/05/FC_Internazionale_Milano_2021.svg",
    "Milan": "https://upload.wikimedia.org/wikipedia/commons/d/d0/Logo_of_AC_Milan.svg",
    "Juventus": "https://upload.wikimedia.org/wikipedia/commons/1/15/Juventus_FC_2017_logo.svg",
    "Napoli": "https://upload.wikimedia.org/wikipedia/commons/d/de/SSC_Napoli.svg",
    "Roma": "https://upload.wikimedia.org/wikipedia/en/f/f7/AS_Roma_logo_%282017%29.svg",
    "Lazio": "https://upload.wikimedia.org/wikipedia/en/c/ce/S.S._Lazio_badge.svg",
    # France
    "Paris Saint Germain": "https://upload.wikimedia.org/wikipedia/en/a/a7/Paris_Saint-Germain_F.C..svg",
    "Olympique Lyonnais": "https://upload.wikimedia.org/wikipedia/fr/e/e2/Logo_Olympique_Lyonnais_-_2022.svg",
    "Monaco": "https://upload.wikimedia.org/wikipedia/en/b/ba/AS_Monaco_FC.svg",
    # Others
    "Benfica": "https://upload.wikimedia.org/wikipedia/en/a/a2/SL_Benfica_logo_with_3_stars.svg",
    "Porto": "https://upload.wikimedia.org/wikipedia/en/4/4c/FC_Porto.svg",
    "Sporting CP": "https://upload.wikimedia.org/wikipedia/en/3/3e/Sporting_Clube_de_Portugal.svg",
    "Ajax": "https://upload.wikimedia.org/wikipedia/en/7/79/Ajax_Amsterdam.svg",
}

LEAGUE_LOGOS = {
    "Premier League": "https://upload.wikimedia.org/wikipedia/en/f/f2/Premier_League_Logo.svg",
    "La Liga": "https://upload.wikimedia.org/wikipedia/commons/0/0f/LALIGA_Logo_2023.svg",
    "Bundesliga": "https://upload.wikimedia.org/wikipedia/en/d/df/Bundesliga_logo_%282017%29.svg",
    "Serie A": "https://upload.wikimedia.org/wikipedia/commons/e/e9/Serie_A_logo_2022.svg",
    "Ligue 1": "https://upload.wikimedia.org/wikipedia/commons/5/5e/Ligue1.svg",
    "Eredivisie": "https://upload.wikimedia.org/wikipedia/commons/0/0f/Eredivisie_nieuw_logo_2017-.svg",
    "Major League Soccer": "https://upload.wikimedia.org/wikipedia/commons/7/76/MLS_logo.svg",
    # UEFA Competitions (Alternative URLs to avoid 429)
    "champions_league": "https://www.logo.wine/a/logo/UEFA_Champions_League/UEFA_Champions_League-Logo.wine.svg",
    "europa_league": "https://upload.wikimedia.org/wikipedia/en/b/b5/UEFA_Europa_League_logo_%282021%29.svg",
    "conference_league": "https://upload.wikimedia.org/wikipedia/commons/7/7a/UEFA_Europa_Conference_League_logo.svg",
}

def download_file(url, path):
    # Some URLs might be Thumb URLs which are often more reliable for SVG-to-PNG
    # but we want SVGs. However, if SVG fails, we could try PNG.
    print(f"Downloading {url} to {path}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, stream=True, timeout=10, headers=headers)
        response.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

import time

def main():
    db_path = SAVE_DIR / DB_NAME
    if not db_path.exists():
        print(f"Database not found at {db_path}. Please run ingestion first.")
        
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    # Download Club Logos
    clubs = session.query(Club).all()
    for club in clubs:
        if club.name in CLUB_LOGOS:
            url = CLUB_LOGOS[club.name]
            ext = url.split('.')[-1]
            dest = CLUBS_DIR / f"{club.id}.{ext}"
            if not dest.exists():
                download_file(url, dest)
                time.sleep(5) # Be nice to Wikimedia

    # Download League Logos
    leagues = session.query(League).all()
    for league in leagues:
        if league.name in LEAGUE_LOGOS:
            url = LEAGUE_LOGOS[league.name]
            ext = url.split('.')[-1]
            dest = LEAGUES_DIR / f"{league.id}.{ext}"
            if not dest.exists():
                download_file(url, dest)
                time.sleep(5) # Be nice to Wikimedia

    # Download UEFA/Custom logos (if not already downloaded by ID)
    custom_names = ["champions_league", "europa_league", "conference_league"]
    for name in custom_names:
        if name in LEAGUE_LOGOS:
            url = LEAGUE_LOGOS[name]
            ext = url.split('.')[-1]
            dest = LEAGUES_DIR / f"{name}.{ext}"
            if not dest.exists():
                download_file(url, dest)
                time.sleep(5)

    session.close()

if __name__ == "__main__":
    main()
