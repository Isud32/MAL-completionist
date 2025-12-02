import sqlite3
import requests
import time

ANILIST_URL = "https://graphql.anilist.co"
QUERY = """
query ($year: Int, $page: Int) {
  Page(page: $page, perPage: 500) {
    media(type: ANIME, seasonYear: $year) {
      idMal
      title { romaji english native }
      seasonYear
      season
      averageScore
      favourites
      episodes
      duration
      format
      genres
      source
      studios(isMain: true) { nodes { name } }
      description(asHtml: false)
      coverImage { large }
      tags { name category }
    }
    pageInfo { hasNextPage }
  }
}
"""

conn = sqlite3.connect("anime.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS anime (
    mal_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    rating REAL,
    cant_episodes INTEGER,
    duration_per_episode INTEGER,
    type TEXT,
    genre TEXT,
    demographic TEXT,
    season TEXT,
    source TEXT,
    studio TEXT,
    favourites INTEGER,
    description TEXT,
    cover_url TEXT
)
""")
conn.commit()

def insert(row):
    cur.execute("""
        INSERT OR IGNORE INTO anime
        (mal_id, title, year, rating, cant_episodes, duration_per_episode,
         type, genre, demographic, season, source, studio, favourites, description, cover_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, row)
    conn.commit()


def fetch_year(year):
    page = 1
    count = 0
    wait_time = 1

    while True:
        try:
            r = requests.post(ANILIST_URL, json={"query": QUERY, "variables": {"year": year, "page": page}})
            r.raise_for_status()
            resp_json = r.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            time.sleep(5)
            continue

        # Handle AniList errors or missing data
        if "errors" in resp_json:
            err = resp_json["errors"][0]
            if err.get("status") == 429:
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 20)
                continue
            else:
                print(f"[AniList ERROR] year={year} page={page}: {resp_json['errors']}")
                break

        wait_time = 1  # reset wait time on success
        data = resp_json.get("data", {}).get("Page")
        if not data:
            print(f"[No data] year={year} page={page}")
            break

        for m in data.get("media", []):
            genres_list = m.get("genres") or []
            if "Hentai" in genres_list:
                continue  # skip Hentai

            mal_id = m["idMal"]
            title = m["title"].get("english") or m["title"].get("romaji") or m["title"].get("native")
            score = m.get("averageScore")
            episodes = m.get("episodes")
            duration = m.get("duration")
            fmt = m.get("format")
            genres = ", ".join(genres_list)
            season = m.get("season")
            source = m.get("source")
            studio = ", ".join([s["name"] for s in m.get("studios", {}).get("nodes", [])])
            favourites = m.get("favourites")
            description = m.get("description")
            cover_url = m.get("coverImage", {}).get("large")

            # demographic guess
            demo = None
            for t in m.get("tags", []):
                n = t.get("name", "").lower()
                if n in ("shounen", "shoujo", "seinen", "josei"):
                    demo = t["name"]
                    break

            row = (
                mal_id, title, year, score, episodes, duration, fmt,
                genres, demo, season, source, studio, favourites, description, cover_url
            )
            insert(row)
            count += 1

        if not data.get("pageInfo", {}).get("hasNextPage"):
            break

        page += 1
        time.sleep(0.25)

    print(f"{year} → {count} saved ")


if __name__ == "__main__":
    for y in range(1940, 2024):
        fetch_year(y)
