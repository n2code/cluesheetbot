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


	def execute(self, query):
		return self.cursor.execute(query)


	def destroy(self):
		self.dbconn.close()
		#os.remove(self.dbname)


class Memory:
	forecasting = False
	brain_file = 'cluesheetbot.py.db'
	oracle_file = 'cluesheetbot.py.oracle.db'

	def __init__(self):
		self.real_brain = DB(self.brain_file)
		self.oracle_brain = DB(self.oracle_file) #Heh. As if I'd use Oracle.


	def execute(self, query):
		if not self.forecasting:
			self.real_brain.execute(query)
		return self.oracle_brain.execute(query)


	def start_forecast(self):
		forecasting = True


	def forget_future(self):
		self.oracle_brain.destroy()
		self.oracle_brain = DB(oracle_file, brain_file) #Clone from backup.
		forecasting = False


	def game_setup(self):
		#The three card types
		self.execute("""
		CREATE TABLE cardtypes(
			type TEXT PRIMARY KEY
		)
		""")
		self.execute("INSERT INTO cardtypes VALUES ('suspect'),('weapon'),('room')")

		#All the playing cards
		self.execute("""
		CREATE TABLE cards (
			id INTEGER PRIMARY KEY,
			type TEXT NOT NULL,
			name TEXT NOT NULL UNIQUE,
			FOREIGN KEY(type) REFERENCES cardtypes(type)
		);
		""")

		#Well... players and their figure
		self.execute("""
		CREATE TABLE players (
			id INTEGER PRIMARY KEY,
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
			likely INTEGER DEFAULT 0,
			FOREIGN KEY(perspective) REFERENCES players(id),
			FOREIGN KEY(player) REFERENCES players(id),
			FOREIGN KEY(card) REFERENCES cards(id)
		)
		""")

		#A clue is an unresolved "player X holds one of these" from someone's perspective
		self.execute("""
		CREATE TABLE clues (
			id INTEGER PRIMARY KEY,
			perspective INTEGER NOT NULL,
			player INTEGER NOT NULL,
			card INTEGER NOT NULL,
			FOREIGN KEY(perspective) REFERENCES players(id),
			FOREIGN KEY(player) REFERENCES players(id),
			FOREIGN KEY(card) REFERENCES cards(id)
		)
		""")

memory = Memory()
memory.game_setup()
