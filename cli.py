from pathlib import Path
import threading
import time
import typer
import rich

from controllers.database import connect, init_db
import controllers.song_manager as song_manager
from controllers.match_service import MatchService
from audio_processing.audio import record_audio
from audio_pipeline import AudioFingerprintPipeline

app = typer.Typer()

conn = connect()
init_db(conn)

match_service = MatchService(conn)
audio_pipeline = AudioFingerprintPipeline()

@app.command()
def list():
    rich.print(f"[blue]Listing songs in DB:[/blue]")
    table = rich.table.Table("ID", "Name", "Fingerprints", title="Songs in Database")
    table.style = "magenta"
    table.row_styles = ["none", "dim"]
    for song in song_manager.list_songs(conn):
        table.add_row(str(song[0]), song[1], str(song[2]))
    rich.print(table)

@app.command()
def add(path: str):
    rich.print(f"[green]Adding song from {path}[/green]")
    path = Path(path)
    if not path.exists():
        rich.print(f"[red]Error: File '{path}' does not exist.[/red]")
        return
    file_list = []
    if path.is_dir():
        file_list = path.glob("*.wav")
    else:
        file_list = [path]
    for file in file_list:
        code, msg = song_manager.add_song(conn, file.as_posix())
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
    threading.Thread(target=match_service.run).start()
    n_queries = 0
    while not match_service.match_found.is_set():
        y, sr = record_audio(seconds)
        fps_mic = audio_pipeline.run(y)
        match_service.submit_fingerprints(fps_mic)
        n_queries += 1
        print(f"Submitted fingerprints batch #{n_queries} at time: {time.strftime('%H:%M:%S')}")
        time.sleep(1)
    rich.print(f"[blue]{match_service.match_result[0]}[/blue]: {match_service.match_result[1]}")

if __name__ == "__main__":
    app()
