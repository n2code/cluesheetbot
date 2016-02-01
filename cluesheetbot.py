# ClueSheetBot is a clue[do] sheet at first sight but records EVERYTHING and thereby does fancy advanced logic stuff
import sqlite3, os

# Setup empty DB
dbname = 'cluesheetbot.py.db'
try:
    os.remove(dbname)
except OSError:
    pass

db = sqlite3.connect(dbname, isolation_level=None)
cur = db.cursor()


# Basic DB structure
cur.execute("""
CREATE TABLE cardtypes(
    type TEXT PRIMARY KEY
)
""")
cur.execute("INSERT INTO cardtypes VALUES ('suspect'),('weapon'),('room')")

cur.execute("""
CREATE TABLE cards (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    FOREIGN KEY(type) REFERENCES cardtypes(type)
);

""")
cur.execute("""
CREATE TABLE players (
    id integer PRIMARY KEY,
    suspectcard integer NOT NULL,
    name text NOT NULL,
    FOREIGN KEY(suspectcard) REFERENCES cards(id)
)
""")

cur.execute("""
CREATE TABLE mind (
    perspective INTEGER NOT NULL,
    player INTEGER NOT NULL,
    card INTEGER NOT NULL,
    has INTEGER DEFAULT NULL,
    likely INTEGER DEFAULT 0,
    FOREIGN KEY(perspective) REFERENCES players(id),
    FOREIGN KEY(player) REFERENCES players(id),
    FOREIGN KEY(card) REFERENCES cards(id)
)
""")
