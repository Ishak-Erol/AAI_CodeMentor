from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import json

app = FastAPI()

# Definiere den korrekten Pfad zum Verzeichnis
STATIC_DIR = os.path.join(os.path.dirname(__file__), "src/codementor/static")
# 1. Statische Dateien einbinden
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 2. Die Hauptseite aufrufen
@app.get("/")
async def read_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/api/results")
async def get_results():
    try:
        # Hier liest er die Datei, die dein main.py erzeugt hat
        with open("last_run.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        # Das ist die Antwort, wenn das Skript noch nie lief
        return {"error": "No results yet. Run main.py first!"}