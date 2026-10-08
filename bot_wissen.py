"""Wissensbasis des StreamDex Bots – automatisch erzeugt aus den Apps v5.2.6 und BETA VERSION V3.

Nicht von Hand ändern: neu erzeugen mit build_wissen.py. Eigene Ergänzungen/Korrekturen gehören in das
Support-Panel (Admin → Support → „Eigene Antworten“) – die haben immer Vorrang vor diesen Einträgen.

Felder je Eintrag:
  title    Titel (eindeutig)
  v        "beide" = v5.2.6 + BETA V3, "beta" = nur BETA V3
  kw       Stichwörter (Wortanfang; "$" am Ende = ganzes Wort; "!befehl" = genau dieser Chat-Befehl)
  answer   Antworttext (BETA V3); answer_v526 = abweichender Text für v5.2.6
"""

WISSEN_STAND = "2026-10-07"
VERSIONEN = ("v5.2.6", "BETA VERSION V3")


WISSEN = [{'title': '!giveaway – Giveaway',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!giveaway', 'giveaway mitmachen', 'am giveaway teilnehmen', 'teilnehmen giveaway', 'mitmachen giveaway'],
  'answer': '🎁 !giveaway  (Giveaway)\n'
            'Nimmt am aktuellen regulären Giveaway teil.\n'
            '• Beispiel: !giveaway\n'
            '• Platzhalter für eigene Texte: {user}, {prize}, {command}',
  'cmd': '!giveaway',
  'cat': 'Giveaway'},
 {'title': '!remove – Giveaway',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!remove', 'austragen', 'aus giveaway austragen', 'nicht mehr teilnehmen', 'abmelden giveaway'],
  'answer': '🎁 !remove  (Giveaway)\n'
            'Trägt den Zuschauer aus dem aktuellen Giveaway wieder aus.\n'
            '• Beispiel: !remove\n'
            '• Platzhalter für eigene Texte: {user}, {prize}',
  'cmd': '!remove',
  'cat': 'Giveaway'},
 {'title': '!lurk – Interaktion',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!lurk', 'lurk', 'lurken'],
  'answer': '💬 !lurk  (Interaktion)\n'
            'Aktiviert den Lurk-Status für den Zuschauer mit zufälliger Textausgabe.\n'
            '• Beispiel: !lurk\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!lurk',
  'cat': 'Interaktion'},
 {'title': '!checkin – Interaktion',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!checkin', 'checkin', 'check in', 'streak', 'xp', 'level up'],
  'answer': '💬 !checkin  (Interaktion)\n'
            'Täglicher Check-in mit XP, Level-Up und Streak (Max. 1x pro Stream).\n'
            '• Beispiel: !checkin\n'
            '• Platzhalter für eigene Texte: {user}, {streak}, {level}, {xp}',
  'cmd': '!checkin',
  'cat': 'Interaktion'},
 {'title': '!event – Interaktion',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!event', 'community event', 'halloween', 'doppel coins'],
  'answer': '💬 !event  (Interaktion)\n'
            'Zeigt das aktuell laufende Community-Event (Halloween, Doppel-Coins-Wochenende, o.ä.) inkl. '
            'Restlaufzeit, aktiven Coin-/XP-Boni und einem eventuellen exklusiven Titel. Ist kein Event aktiv, wird '
            'das im Chat mitgeteilt.\n'
            '• Beispiel: !event\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!event',
  'cat': 'Interaktion'},
 {'title': '!clip – Interaktion',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!clip', 'clip$', 'clips', 'twitch clip'],
  'answer': '💬 !clip  (Interaktion)\n'
            'Erstellt einen Twitch-Clip der letzten Sekunden des Streams und postet den Link im Chat und (falls der '
            'Discord-Webhook aktiv ist) auch in Discord. Nur möglich, solange der Stream live ist. Es gilt ein '
            'gemeinsamer Cooldown (Standard: 30 Sekunden).\n'
            '• Beispiel: !clip\n'
            '• Platzhalter für eigene Texte: {user}, {url}',
  'cmd': '!clip',
  'cat': 'Interaktion'},
 {'title': '!so – Interaktion',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!so', 'shoutout', 'shout out'],
  'answer': '💬 !so <username>  (Interaktion)\n'
            'Shoutout für einen anderen Twitch-Kanal: postet eine Chat-Nachricht und blendet im Shoutout-Overlay je '
            'nach Einstellung Logo/Name/Text ODER einen zufälligen Twitch-Clip des Kanals ein. Zusätzlich können '
            "unter 'Auto-!so' Usernamen hinterlegt werden, die automatisch (mit ihrem eigenen, individuell "
            'angepassten Shoutout-Look) einmal pro Stream einen Shoutout bekommen, sobald sie im Chat schreiben.\n'
            '• Parameter: <username> (Twitch-Name des Kanals, ohne @)\n'
            '• Beispiel: !so freeschok01\n'
            '• Platzhalter für eigene Texte: {user}, {game}',
  'cmd': '!so',
  'cat': 'Interaktion'},
 {'title': '!slot – Minigame',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!slot', 'slot$', 'slot machine', 'slotmaschine', '3 walzen'],
  'answer': '🎲 !slot <einsatz>  (Minigame)\n'
            'Dreht die 3-Walzen Slot Machine mit den eigenen Community-Coins als Einsatz. Bei 3 gleichen Symbolen '
            'gibt es den Einsatz multipliziert mit dem Symbol-Multiplikator zurück, beim Jackpot-Symbol zusätzlich '
            'den kompletten Jackpot-Pool.\n'
            '• Parameter: einsatz (Anzahl Coins, optional - Standard: Mindesteinsatz)\n'
            '• Beispiel: !slot 50\n'
            '• Platzhalter für eigene Texte: {user}, {bet}, {payout}, {symbols}, {jackpot}, {coins}',
  'cmd': '!slot',
  'cat': 'Minigame'},
 {'title': '!megaslot – Minigame',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!megaslot', 'megaslot', 'mega slot', '5 walzen', 'gewinnlinien', 'video slot'],
  'answer': '🎲 !megaslot <einsatz> [anzahl_spins] [linien]  (Minigame)\n'
            'Dreht den 5x3-Video-Slot mit wahlweise 5 oder 20 Gewinnlinien (Standard: 20). Der Einsatz ist der '
            'GESAMTEINSATZ pro Spin (wird genau in dieser Höhe abgebucht, nicht mehr x Linien). Intern wird der '
            'Betrag auf die gewählten Linien verteilt. 3, 4 oder 5 gleiche Symbole ab der ersten Walze auf einer '
            'Linie zahlen mit einfachem/doppeltem/vierfachem Multiplikator aus. 5 Jackpot-Symbole auf einer Linie '
            'gewinnen den kompletten Mega-Jackpot-Pool. Optional kann eine Anzahl an Spins angegeben werden (z.B. '
            '10), die dann nacheinander im Overlay abgespielt werden. Pro User gilt ein Cooldown zwischen Befehlen.\n'
            '• Parameter: einsatz (Gesamt-Coins pro Spin, optional - Standard: Mindesteinsatz), anzahl_spins '
            '(optional, Standard: 1), linien (optional: 5 oder 20, Standard laut Mega Slot Studio)\n'
            '• Beispiel: !megaslot 5 10 5\n'
            '• Platzhalter für eigene Texte: {user}, {bet}, {total_bet}, {payout}, {lines}, {jackpot}, {coins}, '
            '{spins}',
  'cmd': '!megaslot',
  'cat': 'Minigame'},
 {'title': '!safe – Minigame',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!safe', 'safe$', 'tresor', 'safe knacker', 'tresor code'],
  'answer': '🎲 !safe <Zahlencode>  (Minigame)\n'
            'Tippt auf den geheimen Tresor-Code. Bei Treffer öffnet sich der Tresor!\n'
            '• Parameter: <Zahlencode> = Ziffernfolge (z.B. 4-stellig)\n'
            '• Beispiel: !safe 4829\n'
            '• Platzhalter für eigene Texte: {user}, {code}, {prize}',
  'cmd': '!safe',
  'cat': 'Minigame'},
 {'title': '!fish – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!fish', 'angeln', 'fischen', 'auswerfen'],
  'answer': '🎣 !fish  (Angeln)\n'
            'Angeln: Wirft die Angel aus und bringt einen zufälligen Fang aus der Loot-Tabelle ein (von Alten '
            'Stiefeln bis zur Schatztruhe). Unterliegt einem Cooldown pro Nutzer.\n'
            '• Beispiel: !fish\n'
            '• Platzhalter für eigene Texte: {user}, {item}, {amount}, {coins}',
  'cmd': '!fish',
  'cat': 'Angeln'},
 {'title': '!pull – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!pull', 'einholen', 'anziehen'],
  'answer': '🎣 !pull  (Angeln)\n'
            'Anziehen (Variante 1): Reaktion auf den Biss innerhalb des Fangzeit-Fensters, um den Fisch einzuholen.\n'
            '• Beispiel: !pull\n'
            '• Platzhalter für eigene Texte: {user}, {item}, {coins}',
  'cmd': '!pull',
  'cat': 'Angeln'},
 {'title': '!reel – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!reel', 'einholen', 'anziehen'],
  'answer': '🎣 !reel  (Angeln)\n'
            'Anziehen (Variante 2): identisch zu !pull, alternativer Befehl für dieselbe Aktion.\n'
            '• Beispiel: !reel\n'
            '• Platzhalter für eigene Texte: {user}, {item}, {coins}',
  'cmd': '!reel',
  'cat': 'Angeln'},
 {'title': '!sell – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!sell', 'fische verkaufen', 'marktpreis'],
  'answer': '🎣 !sell [ID | all]  (Angeln)\n'
            'Verkauft gefangene Fische zum aktuellen, durch Angebot/Nachfrage bestimmten Marktpreis. Ohne Angabe '
            "oder mit 'all'/'alle' werden alle verkaufbaren Fische auf einmal verkauft; im Aquarium platzierte "
            'Fische zählen nicht mit.\n'
            '• Parameter: ID (optional, einzelner Fisch) oder all/alle (Standard: alle)\n'
            '• Beispiel: !sell all\n'
            '• Platzhalter für eigene Texte: {user}, {amount}, {coins}',
  'cmd': '!sell',
  'cat': 'Angeln'},
 {'title': '!aquarium – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!aquarium', 'aquarium'],
  'answer': '🎣 !aquarium  (Angeln)\n'
            'Schickt dem Zuschauer den Link zu seinem persönlichen Web-Aquarium-Dashboard.\n'
            '• Beispiel: !aquarium\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!aquarium',
  'cat': 'Angeln'},
 {'title': '!auftrag – Angeln',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!auftrag', 'auftrag', 'auftraege', 'fisch abkommen', 'grossauftrag', 'hoflieferant'],
  'answer': '🎣 !auftrag [liefern]  (Angeln)\n'
            "Fisch-Abkommen & Großaufträge: Ohne Zusatz zeigt der Befehl den aktuellen Auftrag (z.B. 'Der "
            "Hoflieferant benötigt 5x Forelle') samt Belohnung. Mit 'liefern' gibt man die geforderten, unverkauften "
            'Fische ab - wer als Erstes alles liefert, bekommt Coins, Event-Punkte (und bei Großaufträgen evtl. '
            "einen exklusiven Skin). Mods/Broadcaster können mit 'neu', 'gross' und 'abbrechen' eingreifen.\n"
            '• Parameter: liefern = Fische abgeben (Mods: neu / gross / abbrechen)\n'
            '• Beispiel: !auftrag liefern\n'
            '• Platzhalter für eigene Texte: {user}, {text}, {reward}, {missing}',
  'cmd': '!auftrag',
  'cat': 'Angeln'},
 {'title': '!koeder – Angeln',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!koeder', 'koeder', 'leucht wurm', 'platin blinker', 'radioaktive made'],
  'answer': '🎣 !koeder [typ]  (Angeln)\n'
            'Köder-Shop: Kauft einen Verbrauchs-Köder für den nächsten Wurf (z.B. Leucht-Wurm = mehr Tiefsee-Fische, '
            'Platin-Blinker = doppelte Mutations-Chance, Radioaktive Made = Radioaktiv-Mutation). Ohne Typ wird die '
            'Köder-Liste mit Preisen angezeigt. Der Köder wird beim nächsten !fish automatisch verbraucht.\n'
            '• Parameter: Köder-Typ (optional): leucht / platin / made\n'
            '• Beispiel: !koeder leucht\n'
            '• Platzhalter für eigene Texte: {user}, {bait}, {price}, {coins}',
  'cmd': '!koeder',
  'cat': 'Angeln'},
 {'title': '!haken – Angeln',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!haken', 'haken', 'angelhaken', 'reissgefahr', 'reissen'],
  'answer': '🎣 !haken [kaufen]  (Angeln)\n'
            'Angel v2: zeigt den eigenen Haken oder kauft die nächste Stufe. Bessere Haken senken die Reißgefahr der '
            'Schnur und verlängern die Fangzeit.\n'
            '• Parameter: kaufen (optional)\n'
            '• Beispiel: !haken kaufen\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!haken',
  'cat': 'Angeln'},
 {'title': '!nachlassen – Angeln',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!nachlassen', 'nachlassen', 'schnur nachlassen', 'schwerer fisch'],
  'answer': '🎣 !nachlassen  (Angeln)\n'
            'Angel v2: Bei einem schweren Fisch spannt sich die Schnur. Wer rechtzeitig Schnur nachlässt, senkt die '
            'Reißgefahr deutlich.\n'
            '• Beispiel: !nachlassen\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!nachlassen',
  'cat': 'Angeln'},
 {'title': '!praeparieren – Angeln',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!praeparieren', 'praeparieren', 'praeparier', 'fische ausnehmen', 'ausnehmen'],
  'answer': '🎣 !praeparieren [ID | all]  (Angeln)\n'
            'Angel v2: präpariert (nimmt aus) gefangene Fische gegen eine kleine Gebühr. Präparierte Fische bringen '
            'beim Verkauf einen Wertbonus.\n'
            '• Parameter: ID (optional) oder all/alle (Standard: alle)\n'
            '• Beispiel: !praeparieren alle\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!praeparieren',
  'cat': 'Angeln'},
 {'title': '!rute – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!rute', 'rute$', 'angelrute'],
  'answer': '🎣 !rute  (Angeln)\n'
            'Zeigt die aktuell ausgerüstete Rute, das Angel-Level, die Gesamtfänge und das aktuelle Biom des '
            'Nutzers.\n'
            '• Beispiel: !rute\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!rute',
  'cat': 'Angeln'},
 {'title': '!gewaesser – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!gewaesser', 'gewaesser', 'biom'],
  'answer': '🎣 !gewaesser  (Angeln)\n'
            'Listet alle Gewässer inkl. ID, benötigtem Angel-Level und Reisekosten auf. Die ID wird für !reise <ID> '
            'benötigt.\n'
            '• Beispiel: !gewaesser\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!gewaesser',
  'cat': 'Angeln'},
 {'title': '!ruten – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!ruten', 'ruten$', 'rutenliste'],
  'answer': '🎣 !ruten  (Angeln)\n'
            'Listet alle kaufbaren Ruten inkl. ID und Preis auf. Die ID wird für !buyrute <ID> benötigt.\n'
            '• Beispiel: !ruten\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!ruten',
  'cat': 'Angeln'},
 {'title': '!reise – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!reise', 'reise$', 'gewaesser wechseln'],
  'answer': '🎣 !reise <ID>  (Angeln)\n'
            'Wechselt zum Gewässer mit der angegebenen ID (siehe !gewaesser), sofern das Angel-Level ausreicht. Noch '
            'nicht freigeschaltete Gewässer kosten beim ersten Besuch einmalig die Reisekosten, danach ist das '
            'Reisen dorthin kostenlos.\n'
            '• Parameter: <ID> = Gewässer-ID aus !gewaesser\n'
            '• Beispiel: !reise 2\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!reise',
  'cat': 'Angeln'},
 {'title': '!buyrute – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!buyrute', 'buyrute', 'rute kaufen'],
  'answer': '🎣 !buyrute <ID>  (Angeln)\n'
            'Kauft eine neue Rute (siehe !ruten für die Liste) und rüstet sie automatisch aus, sofern genug Coins '
            'vorhanden sind.\n'
            '• Parameter: <ID> = Ruten-ID aus !ruten\n'
            '• Beispiel: !buyrute 3\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!buyrute',
  'cat': 'Angeln'},
 {'title': '!upgraderute – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!upgraderute', 'upgraderute', 'rute upgraden', 'rute aufruesten', 'rute verbessern'],
  'answer': '🎣 !upgraderute  (Angeln)\n'
            'Rüstet die aktuell ausgerüstete Rute auf die nächste Stufe auf (bis zum jeweiligen Max-Level), sofern '
            'genug Coins vorhanden sind.\n'
            '• Beispiel: !upgraderute\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!upgraderute',
  'cat': 'Angeln'},
 {'title': '!toplevel – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!toplevel', 'toplevel', 'angler bestenliste', 'bestenliste angeln'],
  'answer': '🎣 !toplevel [Anzahl]  (Angeln)\n'
            "Zeigt die Angler-Bestenliste nach Level/Gesamtfängen. Optionales Zahlen-Argument (auch als 'top10' "
            'schreibbar) wählt die Listengröße zwischen 5 und 20, Standard ist die im Angel Game Tab eingestellte '
            'Bestenlisten-Größe.\n'
            '• Parameter: Anzahl (optional, 5-20, Standard: einstellbar)\n'
            '• Beispiel: !toplevel 10\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!toplevel',
  'cat': 'Angeln'},
 {'title': '!topreich – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!topreich', 'topreich', 'reichtum', 'reichste', 'bestenliste coins'],
  'answer': '🎣 !topreich [Anzahl]  (Angeln)\n'
            "Zeigt die Reichtums-Bestenliste nach Coins. Optionales Zahlen-Argument (auch als 'top15' schreibbar) "
            'wählt die Listengröße zwischen 5 und 20, Standard ist die im Angel Game Tab eingestellte '
            'Bestenlisten-Größe.\n'
            '• Parameter: Anzahl (optional, 5-20, Standard: einstellbar)\n'
            '• Beispiel: !topreich 15\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!topreich',
  'cat': 'Angeln'},
 {'title': '!mine – Minigame',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!mine', 'mine$', 'minen', 'mining', 'spitzhacke', 'schuerfen', 'bergbau'],
  'answer': '🎲 !mine  (Minigame)\n'
            'Minen: Schwingt die Spitzhacke und fördert einen zufälligen Fund aus der Loot-Tabelle zu Tage (von '
            'Kieselsteinen bis zur Mythril-Ader). Unterliegt einem Cooldown pro Nutzer.\n'
            '• Beispiel: !mine\n'
            '• Platzhalter für eigene Texte: {user}, {item}, {amount}, {coins}',
  'cmd': '!mine',
  'cat': 'Minigame'},
 {'title': '!raffel – Minigame',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!raffel', 'raffel$', 'raffel um points'],
  'answer': '🎲 !raffel <einsatz>  (Minigame)\n'
            'Raffel um Points: Setzt Coins ein. Es gibt eine kleine, frei einstellbare Chance, den kompletten Pot zu '
            'gewinnen. Wird der Pot verfehlt, wird per ebenfalls einstellbarer Chance entweder der Einsatz '
            'verdoppelt oder komplett verloren - ein Teil eines Verlusts fließt dann in den wachsenden Pot.\n'
            '• Parameter: einsatz (Anzahl Coins, optional - Standard: Mindesteinsatz)\n'
            '• Beispiel: !raffel 50\n'
            '• Platzhalter für eigene Texte: {user}, {bet}, {payout}, {pot}, {coins}',
  'cmd': '!raffel',
  'cat': 'Minigame'},
 {'title': '!klau – Minigame',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!klau', 'klau$', 'taschenraub', 'klauen', 'stehlen', 'diebstahl'],
  'answer': '🎲 !klau <Nutzername>  (Minigame)\n'
            'Taschenraub: Versucht, einem anderen Zuschauer einen zufälligen Prozentsatz seiner Coins zu stehlen. '
            'Bei Erfolg wandern die Coins zum Dieb, bei Misserfolg zahlt der Dieb selbst eine Strafe. Unterliegt '
            'einem Cooldown pro Nutzer.\n'
            '• Parameter: <Nutzername> = Name des Opfers (mit oder ohne @)\n'
            '• Beispiel: !klau Bob\n'
            '• Platzhalter für eigene Texte: {user}, {victim}, {amount}, {penalty}, {coins}',
  'cmd': '!klau',
  'cat': 'Minigame'},
 {'title': '!duell – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!duell', 'duell', 'duelle', 'pvp'],
  'answer': '🚶 !duell <Nutzername>  (Viewer-Arena)\n'
            'Fordert einen anderen aktiven Chatter in der 2D-Viewer-Arena zum PvP-Duell heraus: beide Sprites laufen '
            'aufeinander zu, es folgt ein Schlagabtausch mit HP-Balken, Treffer-Effekten und Waffen-Animation, '
            "danach 'poofed' der Verlierer kurz weg. Der Sieger erhält optional einen kleinen Coin-Bonus. Ist die "
            'Annahmepflicht aktiviert, muss der Herausgeforderte erst mit dem Annahme-Befehl (Standard !akzept) '
            'bestätigen, sonst verfällt die Herausforderung nach Ablauf der Frist. Beide Duellanten müssen aktuell '
            'in der Arena aktiv sein, es gilt ein Cooldown pro Herausforderer sowie optional eine kurze '
            'Unangreifbarkeit für den letzten Verlierer.\n'
            '• Parameter: <Nutzername> = Name des Herausgeforderten (mit oder ohne @)\n'
            '• Beispiel: !duell Bob\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!duell',
  'cat': 'Viewer-Arena'},
 {'title': '!akzept – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!akzept', 'akzept', 'duell annehmen'],
  'answer': '🚶 !akzept  (Viewer-Arena)\n'
            'Nimmt eine offene !duell-Herausforderung an (nur nötig, wenn die Annahmepflicht in den '
            'Arena-Einstellungen aktiviert ist). Erst danach startet die Kampf-Animation. Reagiert der '
            'Herausgeforderte nicht rechtzeitig, verfällt die Herausforderung automatisch.\n'
            '• Beispiel: !akzept\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!akzept',
  'cat': 'Viewer-Arena'},
 {'title': '!hug – Viewer-Arena',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!hug', 'hug$', 'umarmen', 'umarmung'],
  'answer': '🚶 !hug <Nutzername>  (Viewer-Arena)\n'
            'Dein Sprite läuft in der 2D-Viewer-Arena zu einem anderen aktiven Chatter und umarmt ihn. Solange die '
            'Umarmung dauert, schweben Herzen über beiden Figuren. Beide müssen aktuell in der Arena aktiv sein; es '
            'gilt ein Cooldown pro Nutzer.\n'
            '• Parameter: <Nutzername> = Name des Umarmten (mit oder ohne @)\n'
            '• Beispiel: !hug Bob\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!hug',
  'cat': 'Viewer-Arena'},
 {'title': '!fliegen – Viewer-Arena',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!fliegen', 'fliegen$', 'ballon'],
  'answer': '🚶 !fliegen  (Viewer-Arena)\n'
            'Ballon-Flug in der 2D-Viewer-Arena: Dein Sprite schnallt sich einen bunten Luftballon um, schwebt vom '
            'Boden hoch an die Decke des Overlays und läuft dort standardmäßig 5 Minuten im oberen Stockwerk herum. '
            'Danach platzt der Ballon und der Sprite fällt zurück auf den Boden. Solange du oben bist, kannst du '
            'nicht duelliert, umarmt oder für den Liebes-Test gewählt werden. Flugdauer und Cooldown sind in den '
            'Arena-Einstellungen anpassbar.\n'
            '• Beispiel: !fliegen\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!fliegen',
  'cat': 'Viewer-Arena'},
 {'title': '!love – Viewer-Arena',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!love', 'love$', 'liebestest', 'liebes test'],
  'answer': '🚶 !love [Nutzername]  (Viewer-Arena)\n'
            'Liebes-Test in der 2D-Viewer-Arena: Dein Sprite läuft zu einem anderen aktiven Chatter (mit Namen '
            'gewählt, ohne Namen zufällig). Über beiden schweben Herzen, ein Liebes-Balken füllt sich auf einen '
            'zufälligen Prozentwert, und der Bot schreibt eine dazu passende Nachricht in den Chat. Prozent-Bereich, '
            'Balkenfarben, Dauer, Cooldown und alle Chat-Texte sind in den Arena-Einstellungen anpassbar.\n'
            '• Parameter: [Nutzername] = optional, Name des Liebes-Partners (mit oder ohne @). Ohne Angabe wird '
            'zufällig ein anderer aktiver Chatter gewählt.\n'
            '• Beispiel: !love Bob\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!love',
  'cat': 'Viewer-Arena'},
 {'title': '!skin – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!skin', 'skin$', 'kostuem', 'arena skin'],
  'answer': '🚶 !skin <id>  (Viewer-Arena)\n'
            'Rüstet ein Arena-Kostüm (je nach Skin ein komplett neues Aussehen oder ein kleines Badge am Sprite in '
            'der 2D-Viewer-Arena) aus. Ist der Skin noch nicht im Besitz, wird er bei ausreichendem Coin-Guthaben '
            "automatisch gekauft und direkt angelegt. '!skin none' setzt wieder das Standard-Aussehen ohne Kostüm.\n"
            '• Parameter: <id> = Skin-ID aus dem Katalog (siehe !skins), z.B. cat, ghost, ninja, robot, wizard, '
            'crown, alien, pumpkin, none\n'
            '• Beispiel: !skin cat\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!skin',
  'cat': 'Viewer-Arena'},
 {'title': '!skins – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!skins', 'skins$', 'skin katalog'],
  'answer': '🚶 !skins  (Viewer-Arena)\n'
            'Listet den kompletten Arena-Skin-Katalog inkl. Preis und eigenem Besitz-/Ausgerüstet-Status im Chat '
            'auf.\n'
            '• Beispiel: !skins\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!skins',
  'cat': 'Viewer-Arena'},
 {'title': '!saeen – Farmen',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!saeen', 'saeen', 'saen', 'aussaeen'],
  'answer': '🌱 !saeen <saatgut>  (Farmen)\n'
            'Sät ein Saatgut auf dem eigenen Feld aus, sofern das Feld gerade leer ist, das nötige Farm-Level '
            'erreicht wurde und genug Coins für die Saatgut-Kosten vorhanden sind. Nach der Wachstumszeit der '
            'jeweiligen Pflanze kann mit dem Ernten-Befehl geerntet werden. Verfügbares Saatgut siehe '
            '{saatgut_cmd}.\n'
            '• Parameter: <saatgut> = Schlüssel/Name des Saatguts aus der Saatgut-Liste\n'
            '• Beispiel: !saeen kartoffel\n'
            '• Platzhalter für eigene Texte: {user}, {coins}, {saatgut_cmd}',
  'cmd': '!saeen',
  'cat': 'Farmen'},
 {'title': '!ernten – Farmen',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!ernten', 'ernten', 'ernte$'],
  'answer': '🌱 !ernten  (Farmen)\n'
            'Erntet die auf dem eigenen Feld ausgereifte Pflanze, sofern die Wachstumszeit abgelaufen ist. Der '
            'Ertrag wandert ins Farm-Inventar (weder automatisch verkauft noch verloren) und kann später mit dem '
            'Verkaufs-Befehl zu Coins gemacht oder für zukünftige Rezepte/den Shop verwendet werden. Gibt außerdem '
            'Farm-XP und schaltet bei genug XP neues Saatgut frei.\n'
            '• Beispiel: !ernten\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!ernten',
  'cat': 'Farmen'},
 {'title': '!farm – Farmen',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!farm', 'farm$', 'feld'],
  'answer': '🌱 !farm  (Farmen)\n'
            'Zeigt den Status des eigenen Feldes (leer / wächst noch inkl. Restzeit / erntereif), sowie das aktuelle '
            'Farm-Level und die Gesamtzahl an Ernten.\n'
            '• Beispiel: !farm\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!farm',
  'cat': 'Farmen'},
 {'title': '!saatgut – Farmen',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!saatgut', 'saatgut'],
  'answer': '🌱 !saatgut  (Farmen)\n'
            'Listet alle Saatgut-Sorten auf, inkl. benötigtem Farm-Level, Kosten und Wachstumszeit. Noch nicht '
            'freigeschaltetes Saatgut wird als gesperrt markiert.\n'
            '• Beispiel: !saatgut\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!saatgut',
  'cat': 'Farmen'},
 {'title': '!farmverkaufen – Farmen',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!farmverkaufen', 'farmverkaufen', 'ernte verkaufen'],
  'answer': '🌱 !farmverkaufen [all | <ernte> [menge]]  (Farmen)\n'
            "Verkauft geerntete Pflanzen aus dem Farm-Inventar für Coins. Ohne oder mit 'all' wird das komplette "
            'Inventar verkauft, alternativ kann eine bestimmte Ernte (optional mit Menge) angegeben werden.\n'
            "• Parameter: Optional: 'all' oder <ernte> [menge]\n"
            '• Beispiel: !farmverkaufen all\n'
            '• Platzhalter für eigene Texte: {user}, {coins}',
  'cmd': '!farmverkaufen',
  'cat': 'Farmen'},
 {'title': '!topfarm – Farmen',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!topfarm', 'topfarm', 'farmer bestenliste'],
  'answer': '🌱 !topfarm [Anzahl]  (Farmen)\n'
            "Zeigt die Farmer-Bestenliste nach Level/Gesamternten. Optionales Zahlen-Argument (auch als 'top10' "
            'schreibbar) wählt die Listengröße zwischen 5 und 20, Standard ist die im Angel Game Tab eingestellte '
            'Bestenlisten-Größe.\n'
            '• Parameter: Anzahl (optional, 5-20, Standard: einstellbar)\n'
            '• Beispiel: !topfarm 10\n'
            '• Platzhalter für eigene Texte: {user}',
  'cmd': '!topfarm',
  'cat': 'Farmen'},
 {'title': '!buywerkzeug – Farmen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!buywerkzeug', 'werkzeug', 'sprinkler', 'duenger', 'buywerkzeug'],
  'answer': '🌱 !buywerkzeug [<werkzeug>]  (Farmen)\n'
            'Kauft ein Farm-Werkzeug zum ersten Mal (Stufe 1) für Coins: Automatische Sprinkler und Premium-Dünger '
            'verkürzen die Wachstumszeit ALLER Pflanzen dauerhaft, die Ernte-Sense erhöht den Mindest-Ertrag. Ohne '
            'Angabe wird eine Übersicht aller Werkzeuge mit Stufe und Kosten angezeigt. Manche Werkzeuge brauchen '
            'ein bestimmtes Farm-Level.\n'
            '• Parameter: Optional: <werkzeug> = sprinkler, duenger oder sense\n'
            '• Beispiel: !buywerkzeug sprinkler\n'
            '• Platzhalter für eigene Texte: {user}, {tool}, {level}, {max_level}, {cost}, {coins}, {effect}',
  'cmd': '!buywerkzeug',
  'cat': 'Farmen'},
 {'title': '!upgradewerkzeug – Farmen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!upgradewerkzeug', 'upgradewerkzeug', 'werkzeug upgraden', 'werkzeug verbessern'],
  'answer': '🌱 !upgradewerkzeug [<werkzeug>]  (Farmen)\n'
            'Verbessert ein bereits gekauftes Farm-Werkzeug um eine Stufe. Jede Stufe wird teurer, bis die '
            'Maximalstufe erreicht ist. Die Boni gelten dauerhaft für alle Pflanzen (kürzere Wachstumszeit bzw. '
            'höherer Mindest-Ertrag).\n'
            '• Parameter: Optional: <werkzeug> = sprinkler, duenger oder sense\n'
            '• Beispiel: !upgradewerkzeug sprinkler\n'
            '• Platzhalter für eigene Texte: {user}, {tool}, {level}, {max_level}, {cost}, {coins}, {effect}',
  'cmd': '!upgradewerkzeug',
  'cat': 'Farmen'},
 {'title': '!buytraktor – Farmen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!buytraktor', 'traktor', 'buytraktor'],
  'answer': '🌱 !buytraktor  (Farmen)\n'
            'Kauft den Traktor – das High-End-Statussymbol für erfahrene Farmer (einmalig, benötigt ein hohes '
            'Farm-Level und viele Coins). Wer einen Traktor besitzt, bekommt dauerhaft einen Bonus auf ALLE '
            'Farm-Verkäufe (je nach Einstellung mehr Coins, mehr Farm-XP oder beides). Außerdem tuckert ein kleines '
            'Traktor-Emoji durchs 2D-Arena-Overlay, sobald der Besitzer den Farm-Status-Befehl nutzt.\n'
            '• Beispiel: !buytraktor\n'
            '• Platzhalter für eigene Texte: {user}, {cost}, {coins}, {bonus}, {farm_cmd}',
  'cmd': '!buytraktor',
  'cat': 'Farmen'},
 {'title': '!points – Währung',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!points', 'punktestand', 'meine punkte', 'wie viele punkte', 'coins anzeigen', 'kontostand'],
  'answer': '💰 !points\n'
            'Zeigt dir im Chat deinen aktuellen Punktestand (die Community-Währung). Name und Vergabe der Währung '
            'stellt der Streamer unter Currency → Punkte-Einstellungen ein. Fast alle Chat Games bezahlen mit dieser '
            'Währung.',
  'cmd': '!points',
  'cat': 'Währung'},
 {'title': '!givepoints – Währung',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!givepoints',
         'punkte verschenken',
         'coins verschenken',
         'coins senden',
         'punkte senden',
         '!pay',
         '!transfer'],
  'answer': '💰 !givepoints\n'
            'Überweist Coins an einen anderen Zuschauer: !givepoints @user <menge>. Abbuchung und Gutschrift laufen '
            'in EINER Transaktion – es geht also kein Coin verloren und nichts wird doppelt gebucht. In der BETA V3 '
            'klappen auch die Aliase !pay und !transfer.',
  'cmd': '!givepoints',
  'cat': 'Währung'},
 {'title': '!eventpunkte – Währung',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!eventpunkte', 'event waehrung', 'eventinfo', '!eventinfo', 'event punkte', 'eventpunkte'],
  'answer': '💰 !eventpunkte\n'
            'Event-Währung (nur BETA V3): !eventpunkte zeigt deinen Stand der Event-Punkte, !eventinfo zeigt Infos '
            'dazu und !event das aktuell laufende Community-Event. Die Event-Währung stellt der Streamer unter '
            'Currency → Punkte-Einstellungen ein. Mit Event-Punkten kann man auch Giveaway-Lose kaufen (!ticket).',
  'cmd': '!eventpunkte',
  'cat': 'Währung'},
 {'title': '!race – Minigame',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!race', 'rennen', 'sim racing', 'rennspiel', 'race start', 'race$'],
  'answer': '🎲 !race\n'
            'Sim-Racing-Giveaway: Zuschauer tragen sich in der Anmeldephase mit !race ein. Mit !race start eröffnet '
            'man die Anmeldephase – wer das darf, stellt der Streamer über die Berechtigungsstufen ein (vom nur '
            'Broadcaster bis zu jedem Zuschauer). Danach fährt das Feld automatisch ein Rennen im OBS-Overlay, Platz '
            '1 bis 3 bekommen zufällige Coins. Es gibt eine Mindestteilnehmerzahl.',
  'cmd': '!race',
  'cat': 'Minigame'},
 {'title': '!krakenraid – Angeln',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!krakenraid',
         'kraken',
         'kraken raid',
         'kraken boss',
         'harpoon',
         'harpune',
         '!harpoon',
         '!net',
         'boss event'],
  'answer': '🎣 !krakenraid\n'
            'Kraken-Boss-Raid (Teil vom Angel Game): Mod oder Streamer starten ihn mit !krakenraid. Im Overlay '
            'erscheint ein Kraken mit HP-Balken, alle Zuschauer greifen gemeinsam mit !harpoon und !net an. '
            'Einstellbar ist alles im Angel Game (Kraken-Bereich).',
  'cmd': '!krakenraid',
  'cat': 'Angeln'},
 {'title': '!hi – Minigame',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!hi', '!low', 'hi lo', 'hilo', 'kartenspiel', 'karte hoeher', 'karte niedriger'],
  'answer': '🎲 !hi\n'
            'Hi-Lo Kartenspiel (nur BETA V3): !hi <einsatz> oder !low <einsatz> – du tippst, ob die nächste gezogene '
            'Karte höher oder niedriger ist als die offene Karte. Sofortige Auflösung mit animiertem OBS-Overlay, '
            'Cooldown pro Nutzer. Gewinn = Einsatz gutgeschrieben, Verlust = Einsatz abgezogen, Unentschieden zählt '
            'nicht. Das Spiel braucht eine Freischaltung.',
  'cmd': '!hi',
  'cat': 'Minigame'},
 {'title': '!raffle – Minigame',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!raffle', '!join', 'raffle$', 'raffle starten', 'join$', 'punkte raffle', 'unterschied raffle raffel'],
  'answer': '🎲 !raffle\n'
            'Punkte-Raffle (nur BETA V3): Mod/Streamer starten es mit !raffle [Pot] [Gewinner] [Sekunden] (!raffle '
            'stop bricht ab). Zuschauer machen mit !join mit. Nach Ablauf des Timers zieht der Bot automatisch die '
            'Gewinner und teilt den Pot gleichmäßig auf. Achtung: !raffle (Mods) ist etwas anderes als !raffel '
            '<einsatz> (Zuschauer-Spiel).',
  'cmd': '!raffle',
  'cat': 'Minigame'},
 {'title': '!ticket – Giveaway',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!ticket',
         '!cointicket',
         'ticket$',
         'tickets',
         'lose kaufen',
         'los kaufen',
         'gewinnchance erhoehen',
         'zusaetzliche lose',
         'nur teilnahme per los'],
  'answer': '🎁 !ticket\n'
            'Giveaway-Lose kaufen (nur BETA V3): !ticket <anzahl> tauscht Event-Punkte gegen zusätzliche Lose, '
            '!cointicket <anzahl> tut dasselbe mit Coins (Schokos). Jedes Los ist ein weiterer Eintrag im Lostopf '
            'und erhöht die Gewinnchance. Preis, Maximum und Aktiv-Status stellt der Streamer pro Giveaway in '
            "Schritt 1 (Konfig) ein; es gilt für Standard- UND parallele Giveaways. Im Modus 'Nur Teilnahme per Los' "
            'ist das der einzige Weg mitzumachen.',
  'cmd': '!ticket',
  'cat': 'Giveaway'},
 {'title': '!gambel – Minigame',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!gambel', '!gamble', 'gambeln', 'gamble$', 'gambel$', 'glücksspiel', 'gluecksspiel'],
  'answer': '🎲 !gambel\n'
            'Gambeln (nur BETA V3): !gambel <einsatz> oder !gambel all. Mit der eingestellten Chance (Standard 50 %) '
            "wird der Einsatz verdoppelt, sonst ist er weg. 'all' setzt das gesamte Guthaben (begrenzt durch den "
            'eingestellten Maximaleinsatz). Gewinne werden bewusst ohne Event-Coin-Multiplikator gutgeschrieben. '
            'Auch !gamble funktioniert.',
  'cmd': '!gambel',
  'cat': 'Minigame'},
 {'title': '!panel – Panels',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!panel',
         'zuschauer panel',
         'viewer panel',
         'userpanel',
         'user panel',
         'panel$',
         'login code',
         'fluestern',
         'whisper'],
  'answer': '🛡️ !panel\n'
            'Zuschauer-Panel (nur BETA V3): Mit !panel bekommen Zuschauer den Zugang zu ihrem persönlichen '
            'Browser-Panel (Angeln, Farm, Aquarium, Ausrüstung, Mine, Duelle, Lotterie, Quests, Erfolge, Haustiere & '
            'Album). Der Login läuft über einen einmaligen Code, der per Twitch-Flüsternachricht kommt. Der Streamer '
            'muss das Panel in den Einstellungen einschalten.',
  'cmd': '!panel',
  'cat': 'Panels'},
 {'title': '!report – Panels',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!report', 'report$', 'chatter melden', 'user melden', 'zuschauer melden', 'mod queue'],
  'answer': '🛡️ !report\n'
            'Zuschauer melden Chatter (nur BETA V3): !report <Name> <Grund> – die Meldung landet in der Mod-Queue '
            'des Mod-Panels, wo Mods sie bearbeiten.',
  'cmd': '!report',
  'cat': 'Panels'},
 {'title': '!modpanel – Panels',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!modpanel', 'modpanel', 'mod panel', 'moderatoren panel', 'mod link'],
  'answer': '🛡️ !modpanel\n'
            'Mod-Panel (nur BETA V3): Mods und Streamer tippen !modpanel im Chat und bekommen den Link zum Mod-Panel '
            'per Twitch-Flüsternachricht. Im Panel starten Mods Giveaways, bearbeiten Reports und mehr – ohne '
            'Zugriff auf deine App oder deinen Rechner. Du schaltest es nur ein: keine Domain, kein Konto, keine '
            'Twitch-Developer-Console nötig.',
  'cmd': '!modpanel',
  'cat': 'Panels'},
 {'title': '!sr – Musik',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!sr', '!song', 'songrequest', 'song request', 'musikwunsch', 'song wuenschen', 'dmca', 'youtube api'],
  'answer': '🎵 !sr\n'
            'Songrequest (nur BETA V3): !sr <YouTube- oder Spotify-Link> wünscht einen Song, !song zeigt den '
            'aktuellen Song. Mods hören im Mod-Panel vor und geben frei. Der Streamer stellt Befehle, Limits, den '
            'DMCA-frei-Modus und den YouTube-API-Key ein; der Player läuft als OBS-Browserquelle.',
  'cmd': '!sr',
  'cat': 'Musik'},
 {'title': '!liste – Giveaway',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!liste', 'teilnehmerliste', 'giveaway banner', 'liste ausblenden', 'liste einblenden', 'banner liste'],
  'answer': '🎁 !liste\n'
            'Teilnehmerliste im Giveaway-Banner (nur BETA V3, nur Mods/Streamer): !liste schaltet um, !liste an / '
            '!liste aus blendet sie ein/aus, !liste aus !gewinn betrifft nur das Giveaway mit dem Befehl !gewinn. '
            'Command und Preis bleiben immer sichtbar.',
  'cmd': '!liste',
  'cat': 'Giveaway'},
 {'title': '!avcode – Viewer-Arena',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!avcode', 'avatar code', 'avcode', 'avatar codes', 'avatar kiste', 'loot box avatar', 'avatar editor'],
  'answer': '🚶 !avcode\n'
            'Avatar-Code (nur BETA V3, nur Streamer): !avcode [kiste|selten|episch|legendär] [Anzahl Kisten] [Anzahl '
            'Einlösungen] erstellt einen Code und postet ihn im Chat. Wer ihn im Zuschauer-Panel einlöst, bekommt '
            'die Kiste(n) – bei 1 Einlösung gewinnt der Schnellste. Codes verwaltest du auch im Avatar-Editor '
            '(Avatar-Codes).',
  'cmd': '!avcode',
  'cat': 'Viewer-Arena'},
 {'title': '!king – Viewer-Arena',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!king', 'koenig', 'koenig des huegels', 'thron', 'podest'],
  'answer': '🚶 !king\n'
            'König des Hügels (nur BETA V3): !king besteigt das Podest in der 2D-Viewer-Arena, solange der Thron '
            'frei ist. Ein König wird per !duell vom Thron gestoßen.',
  'cmd': '!king',
  'cat': 'Viewer-Arena'},
 {'title': '!foto – Viewer-Arena',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!foto', '!foto_abbrechen', 'foto$', 'gruppenfoto', 'arena foto'],
  'answer': '🚶 !foto\n'
            'Gruppenfoto (nur BETA V3, nur Mods): !foto lässt alle Avatare in der Arena in zwei Reihen antreten, '
            'dann blitzt es im Overlay. !foto_abbrechen bricht ab.',
  'cmd': '!foto',
  'cat': 'Viewer-Arena'},
 {'title': '!pet – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!pet', 'pet$', 'haustier', 'haustiere'],
  'answer': '🚶 !pet\n'
            'Haustier in der 2D-Viewer-Arena: !pet <id> kauft bzw. rüstet ein Haustier aus (kostet Coins), !pet off '
            'legt es wieder ab.',
  'cmd': '!pet',
  'cat': 'Viewer-Arena'},
 {'title': '!mount – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!mount', 'mount$', 'reittier', 'reittiere'],
  'answer': '🚶 !mount\n'
            'Reittier in der 2D-Viewer-Arena: !mount <id> kauft bzw. rüstet ein Reittier aus (macht deinen Avatar im '
            'Overlay schneller), !mount off steigt wieder ab.',
  'cmd': '!mount',
  'cat': 'Viewer-Arena'},
 {'title': '!build – Viewer-Arena',
  'v': 'beide',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!build', 'build$', 'haus bauen', 'huette', 'hausbau', 'huettenbau'],
  'answer': '🚶 !build\n'
            'Hüttenbau in der 2D-Viewer-Arena: !build <haus_typ> baut bzw. verbessert ein Haus, sofern du genug '
            'gefarmte Ressourcen (Holz/Stein/Erz aus !mine) hast.',
  'cmd': '!build',
  'cat': 'Viewer-Arena'},
 {'title': '!schacht – Minen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!schacht', 'schacht', 'schaechte', 'minen 2.0', 'minen 2', 'mine2', 'tiefer graben'],
  'answer': '⛏️ !schacht\n'
            'Minen 2.0 (nur BETA V3): !schacht [1-4] zeigt deinen Schacht, wechselt ihn oder schaltet den nächsten '
            'der Reihe nach frei. Tiefere Schächte liefern bessere Funde. Standardpreise der Schächte: 0 / 300 / '
            '1500 / 6000 Coins (einstellbar).',
  'cmd': '!schacht',
  'cat': 'Minen'},
 {'title': '!sprengen – Minen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!sprengen', 'sprengen', 'dynamit', 'einsturz', 'verschuettet'],
  'answer': '⛏️ !sprengen\n'
            'Minen 2.0 (nur BETA V3): !sprengen kostet Coins und liefert mehrere Funde auf einmal – aber mit '
            'Einsturz-Gefahr! Wer verschüttet wird, kann mit !rette @user von einem Kumpel befreit werden.',
  'cmd': '!sprengen',
  'cat': 'Minen'},
 {'title': '!rette – Minen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!rette', 'rette$', 'retten', 'verschuetteten retten', 'kumpel retten'],
  'answer': '⛏️ !rette\n'
            'Minen 2.0 (nur BETA V3): !rette @user befreit einen verschütteten Kumpel (nach einem !sprengen) und '
            'bringt dir eine Prämie.',
  'cmd': '!rette',
  'cat': 'Minen'},
 {'title': '!sockel – Minen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!sockel', 'sockel', 'edelsteine', 'edelstein', 'spitzhacke aufruesten'],
  'answer': '⛏️ !sockel\n'
            "Minen 2.0 (nur BETA V3): !sockel setzt Edelsteine aus !mine in deine Spitzhacke (max. 3). '!sockel "
            "leer' legt alle zurück in den Beutel.",
  'cmd': '!sockel',
  'cat': 'Minen'},
 {'title': '!schmelzen – Minen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!schmelzen', 'schmelzen', 'barren', 'erz schmelzen', 'erze'],
  'answer': '⛏️ !schmelzen\n'
            'Minen 2.0 (nur BETA V3): !schmelzen [erz|alle] [anzahl] wandelt Erz aus dem Lager in Barren um '
            '(Verhältnis einstellbar). Barren verkaufst du mit !erzkurs verkaufen.',
  'cmd': '!schmelzen',
  'cat': 'Minen'},
 {'title': '!erzkurs – Minen',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['!erzkurs', 'erzkurs', 'erz kurs', 'barren verkaufen', 'tageskurs'],
  'answer': '⛏️ !erzkurs\n'
            'Minen 2.0 (nur BETA V3): !erzkurs zeigt den aktuellen Erzkurs (Zufallsbewegung je Erz zwischen 0,6x und '
            "1,6x, wird nach einer einstellbaren Zeit neu gewürfelt). '!erzkurs verkaufen' verkauft alle Barren zum "
            'Tageskurs.',
  'cmd': '!erzkurs',
  'cat': 'Minen'},
 {'title': '!so Rechte & an/aus',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['so an', 'so aus', 'so vip', 'shoutout vip', 'auto shoutout', 'shoutout rechte', 'wer darf so'],
  'answer': '📣 !so – wer darf das?\n'
            "Standardmäßig dürfen !so nur Broadcaster, Mods und VIPs manuell auslösen (Einstellung 'nur VIP', in den "
            'Shoutout-Einstellungen). Mit !so an / !so aus schaltet ein Mod oder der Streamer !so inklusive '
            "Auto-Shoutout komplett ein oder aus. Unter 'Shoutout (!so)' hinterlegst du außerdem Usernamen, für die "
            'der Shoutout automatisch ausgelöst wird. Im Overlay erscheint je nach Modus Logo/Name/Text oder ein '
            'zufälliger Twitch-Clip des Kanals (Clip mit Ton). Nur BETA V3.'},
 {'title': 'Minen 2.0 – Überblick',
  'v': 'beta',
  'group': 'spiel',
  'boost': 1.4,
  'kw': ['minen 2.0', 'minen 2', 'mine2', 'minen erweiterung', 'minen schaechte', 'minen neu'],
  'answer': '⛏️ Minen 2.0 (nur BETA V3)\n'
            'Erweiterung für !mine: Schächte (!schacht), Dynamit (!sprengen) mit Einsturz-Gefahr und Rettung '
            '(!rette), Edelstein-Sockel (!sockel), Schmelzen (!schmelzen) und Erzkurs (!erzkurs). Erze aus !mine '
            'landen im Lager und zahlen beim Fund nur den eingestellten Prozentsatz sofort aus; der Rest steckt in '
            'den Barren (Erzkurs 0,6x–1,6x). Schacht-Preise stehen in der settings.json unter mine2_shaft_prices '
            "(Standard 0, 300, 1500, 6000). Einschalten: Minen-Seite → 'Minen 2.0 aktiv'. Das Mining-Game braucht "
            'eine Freischaltung.'},
 {'title': 'Unterschied !raffel und !raffle',
  'v': 'beta',
  'group': 'befehl',
  'boost': 1.4,
  'kw': ['unterschied raffel raffle', 'raffel oder raffle', 'raffel vs raffle'],
  'answer': '🎟️ !raffel ≠ !raffle (nur BETA V3)\n'
            '• !raffel <einsatz> ist ein Spiel für Zuschauer: du setzt Coins ein, hast eine kleine Chance auf den '
            'ganzen Pot, sonst Verdopplung oder Verlust.\n'
            '• !raffle [Pot] [Gewinner] [Sekunden] startet ein Punkte-Raffle (nur Mods/Streamer), Zuschauer machen '
            'mit !join mit und der Pot wird unter den Gewinnern aufgeteilt.'},
 {'title': 'Seite: Giveaway (Dashboard)',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['giveaway dashboard',
         'giveaway starten',
         'giveaway steuern',
         'gewinner ziehen',
         'auslosen',
         'ziehung',
         'standard giveaway',
         'paralleles giveaway',
         'parallele giveaways',
         'zweites giveaway',
         'gewinnspiel',
         'gewinner bestaetigen',
         'giveaway schliessen',
         'testpreis',
         'giveaway  dashboard',
         'dashboard'],
  'answer': '🎁 Giveaway (Dashboard)\n'
            'Hier läuft dein Standard-Giveaway ab: Konfigurieren → Starten → Schließen → Gewinner ziehen → Gewinner '
            'bestätigen. Du steuerst alles über die Buttons oben.\n'
            'Zuschauer machen mit dem Chat-Befehl !giveaway mit. Mit !remove tragen sie sich wieder aus (beide '
            'Befehle sind änderbar).\n'
            'Zusätzlich gibt es ein paralleles Giveaway mit eigener Teilnehmerliste und eigenem Chat-Befehl. Es '
            'lässt sich unabhängig vom Standard-Giveaway steuern.\n'
            'Tipp: Teste alles einmal mit einem Testpreis, bevor du live gehst.',
  'answer_v526': '🎁 Dashboard\n'
                 'Hier läuft dein eigentliches Giveaway ab: Konfigurieren, Starten, Schließen, Ziehen und den '
                 'Gewinner bestätigen – Schritt für Schritt über die Buttons oben.'},
 {'title': 'Seite: Giveaway Setup',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['giveaway setup',
         'app setup',
         'einstellungen',
         'follower giveaway',
         'nur follower',
         'chat reminder',
         'nicht melder',
         'sprache',
         'englisch',
         'auto whisper',
         'code whisper',
         'autospeicher',
         'absturz teilnehmer',
         'teilnehmer gespeichert'],
  'answer': '⚙️ Giveaway Setup\n'
            'Die zentralen Einstellungen des Giveaways:\n'
            '• Follower-Giveaway: nur Follower dürfen teilnehmen.\n'
            '• Chat-Reminder: erinnert den Chat in Abständen an das laufende Giveaway.\n'
            '• Nicht-Melder-Regel: legt fest, was passiert, wenn ein Gewinner sich nicht meldet.\n'
            '• Timer und Animationen sowie die Sprache der App (Deutsch/Englisch).\n'
            'Hier kannst du außerdem nach Updates suchen und diesen Rundgang jederzeit neu starten.',
  'answer_v526': '⚙️ App-Setup\n'
                 'Zentrale Einstellungen: Zeiten für Ziehungen, Sprache, Update-Check und den Austragen-Befehl. Hier '
                 'kannst du diesen Rundgang später auch jederzeit erneut starten.'},
 {'title': 'Seite: Live Stats',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['live stats', 'live statistiken', 'livestats', 'stream dauer', 'chat aktivitaet', 'kennzahlen'],
  'answer': '📊 Live Stats\n'
            'Live-Kennzahlen zum laufenden Stream, z. B. Stream-Dauer und Chat-Aktivität. Die Werte aktualisieren '
            'sich automatisch alle paar Sekunden. Du musst nichts klicken, die Seite ist einfach eine Anzeige für '
            'dich nebenbei.',
  'answer_v526': '📊 Live-Statistiken\n'
                 'Zeigt dir Live-Werte zum aktuellen Stream, z.B. Stream-Dauer und Chat-Aktivität, während du '
                 'sendest.'},
 {'title': 'Seite: Statistik-Dashboard',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['statistik', 'statistik dashboard', 'csv export', 'auswertung', 'giveaway historie', 'giveaway verlauf'],
  'answer': '📈 Statistik-Dashboard\n'
            'Der Verlauf aller abgeschlossenen Giveaways mit Auswertungen. Damit siehst du, wie viele Zuschauer bei '
            'welchem Giveaway mitgemacht haben, und kannst die Daten für deine Unterlagen exportieren. Die Rangliste '
            "und den Punkte-Editor findest du unter Currency → 'Punkte-Einstellungen'.",
  'answer_v526': '📊 Statistik-Dashboard\n'
                 'Der Verlauf aller vergangenen Giveaways inkl. Auswertungen und CSV-Export für deine Unterlagen.'},
 {'title': 'Seite: Gewinner Verwaltung',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['gewinner verwaltung',
         'gewinner einloes',
         'codes hinterlegen',
         'code einloesen',
         'einloesung',
         'gewinner bestaetigen',
         'nicht melder',
         'einloese dashboard',
         'gewinner einlosungs dashboard'],
  'answer': '🏆 Gewinner Verwaltung\n'
            'Hier hinterlegst du Codes für Commands vorab, verwaltest eingelöste Codes und bestätigst Gewinner.\n'
            'So behältst du den Überblick, wer seinen Preis schon bekommen hat, und kannst die Regeln für '
            'Nicht-Melder sauber nachvollziehen.',
  'answer_v526': '🏆 Gewinner-Einlösungs-Dashboard\n'
                 'Hier verwaltest du eingelöste Codes, bestätigst Gewinner und stellst die Regeln für Nicht-Melder '
                 'ein.'},
 {'title': 'Seite: Giveaway Planer',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['giveaway planer',
         'geplantes giveaway',
         'zeitplan giveaway',
         'automatisch starten',
         'giveaway planen',
         'planer$'],
  'answer': '⏱️ Giveaway Planer\n'
            'Plane Giveaways für später: Du trägst Startzeit, Ziehungszeit, Preis und Chat-Befehl ein. Das Tool '
            'startet und zieht automatisch zur eingestellten Uhrzeit, auch wenn du gerade nicht am Rechner sitzt. '
            'Die App muss dafür laufen und der Bot verbunden sein.',
  'answer_v526': '⏱️ Giveaway-Planer\n'
                 'Damit kannst du Giveaways im Voraus zeitlich planen, statt sie manuell zu starten.'},
 {'title': 'Seite: OBS Tools Giveaway (wichtig!)',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['obs tools',
         'obs browser quellen',
         'browserquelle',
         'browser quelle',
         'overlay link',
         'overlay url',
         'dual pc',
         'zweiter pc',
         'websocket',
         'obs websocket',
         'fernsteuerung',
         'overlay einbinden',
         'in obs einbinden',
         'obs einbinden',
         'obs tools giveaway  wichtig',
         'obs browser quellen  wichtig'],
  'answer': '📺 OBS Tools Giveaway (wichtig!)\n'
            'Hier stehen ALLE Overlay-Links der App zum Kopieren, dazu Dual-PC-Setup und '
            'OBS-WebSocket-Fernsteuerung.\n'
            'So bindest du ein Overlay in OBS ein:\n'
            "1. In OBS bei 'Quellen' auf + klicken und 'Browser' wählen.\n"
            '2. Den kopierten Link bei URL einfügen.\n'
            '3. Breite und Höhe setzen (die empfohlene Größe steht bei jedem Overlay).\n'
            "4. Haken bei 'Bild aktualisieren, wenn Szene aktiv wird' setzen und mit OK bestätigen.\n"
            'Das wiederholst du für jedes Overlay, das du nutzen möchtest.',
  'answer_v526': '📺 OBS Browser-Quellen (wichtig!)\n'
                 'Hier findest du ALLE Overlay-Links deines Tools zum Kopieren. So bindest du einen davon in OBS '
                 "ein: Quellen (+) → 'Browser' → die kopierte URL einfügen → Breite/Höhe setzen → Haken bei 'Bild "
                 "aktualisieren, wenn Szene aktiv wird' setzen → OK. Diesen Vorgang wiederholst du für jede "
                 'Overlay-URL, die du nutzen möchtest.'},
 {'title': 'Seite: Mod-Panel',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['mod panel', 'modpanel', 'mods giveaway starten', 'moderatoren panel', 'mod portal'],
  'answer': '🛡️ Mod-Panel\n'
            'Deine Mods starten Giveaways bequem im Browser. Du schaltest es nur ein: keine Domain, kein Konto, '
            'keine Twitch-Developer-Console nötig. So können Mods helfen, ohne Zugriff auf deine App oder deinen '
            'Rechner zu haben.'},
 {'title': 'Seite: Sounds Giveaway',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['sounds',
         'sound$',
         'audio',
         'lautstaerke',
         'soundeffekte',
         'wiedergabeziel',
         'ton spielt nicht',
         'sounds giveaway'],
  'answer': '🔊 Sounds Giveaway\n'
            'Sounds für Ziehung, Glücksrad, Countdown, Disqualifikation und Gewinner. Du stellst pro Sound Datei und '
            'Lautstärke ein und wählst das Wiedergabeziel, also wo der Ton abgespielt wird.',
  'answer_v526': '🔊 Sounds\n'
                 'Verwaltet die Soundeffekte, die bei Giveaway-Ereignissen abgespielt werden (Ziehung, Sieg, etc.).'},
 {'title': 'Seite: Design & Effekte',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['design und effekte',
         'design und animationen',
         'ziehungs animation',
         'gluecksrad',
         'partikel',
         'farben overlay',
         'schrift overlay',
         'animation',
         'design   effekte',
         'design   animationen'],
  'answer': '🎨 Design & Effekte\n'
            'Farben und Schrift aller OBS-Overlays, die Art der Ziehungs-Animation, das Tempo des Glücksrads und der '
            'Partikel-Effekt. Änderungen siehst du im Overlay, sobald du sie speicherst.',
  'answer_v526': '🎨 Design & Animationen\n'
                 'Hier gestaltest du das Aussehen der Ziehungs-Animation, z.B. inklusive Glücksrad-Option.'},
 {'title': 'Seite: Theme Studio',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['theme studio', 'theme$', 'farbwelt', 'hauptfarbe', 'akzentfarbe', 'app farben'],
  'answer': '🖌️ Theme Studio\n'
            'Stelle dir eine eigene Farbwelt zusammen: Hauptfarbe, Sekundärfarbe, Hintergrund, Text und Akzent. Sie '
            'wird live auf die App und auf dein OBS-Overlay angewendet.',
  'answer_v526': '🖌️ Theme Studio\n'
                 'Wähle Haupt-/Sekundärfarbe, Hintergrund, Text und Akzentfarbe für ein eigenes App-Theme und '
                 'synchronisiere den Look live per WebSocket mit deinem OBS-Overlay.'},
 {'title': 'Seite: Logs',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['logs', 'log$', 'protokoll', 'system logs', 'logeintraege'],
  'answer': '📜 Logs\n'
            'Ein Protokoll von allem, was das Tool gerade tut. Es werden die letzten 300 Einträge angezeigt. Wenn '
            'etwas nicht wie erwartet läuft, schau zuerst hier nach und nenne dem Support die passende Zeile.',
  'answer_v526': '📜 System-Logs\n'
                 'Ein Protokoll aller Ereignisse im Tool – nützlich, falls mal etwas nicht wie erwartet läuft.'},
 {'title': 'Seite: Feedback & Bugs',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['feedback und bugs',
         'feedback seite',
         'feedback senden',
         'bugs und ideen',
         'bug melden',
         'fehler melden',
         'idee melden',
         'feature wunsch',
         'feedback geben',
         'wo melde ich',
         'feedback   bugs'],
  'answer': '💬 Feedback & Bugs\n'
            'Wähle die Art (Feedback, Bug oder Feature-Wunsch), beschreibe dein Anliegen und sende es ab. Deine '
            "Meldung geht direkt an das Team und erscheint dort im Bereich 'Bugs & Ideen'. Schreibe bei Bugs, was du "
            'vorher getan hast.',
  'answer_v526': '💬 Feedback & Bugs\nSende Feedback oder Fehlermeldungen direkt an den Entwickler.'},
 {'title': 'Seite: Support-Chat',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['support chat', 'mit support schreiben', 'support kontaktieren'],
  'answer': '🛟 Support-Chat\n'
            'Hier schreibst du direkt mit dem Support. Antworten erscheinen automatisch in diesem Fenster, du musst '
            'die Seite nicht neu laden. Nutze den Chat für Fragen zur Einrichtung oder wenn etwas nicht '
            'funktioniert.'},
 {'title': 'Seite: Chat Games',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['chat games', 'chat games   overlays'],
  'answer': '🎮 Chat Games\n'
            'Twitch Check-in und der Safe-Knacker an einem Ort, inklusive Live-Status und Test-Buttons.\n'
            '• Check-in: Zuschauer melden sich mit !checkin an und sammeln so Aktivität für die Rangliste.\n'
            '• Safe-Knacker: Minispiel mit !safe und eigenem Overlay.\n'
            'Mit den Test-Buttons prüfst du, ob dein Overlay in OBS richtig reagiert.',
  'answer_v526': '🎮 Chat Games & Overlays\n'
                 'Übersicht der interaktiven Chat-Games, z.B. das Check-in-Overlay für neue Zuschauer.'},
 {'title': 'Seite: Kanalpunkte',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['kanalpunkte',
         'kanalpunkte belohnung',
         'channel points',
         'belohnung einloesen',
         'kanalpunkte medien',
         'kanalpunkte sound',
         'kanalpunkte video'],
  'answer': '🎉 Kanalpunkte\n'
            'Verknüpfe echte Twitch-Kanalpunkte-Belohnungen mit einem Sound und/oder Video. Bei jeder Einlösung wird '
            'das Hinterlegte automatisch abgespielt.\n'
            'Dafür bindest du das Kanalpunkte-Medien-Overlay (Empfehlung: 1920x1080) als Browser-Quelle in OBS ein. '
            'Die Belohnung selbst legst du wie gewohnt bei Twitch an.'},
 {'title': 'Seite: 2D-Viewer-Arena',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['arena',
         '2d arena',
         'viewer arena',
         'avatar',
         'avatare',
         'sprechblase',
         'emotes',
         'pvp',
         'huette',
         'hausbau',
         'arena skins',
         'avatar editor',
         '2d viewer arena'],
  'answer': '🚶 2D-Viewer-Arena\n'
            'Aktive Chat-Zuschauer laufen als kleine Avatare am unteren Rand deines Streams. Hier stellst du '
            'Avatare, Sprechblasen, Emotes, PvP-Duelle, Umarmungen, Skins, Haustiere, Reittiere und Hüttenbau ein.\n'
            'Befehle: !duell und !akzept (Duell), !hug und !love, !skin und !skins (Skins ansehen), !pet, !mount, '
            '!build und !fliegen.\n'
            'Binde das Arena-Overlay als Vollbild-Browser-Quelle ein.\n'
            '\n'
            "ℹ️ In v5.2.6 liegen die Arena-Einstellungen in 'Chat Games' (Befehle: !duell, !akzept, !skin, !skins, "
            '!pet, !mount, !build; !hug, !love, !fliegen, !king, !foto gibt es erst in der BETA V3).'},
 {'title': 'Seite: Stempeluhr',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['stempeluhr', 'zeiterfassung', 'einstempeln', 'ausstempeln', 'id karte'],
  'answer': '⏱️ Stempeluhr\n'
            'Kanalpunkte-Zeiterfassung mit ID-Karten-Animation. Zuschauer stempeln sich per Kanalpunkte-Belohnung '
            'ein und aus. Hier stellst du die Belohnungen fürs Ein- und Ausstempeln, die Optionen und die '
            'OBS-Browser-Quelle (Empfehlung: 400x350) an einem Ort ein.\n'
            '\n'
            'ℹ️ In v5.2.6 findest du die Stempeluhr bei den OBS Browser-Quellen.'},
 {'title': 'Seite: Minen',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['minen spiel',
         'mining game',
         'bergbau',
         'mining einstellungen',
         'minen seite',
         'loot tabelle minen',
         'minen'],
  'answer': '⛏️ Minen\n'
            'Zuschauer graben mit !mine nach Loot in verschiedenen Seltenheiten. Du legst fest, was es zu finden '
            'gibt und wie oft gegraben werden darf. Das Game braucht eine Freischaltung.'},
 {'title': 'Seite: Hi-Lo',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['hi lo', 'hilo', 'karte hoeher', 'karte niedriger', 'kartenspiel'],
  'answer': '🃏 Hi-Lo\n'
            'Zuschauer tippen per Chat, ob die nächste Karte höher (!hi) oder niedriger (!low) ist. Die Auflösung '
            'erfolgt sofort mit einem animierten OBS-Overlay. Gespielt wird mit deinen Community-Punkten.'},
 {'title': 'Seite: Raffle',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['raffle seite', 'raffle einstellungen', 'punkte raffle', 'raffle'],
  'answer': '🎟️ Raffle\n'
            'Kostenloses Punkte-Raffle: Du startest es mit !raffle, Zuschauer machen mit !join mit. Nach Ablauf des '
            'Timers zieht der Bot automatisch die Gewinner und teilt den Pot gleichmäßig auf.'},
 {'title': 'Seite: Slot Machine Studio',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['slot machine',
         'slotmaschine',
         'slot studio',
         '3 walzen',
         'slot overlay',
         'slot symbole',
         'slot machine studio'],
  'answer': '🎰 Slot Machine Studio\n'
            'Klassische 3-Walzen-Slotmaschine mit den Community-Coins als Einsatz. Zuschauer spielen mit !slot. Du '
            'stellst Einsatz, Gewinnchancen und Auszahlungen ein und bindest das Slot-Overlay (Empfehlung: 500x400) '
            'in OBS ein.',
  'answer_v526': '🎰 Slot Machine Studio\n'
                 'Konfiguriert deine Chat-Slotmaschine inklusive ihrer eigenen OBS-Overlay-URL.'},
 {'title': 'Seite: Mega Slot Studio',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['mega slot', 'megaslot', '5 walzen', 'gewinnlinien', 'video slot', 'mega slot studio'],
  'answer': '🎡 Mega Slot Studio\n'
            'Klassischer 5-Walzen-Video-Slot mit 5 oder 20 Gewinnlinien und eigenem Overlay (Empfehlung: 620x400). '
            'Gespielt wird mit !megaslot. Er ist komplett unabhängig von der normalen Slot Machine.',
  'answer_v526': '🎡 Mega Slot Studio\nEine größere Sonder-Slot-Variante mit eigenem Overlay für besondere Anlässe.'},
 {'title': 'Seite: Angel Game',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['angel game',
         'angelspiel',
         'angeln',
         'fishing',
         'fische',
         'gewaesser',
         'kraken',
         'kraken boss',
         'eigene fische',
         'angel events',
         'angel spiel'],
  'answer': '🎣 Angel Game\n'
            'Das komplette Chat-Fishing-System. Befehle: !fish (auswerfen), !pull und !reel (einholen), !sell '
            '(verkaufen), !aquarium und !rute (Ruten).\n'
            'Dazu gehört der Kraken-Boss-Raid (!krakenraid, dann !harpoon und !net). Du verwaltest Fische, legst '
            'eigene Fische und eigene Gewässer an und steuerst die Events.\n'
            '\n'
            'ℹ️ In v5.2.6 ohne Köder-Shop (!koeder), Angel v2 (!haken, !nachlassen, !praeparieren) und '
            'Fisch-Abkommen (!auftrag) – die kamen erst mit der BETA V3.',
  'answer_v526': '🎣 Angel Game\n'
                 'Das komplette Chat-Fishing-System: Ruten, Genetik, Markt, Aquarium und Kraken-Event.'},
 {'title': 'Seite: Farm Game',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['farm game', 'farmspiel', 'farmen', 'farm$', 'pflanzen', 'saatgut', 'ernte', 'eigene pflanzen'],
  'answer': '🌱 Farm Game\n'
            'Sammel-Minigame nach dem Prinzip des Angelns: Jeder Zuschauer hat ein eigenes Feld. Saatgut wird per '
            'Level freigeschaltet, die Ernte landet in einem Farm-Inventar.\n'
            'Befehle: !saeen, !ernten, !farm (Status), !saatgut (Auswahl), !farmverkaufen und !topfarm '
            '(Bestenliste). Du kannst auch eigene Pflanzen anlegen.\n'
            '\n'
            'ℹ️ In v5.2.6 ohne Farm-Werkzeuge und Traktor (!buywerkzeug, !upgradewerkzeug, !buytraktor).',
  'answer_v526': '🌱 Farm Game\n'
                 'Das Farmen-Minigame: Saatgut aussäen, warten und ernten, eigene Pflanzen anlegen und eine eigene '
                 'Farmer-Bestenliste.'},
 {'title': 'Seite: Taschenraub',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['taschenraub', 'klauen', 'stehlen', 'diebstahl', 'taschenraub einstellungen'],
  'answer': '🥷 Taschenraub\n'
            'Zuschauer klauen sich mit !klau gegenseitig Coins. Du stellst den Befehl, die Erfolgschance, die '
            'Diebstahl-Prozente, die Strafe bei Misserfolg, den Cooldown und die Chat-Nachrichten ein.\n'
            '\n'
            'ℹ️ In v5.2.6 sitzen die Taschenraub-Einstellungen im Bereich Currency.'},
 {'title': 'Seite: Sim Racing',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['sim racing', 'rennspiel', 'rennen', 'racing', 'race overlay', 'berechtigungsstufen', 'sim racing giveaway'],
  'answer': '🏎️ Sim Racing\n'
            'Zuschauer tragen sich mit !race ein. Nach der Anmeldezeit fährt das Feld automatisch ein Rennen im '
            'Overlay. Platz 1 bis 3 bekommen zufällige Coins gutgeschrieben. Wer !race start auslösen darf, stellst '
            'du über die Berechtigungsstufen ein, vom nur Broadcaster bis zu jedem Zuschauer.',
  'answer_v526': '🏎️ Sim Racing Giveaway\n'
                 'Ein Renn-Overlay samt Leaderboard, bei dem Zuschauer gegeneinander antreten.'},
 {'title': 'Seite: Subathon',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['subathon', 'sub athon', 'subathon timer', 'subathon ziele'],
  'answer': '🔥 Subathon\n'
            "Ein eigener Countdown fürs Subathon plus eine Ziel-Liste, z. B. 'bei 25 Subs: Minecraft-Stream für 4 "
            "Stunden'. Du kannst den Timer steuern, Ziele anlegen und löschen. Timer und Ziele haben eigene Overlays "
            'für OBS.'},
 {'title': 'Seite: 24-Stunden-Stream',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['24 stunden stream', '24h stream', '24 stunden countdown', 'streams24', '24 stunden'],
  'answer': '⏳ 24-Stunden-Stream\n'
            'Ein eigener 24-Stunden-Countdown mit eigener Ziel-Liste. Er läuft unabhängig vom Subathon-Timer, du '
            'kannst also beide gleichzeitig nutzen.'},
 {'title': 'Seite: Punkte-Einstellungen',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['punkte einstellungen',
         'currency',
         'waehrung',
         'community waehrung',
         'punkte$',
         'schokos',
         'event waehrung',
         'passiv punkte',
         'rangliste',
         'loyalty',
         'punkte editor',
         'coins',
         'currency   punkte'],
  'answer': '💰 Punkte-Einstellungen\n'
            'Name und Vergabe deiner Community-Währung, dazu die User-Loyalty-Rangliste mit Punkte-Editor, '
            'Passiv-Punkte für Zuschauer im Chat und die Event-Währung.\n'
            'Zuschauer sehen ihren Stand mit !points und verschenken Punkte mit !givepoints. Die Event-Währung hat '
            'eigene Befehle (!eventpunkte, !eventinfo, !event).\n'
            'Wichtig: Fast alle Chat Games zahlen mit dieser Währung. Stelle sie daher zuerst ein.\n'
            '\n'
            'ℹ️ In v5.2.6 gibt es keine Event-Währung (!eventpunkte, !eventinfo) und keine Giveaway-Lose.',
  'answer_v526': '💰 Currency & Punkte\n'
                 'Einstellungen für die virtuelle Zuschauer-Währung, mit der z.B. Chat-Games bezahlt werden.'},
 {'title': 'Seite: Raid-Greeter',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['raid greeter', 'raid begruessung', 'raids begruessen', 'raid', 'hologramm'],
  'answer': '🛡️ Raid-Greeter\n'
            'Begrüßt eingehende Raids automatisch im Chat und per Overlay (Empfehlung: 800x400). Hier legst du '
            'außerdem fest, wie viele Punkte es für Follows, Bits und Subs gibt.',
  'answer_v526': '🛡️ Raid-Greeter\nBegrüßt eingehende Raids automatisch im Chat und/oder per Overlay.'},
 {'title': 'Seite: Befehle Übersicht',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['befehle uebersicht',
         'befehlsuebersicht',
         'command info',
         'alle befehle',
         'welche befehle',
         'befehlsliste',
         'syntax',
         'command uebersicht',
         'befehle ubersicht',
         'command ubersicht'],
  'answer': '⚡ Befehle Übersicht\n'
            'Alle aktiven Chat-Befehle mit genauer Syntax, Bedeutung und Platzhaltern. Dazu gehören auch Befehle wie '
            '!gambel, !raffel und !panel. Schau hier nach, wenn du einem Zuschauer einen Befehl erklären willst.',
  'answer_v526': '📖 Command-Übersicht\n'
                 'Eine Übersicht aller verfügbaren Chat-Befehle inklusive ihrer genauen Syntax.'},
 {'title': 'Seite: Clip-Einstellungen',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['clip einstellungen', 'clip cooldown', 'clips erstellen', 'clip befehl'],
  'answer': '🎬 Clip-Einstellungen\n'
            'Zuschauer erstellen mit !clip einen Twitch-Clip der letzten Sekunden. Der Link geht in den Chat und auf '
            'Wunsch zusätzlich nach Discord. Das geht nur, solange der Stream live ist. Es gibt einen gemeinsamen '
            'Cooldown, Standard sind 30 Sekunden.'},
 {'title': 'Seite: Shoutout (!so)',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['shoutout', 'shout out', 'auto shoutout', 'shoutout overlay', 'shoutout einstellungen', 'shoutout  so'],
  'answer': '📣 Shoutout (!so)\n'
            'Zuschauer oder Mods lösen mit !so einen Shoutout für einen anderen Kanal aus. Im Overlay erscheint je '
            'nach Modus Logo, Name und Text oder ein zufälliger Twitch-Clip des Kanals. Unten kannst du Usernamen '
            'hinterlegen, für die der Shoutout automatisch ausgelöst wird.'},
 {'title': 'Seite: Songrequest (!sr)',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['songrequest',
         'song request',
         'musikwunsch',
         'youtube link',
         'spotify',
         'dmca',
         'songwunsch',
         'songrequest  sr'],
  'answer': '🎵 Songrequest (!sr)\n'
            'Zuschauer wünschen sich mit !sr Songs per YouTube- oder Spotify-Link. Mods hören im Mod-Panel vor und '
            'geben frei. Hier stellst du Befehle, Limits, den DMCA-frei-Modus und den YouTube-API-Key ein. Der '
            'Player läuft als OBS-Browserquelle.'},
 {'title': 'Seite: Eigene Commands',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['eigene commands',
         'eigene befehle',
         'custom commands',
         'custom befehl',
         'command erstellen',
         'neuen befehl',
         'eigener befehl',
         'eigene chat commands'],
  'answer': '🧩 Eigene Commands\n'
            'Erstelle völlig neue Chat-Commands mit eigener Text-Antwort. Mit dem Platzhalter {user} sprichst du den '
            'Auslöser direkt an. Befehle aus anderen Bots kannst du über den Bereich Import übernehmen.',
  'answer_v526': '🧩 Eigene Chat-Commands\n'
                 'Hier legst du komplett eigene Chat-Commands mit individueller Text-Antwort an.'},
 {'title': 'Seite: Timed Commands',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['timed commands',
         'zeitgesteuerte befehle',
         'automatische nachrichten',
         'intervall nachricht',
         'timer nachricht',
         'zeitgesteuerte'],
  'answer': '⏱️ Timed Commands\n'
            'Automatische Chat-Nachrichten in einem festen Zeitintervall, solange der Bot läuft. Gut für '
            'Social-Media-Links, Regeln oder Erinnerungen. Wähle das Intervall nicht zu kurz, sonst nervt es den '
            'Chat.',
  'answer_v526': '⏱️ Timed Commands\n'
                 'Automatische Chat-Nachrichten, die in einem festen Zeitintervall gesendet werden.'},
 {'title': 'Seite: Automationen',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['automationen', 'automation', 'wenn dann', 'streamer bot', 'eventsub regel', 'aktion regel'],
  'answer': '🤖 Automationen\n'
            'Wenn-Dann-Regeln wie bei Streamer.bot: Ein Ereignis (Follow, Sub, Raid, Bits, Kanalpunkte, '
            'Chat-Command, Stichwort, Stream live/offline) löst nacheinander Aktionen aus - Chat-Nachricht, '
            'OBS-Szene oder -Quelle, Sound oder Coins. Mit Bedingungen (Mindestmenge, Rolle, Wahrscheinlichkeit, '
            'Abklingzeit) und Test-Knopf.'},
 {'title': 'Seite: Stream Titel/Spiel',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['stream titel',
         'stream presets',
         'titel und spiel',
         'kategorie aendern',
         'vorlage titel',
         'stream vorlage',
         'stream titel spiel',
         'stream titel spiel vorlagen'],
  'answer': '🎬 Stream Titel/Spiel\n'
            'Speichere Stream-Titel und Spiel als Vorlage und übernimm sie per Klick direkt auf Twitch. So wechselst '
            'du vor dem Stream mit einem Klick zwischen deinen üblichen Kombinationen.',
  'answer_v526': '🎬 Stream Titel/Spiel Vorlagen\n'
                 'Speichere Stream-Titel samt Spiel/Kategorie als Vorlage und übernimm sie per Klick auf Twitch.'},
 {'title': 'Seite: Chat Vorlagen',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['chat vorlagen', 'chat nachrichten vorlagen', 'nachrichten vorlagen', 'chat template'],
  'answer': '📝 Chat Vorlagen\n'
            'Lege für jedes Giveaway-Ereignis eine eigene Chat-Nachricht fest, z. B. Start, Ziehung oder Gewinner. '
            'Jede Vorlage lässt sich einzeln ein- oder ausschalten.',
  'answer_v526': '📝 Chat-Nachrichten-Vorlagen\n'
                 'Vorlagen für automatische Chat-Nachrichten bei bestimmten Ereignissen.'},
 {'title': 'Seite: Twitch Chat Bot',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['chat bot',
         'chatbot',
         'bot verbinden',
         'bot verbindung',
         'bot reagiert nicht',
         'bot antwortet nicht',
         'bot trennen',
         'bot steuerung',
         'twitch chat bot',
         'chat bot steuerung'],
  'answer': '🤖 Twitch Chat Bot\n'
            'Steuert die Verbindung deines Chatbots: verbinden und trennen. Außerdem siehst du sein Live-Protokoll. '
            'Ist der Bot nicht verbunden, reagiert kein Chat-Befehl. Prüfe das hier zuerst, wenn im Chat nichts '
            'passiert.',
  'answer_v526': '🤖 Chat-Bot-Steuerung\nSteuert die Verbindung deines Twitch-Chatbots (verbinden/trennen, Status).'},
 {'title': 'Seite: Discord Webhook',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['discord', 'webhook', 'discord webhook', 'live ankuendigung', 'discord live', 'embed'],
  'answer': '💬 Discord Webhook\n'
            'Sendet Clip-Links und Giveaway-Ankündigungen automatisch in einen Discord-Kanal. Du trägst die '
            'Webhook-URL deines Kanals ein und schaltest die Benachrichtigungen ein. Die URL erstellst du in den '
            'Discord-Kanaleinstellungen unter Integrationen.',
  'answer_v526': '💬 Discord-Webhook\n'
                 'Bindet einen Discord-Webhook ein, um dort automatisch Benachrichtigungen zu erhalten.'},
 {'title': 'Seite: Lurk Tool',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['lurk tool', 'lurk', 'willkommen zurueck', 'zuhoeren abmelden', 'lurk nachrichten'],
  'answer': '💤 Lurk Tool\n'
            'Zuschauer melden sich mit !lurk zum Zuhören ab. Kehren sie zurück, bekommen sie automatisch eine '
            'Willkommen-zurück-Nachricht. Du stellst die Nachrichten ein.',
  'answer_v526': '💤 Lurk Tool\n'
                 "Schickt in einstellbaren Abständen zufällige Nachrichten für Zuschauer, die gerade 'lurken'."},
 {'title': 'Seite: Alert Editor',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['alert editor',
         'overlay editor',
         'alerts',
         'follow alert',
         'sub alert',
         'raid alert',
         'bits alert',
         'alert bauen'],
  'answer': '🚨 Alert Editor\n'
            'Baue eigene Follow-, Sub-, Raid- und Bits-Alerts. Bilder, Videos, Sounds, Texte und eingebettete Spiele '
            'oder Giveaways platzierst du frei auf der Bühne. Jedes Element verschiebst du per Maus und stellst '
            'Größe und Verhalten im Seitenfeld ein.'},
 {'title': 'Seite: Starting Soon / Pause',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['starting soon',
         'pause szene',
         'szenen editor',
         'pause overlay',
         'countdown szene',
         'starting soon   pause'],
  'answer': '🎬 Starting Soon / Pause\n'
            "Baue die dauerhaften Szenen 'Starting Soon' und 'Pause'. Bilder, Videos, Sounds, Texte, einen Countdown "
            'und einen Giveaway-Hinweis platzierst du frei auf der Bühne.'},
 {'title': 'Seite: Eigene Overlays',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['eigene overlays', 'eigenes overlay', 'custom overlay', 'overlay bauen'],
  'answer': '🧩 Eigene Overlays\n'
            'Baue beliebig viele eigene Overlays mit Bildern, Videos, Sounds, Texten, Countdown, Giveaway-Hinweis '
            'und eingebetteten Spielen. Jedes Overlay bekommt eine eigene Browser-Quelle für OBS.'},
 {'title': 'Seite: Goal-Bars',
  'v': 'beide',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['goal bar', 'goalbar', 'goal bars', 'fortschrittsbalken', 'follower ziel', 'sub ziel', 'goalbar overlay'],
  'answer': '🎯 Goal-Bars\n'
            "Baue Fortschrittsbalken für Follower-, Sub- oder Coin-Ziele, dazu ein 'Custom'-Ziel, das du selbst "
            'pflegst. Alle Goal-Bars erscheinen in EINER Browser-Quelle (goalbar_overlay.html).'},
 {'title': 'Seite: Punkte-Import',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['punkte import', 'punkte importieren', 'csv punkte', 'punkte uebernehmen'],
  'answer': '📥 Punkte-Import\n'
            'Lade die CSV-Datei eines anderen Tools oder Bots hoch. Die Punkte werden deinen Zuschauern '
            'gutgeschrieben oder gesetzt. Vor dem Schreiben siehst du eine Vorschau, und es wird automatisch eine '
            'Sicherung angelegt.'},
 {'title': 'Seite: Command-Import',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['command import', 'commands importieren', 'commands uebernehmen', 'anderer bot commands'],
  'answer': '📥 Command-Import\n'
            "Lade die CSV-Datei mit Chat-Commands eines anderen Bots hoch. Sie landen unter 'Eigene Commands', "
            'Variablen wie $(user) werden automatisch zu {user}. Auch hier gibt es vorher eine Vorschau und eine '
            'automatische Sicherung.'},
 {'title': 'Aufbau der App (v5.2.6 und BETA V3)',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.4,
  'kw': ['aufbau',
         'menue',
         'navigation',
         'seitenleiste',
         'hauptbereiche',
         'wo finde ich',
         'reihenfolge anpassen',
         'drag and drop',
         'ausblenden',
         'archiv',
         'tabs',
         'reiter',
         'bereiche'],
  'answer': '🧭 So ist die App aufgebaut\n'
            '• BETA V3: Oben siehst du 7 Hauptbereiche – Giveaway Tool, Chat Games, Currency, Commands, Lurk Tool, '
            'Overlay Editor und Import. Links in der Seitenleiste stehen die Seiten des gewählten Bereichs, ganz '
            "unten 'Feedback & Bugs' und der 'Support-Chat'. Reihenfolge der Bereiche/Seiten lässt sich per Drag & "
            'Drop anpassen, nicht benötigte Einträge kannst du ausblenden oder ins Archiv schieben (pro Bereich).\n'
            '• v5.2.6: Klassisches Fenster mit Seitenleiste – Dashboard, Live-Statistiken, Chat Games, Raid-Greeter, '
            'Currency, Slot Machine, Mega Slot, Angel-Spiel, Farm-Spiel, Rennspiel, Gewinner-Einlösung, Statistik, '
            'Chatbot, Chat-Vorlagen, Command-Übersicht, Eigene Commands, Timed Commands, Stream-Presets, Planer, '
            'OBS-Quellen, Logs, Sounds, Design, Theme Studio, Lurk-Tool, Overlay-/Szenen-Editor, Eigene Overlays, '
            'Goal-Bars, Feedback, Support-Chat, Discord und Setup.'},
 {'title': 'Was ist neu in der BETA V3? (Unterschiede zu v5.2.6)',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.8,
  'kw': ['was ist neu',
         'neuerungen',
         'unterschied beta',
         'beta v3',
         'beta version',
         'beta vs',
         'v3',
         'v5.2.6',
         '5 2 6',
         'was kann die beta',
         'was hat die beta',
         'neue funktionen',
         'neue features',
         'changelog',
         'unterschiede version',
         'beta oder'],
  'answer': '🆕 BETA VERSION V3 gegenüber v5.2.6:\n'
            '• Neue Web-Oberfläche (die BETA V3 läuft im neuen UI mit 7 Hauptbereichen)\n'
            '• Mod-Panel & Zuschauer-Panel (!modpanel, !panel, !report)\n'
            '• Automationen (Wenn-Dann-Regeln wie bei Streamer.bot)\n'
            '• Songrequest (!sr, !song), Shoutout (!so) mit Clip-Ton\n'
            '• Hi-Lo (!hi/!low), Raffle (!raffle/!join), !raffel, !gambel\n'
            '• Giveaway-Lose (!ticket, !cointicket) und Event-Währung (!eventpunkte, !eventinfo)\n'
            '• Angel v2: Köder (!koeder), Haken (!haken), !nachlassen, !praeparieren, Fisch-Abkommen (!auftrag)\n'
            '• Farm: Werkzeuge (!buywerkzeug, !upgradewerkzeug) und Traktor (!buytraktor)\n'
            '• Minen 2.0: !schacht, !sprengen, !rette, !sockel, !schmelzen, !erzkurs\n'
            '• Arena: !hug, !love, !fliegen, !king, !foto, Avatar-Codes (!avcode), mehr Avatare/Skins\n'
            '• Subathon- und 24-Stunden-Stream-Timer mit Zielen\n'
            '• Eigene Overlays (mehrere, auch mit eingebetteten Spielen), Goal-Bars\n'
            '• Punkte- und Command-Import aus anderen Tools (CSV)\n'
            '• Discord Live-Ankündigung mit Embed-Editor, Auto-Speicherstand für Giveaway-Teilnehmer, Rundgang durch '
            'alle Seiten\n'
            '\n'
            'Alles aus v5.2.6 gibt es weiterhin (Giveaway, Slot/Mega Slot, Angeln, Farmen, Taschenraub, Rennspiel, '
            'Arena, Raid-Greeter, Lurk, Eigene Commands, Timed Commands, Stream-Presets, Planer, Overlays, Discord, '
            '…).'},
 {'title': 'Rundgang (Onboarding-Tour)',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.4,
  'kw': ['rundgang',
         'tour',
         'einfuehrung',
         'onboarding',
         'rundgang neu starten',
         'rundgang ueberspringen',
         'ueberspringen',
         '2 euro',
         'spende'],
  'answer': '🧭 Rundgang: Beim ersten Start führt dich StreamDex durch JEDE Seite und erklärt, was sie kann, welche '
            "Chat-Befehle dazugehören und was du zuerst einstellen solltest. Mit 'Weiter'/'Zurück' bestimmst du das "
            'Tempo. In der BETA V3 kostet Überspringen einmalig 2 € Spende – danach darfst du jeden Rundgang '
            "überspringen, auch nach Updates. Neu starten: Giveaway Tool → 'Giveaway Setup' (v5.2.6: 'App-Setup') → "
            "'Rundgang erneut starten'."},
 {'title': 'In 4 Schritten startklar',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.5,
  'kw': ['startklar',
         '4 schritte',
         'vier schritte',
         'loslegen',
         'erste einrichtung',
         'setup anleitung',
         'wie starte ich'],
  'answer': '🚀 In 4 Schritten startklar:\n'
            "1) Chat-Bot verbinden: Commands → 'Twitch Chat Bot' (ohne verbundenen Bot reagiert nichts im Chat).\n"
            "2) Community-Währung einrichten: Currency → 'Punkte-Einstellungen' (Name, Vergabe, Passiv-Punkte).\n"
            "3) Overlays in OBS einbinden: Giveaway Tool → 'OBS Tools Giveaway' kopiert dir alle "
            'Browser-Quellen-Links.\n'
            "4) Games aktivieren: Chat Games sind standardmäßig gesperrt – über '🛒 Shop / Freischalten' unten in der "
            'Seitenleiste schaltest du sie frei (nach ca. 1 Minute aktiv, ohne Neustart).'},
 {'title': 'Twitch-Berechtigungen (Scopes)',
  'v': 'beta',
  'group': 'allgemein',
  'boost': 1.4,
  'kw': ['berechtigung',
         'berechtigungen',
         'scope',
         'scopes',
         'twitch rechte',
         'fehlende berechtigung',
         'token waechter',
         'darf streamdex',
         'welche rechte'],
  'answer': '🔐 Twitch-Berechtigungen, die StreamDex beim Login anfragt (je nach Funktion):\n'
            '• Chat lesen und schreiben\n'
            '• Follower-Prüfung & Follow-Alerts\n'
            '• Sub-Alerts & Sub-Abfragen\n'
            '• Bits-Alerts\n'
            '• Kanalpunkte-Einlösungen\n'
            '• Stream-Titel & Kategorie ändern\n'
            '• Clips erstellen\n'
            '• Shoutouts\n'
            '• Mod-Aktionen (Bann, Nachrichten löschen, Chat-Modi) (nur wenn Mod-Panel aktiv)\n'
            '• Blockierte Begriffe (nur wenn Mod-Panel aktiv)\n'
            '• VIPs verwalten (nur wenn Mod-Panel aktiv)\n'
            '• Raids, Umfragen & Vorhersagen starten (nur wenn Mod-Panel aktiv)\n'
            '• Flüstern (Panel-Login-Code, Gewinner-Codes)\n'
            'Fehlt eine Berechtigung, funktioniert nur die zugehörige Funktion nicht. Lösung: im Tool bei Twitch neu '
            "anmelden und alles bestätigen – der Token-Wächter im Reiter 'StreamDex' zeigt, was fehlt."},
 {'title': 'Befehle anpassen / umbenennen',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.4,
  'kw': ['befehl umbenennen',
         'befehl aendern',
         'command aendern',
         'andere schreibweise',
         'befehl heisst anders',
         'standard befehl',
         'eigenen befehl nennen'],
  'answer': '✏️ Alle Chat-Befehle sind änderbar: Die Befehle stehen in den Einstellungen der jeweiligen Seite (z. B. '
            "Currency, Angel Game, Farm Game) und in der Befehls-Übersicht (Commands → 'Befehle Übersicht') mit der "
            "tatsächlich eingestellten Schreibweise. Eigene Befehle mit fester Text-Antwort legst du unter 'Eigene "
            "Commands' an ({user} spricht den Auslöser an). Hinweis: Hier nenne ich die Standard-Befehle – bei dir "
            'können sie anders heißen.'},
 {'title': 'Spiele freischalten / Shop',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.4,
  'kw': ['spiel freischalten',
         'game freischalten',
         'freischaltung',
         'shop freischalten',
         'shop button',
         'wie schalte ich',
         'gesperrt spiel',
         'spiel gesperrt'],
  'answer': "🛒 Chat Games sind am Anfang gesperrt und werden über '🛒 Shop / Freischalten' (unten in der "
            'Seitenleiste) bzw. vom Support freigeschaltet. Die Freischaltung ist nach ca. 1 Minute ohne Neustart '
            "aktiv. Welche Spiele bei dir gerade frei sind, sehe ich live – tippe dafür einfach 'Spiele'."},
 {'title': 'Bot reagiert im Chat nicht',
  'v': 'beide',
  'group': 'hilfe',
  'boost': 1.6,
  'kw': ['bot reagiert nicht',
         'bot antwortet nicht',
         'nichts im chat',
         'befehl geht nicht',
         'command geht nicht',
         'befehl reagiert nicht',
         'chat reagiert nicht',
         'bot tot',
         'bot offline',
         'bot verbunden'],
  'answer': '🤖 Wenn im Chat nichts passiert:\n'
            "1) Ist der Bot verbunden? Commands → 'Twitch Chat Bot' (Live-Protokoll prüfen).\n"
            '2) Ist das Spiel/Feature freigeschaltet und eingeschaltet? (Chat Games sind standardmäßig gesperrt.)\n'
            '3) Stimmt die Schreibweise des Befehls? Die Befehle sind änderbar – schau in der Befehls-Übersicht '
            'nach.\n'
            '4) Cooldown/Rechte: Viele Befehle haben einen Cooldown, manche sind nur für Mods/VIPs.\n'
            "5) Logs ansehen (Seite 'Logs') – dort steht, was das Tool gerade tut.\n"
            'Hilft nichts? Schreib mir die Zeile aus den Logs und deine Version.'},
 {'title': 'Gewinner meldet sich nicht',
  'v': 'beide',
  'group': 'hilfe',
  'boost': 1.4,
  'kw': ['gewinner meldet sich nicht',
         'nicht gemeldet',
         'gewinner reagiert nicht',
         'gewinner code',
         'code fluestern',
         'gewinner disqualifiziert',
         'disqualifikation',
         'neuen gewinner'],
  'answer': '⏳ Meldet sich ein Gewinner nicht, greift die Nicht-Melder-Regel (Giveaway Setup): Sie legt fest, was '
            'passiert – z. B. neuen Gewinner ziehen oder Disqualifikation. Eingelöste Codes und bestätigte Gewinner '
            "verwaltest du in 'Gewinner Verwaltung' (v5.2.6: 'Gewinner-Einlösungs-Dashboard'). Der Code kann dem "
            'Gewinner automatisch geflüstert werden (An/Aus-Schalter im Giveaway Setup).'},
 {'title': 'Giveaway startet nicht automatisch (Planer)',
  'v': 'beide',
  'group': 'hilfe',
  'boost': 1.4,
  'kw': ['planer startet nicht',
         'giveaway startet nicht',
         'planer funktioniert nicht',
         'automatisch gezogen',
         'geplant startet nicht',
         'uhrzeit giveaway'],
  'answer': '⏱️ Der Giveaway Planer startet und zieht zur eingestellten Uhrzeit automatisch – aber nur, wenn die App '
            'läuft und der Bot verbunden ist. Prüfe außerdem Startzeit, Ziehungszeit, Preis und Chat-Befehl im '
            'Planer.'},
 {'title': 'Teilnehmer nach Absturz weg',
  'v': 'beta',
  'group': 'hilfe',
  'boost': 1.4,
  'kw': ['teilnehmer weg',
         'teilnehmer verloren',
         'absturz teilnehmer',
         'versehentlich geschlossen',
         'tool geschlossen',
         'autospeicher',
         'wiederherstellen'],
  'answer': '💾 In der BETA V3 speichert das Tool die Giveaway-Teilnehmer automatisch (Auto-Speicherstand) und stellt '
            'sie beim nächsten Start wieder her – auch nach einem Absturz oder versehentlichem Schließen. Wichtig: '
            'Tool wieder starten und den Bot verbinden. In v5.2.6 gibt es diesen Auto-Speicherstand noch nicht.'},
 {'title': 'Discord Live-Ankündigung',
  'v': 'beta',
  'group': 'seite',
  'boost': 1.4,
  'kw': ['discord live',
         'live ankuendigung',
         'streamstart discord',
         'embed editor',
         'discord embed',
         'webhook url',
         'discord benachrichtigung'],
  'answer': '📣 Discord (BETA V3): Neben Clip-Links und Giveaway-Ankündigungen sendet das Tool beim Streamstart eine '
            'Live-Ankündigung in deinen Discord-Kanal – mit eingebautem Embed-Editor (Titel, Text, Farbe, Bild …). '
            'Du trägst dafür deine eigene Webhook-URL ein (Discord → Kanal-Einstellungen → Integrationen → '
            'Webhook).'},
 {'title': "Bugs & Ideen melden (so geht's)",
  'v': 'beide',
  'group': 'hilfe',
  'boost': 1.8,
  'kw': ['wie melde ich',
         'wo melde ich',
         'bug melden',
         'bugs melden',
         'fehler melden',
         'idee melden',
         'idee einreichen',
         'feedback geben',
         'feedback abgeben',
         'wohin melden',
         'wo kann ich bugs',
         'wo kann ich ideen',
         'bugs und ideen',
         'bugs & ideen',
         'vorschlag einreichen'],
  'answer': '🐞💡 Bug, Idee oder Feedback melden – zwei Wege:\n'
            '1) Direkt hier im Chat: schreib mir einfach „Bug: …“, „Idee: …“ oder „Feedback: …“ – ich trage es für '
            "dich in 'Bugs & Ideen' ein, der Support sieht es dort.\n"
            "2) In der App: Seite 'Feedback & Bugs' (Giveaway Tool, ganz unten in der Seitenleiste) – Art wählen "
            '(Feedback, Bug oder Feature-Wunsch), beschreiben und absenden.\n'
            'Bei Bugs bitte dazuschreiben: Version, was du vorher getan hast, was passiert ist, was du erwartet hast '
            'und die Fehlermeldung.'},
 {'title': 'Support-Chat benutzen',
  'v': 'beide',
  'group': 'allgemein',
  'boost': 1.4,
  'kw': ['support chat benutzen', 'chat mit support', 'support erreichen', 'support schreiben', 'support nachricht'],
  'answer': '🛟 Der Support-Chat steht in jedem Bereich unten in der Seitenleiste. Antworten erscheinen automatisch '
            'im Fenster (kein Neuladen nötig). Nutze ihn für Fragen zur Einrichtung oder wenn etwas nicht '
            'funktioniert. Wenn der Support im Urlaub ist, antworte ich (StreamDex Bot) und gebe an den Support '
            'weiter, wenn ich nicht weiterkomme.'},
 {'title': 'Befehle: Giveaway',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['giveaway befehle', 'giveaway commands', 'alle giveaway befehle'],
  'answer': '🎁 Giveaway-Befehle: !giveaway, !remove, !ticket ✦, !liste ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !giveaway), dann erkläre ich ihn '
            'genau.'},
 {'title': 'Befehle: Interaktion',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['interaktion befehle', 'interaktion commands', 'alle interaktion befehle'],
  'answer': '💬 Interaktion-Befehle: !lurk, !checkin, !event, !clip, !so ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !lurk), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Minigame',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['minigame befehle', 'minigame commands', 'alle minigame befehle'],
  'answer': '🎲 Minigame-Befehle: !slot, !megaslot, !safe, !mine, !raffel ✦, !klau, !race, !hi ✦, !raffle ✦, !gambel '
            '✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !slot), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Angeln',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['angeln befehle', 'angeln commands', 'alle angeln befehle'],
  'answer': '🎣 Angeln-Befehle: !fish, !pull, !reel, !sell, !aquarium, !auftrag ✦, !koeder ✦, !haken ✦, !nachlassen '
            '✦, !praeparieren ✦, !rute, !gewaesser, !ruten, !reise, !buyrute, !upgraderute, !toplevel, !topreich, '
            '!krakenraid\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !fish), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Viewer-Arena',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['viewer-arena befehle', 'viewer-arena commands', 'alle viewer-arena befehle'],
  'answer': '🚶 Viewer-Arena-Befehle: !duell, !akzept, !hug ✦, !fliegen ✦, !love ✦, !skin, !skins, !avcode ✦, !king '
            '✦, !foto ✦, !pet, !mount, !build\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !duell), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Farmen',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['farmen befehle', 'farmen commands', 'alle farmen befehle'],
  'answer': '🌱 Farmen-Befehle: !saeen, !ernten, !farm, !saatgut, !farmverkaufen, !topfarm, !buywerkzeug ✦, '
            '!upgradewerkzeug ✦, !buytraktor ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !saeen), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Währung',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['währung befehle', 'währung commands', 'alle währung befehle'],
  'answer': '💰 Währung-Befehle: !points, !givepoints, !eventpunkte ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !points), dann erkläre ich ihn '
            'genau.'},
 {'title': 'Befehle: Panels',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['panels befehle', 'panels commands', 'alle panels befehle'],
  'answer': '🛡️ Panels-Befehle: !panel ✦, !report ✦, !modpanel ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !panel), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Musik',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['musik befehle', 'musik commands', 'alle musik befehle'],
  'answer': '🎵 Musik-Befehle: !sr ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !sr), dann erkläre ich ihn genau.'},
 {'title': 'Befehle: Minen',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.2,
  'kw': ['minen befehle', 'minen commands', 'alle minen befehle'],
  'answer': '⛏️ Minen-Befehle: !schacht ✦, !sprengen ✦, !rette ✦, !sockel ✦, !schmelzen ✦, !erzkurs ✦\n'
            '(✦ = nur in der BETA V3). Schreib mir einfach einen Befehl (z. B. !schacht), dann erkläre ich ihn '
            'genau.'},
 {'title': 'Alle Befehle (Übersicht)',
  'v': 'beide',
  'group': 'uebersicht',
  'boost': 1.7,
  'kw': ['alle befehle',
         'welche befehle',
         'befehlsliste',
         'befehle liste',
         'liste befehle',
         'chat befehle',
         'commands liste',
         'was kann der bot',
         'was kann der chat',
         'welche commands',
         'befehle$'],
  'answer': '📖 Alle Chat-Befehle von v5.2.6 und BETA V3:\n'
            '🎁 Giveaway: !giveaway !remove !ticket !liste\n'
            '💬 Interaktion: !lurk !checkin !event !clip !so\n'
            '🎲 Minigame: !slot !megaslot !safe !mine !raffel !klau !race !hi !raffle !gambel\n'
            '🎣 Angeln: !fish !pull !reel !sell !aquarium !auftrag !koeder !haken !nachlassen !praeparieren !rute '
            '!gewaesser !ruten !reise !buyrute !upgraderute !toplevel !topreich !krakenraid\n'
            '🚶 Viewer-Arena: !duell !akzept !hug !fliegen !love !skin !skins !avcode !king !foto !pet !mount !build\n'
            '🌱 Farmen: !saeen !ernten !farm !saatgut !farmverkaufen !topfarm !buywerkzeug !upgradewerkzeug '
            '!buytraktor\n'
            '💰 Währung: !points !givepoints !eventpunkte\n'
            '🛡️ Panels: !panel !report !modpanel\n'
            '🎵 Musik: !sr\n'
            '⛏️ Minen: !schacht !sprengen !rette !sockel !schmelzen !erzkurs\n'
            '\n'
            'Schreib mir einen Befehl (z. B. !fish) und ich erkläre ihn genau. Hinweis: Befehle sind änderbar, hier '
            'stehen die Standardnamen. In v5.2.6 gibt es u. a. !mine, !klau, !safe, !slot, !megaslot, !race, !pet, '
            '!mount, !build und das komplette Angeln/Farmen; Befehle wie !koeder, !auftrag, !hi/!low, !sr, !ticket, '
            '!panel, !schacht gibt es erst in der BETA V3.'}]
