import xml.etree.ElementTree as ET 
import sqlite3

MAL_EXPORT_PATH = "data/animelist-1-12-25.xml"
DB_PATH = "anime.db"
def load_mal_watched(path):
    tree = ET.parse(path)
    root = tree.getroot()

    watched = set()

    for anime in root.findall("anime"):
        series_id = anime.find("series_animedb_id")
        if series_id is None or series_id.text is None:
            continue
        mal_id = int(series_id.text)

        status = anime.find("my_status")
        if status is None or status.text is None:
            status = ""
        else: 
            status = status.text.strip()

        if status.lower() == "completed" or status == "2":
            watched.add(mal_id)

    return watched

# Connect to local anime.db
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def get_anime_by_year(year):
    cur.execute("""
            SELECT mal_id, title
            FROM anime
            WHERE year = ?
        """, (year,))
    rows = cur.fetchall()
    return [{"mal_id": r[0], "title": r[1]} for r in rows]


def compare_year(year, watched_ids, year_list):
    total = len(year_list)
    remaining = [a for a in year_list if a["mal_id"] not in watched_ids]
    completed = total - len(remaining)
    percent = (completed / total * 100) if total > 0 else 0
    return year, completed, total, percent, remaining

# Load MAL export
watched_ids = load_mal_watched(MAL_EXPORT_PATH)

for year in range(1940, 2025):
    year_list = get_anime_by_year(year)

    if not year_list:
        continue
 
    year, completed, total, percent, remaining = compare_year(year, watched_ids, year_list)

    print(f"{year} | {percent:.2f}% | {completed}/{total}")
