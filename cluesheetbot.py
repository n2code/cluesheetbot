# ClueSheetBot is a clue[do] sheet at first sight but records EVERYTHING and thereby does fancy advanced logic stuff
import sqlite3, os, shutil, string, re, datetime, traceback
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

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
            and self.id == other.id)

    def __ne__(self, other):
        return not self.__eq__(other)


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
    perspective_default = None
    user = None
    rowcount = 0

    def __init__(self, restore_file=None):
        if restore_file:
            raise NotImplementedError("restore not coded yet")
        else:
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
            perspective INTEGER NOT NULL,
            number INTEGER NOT NULL,
            player INTEGER NOT NULL,
            lead INTEGER NOT NULL,
            FOREIGN KEY(perspective) REFERENCES players(id),
            FOREIGN KEY(player) REFERENCES players(id),
            FOREIGN KEY(lead) REFERENCES cards(id)
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
        self.execute("""INSERT INTO facts (perspective, player, card)
                            SELECT p1.id, p2.id, c.id
                            FROM players p1
                                JOIN players p2
                                JOIN cards c""")
        return

    def db_setup(self):
        self.db_create_tables()
        self.init_cardtypes()
        return

    def get_players(self):
        self.execute("SELECT id FROM players ORDER BY porder ASC")
        rows = self.fetchall()
        players = [Player(self, playerid=row[0]) for row in rows]
        return players

    def get_cards(self):
        self.execute("SELECT id FROM cards")
        rows = self.fetchall()
        cards = [Card(self, cardid=row[0]) for row in rows]
        return cards

    def add_fact(self, player, card, has, certainty=None, perspective=None):
        if not perspective:
            perspective = self.perspective
        if not perspective:
            raise LookupError("No perspective set!")
        self.execute("""UPDATE facts SET has = ?, certainty = ?
                        WHERE perspective = ? AND player = ? AND card = ?""",
                (has, certainty, perspective.id, player.id, card.id))

    def add_clue(self, player, leads):
        if len(leads) != 3:
            raise AssertionError("Clue should contain three cards")
        self.execute("""INSERT INTO clues (perspective, number, player, lead)
                            WITH number (last) AS (SELECT IFNULL(MAX(number),0) FROM clues)
                            SELECT p.id, (number.last+1), ?, leads.id
                                FROM players p
                                    JOIN number
                                    JOIN (SELECT ? id UNION SELECT ? id UNION SELECT ? id) leads
                     """, (player.id,)+tuple(c.id for c in leads))

    def next_player(self, current):
        players = self.get_players()
        return players[(players.index(current)+1)%len(players)]


class Display:
    csi = "\033["
    prompt_row = 20
    prompt_col = 34
    prompt_width = 40
    question = ""
    userinput = ""
    alert = ""
    max_userinput = 20
    possible = None
    matches = None
    logs = {'engine':[], 'game':[]}
    log_row = 3
    log_col = 34
    log_height = 15
    log_width = 40
    log_scrollup = 0
    log_max_scrollup = 0
    title_row = 2
    title_col = 43
    sheet_row = 2
    sheet_col = 2
    simbuffer = ""
    recording = True
    recordbuffer = ""

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
                """, (memory.perspective.id,))
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
        row = self.sheet_row
        players = memory.get_players()
        players.sort(key = lambda p: p.order)
        for card_name in card_names:
            col = self.sheet_col
            self.print_at(row, col, card_name)
            has_map = {None:'.', 1:'O', 0:'X'}
            col_offset = 0
            for player in players:
                self.print_at(row, col + 20 + col_offset, has_map[cards[card_name]['players'][player.id]['has']])
                col_offset += 2
            row += 1
        return

    def update_prompt(self):
        prefix = ">>> " 
        self.print_at(self.prompt_row+0, self.prompt_col, self.question.ljust(self.prompt_width))
        inputline = prefix + self.userinput
        self.print_at(self.prompt_row+1, self.prompt_col, (inputline+"_").ljust(self.prompt_width))

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

    def load_recording(self, filename, inform_user=True):
        with open(filename, "r", newline='') as save:
            self.simbuffer = save.read()
        if inform_user:
            display.log("Loading game from "+filename)

    def save_recording(self, filename, inform_user=True):
        with open(filename, "w", newline='') as save:
            save.write(self.recordbuffer)
        if inform_user:
            display.log("Saved game as "+filename)

    def getch(self):
        if self.simbuffer:
            ch, self.simbuffer = self.simbuffer[0], self.simbuffer[1:]
            if not self.simbuffer:
                display.log("Game successfully loaded!")
                termios.tcflush(sys.stdin, termios.TCIOFLUSH)
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        #self.log("Getch received: "+str(ord(ch)))

        if ord(ch) == 19: #Manual save with Ctrl+S
            filename = "CSBot_"+datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")+".sav"
            self.save_recording(filename, inform_user=True)
        elif self.recording: #in else to not record manual saves
            self.recordbuffer += ch

        if ord(ch) == 17: #Quit with Ctrl+Q
            raise SystemExit("fast quit")
        if ord(ch) == 3: #Quit command with Ctrl+C
            raise KeyboardInterrupt("panic abort")
        return ch

    def ask(self, question, possible=None): #if possible given: allowed answers
        self.userinput = ""
        self.question = question
        self.possible = possible
        tabcount = -1

        while True:
            #Everything is possible if nothing has been entered
            if not self.userinput:
                self.matches = self.possible
                if self.matches and len(self.matches) == 1:
                    (self.userinput,) = self.matches

            #Show prompt/alerts/...
            self.update_kpis()
            self.update_log()
            self.update_prompt()
            sys.stdout.flush()

            #Get input
            keycode = self.getch()
            if keycode == '\033':
                self.getch() #skip [
                keycode = self.getch()
                arrows = {'A':"up",'B':"down",'C':"right",'D':"left"}
                if keycode in arrows:
                    arrow = arrows[keycode]
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
            if char in [0, 19]:
                pass #special treatment done already
            elif char == 21 or char == 23: #Ctrl+U and Ctrl+W clears line almost like in bash
                self.userinput = ""
            elif char == 127: #Delete... deletes one character
                self.userinput = self.userinput[:-1]
            elif char == 63: #? prints all commands
                if self.possible:
                    self.log("Commands currently available:")
                    self.log("\n".join(["   "+x for x in self.possible]))
                else:
                    self.alert = "This is a freestyle prompt!"
                    continue
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
        self.print_at(base+0, self.log_col, (" /------\\").ljust(self.log_width, ' '))
        self.print_at(base+1, self.log_col, ("/  GAME  \\ ENGINE \\").ljust(self.log_width-1, '-')+"\\")
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
                lines += self.prepare_log_lines(line, breakindent)
            return lines
        elif text == "":
            return [""]
        elif re.match("^#FILL\(.\)$", text): #e.g. "#FILL(~)" produces a line full of "~"
            return [(self.log_width-2)*text[6]]
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

    def log(self, text):
        lines = self.prepare_log_lines(text)
        self.logs['engine'] += lines
        if self.log_scrollup:
            self.log_scrollup += len(lines)
        return

    def clearlog(self, text):
        self.logs['engine'] = []
        return

    def update_kpis(self):
        self.print_at(self.title_row, self.title_col, ".::*** ClueSheetBot 2000 ***::.")
        return

    def pick_player(self, memory, question):
        return Player(memory, playername=display.ask(question, [p.name for p in memory.get_players()]))

    def pick_card(self, memory, question, cardtype=None):
        cards = memory.get_cards()
        if cardtype: #narrow down if type given
            cards = [c for c in cards if c.type == cardtype.rstrip('s')]
        return Card(memory, cardname=display.ask(question, [c.name for c in cards]))

    def refresh(self, memory):
        self.update_kpis()
        self.update_log()
        self.update_prompt()
        self.print_board(memory)

### GAME FLOW ###

#Initialization
cards = {
        "names": {
            "suspects": ["Miss Red", "Prof. Purple", "Mrs. Blue", "Rev. Green", "Col. Yellow", "Mrs. White"],
            "weapons": ["Candlestick", "Dagger", "Lead pipe", "Revolver", "Rope", "Wrench"],
            "rooms": ["Kitchen", "Ballroom", "Conservatory", "Billiard Room", "Library", "Study", "Hall", "Lounge", "Dining Room"]
            }
        }


def programloop():
    action = display.ask("", ["new game", "exit"])

    if action == "exit":
        return True

#    elif action == "load backup":
#        memory = Memory(restore_file=Memory.safety_file)

    elif action == "new game":
        memory = Memory()
        memory.db_setup()

        for cardtype in cards["names"]:
            for cardname in cards["names"][cardtype]:
                memory.new_card(cardname, cardtype.rstrip('s'))

        display.log("#FILL(~)\nLet's prepare the game!\nAdd all players starting with you and proceeding clockwise. Commence the game when ready.")

        adding = True
        while adding:
            action = display.ask("", ["add player", "start game", "abort"])

            if action == "abort":
                display.log("Aborting game creation.")
                return

            elif action == "start game":
                if len(memory.get_players()) < 2:
                    display.alert = "Two players or more needed!"
                else:
                    adding = False
                    display.log("The game is on!")

            elif action == "add player":
                name_pick = display.ask("Player name:")
                players = memory.get_players()
                playernames_lower = [p.name.lower() for p in players]
                forbidden = ["all"]
                while name_pick.lower() in playernames_lower + ["all"]:
                    name_pick = display.ask("Please chose a different name:")

                picked_suspects = [p.suspectcard.name for p in players]
                suspectnames = [c.name for c in memory.get_cards() if c.type == "suspect" and c.name not in picked_suspects]
                if not suspectnames:
                    display.alert = "Already at player maximum!"
                    continue
                suspect_pick = display.ask(name_pick+"'s pawn:", suspectnames)
                suspectcard = Card(memory, cardname=suspect_pick)

                memory.new_player(name_pick, suspectcard)
                display.log("Player "+str(len(players)+1)+": "+name_pick+" as "+suspect_pick)


        memory.init_facts()
        memory.user = players[0]
        memory.perspective_default = players[0]
        memory.perspective = players[0]

        while True:
            try:
                if gameloop(memory):
                    return True
            except KeyboardInterrupt as e:
                display.log("Panic abort from current command.")

def gameloop(memory):
    display.print_board(memory)
    action = display.ask("", ["turn", "manual fact", "refresh", "quit"])
    display.save_recording("autosave.sav", inform_user=False)
    
    def ask_perspectives():
        playernames = [p.name for p in memory.get_players()]
        perspective_input = display.ask("Recorded from whose perspective?", playernames+["all"])
        if perspective_input == "all":
            chosen = playernames
        else:
            chosen = [perspective_input]
        return [Player(memory, playername=x) for x in chosen]


    if action == "quit":
        if display.ask("Really quit the running game?", ["yes", "no", "cancel"]) == "yes":
            display.log("You quit the game prematurely.")
            return True

    elif action == "refresh":
        display.log("Manual screen refresh.")
        display.refresh(memory)

    elif action == "manual fact":
        if display.ask("Override mechanics and manually enter fact?", ["override", "cancel"]) == "override":
            player = display.pick_player(memory, "Fact about which player?")
            card = Card(memory, cardname=display.ask(player.name+"'s relation to which card?", [c.name for c in memory.get_cards()]))
            has_options = {"holding":True, "missing":False, "unknown":None}
            has = has_options[display.ask("What about the card?", list(has_options))]

            for current_perspective in ask_perspectives():
                memory.add_fact(player, card, has, certainty=None, perspective=current_perspective)

            display.log("Fact manually added.")

    elif action == "turn":
        player = display.pick_player(memory, "Whose turn?") #TODO auto detect
        room = display.pick_card(memory, "Suggested room of the murder:", "room")
        suspect = display.pick_card(memory, "Suggested suspect:", "suspect")
        weapon = display.pick_card(memory, "Suggested weapon:", "weapon")
        leads = [room, suspect, weapon]

        display.log(player.name+" is making a suggestion: \""+suspect.name.upper()+" did the deed in the "+room.name.upper()+" with the "+weapon.name.upper()+".\"")

        interviewee = memory.next_player(player)
        while interviewee != player:
            display.log(interviewee.name+" is questioned...")

            if display.ask("Can "+interviewee.name+" show a card?", ["show", "pass"]) == "show":

                #if we are the inspector we gain plain facts...
                if player == memory.user:
                    shown = Card(memory, cardname=display.ask("Which card is shown to you?", [c.name for c in leads]))
                    memory.add_fact(interviewee, shown, has=True, certainty=1, perspective=player)
                    memory.add_fact(interviewee, shown, has=True, certainty=1, perspective=interviewee)
                #...but in any case everyone gets a clue
                memory.add_clue(interviewee, leads)

                display.log(interviewee.name+" shows "+player.name+" "+(shown.name.upper() if player == memory.user else "a card")+".")
                break #turn ends when someone can show
                
            else: #cannot show so everyone gains facts
                for inspector in memory.get_players():
                    for lead in leads:
                        memory.add_fact(interviewee, lead, has=False, certainty=1, perspective=inspector)

                display.log(interviewee.name+" cannot show a card.")

            interviewee = memory.next_player(interviewee)

### REAL EXECUTION

display = Display()
display.clear_screen()
display.log("Welcome to Clue/Cluedo!\n\nType available commands in [brackets] to interact. Hit TAB to cycle through options, type ? to get a full list and use ENTER to accept. Clear the input line with CTRL+U. Use arrow keys to scroll in tabs and switch between tabs. Once the game has started CTRL+C aborts the current command. CTRL+Q exits *immediately*.")

if sys.argv[1:]:
    display.load_recording(sys.argv[1])

while True:
    try:
        if programloop():
            display.clear_screen()
            print("\nBye!")
            break
    except (SystemExit, KeyboardInterrupt) as e:
        display.clear_screen()
        print("Fast quit... bye!")
        sys.exit()
    except Exception as e:
        display.clear_screen()
        traceback.print_exc()
        sys.exit()

