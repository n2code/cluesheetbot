# ClueSheetBot is a clue[do] sheet at first sight but records EVERYTHING and thereby does fancy advanced logic stuff
import sqlite3, os, shutil, string, re
import sys, tty, termios

class DB(object):
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

    def get_rowcount(self):
        return self.cursor.rowcount

    def destroy(self):
        self.dbconn.close()
        #os.remove(self.dbname)
        return

class Player(object):
    def __init__(self, memory, playerid=None, playername=None):
        select = "SELECT id, porder, suspectcard, name FROM players "
        if playerid:
            memory.execute(select + "WHERE id = ?", (playerid,))
        elif playername:
            memory.execute(select + "WHERE name = ?", (playername,))
        else:
            raise ValueError("Player instantiation without identifier")
        rows = memory.fetchall()
        if len(rows) != 1:
            raise RuntimeError("Player lookup failed")
        self.id = rows[0][0]
        self.order = rows[0][1]
        self.suspectcard = Card(memory, rows[0][2])
        self.name = rows[0][3]

class Card(object):
    def __init__(self, memory, cardid=None, cardname=None):
        select = "SELECT id, type, name FROM cards "
        if cardid:
            memory.execute(select + "WHERE id = ?", (cardid,))
        elif cardname:
            memory.execute(select + "WHERE name = ?", (cardname,))
        else:
            raise ValueError("Card instantiation without identifier")
        rows = memory.fetchall()
        if len(rows) != 1:
            raise RuntimeError("Card lookup failed")
        self.id = rows[0][0]
        self.type = rows[0][1]
        self.name = rows[0][2]

class Memory(object):
    forecasting = False
    safety_file = 'cluesheetbot.py.backup.db'
    real_file = 'cluesheetbot.py.dangerzone.db'
    perspective = None
    rowcount = 0

    def __init__(self):
        self.backup_brain = DB(self.safety_file)
        self.real_brain = DB(self.real_file)
        return

    def execute(self, query, vals=()):
        if not self.forecasting:
            self.backup_brain.execute(query, vals)
        result = self.real_brain.execute(query, vals)
        self.rowcount = self.real_brain.get_rowcount()
        return result

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

    def new_card(self, name, cardtype):
        self.execute("INSERT INTO cards (type, name) VALUES (?, ?)", (cardtype, name,))
        return Card(self, cardname=name)

    def new_player(self, name, suspectcard):
        self.execute("INSERT INTO players (porder, suspectcard, name) VALUES ((SELECT COUNT(*) FROM players) + 1, ?, ?)", (suspectcard.id, name,))
        return Player(self, playername=name)

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

    def set_perspective(self, playerid):
        self.perspective = playerid
        return playerid

    def add_fact(self, player, card, has, certainty=None):
        if not self.perspective:
            raise LookupError("No perspective set!")
        self.execute("""UPDATE facts SET has = ?, certainty = ?
                        WHERE perspective = ? AND player = ? AND card = ?""",
                (has, certainty, self.perspective, player.id, card.id))


class Display:
    csi = "\033["
    prompt_row = 3
    prompt_col = 30
    prompt_width = 40
    question = ""
    userinput = ""
    alert = ""
    max_userinput = 20
    possible = None
    matches = None
    logs = {'engine':[], 'game':[]}
    log_row = 7
    log_col = 30
    log_height = 16
    log_width = 40
    log_scrollup = 0
    log_max_scrollup = 0

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
        memory.execute("""
                SELECT c.name, fjoined.player, fjoined.has, fjoined.certainty
                FROM cards c JOIN
                    (SELECT player, card, has, certainty FROM facts WHERE perspective = ?) fjoined
                    ON c.id = fjoined.card
                ORDER BY c.type = 'suspect' DESC, c.type = 'weapon' DESC, c.type = 'room' DESC, c.name ASC
                """, (memory.perspective,))
        rows = memory.fetchall()
        card_names = [] #keep names separately to recall order
        cards = {}
        #first aggregate: grouping by card and splitting into players
        for row in rows:
            name = row[0]
            playerid = row[1]
            if name not in card_names:
                card_names += [name]
                cards[name] = {'players':{}}
            cards[name]['players'][playerid] = {'has':row[2], 'certainty':row[3]}
        #collection done, now print it
        row = 2
        for card_name in card_names:
            col = 1
            self.print_at(row, col, card_name)
            has_map = {None:'.', 1:'O', 0:'X'}
            self.print_at(row, col + 20 + 0, has_map[cards[card_name]['players'][1]['has']])
            self.print_at(row, col + 20 + 2, has_map[cards[card_name]['players'][2]['has']])
            self.print_at(row, col + 20 + 4, has_map[cards[card_name]['players'][3]['has']])
            row += 1
        return

    def update_prompt(self):
        prefix = ">>> " 
        self.print_at(self.prompt_row+0, self.prompt_col, self.question.ljust(self.prompt_width))
        inputline = prefix + self.userinput
        self.print_at(self.prompt_row+1, self.prompt_col, inputline+"_".ljust(self.prompt_width))

        if self.alert:
            reactionline = (len(prefix)*' ' + self.alert)
            self.alert = ""
        elif self.possible is None:
            reactionline = ""
        elif len(self.matches) == 1:
            reactionline = len(prefix)*' ' + "Choose " + self.matches[0].upper() + "? (Enter)"
        else:
            suggestions = '/'.join(self.matches)
            if (len("["+suggestions+"]") > self.prompt_width):
                suggestions = suggestions[:(self.prompt_width - len("[...]"))] + "..."
            reactionline = "["+suggestions+"]"

        self.print_at(self.prompt_row+2, self.prompt_col, reactionline.ljust(self.prompt_width))

        self.print_at(self.prompt_row+1, self.prompt_col + len(inputline), "")
        sys.stdout.flush()
        return

    def getch(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if ord(ch) == 17: #Quit with Ctrl+Q
            sys.exit()
        return ch

    def ask_for_input(self, question, possible=None): #if possible given: allowed answers
        self.userinput = ""
        self.question = question
        self.possible = possible
        tabcount = -1

        while True:
            #Everything is possible if nothing has been etered
            if not self.userinput:
                self.matches = self.possible

            #Show prompt/alerts/...
            self.update_kpis()
            self.update_log()
            self.update_prompt()
            sys.stdout.flush()

            #Get input
            keycode = self.getch()
            if keycode == '\033':
                self.getch() #skip [
                arrow = {'A':"up",'B':"down",'C':"right",'D':"left"}[self.getch()]
                if arrow == "up":
                    self.log_scrollup = min(self.log_scrollup+1, self.log_max_scrollup)
                elif arrow == "down":
                    self.log_scrollup = max(self.log_scrollup-1, 0)
                char = 0
            else:
                char = ord(keycode)

            #Tab cycling, special treatment and skipping regular processing if active
            if char == 9:
                if self.possible:
                    tabcount += 1
                    self.userinput = self.possible[tabcount % len(self.possible)]
                    self.matches = self.possible
                else:
                    self.alert = "This is a freestyle prompt!"
                continue
            else:
                tabcount = -1

            #React to input
            if char == 0:
                pass #special treatment done already
            elif char == 21 or char == 23: #Ctrl+U and Ctrl+W clears line almost like in bash
                self.userinput = ""
            elif char == 127: #Delete... deletes one character
                self.userinput = self.userinput[:-1]
            elif char == 13:
                self.userinput = self.userinput.strip()
                if not self.userinput:
                    self.alert = "Give me something!"
                elif self.possible is None:
                    return self.userinput
                else:
                    num_matches = len(self.matches)
                    if num_matches == 1:
                        #select typed matching entry
                        return self.matches[0]
                    elif (num_matches > 1 and self.userinput in self.matches):
                        #tab cycled
                        return self.userinput
                    else:
                        self.alert = "Ambiguous input!"
            else:
                if len(self.userinput) >= self.max_userinput:
                    self.alert = "Maximum input length!"
                    continue
                elif chr(char) not in string.ascii_letters + string.digits + ' ':
                    self.alert = "Invalid character!"
                    continue
                else:
                    self.userinput += chr(char)

            #Process input
            if self.possible:
                self.matches = []
                for word in self.possible:
                    if re.match(".*" + ".*".join(self.userinput) + ".*", word, re.IGNORECASE):
                        self.matches += [word]
                if not self.matches:
                    self.alert = "No matches!"
        return

    def update_log(self):
        #what do we have?
        all_content = self.logs['engine'] + [""]
        free_height = self.log_height - 2

        #if it's too short, stretch it to fill at least one display
        if len(all_content) < free_height:
            all_content += [""]*(free_height-len(all_content))

        #how far can we scroll up?
        max_scrollup = -min(-len(all_content) + free_height, 0)
        effective_scrollup = min(self.log_scrollup, max_scrollup)
        self.log_max_scrollup = max_scrollup

        #calculate window to display
        display_content = all_content[(-free_height - effective_scrollup):(-effective_scrollup if effective_scrollup else None)]

        base = self.log_row
        #print tabs...
        self.print_at(base+0, self.log_col, (" /-----\\").ljust(self.log_width, ' '))
        self.print_at(base+1, self.log_col, ("/  GAME \\ ENGINE \\").ljust(self.log_width-1, '-')+"\\")
        #...and box with scroll arrows
        row = 1
        end = len(display_content)
        for line in display_content:
            border = '|'
            if row in [1, 2] and max_scrollup > effective_scrollup:
                border = '^'
            elif row in [end-1, end] and effective_scrollup:
                border = 'v'
            self.print_at((base+1)+row, self.log_col, "|"+line.ljust(self.log_width-2)+border)
            row += 1
        self.print_at((base+1)+row, self.log_col, "\\"+'-'*(self.log_width-2)+"/")

        return

    def prepare_log_lines(self, text, breakindent=2):
        lines = []
        if '\n' in text:
            for line in text.split('\n'):
                lines += add_line(line)
            return lines
        else:
            part = ""
            while text:
                upto = self.log_width -2 -len(part)
                lastspace = text[:upto].rfind(' ') + 1
                upto = lastspace if lastspace > 0 and len(text) > upto else upto
                part += text[:upto]
                text = text[upto:].strip()
                lines += [part]
                part = breakindent*' '
            return lines

    def add_engine_line(self, text):
        lines = self.prepare_log_lines(text)
        self.logs['engine'] += lines
        if self.log_scrollup:
            self.log_scrollup += len(lines)
        return

    def update_kpis(self):
        self.print_at(self.prompt_row-2, self.prompt_col, ".::*** ClueSheetBot 2000 ***::.")
        return

memory = Memory()
memory.db_setup()

cards = {
        "names": {
            "suspects": ["Miss Red", "Prof. Purple", "Mrs. Blue", "Rev. Green", "Col. Yellow", "Mrs. White"],
            "weapons": ["Candlestick", "Dagger", "Lead pipe", "Revolver", "Rope", "Wrench"],
            "rooms": ["Kitchen", "Ballroom", "Conservatory", "Billiard Room", "Library", "Study", "Hall", "Lounge", "Dining Room"]
            },
        "suspects": [],
        "weapons": [],
        "rooms": []
        }

for cardtype in cards["names"]:
    for cardname in cards["names"][cardtype]:
        cards[cardtype] += [memory.new_card(cardname, cardtype.rstrip('s'))]

players = [
    memory.new_player("Niko", Card(memory, cardid=1)),
    memory.new_player("Tiki", Card(memory, cardid=2)),
    memory.new_player("Tobi", Card(memory, cardid=3)),
]

memory.game_setup()

display = Display()
display.clear_screen()

memory.perspective = 1
display.print_board(memory)

display.add_engine_line(players[1].name+" is playing "+players[1].suspectcard.name)
display.add_engine_line("Hello "+Player(memory, playerid=3).name)

#display.ask_for_input("Select the room of your accusation:", rooms)
#display.ask_for_input("Enter random bullshit:")
while True:
    answer = display.ask_for_input("Select anything:",
            cards["names"]["suspects"]+cards["names"]["weapons"]+cards["names"]["rooms"])
    display.add_engine_line("Your selection was "+answer+".")

input("### TERMINATED (Enter to quit)")
display.clear_screen()
