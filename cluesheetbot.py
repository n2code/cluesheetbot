# ClueSheetBot is a clue[do] sheet at first sight but records EVERYTHING and thereby does fancy advanced logic stuff
import sqlite3, os, shutil

class DB:
    def __init__(self, dbname, clone_from=None):
        self.dbname = dbname

        try:
            os.remove(self.dbname)
        except OSError:
            pass
        if clone_from:
            shutil.copy2(clone_from, self.dbname)

        self.dbconn = sqlite3.connect(self.dbname, isolation_level=None)
        self.cursor = self.dbconn.cursor()

    def execute(self, query, vals):
        return self.cursor.execute(query, vals)

    def fetchall(self):
        return self.cursor.fetchall()

    def destroy(self):
        self.dbconn.close()
        #os.remove(self.dbname)
        return


class Memory:
    forecasting = False
    safety_file = 'cluesheetbot.py.backup.db'
    real_file = 'cluesheetbot.py.dangerzone.db'
    perspective = None

    def __init__(self):
        self.backup_brain = DB(self.safety_file)
        self.real_brain = DB(self.real_file)
        return

    def execute(self, query, vals=()):
        if not self.forecasting:
            self.backup_brain.execute(query, vals)
        return self.real_brain.execute(query, vals)

    def fetchall(self):
        return self.real_brain.fetchall()

    def start_forecast(self):
        forecasting = True
        return

    def forget_future(self):
        self.real_brain.destroy()
        self.real_brain = DB(real_file, safety_file) #Clone from backup.
        forecasting = False
        return

    def db_create_tables(self):
        #The three card types
        self.execute("""
        CREATE TABLE cardtypes(
            type TEXT PRIMARY KEY
        )
        """)

        #All the playing cards
        self.execute("""
        CREATE TABLE cards (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL UNIQUE,
            FOREIGN KEY(type) REFERENCES cardtypes(type)
        )
        """)

        #Well... players and their figure
        self.execute("""
        CREATE TABLE players (
            id INTEGER PRIMARY KEY,
            porder INTEGER NOT NULL,
            suspectcard INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY(suspectcard) REFERENCES cards(id)
        )
        """)

        #Hard facts or cluelessness: Who holds which card (or does not hold or unable to tell yet) from each player's perspective
        self.execute("""
        CREATE TABLE facts (
            perspective INTEGER NOT NULL,
            player INTEGER NOT NULL,
            card INTEGER NOT NULL,
            has INTEGER DEFAULT NULL,
            certainty INTEGER DEFAULT NULL,
            likely INTEGER DEFAULT 0,
            FOREIGN KEY(perspective) REFERENCES players(id),
            FOREIGN KEY(player) REFERENCES players(id),
            FOREIGN KEY(card) REFERENCES cards(id)
        )
        """)

        #A clue is an unresolved "player X holds one of these" from someone's perspective
        self.execute("""
        CREATE TABLE clues (
            turn INTEGER PRIMARY KEY,
            perspective INTEGER NOT NULL,
            player INTEGER NOT NULL,
            card INTEGER NOT NULL,
            FOREIGN KEY(perspective) REFERENCES players(id),
            FOREIGN KEY(player) REFERENCES players(id),
            FOREIGN KEY(card) REFERENCES cards(id)
        )
        """)

        self.execute('pragma foreign_keys=ON')
        return

    def init_cardtypes(self):
        self.execute("INSERT INTO cardtypes VALUES ('suspect'),('weapon'),('room')")
        return

    def add_card(self, name, cardtype):
        self.execute("INSERT INTO cards (type, name) VALUES (?, ?)", (cardtype, name))
        return

    def add_player(self, name, suspectcard):
        self.execute("INSERT INTO players (porder, suspectcard, name) VALUES ((SELECT COUNT(*) FROM players) + 1, ?, ?)", (suspectcard, name))
        return

    def init_facts(self):
        self.execute("INSERT INTO facts (perspective, player, card) SELECT p1.id, p2.id, c.id FROM players p1 JOIN players p2 JOIN cards c")
        return

    def db_setup(self):
        self.db_create_tables()
        self.init_cardtypes()
        return

    def game_setup(self):
        self.init_facts()
        return


class Display:
    csi = "\033["

    def __init__(self):
        #self.clear_screen()
        return

    def print_at(self, row, col, text):
        print(self.csi + str(row) + ";" + str(col) + "H" + text, end='')
        return

    def clear_screen(self):
        print(self.csi + "2J")
        return

    def print_board(self, memory):
        memory.execute("SELECT c.name FROM cards c ORDER BY c.type = 'suspect', c.type = 'weapon', c.type = 'room', c.name ASC")
        cards = [{'name':x[0]} for x in memory.fetchall()]
        row = 2
        for card in cards:
            col = 1
            self.print_at(row, col, card['name'])
            row += 1
        return


memory = Memory()
memory.db_setup()

suspects = ["Miss Red", "Prof. Purple", "Mrs. Blue", "Rev. Green", "Col. Yellow", "Mrs. White"]
weapons = ["Candlestick", "Dagger", "Lead pipe", "Revolver", "Rope", "Wrench"]
rooms = ["Kitchen", "Ballroom", "Conservatory", "Billiard Room", "Library", "Study", "Hall", "Lounge", "Dining Room"]

#Could be way nicer but meh...
for suspect in suspects:
    memory.add_card(suspect, "suspect")
for weapon in weapons:
    memory.add_card(weapon, "weapon")
for room in rooms:
    memory.add_card(room, "room")

memory.add_player("Niko", 1)
memory.add_player("Tiki", 2)
memory.add_player("Tobi", 3)

memory.game_setup()

display = Display()
display.clear_screen()

#display.print_at(10, 1, "Hallo Welt!")
#display.print_at(11, 2, "Hallo Welt!")
#display.print_at(12, 3, "Hallo Welt!")

display.print_board(memory)

#display.clear_screen()
