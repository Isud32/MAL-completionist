import xml.etree.ElementTree as ET 
import sqlite3
from typing import List, Optional, Dict
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

MAL_EXPORT_PATH = "data/animelist-1-12-25.xml"
DB_PATH = "anime.db"

app = typer.Typer(add_completion=False)
console = Console()

def load_mal_watched(path: str) -> set:
    """Load watched anime from MAL export"""
    try:
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
    except Exception as e:
        console.print(f"[red]Error loading MAL export: {e}[/red]")
        return set()

class AnimeDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self.watched_ids = load_mal_watched(MAL_EXPORT_PATH)
    
    def get_anime_by_year(self, year: int) -> List[Dict]:
        """Get all anime for a specific year"""
        self.cur.execute("""
            SELECT mal_id, title, rating, type, genre, duration_per_episode
            FROM anime
            WHERE year = ?
            ORDER BY rating DESC
        """, (year,))
        return [dict(row) for row in self.cur.fetchall()]
    
    def get_year_progress(self) -> List[Dict]:
        """Get progress statistics for all years"""
        self.cur.execute("""
            SELECT year, COUNT(*) as total
            FROM anime
            WHERE year IS NOT NULL
            GROUP BY year
            HAVING total > 0
            ORDER BY year
        """)
        
        progress_data = []
        for row in self.cur.fetchall():
            year = row['year']
            total = row['total']
            year_list = self.get_anime_by_year(year)
            
            watched = len([a for a in year_list if a['mal_id'] in self.watched_ids])
            remaining = len([a for a in year_list if a['mal_id'] not in self.watched_ids])
            percent = (watched / total * 100) if total > 0 else 0
            
            progress_data.append({
                'year': year,
                'watched': watched,
                'total': total,
                'remaining': remaining,
                'percent': percent
            })
        
        return progress_data
    
    def search_remaining(self, year: int, filters: Optional[Dict] = None) -> List[Dict]:
        """Get remaining anime for a year with optional filters"""
        query = """
            SELECT * FROM anime 
            WHERE year = ? AND mal_id NOT IN ({})
        """.format(','.join(['?'] * len(self.watched_ids)))
        
        params = [year] + list(self.watched_ids)
        
        # Add filters if provided
        if filters:
            filter_conditions = []
            order_clause = []
            for key, value in filters.items():
                if key == 'genre' and value:
                    filter_conditions.append("genre LIKE ?")
                    params.append(f'%{value}%')
                elif key == 'type' and value:
                    filter_conditions.append("type = ?")
                    params.append(value)
                elif key == 'duration_min' and value:
                    filter_conditions.append("duration_per_episode >= ?")
                    params.append(value)
                elif key == 'duration_max' and value:
                    filter_conditions.append("duration_per_episode <= ?")
                    params.append(value)
                elif key == 'rating_min' and value:
                    filter_conditions.append("rating >= ?")
                    params.append(value)
                elif key == 'demographic' and value:
                    filter_conditions.append("demographic = ?")
                    params.append(value)
                elif key == 'source' and value:
                    filter_conditions.append("source = ?")
                    params.append(value)
                elif key == 'studio' and value:
                    filter_conditions.append("studio LIKE = ?")
                    params.append(f"%{value}%")
                    # Not filters, ORDER BY
                elif key == 'most_popular' and value:
                    order_clause.append("favourites DESC") 
                elif key == 'least_popular' and value:
                    order_clause.append("favourites ASC")
                elif key == 'most_episodes' and value:
                    order_clause.append("cant_episodes DESC")
                elif key == 'least_episodes' and value:
                    order_clause.append("cant_episodes ASC")
                elif key == 'longest' and value:
                    order_clause.append("(cant_episodes * duration_per_episode) DESC")
                elif key == 'shortest' and value:
                    order_clause.append("(cant_episodes * duration_per_episode) ASC")
 

 
            if filter_conditions:
                query += " AND " + " AND ".join(filter_conditions)
            if order_clause:
                query += " ORDER BY " + ", ".join(order_clause)
            else:
                query += " ORDER BY rating DESC"
        
        self.cur.execute(query, params)
        return [dict(row) for row in self.cur.fetchall()]
    
    def close(self):
        self.conn.close()

@app.command()
def progress():
    """Show progress graph for all years"""
    db = AnimeDB(DB_PATH)
    
    console.print("\n[bold cyan]📊 Anime Completion Progress by Year[/bold cyan]\n")
    
    progress_data = db.get_year_progress()
    
    # Create table
    table = Table(title="Yearly Progress", box=box.ROUNDED)
    table.add_column("Year", style="cyan", justify="center")
    table.add_column("Completed", style="green", justify="center")
    table.add_column("Total", style="white", justify="center")
    table.add_column("Progress", justify="center")
    
    for data in progress_data:
        
        # Color based on completion percentage
        if data['percent'] == 100:
            progress_style = "bold green"
        elif data['percent'] >= 75:
            progress_style = "green"
        elif data['percent'] >= 50:
            progress_style = "yellow"
        elif data['percent'] >= 25:
            progress_style = "orange"
        else:
            progress_style = "red"
        
        table.add_row(
            str(data['year']),
            str(data['watched']),
            str(data['total']),
            f"[{progress_style}]{data['percent']:.1f}%[/{progress_style}]",
        )
    
    console.print(table)
    
    # Summary statistics
    total_watched = sum(d['watched'] for d in progress_data)
    total_anime = sum(d['total'] for d in progress_data)
    overall_percent = (total_watched / total_anime * 100) if total_anime > 0 else 0
    
    console.print(f"\n[bold]📈 Overall Progress:[/bold] {total_watched:,}/{total_anime:,} ({overall_percent:.1f}%)")
    db.close()

@app.command()
def year(
    year: int = typer.Argument(..., help="Year to show remaining anime"),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Filter by genre"),
    type_: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type (TV, Movie, OVA, etc)"),
    min_rating: Optional[float] = typer.Option(None, "--min-rating", "-r", help="Minimum rating"),
    max_duration: Optional[int] = typer.Option(None, "--max-duration", "-d", help="Maximum duration per episode"),
    min_duration: Optional[int] = typer.Option(None, "--min-duration", "-D", help="Minimum duration per episode"),
    studio: Optional[str] = typer.Option(None, "--studio", help="Filter by studio"),
    demographic: Optional[str] = typer.Option(None, "--demographic", "--demo", help="Filter by demographic (Seinen, shoujo, etc)"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter by source"),
    most_popular: bool = typer.Option(False, "--most-popular", help="Sort by most favourites"),
    least_popular: bool = typer.Option(False, "--least-popular", help="Sort by least favourites"),
    most_episodes: bool = typer.Option(False, "--most-episodes", help="Sort by most episodes"),
    least_episodes: bool = typer.Option(False, "--least-episodes", help="Sort by least episodes"),
    longest: bool = typer.Option(False, "--longest", help="Sort by longest total duration (episodes * duration)"),
    shortest: bool = typer.Option(False, "--shortest", help="Sort by shortest total duration (episodes * duration)"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of results to show")
):
    """Show remaining anime for a specific year with filters"""
    db = AnimeDB(DB_PATH)
    
    # Prepare filters
    filters = {}
    if genre:
        filters['genre'] = genre
    if type_:
        filters['type'] = type_
    if min_rating:
        filters['rating_min'] = min_rating
    if max_duration:
        filters['duration_max'] = max_duration
    if min_duration:
        filters['duration_min'] = min_duration
    if studio:
        filters['studio'] = studio
    if demographic:
        filters['demographic'] = demographic 
    if source:
        filters['source'] = source
    if most_popular:
        filters['most_popular'] = True
    if least_popular:
        filters['least_popular'] = True
    if most_episodes:
        filters['most_episodes'] = True
    if least_episodes:
        filters['least_episodes'] = True
    if longest:
        filters['longest'] = True
    if shortest:
        filters['shortest'] = True
    
    remaining = db.search_remaining(year, filters)
    
    if not remaining:
        console.print(f"[yellow]No remaining anime found for {year} with the given filters[/yellow]")
        db.close()
        return
    
    console.print(f"\n[bold cyan]Remaining Anime for {year}[/bold cyan]")
    console.print(f"[white]Found {len(remaining)} anime[/white]\n")
    
    # Create table
    table = Table(box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold", width=40)
    table.add_column("Type", style="cyan", width=8)
    table.add_column("Rating", style="yellow", width=8)
    table.add_column("Duration", style="green", width=10)
    table.add_column("Genre", style="magenta", width=30)
    
    for i, anime in enumerate(remaining[:limit], 1):
        # Truncate long titles
        title = anime['title'][:37] + "..." if len(anime['title']) > 40 else anime['title']
        
        table.add_row(
            str(i),
            title,
            anime.get('type', 'N/A'),
            str(anime.get('rating', 'N/A')),
            f"{anime.get('duration_per_episode', 'N/A')} min",
            anime.get('genre', 'N/A')[:27] + "..." if anime.get('genre') and len(anime['genre']) > 30 else anime.get('genre', 'N/A')
        )
    
    console.print(table)
    
    if len(remaining) > limit:
        console.print(f"\n[yellow]Showing {limit} of {len(remaining)} results. Use --limit to show more.[/yellow]")
    
    # Show available genres for this year
    if not filters.get('genre'):
        console.print(f"\n[bold] Popular Genres in {year}:[/bold]")
        genre_counts = {}
        for anime in remaining:
            if anime.get('genre'):
                genres = [g.strip() for g in anime['genre'].split(',')]
                for genre in genres:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1
        
        # Show top 10 genres
        top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        genre_str = ", ".join([f"{g[0]} ({g[1]})" for g in top_genres])
        console.print(genre_str)
    
    db.close()

@app.command()
def search(
    query: str = typer.Argument(..., help="Search term for anime titles"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Filter by year"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of results to show")
):
    """Search anime by title"""
    db = AnimeDB(DB_PATH)
    
    sql_query = """
        SELECT * FROM anime 
        WHERE title LIKE ? 
    """
    params = [f'%{query}%']
    
    if year:
        sql_query += " AND year = ?"
        params.append(year)
    
    sql_query += " ORDER BY rating DESC LIMIT ?"
    params.append(limit)
    
    db.cur.execute(sql_query, params)
    results = [dict(row) for row in db.cur.fetchall()]
    
    if not results:
        console.print(f"[yellow]No anime found matching '{query}'[/yellow]")
        db.close()
        return
    
    console.print(f"\n[bold cyan]🔍 Search Results for '{query}'[/bold cyan]\n")
    
    table = Table(box=box.ROUNDED)
    table.add_column("Title", style="bold", width=40)
    table.add_column("Year", style="cyan", width=6)
    table.add_column("Type", style="cyan", width=8)
    table.add_column("Rating", style="yellow", width=8)
    table.add_column("Status", width=10)
    
    for anime in results:
        title = anime['title'][:37] + "..." if len(anime['title']) > 40 else anime['title']
        status = "✅ Watched" if anime['mal_id'] in db.watched_ids else "⏳ Pending"
        status_style = "green" if "Watched" in status else "yellow"
        
        table.add_row(
            title,
            str(anime.get('year', 'N/A')),
            anime.get('type', 'N/A'),
            str(anime.get('rating', 'N/A')),
            f"[{status_style}]{status}[/{status_style}]"
        )
    
    console.print(table)
    db.close()

@app.command()
def stats():
    """Show overall statistics"""
    db = AnimeDB(DB_PATH)
    
    # Get overall stats
    db.cur.execute("SELECT COUNT(*) as total FROM anime")
    total_anime = db.cur.fetchone()['total']
    
    db.cur.execute("SELECT COUNT(*) as watched FROM anime WHERE mal_id IN ({})".format(
        ','.join(['?'] * len(db.watched_ids))
    ), list(db.watched_ids))
    watched = db.cur.fetchone()['watched']
    
    percent = (watched / total_anime * 100) if total_anime > 0 else 0
    
    console.print(Panel.fit(
        f"[bold cyan]Anime Statistics[/bold cyan]\n\n"
        f"[bold]Total Anime in DB:[/bold] {total_anime:,}\n"
        f"[bold]Watched:[/bold] {watched:,}\n"
        f"[bold]Remaining:[/bold] {total_anime - watched:,}\n"
        f"[bold]Completion:[/bold] [green]{percent:.1f}%[/green]\n\n"
        f"[dim]MAL Export: {MAL_EXPORT_PATH}[/dim]\n"
        f"[dim]Database: {DB_PATH}[/dim]",
        title="Statistics",
        border_style="cyan"
    ))
    
    db.close()

if __name__ == "__main__":
    app()
