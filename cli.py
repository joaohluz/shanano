import time
import typer
import rich

from controllers.database import connect, init_db
import controllers.song_manager as song_manager
import controllers.match_service as match_service

app = typer.Typer()

conn = connect()
init_db(conn)

@app.command()
def list():
    rich.print(f"[blue]Listing songs in DB:[/blue]")
    for song in song_manager.list_songs(conn):
        rich.print(f"- {song}")

@app.command()
def add(path: str):
    # load -> spectrogram -> peaks -> fingerprints -> DB
    rich.print(f"[green]Adding song from {path}[/green]")
    code, msg = song_manager.add_song(conn, path)
    if code == 0:
        rich.print(f"[green]{msg}[/green]")
    else:
        rich.print(f"[red]{msg}[/red]")

@app.command()
def match(seconds: int = 7):
    for i in range(3, 0, -1):
        print(f"\r--- Recording starts in {i} seconds ---", end='', flush=True)
        time.sleep(1)
    print()
    matches = match_service.match(conn)
    for song_name, score in matches:
        rich.print(f"[blue]{song_name}[/blue]: {score}")


if __name__ == "__main__":
    app()


