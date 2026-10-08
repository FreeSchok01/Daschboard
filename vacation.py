"""Urlaubsmodus + StreamDex Bot (läuft serverseitig im Admin-Dashboard).

So funktioniert es:
  * Ein Hintergrund-Thread (start_vacation_bot) schaut alle paar Sekunden in Firebase nach neuen
    Streamer-Nachrichten (chat_meta.last_sender == "streamer").
  * Ist der Urlaubsmodus an, antwortet der Bot in chats/{twitch_id}/messages (sender = "bot").
    Er schreibt bewusst NICHT in chat_meta -> die Nachricht bleibt für dich "ungelesen" (roter Punkt).

Der Bot ist für Anfänger gebaut:
  * versteht Tippfehler ("overlai", "updaet") und Umgangssprache,
  * zeigt bei unklaren Nachrichten ein Zahlen-Menü (1-9) statt "verstehe ich nicht",
  * erklärt in kurzen Schritten und fragt "Hat das geholfen? ja/nein",
  * bei "nein" / "mit dem Support sprechen" übergibt er an dich (Liste im Panel: bot_escalations),
  * merkt sich pro Streamer das letzte Thema (bot_state/{tid}),
  * kennt ALLE Funktionen/Befehle/Seiten von v5.2.6 und BETA VERSION V3 (Datei bot_wissen.py, daneben legen!)
    und antwortet passend zur Version des Streamers,
  * nimmt Bugs, Ideen (Feature-Wunsch) und allgemeines Feedback an: trägt sie in feedback_inbox ein
    (= Admin → "Bugs & Ideen", gleiches Format wie die App) und antwortet dem Streamer darauf.

Firebase-Knoten:
  support_status    = {vacation, until, text, auto_end, since, updated, by}
  support_faq       = [{on, title, kw, answer}, ...]       (eigene Antworten, Vorrang vor den eingebauten)
  bot_state/{tid}   = {handled_ts, intro_ts, hour_start, n, last_topic, last_topic_ts, menu_ts}
  bot_escalations/{tid} = {name, topic, text, ts}           (vom Bot an dich übergeben)

Eigenständig starten (falls die Streamlit-App schläft):
  DATABASE_URL=https://...firebasedatabase.app SERVICE_ACCOUNT=serviceAccount.json python vacation.py
"""
import hashlib
import importlib.util
import os
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}
BOT_NAME = "StreamDex Bot"
SITE = "https://streamdex.streamlit.app"
RELEASES = "https://github.com/FreeSchok01/Givewaytool/releases/latest"

POLL_ACTIVE_S = 5            # Prüfintervall, solange der Urlaubsmodus an ist
POLL_IDLE_S = 20             # Prüfintervall, solange er aus ist
INTRO_EVERY_S = 12 * 3600    # Begrüßung/Urlaubshinweis höchstens alle 12 h pro Streamer
MENU_VALID_MS = 30 * 60 * 1000      # so lange gilt eine Menü-Zahl als Antwort
TOPIC_VALID_MS = 2 * 3600 * 1000    # so lange gilt "ja/nein" als Antwort auf "Hat das geholfen?"
MAX_REPLIES_PER_HOUR = 10    # Spam-Schutz pro Streamer

FB_MAX_PER_HOUR = 5          # max. Bug/Idee/Feedback-Einträge pro Streamer und Stunde (Spam-Schutz)
INTAKE_VALID_MS = 30 * 60 * 1000    # so lange wartet der Bot auf die Beschreibung eines Bugs/einer Idee
CHUNK = 1700                 # lange Antworten werden in mehrere Nachrichten geteilt
MAX_CHUNKS = 4
MAX_TEXT = CHUNK * MAX_CHUNKS

_CFG = {"games": {}}
_STATE = {"thread": None, "last_run": 0.0, "last_error": "", "replies": 0, "feedback": 0}
_LOCK = threading.Lock()


def _load_wissen():
    """Lädt bot_wissen.py (liegt neben dieser Datei). Fehlt sie, läuft der Bot mit den Grundantworten weiter."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_wissen.py")
        spec = importlib.util.spec_from_file_location("bot_wissen", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return list(mod.WISSEN), getattr(mod, "WISSEN_STAND", "")
    except Exception as ex:
        print("StreamDex Bot: bot_wissen.py nicht geladen:", ex)
        return [], ""


WISSEN, WISSEN_STAND = _load_wissen()


class _Skip(Exception):
    pass


# ----------------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------------
def _now_ms():
    return int(time.time() * 1000)


def _norm(s):
    s = (s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)          # "hilfeeee" -> "hilfee"
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _dict(v):
    return v if isinstance(v, dict) else {}


def _parse_until(s):
    """'20.10.2026' / '20.10.' / '20.10.26' -> date oder None."""
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.?\s*(\d{2,4})?", s or "")
    if not m:
        return None
    today = datetime.now(TZ).date()
    d, mo = int(m.group(1)), int(m.group(2))
    y = int(m.group(3)) if m.group(3) else today.year
    if y < 100:
        y += 2000
    try:
        res = date(y, mo, d)
    except ValueError:
        return None
    if not m.group(3) and res < today - timedelta(days=180):
        try:
            res = date(y + 1, mo, d)
        except ValueError:
            return None
    return res


def _active(cfg):
    """Urlaubsmodus an? Endet automatisch am Rückkehr-Datum (00:00), wenn 'auto_end' an ist."""
    if cfg.get("vacation") is not True:
        return False
    if cfg.get("auto_end", True):
        back = _parse_until(str(cfg.get("until") or ""))
        if back and datetime.now(TZ).date() >= back:
            return False
    return True


def _until_txt(cfg):
    return str(cfg.get("until") or "").strip()


def _when(cfg):
    u = _until_txt(cfg)
    return f"ab dem {u}" if u else "sobald er zurück ist"


def _fill(text, ctx, cfg):
    return (str(text).replace("{name}", ctx.get("name") or "")
            .replace("{zurueck}", _when(cfg)).replace("{seite}", SITE).replace("{releases}", RELEASES))


# ----------------------------------------------------------------------------
# Live-Kontext + dynamische Antworten
# ----------------------------------------------------------------------------
def _ctx(tid):
    if not tid:
        return {"tid": None, "name": "", "version": None, "ban": None}
    pres = _dict(db.reference(f"presence/{tid}").get())
    ban = db.reference(f"bans/twitch/{tid}").get()
    return {"tid": tid, "name": pres.get("twitch_username") or "", "version": pres.get("app_version"),
            "ban": ban if isinstance(ban, dict) else None}


def _ver_key(v):
    """'BETA VERSION V3' -> 'beta', 'v5.2.6' -> 'v526', sonst None."""
    v = str(v or "").lower()
    if "beta" in v:
        return "beta"
    if re.search(r"5\.2\.6", v):
        return "v526"
    return None


def _a_version(ctx, cfg):
    v = ctx.get("version")
    if not v:
        return ("ℹ️ Ich sehe deine Version gerade nicht. Im Tool oben steht ein Badge, z. B. „v5.2.6“ oder „BETA "
                "VERSION V3“. Neueste Version: {releases}")
    k = _ver_key(v)
    extra = {"beta": " Du hast die neueste Funktionsstufe (inkl. Mod-Panel, Songrequest, Minen 2.0, Angel v2 …).",
             "v526": " Die BETA VERSION V3 hat zusätzlich u. a. Mod-/Zuschauer-Panel, Songrequest, Hi-Lo, Automationen, "
                     "Minen 2.0, Angel v2 – tippe „was ist neu“."}.get(k, "")
    return f"ℹ️ Du nutzt: {v}.{extra}\nDownload: {{releases}}"


def _render_wissen(e, ctx):
    ver = _ver_key(ctx.get("version"))
    a = e["answer"]
    if ver == "v526" and e.get("answer_v526"):
        a = e["answer_v526"]
    if e.get("v") == "beta":
        if ver == "v526":
            a = "ℹ️ Das gibt es erst in der BETA VERSION V3 – deine Version (v5.2.6) hat es noch nicht.\n" + a
        elif ver is None and "nur BETA" not in a and "BETA V3" not in a[:80]:
            a += "\n(Nur in der BETA VERSION V3.)"
    return a


def _a_games(ctx, cfg):
    if not ctx["tid"]:
        return "🎮 Hier zeige ich dir live, welche Spiele für dich frei sind. (Testmodus: ohne echte Streamer-Daten)"
    g = _dict(db.reference("game_flags/global").get())
    own = _dict(db.reference(f"game_flags/streamers/{ctx['tid']}").get())
    labels = _CFG["games"] or {}
    keys = list(labels) or sorted(set(g) | set(own))
    on, off = [], []
    for k in keys:
        v = own[k] if isinstance(own.get(k), bool) else bool(g.get(k, False))
        (on if v else off).append(labels.get(k, k))
    lines = ["🎮 Deine Spiele-Freigaben:", "✅ frei: " + (", ".join(on) or "noch keins")]
    if off:
        lines.append("⛔ gesperrt: " + ", ".join(off))
    lines.append("Spiele sind am Anfang immer gesperrt und werden vom Support von Hand freigeschaltet. "
                 "Schreib mir einfach, welches Spiel du brauchst – ich gebe es an den Support weiter.")
    return "\n".join(lines)


_A_BINDING = ("🔐 Dein Login ist an ein Gerät gebunden (Schutz vor Missbrauch). Bei neuem PC, Neuinstallation oder "
              "der Meldung „an ein anderes Gerät gebunden“ muss der Support das zurücksetzen – das kann ich aus "
              "Sicherheitsgründen nicht selbst.\n"
              "So geht’s: Schreib mir hier kurz deinen Twitch-Namen und „neuer PC“. Der Support erledigt es {zurueck}.")


def _a_ban(ctx, cfg):
    if ctx.get("ban"):
        reason = ctx["ban"].get("reason") or "Kein Grund angegeben."
        return ("🚫 Dein Konto ist aktuell ausgeschlossen. Grund: " + str(reason) +
                "\nDas kann nur der Support persönlich prüfen – deine Nachricht ist gespeichert.")
    if ctx["tid"]:
        return ("✅ Bei dir ist keine Sperre eingetragen. Wenn das Tool „Kein Zugriff“ meldet, liegt es meistens "
                "an der Geräte-Bindung:\n" + _A_BINDING)
    return "Ich prüfe hier live, ob bei dir eine Sperre eingetragen ist. (Testmodus)"


def _a_update(ctx, cfg):
    s = ""
    if ctx.get("version"):
        s += f"Deine installierte Version: {ctx['version']}.\n"
    return s + ("🔄 So aktualisierst du:\n1) Neueste Version laden: {releases}\n2) Tool schließen\n"
                "3) Die neue Version starten (die alte ersetzen)")


# ----------------------------------------------------------------------------
# FAQ. kw = Stichwörter (Wortanfang, "$" am Ende = ganzes Wort). weak = nur wenn nichts anderes passt.
# ask = nach der Antwort "Hat das geholfen?" fragen.
# ----------------------------------------------------------------------------
DEFAULT_FAQ = [
    {"title": "Spiele-Freigaben", "answer": _a_games,
     "kw": ["spiele sehen", "welche spiele", "meine spiele", "freigab", "freigeschaltet", "freischalt"]},
    {"title": "Sperre / Ausschluss", "answer": _a_ban,
     "kw": ["ban$", "bann", "gebannt", "ausgeschlossen", "ausschliess", "konto gesperrt", "account gesperrt",
            "ich bin gesperrt", "sperre", "blockiert"]},
    {"title": "Geräte-Bindung", "answer": _A_BINDING,
     "kw": ["gebunden", "bindung", "anderes geraet", "neues geraet", "neuer pc", "neuen pc", "pc gewechselt",
            "kein zugriff", "kennung", "neu installiert", "neuinstall", "windows neu", "laptop"]},
    {"title": "Twitch-Login / Token", "ask": True,
     "answer": ("🔑 Login-Probleme lösen sich meistens so:\n1) Im Tool bei Twitch neu anmelden / verbinden\n"
                "2) Alle Berechtigungen auf der Twitch-Seite bestätigen\n"
                "3) Im Reiter „StreamDex“ zeigt der Token-Wächter, ob dein Login wieder gültig ist"),
     "kw": ["login", "anmeld", "einlogg", "token", "twitch verbinden", "neu verbinden", "authent", "abgelaufen",
            "scope", "berechtigung", "ausgeloggt", "passwort"]},
    {"title": "Updates / Version", "answer": _a_update, "ask": True,
     "kw": ["update", "aktualisier", "neue version", "download", "installer", "herunterladen", "exe$",
            "runterladen"]},
    {"title": "OBS / Overlays", "ask": True,
     "answer": ("🎬 Wenn ein Overlay nichts anzeigt:\n1) Ist das Tool gestartet? (Overlays laufen über dein Tool)\n"
                "2) Stimmt die Overlay-URL (http://localhost:8765/…)? Am besten im Tool neu kopieren\n"
                "3) In OBS: Rechtsklick auf die Quelle → „Cache der aktuellen Seite leeren“ bzw. neu laden"),
     "kw": ["overlay", "obs", "browserquelle", "browser quelle", "browser source", "localhost", "8765",
            "subathon", "streams24", "stempeluhr", "alert", "schwarz", "leer"]},
    {"title": "Beta",
     "answer": "🧪 Beta-Zugang beantragst du hier: {seite}/?beta=1 – der Support prüft Bewerbungen nach dem Urlaub.",
     "kw": ["beta zugang", "beta bewerb", "beta tester", "beta beantragen", "bewerb", "tester"]},
    {"title": "Meine Version", "answer": _a_version,
     "kw": ["welche version", "meine version", "version habe ich", "welche version nutze", "versionsnummer"]},
    {"title": "Dashboard",
     "answer": "📊 Dein Streamer-Dashboard: {seite}/?dashboard=1",
     "kw": ["dashboard", "statistik", "stats$"]},
    {"title": "Shop / Gutscheine",
     "answer": "🛒 Shop & Gutschein-Codes: {seite} – Codes gibst du dort beim Kauf ein.",
     "kw": ["shop", "kaufen", "gutschein", "coupon", "partner code", "partnercode", "preis", "bezahl", "kosten",
            "premium"]},
    {"title": "Erste Schritte",
     "answer": ("🚀 So startest du:\n1) Tool herunterladen: {releases}\n2) Tool starten und bei Twitch anmelden\n"
                "3) In OBS eine Browser-Quelle mit der Overlay-URL aus dem Tool anlegen\n"
                "Wenn es bei einem Schritt hakt, schreib mir die Nummer (z. B. „Schritt 2 geht nicht“)."),
     "kw": ["erste schritte", "anfang", "anleitung", "wie starte", "wie fange", "einrichten", "einrichtung",
            "installier", "tutorial", "komme nicht klar", "neu hier", "anfaenger"]},
    {"title": "Bug / Fehler",
     "answer": ("🐞 Danke für die Meldung! Damit der Support es schnell nachstellen kann, schreib mir bitte:\n"
                "1) deine Version\n2) was genau passiert ist\n3) was du erwartet hast\n4) die Fehlermeldung (abtippen)\n"
                "Alles bleibt für den Support gespeichert."),
     "kw": []},
    {"title": "Wann kommt Antwort?",
     "answer": "⏳ Der Support ist im Urlaub und antwortet {zurueck}. Deine Nachricht ist gespeichert.",
     "kw": ["wann", "urlaub", "erreichbar", "dauert", "antwort", "zurueck", "wie lange"]},
    {"title": "Bist du ein Bot?",
     "answer": ("🤖 Ich bin der StreamDex Bot – ein automatischer Helfer, kein Mensch. Der echte Support liest alles, "
                "sobald er zurück ist. Tippe MENÜ, dann zeige ich dir meine Themen."),
     "kw": ["bist du ein bot", "bist du echt", "bot oder mensch", "wer bist du", "ki$", "echter mensch"]},
    {"title": "Dringend", "weak": True,
     "answer": "⚠️ Verstanden, dass es dringend ist. Die Nachricht bleibt beim Support als ungelesen markiert.",
     "kw": ["dringend", "notfall", "eilt", "sofort", "wichtig"]},
    {"title": "Danke", "weak": True,
     "answer": "Gern geschehen! 😊 Wenn noch etwas ist, schreib einfach.",
     "kw": ["danke", "dankeschoen", "thx", "merci"]},
    {"title": "Begrüßung", "weak": True, "answer": "",
     "kw": ["hallo", "hi$", "hey", "moin", "servus", "guten tag", "guten morgen", "guten abend"]},
]
_WISSEN_FAQ = [dict(w, wissen=True) for w in WISSEN]
_BY_TITLE = {e["title"]: e for e in DEFAULT_FAQ + _WISSEN_FAQ}

# Menü: (Label, [Titel der FAQ-Einträge]). Zahl N+1 = "Mit dem Support sprechen".
# Menü: (Label, [Titel], Aktion). Aktion: None | "bug" | "idee" | "feedback". Zahl N+1 = "Mit dem Support sprechen".
MENU = [
    ("🎮 Spiele sehen / freischalten", ["Spiele-Freigaben"], None),
    ("🔑 Twitch-Login klappt nicht", ["Twitch-Login / Token"], None),
    ("🎬 OBS / Overlay zeigt nichts", ["OBS / Overlays"], None),
    ("🔄 Update / Version", ["Updates / Version", "Meine Version"], None),
    ("🐞 Bug / Fehler melden", [], "bug"),
    ("💻 Neuer PC / „Kein Zugriff“", ["Geräte-Bindung"], None),
    ("🧪 Beta, Dashboard oder Shop", ["Beta", "Dashboard", "Shop / Gutscheine"], None),
    ("🚀 Erste Schritte / Anleitung", ["In 4 Schritten startklar"], None),
    ("📖 Befehle & Funktionen erklärt", ["Alle Befehle (Übersicht)"], None),
    ("🆕 BETA V3 – was ist neu?", ["Was ist neu in der BETA V3? (Unterschiede zu v5.2.6)"], None),
    ("💡 Idee / Feature-Wunsch einreichen", [], "idee"),
    ("💬 Feedback geben", [], "feedback"),
]

YES_W = {"ja", "jo", "jap", "jup", "klar", "geholfen", "klappt", "funktioniert", "laeuft", "top", "super",
         "perfekt", "passt", "danke", "geloest", "erledigt", "geschafft", "ok", "okay"}
NO_W = {"nein", "nee", "nö", "noe", "nope", "ne"}
NO_P = ["geht nicht", "klappt nicht", "hilft nicht", "immer noch", "immernoch", "weiterhin", "nicht geholfen",
        "funktioniert nicht", "nicht gelost", "nicht geloest", "leider nicht", "bringt nichts"]
MENU_W = {"menue", "menu", "hilfe", "help", "start", "uebersicht", "optionen", "themen", "hilf"}
HUMAN_P = ["mit dem support", "support sprechen", "mit einem menschen", "echte person", "echten menschen",
           "mit dir sprechen", "admin sprechen", "mit dem admin", "mit jemandem sprechen", "persoenlich",
           "mit dem chef", "mit dem streamer", "mensch bitte"]
CONFUSED_P = ["verstehe nicht", "versteh nicht", "verstehe das nicht", "versteh das nicht", "keine ahnung",
              "weiss nicht", "weiss ich nicht", "erklaer", "einfacher", "haeh", "wie meinst", "kapier", "blick nicht",
              "durchblick", "ich check", "was soll ich"]


# ----------------------------------------------------------------------------
# Erkennung (Tippfehler-tolerant)
# ----------------------------------------------------------------------------
def _osa(a, b):
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


_REAL_WORDS = {"fehlen", "fehlt"}     # echte Wörter, die sonst als Tippfehler von "fehler" gelten würden


def _fuzzy(k2, toks):
    """Tippfehler-Treffer: Wort ähnelt dem Stichwort (nur Stichwörter ab 6 Buchstaben, 1-2 Fehler)."""
    if " " in k2 or len(k2) < 6:
        return False
    lim = 1 if len(k2) < 9 else 2
    for w in toks:
        if len(w) < 5 or w in _REAL_WORDS or abs(len(w) - len(k2)) > 3:
            continue
        if min(_osa(k2, w), _osa(k2, w[:len(k2)])) <= lim:
            return True
    return False


def _custom_raw():
    raw = db.reference("support_faq").get()
    if isinstance(raw, dict):
        raw = list(raw.values())
    return [x for x in (raw or []) if isinstance(x, dict)]


def _faq():
    items = []
    for it in _custom_raw():
        if it.get("on", True) is False or not it.get("answer") or not it.get("kw"):
            continue
        kws = [k.strip() for k in str(it["kw"]).split(",") if k.strip()]
        items.append({"title": it.get("title") or "Eigene Antwort", "answer": str(it["answer"]),
                      "kw": kws, "custom": True})
    return items + DEFAULT_FAQ + _WISSEN_FAQ


def _score(entry, t, raw=""):
    s = 0.0
    toks = t.split()
    for k in entry["kw"]:
        if k.startswith("!"):      # genau dieser Chat-Befehl (z. B. "!fish")
            if re.search(r"(?<![a-z0-9_!])" + re.escape(k.lower()) + r"(?![a-z0-9_])", raw):
                s += 3.0
            continue
        exact = k.endswith("$")
        k2 = _norm(k.rstrip("$"))
        if not k2:
            continue
        pat = r"(?<![a-z0-9])" + re.escape(k2) + (r"(?![a-z0-9])" if exact else "")
        if re.search(pat, t):
            s += 1 + len(k2) / 12
        elif not exact and _fuzzy(k2, toks):
            s += 0.8 * (1 + len(k2) / 12)
    return s * (1.5 if entry.get("custom") else 1) * float(entry.get("boost", 1))


def pick_answers(text, faq):
    t = _norm(text)
    raw = (text or "").lower()
    scored = sorted(((_score(e, t, raw), i, e) for i, e in enumerate(faq)), key=lambda x: (-x[0], x[1]))
    strong = [(s, e) for s, _, e in scored if s > 0 and not e.get("weak")]
    if strong:
        top = strong[0][0]
        return [e for s, e in strong[:2] if s >= top * 0.6], False, top
    weak = [e for s, _, e in scored if s > 0]
    return weak[:1], True, 0.0


# ----------------------------------------------------------------------------
# Antwort zusammenbauen
# ----------------------------------------------------------------------------
def _intro(ctx, cfg):
    name = ctx.get("name") or ""
    u = _until_txt(cfg)
    s = (f"🏖️ Hi{' ' + name if name else ''}! Ich bin der StreamDex Bot. Der Support ist gerade im Urlaub"
         + (f" und ab dem {u} wieder da" if u else "") + ". Ich helfe dir trotzdem gern – und deine Nachricht bleibt "
         "für den Support gespeichert. Tippe jederzeit MENÜ für eine Übersicht.")
    if cfg.get("text"):
        s += "\n" + str(cfg["text"])
    return s


def _menu_text(first="Wobei brauchst du Hilfe? Antworte einfach mit einer Zahl:"):
    lines = [first]
    for i, (label, _t, _a) in enumerate(MENU, 1):
        lines.append(f"{i}) {label}")
    lines.append(f"{len(MENU) + 1}) 👤 Mit dem Support sprechen")
    return "\n".join(lines)


def _render(e, ctx, cfg):
    a = _render_wissen(e, ctx) if e.get("wissen") else e["answer"]
    a = a(ctx, cfg) if callable(a) else a
    if not a:
        return ""
    a = _fill(a, ctx, cfg)
    if e.get("ask"):
        a += "\n\nHat das geholfen? Antworte mit ja oder nein."
    return a


def _handoff(cfg):
    return ("👤 Alles klar, ich habe deine Nachricht für den Support markiert. Er ist im Urlaub und meldet sich "
            + _when(cfg) + ". Schreib am besten gleich dazu, worum es geht (Version, was passiert, Fehlermeldung) – "
            "dann kann er sofort loslegen.")


# ----------------------------------------------------------------------------
# Bug / Idee / Feedback erkennen
# ----------------------------------------------------------------------------
BUG_STRONG = ["bug", "bugs", "buggy", "verbuggt", "fehler", "absturz", "abgestuerzt", "stuerzt", "crash", "error",
              "exception", "traceback", "kaputt", "freezt", "eingefroren"]
BUG_SOFT = ["funktioniert nicht", "geht nicht", "klappt nicht", "laeuft nicht", "reagiert nicht", "haengt", "friert",
            "problem", "passiert nichts", "nichts passiert", "geht nicht mehr", "funktioniert nicht mehr"]
IDEA_W = ["idee", "ideen", "vorschlag", "vorschlaege", "wunsch", "wuensch", "einbauen", "hinzufuegen", "verbesserung",
          "waere cool", "waere super", "waere toll", "waere gut", "waere schoen", "wuerde mir wuenschen",
          "wuerde gern", "wuerde gerne", "koennt ihr", "koenntet ihr", "koennte man", "bitte einbauen"]
IDEA_STRICT = ["idee", "ideen", "vorschlag", "vorschlaege", "wunsch", "wuensch"]
FEEDBACK_W = ["feedback", "rueckmeldung", "kritik", "lob$", "bewertung", "rezension"]
POS_W = ["super", "toll", "klasse", "cool", "gefaellt", "genial", "perfekt", "liebe", "top$", "gut$", "begeistert",
         "zufrieden", "mega", "beste", "hilfreich"]
NEG_W = ["schlecht", "nervt", "bloed", "unzufrieden", "enttaeuscht", "kompliziert", "verwirrend", "langsam",
         "umstaendlich", "mies", "furchtbar", "schrecklich", "frust", "aergerlich"]
APP_W = ["app", "tool", "streamdex", "programm", "software", "bot$", "overlay", "update"]
CANCEL_W = {"abbrechen", "abbruch", "stop", "stopp", "egal", "cancel", "vergiss"}
Q_START = {"wie", "was", "welche", "welcher", "welches", "wo", "wohin", "wann", "warum", "wieso", "weshalb", "kann",
           "kannst", "koennt", "gibt", "ist", "sind", "hat", "habt", "darf", "muss", "wer"}
KIND_OF = {"bug": "Bug", "idee": "Feature-Wunsch", "feedback": "Feedback"}


def _has(t, words):
    for w in words:
        w2 = _norm(w.rstrip("$"))
        pat = r"(?<![a-z0-9])" + re.escape(w2) + (r"(?![a-z0-9])" if w.endswith("$") else "")
        if re.search(pat, t):
            return True
    return False


def _classify(text):
    """-> 'Bug' | 'Feature-Wunsch' | 'Feedback' | None (nur eindeutige Fälle; Fragen bleiben Fragen)."""
    t = _norm(text)
    toks = t.split()
    if not toks:
        return None
    raw = (text or "").lower()
    is_q = "?" in raw or toks[0] in Q_START
    if re.search(r"\b(wie|wo|wohin|kann ich|kann man|darf ich)\b.*\b(melde|melden|einreichen|abgeben|schicken|senden)\b", t):
        return None
    if _has(t, BUG_STRONG):
        return "Bug"
    if _has(t, IDEA_W) and (not is_q or _has(t, IDEA_STRICT)):
        return "Feature-Wunsch"
    if _has(t, FEEDBACK_W) and not (is_q and len(toks) <= 4):
        return "Feedback"
    if (_has(t, POS_W) or _has(t, NEG_W)) and _has(t, APP_W) and len(toks) >= 4 and not is_q:
        return "Feedback"
    return None


def _intake_prompt(kind):
    if kind == "bug":
        return ("🐞 Gern! Beschreibe mir den Bug am besten in EINER Nachricht:\n1) Welche Version nutzt du?\n"
                "2) Was hast du vorher getan?\n3) Was ist passiert – und was hast du erwartet?\n"
                "4) Fehlermeldung (abtippen), falls vorhanden.\nIch trage ihn dann in „Bugs & Ideen“ ein. "
                "(Zum Abbrechen: „abbrechen“)")
    if kind == "idee":
        return ("💡 Sehr gern! Schreib mir deine Idee / deinen Feature-Wunsch – je genauer, desto besser: "
                "Was soll passieren, und wo in der App? Ich trage sie dann in „Bugs & Ideen“ ein. "
                "(Zum Abbrechen: „abbrechen“)")
    return ("💬 Sehr gern! Schreib mir dein Feedback (Lob, Kritik, was dich nervt oder was gut läuft). Ich trage es "
            "in „Bugs & Ideen“ ein und der Support liest es. (Zum Abbrechen: „abbrechen“)")


def _fb_confirm(kind, body, ctx, cfg, help_text):
    test = "" if ctx.get("tid") else "\n(Testmodus: es wird nichts gespeichert.)"
    when = _when(cfg)
    if kind == "Bug":
        v = ctx.get("version")
        s = ("🐞 Danke für die Meldung! Ich habe deinen Bug in „Bugs & Ideen“ eingetragen – der Support sieht ihn dort "
             f"und kümmert sich {when} darum.")
        s += (f"\nErfasste Version: {v}." if v else
              "\nWelche Version nutzt du? (steht oben im Tool) – schreib sie mir gern dazu, dann kann der Support "
              "schneller helfen.")
        if help_text:
            s += "\n\n💡 Vielleicht hilft dir das schon weiter:\n" + help_text
        s += "\n\nFallen dir noch Details ein (Schritte, Fehlermeldung)? Schreib sie einfach hier dazu – sie bleiben im Chat für den Support gespeichert."
    elif kind == "Feature-Wunsch":
        s = ("💡 Danke für deine Idee! Ich habe sie als Feature-Wunsch in „Bugs & Ideen“ eingetragen – der Support "
             "liest sie dort und bewertet sie.")
        if help_text:
            s += "\n\nÜbrigens, etwas Ähnliches gibt es vielleicht schon:\n" + help_text
        s += "\n\nWenn du magst, beschreibe gern noch genauer, wie du dir das vorstellst."
    else:
        t = _norm(body)
        if _has(t, NEG_W):
            s = ("🙏 Danke für dein ehrliches Feedback – das tut uns leid zu hören. Ich habe es in „Bugs & Ideen“ "
                 f"eingetragen, der Support liest es und meldet sich {when}.")
        elif _has(t, POS_W):
            s = ("🙏 Danke für dein Feedback – das freut uns riesig! Ich habe es in „Bugs & Ideen“ eingetragen, der "
                 "Support liest es dort.")
        else:
            s = "🙏 Danke für dein Feedback! Ich habe es in „Bugs & Ideen“ eingetragen, der Support liest es dort."
    return s + test


def compose(ctx, text, cfg, intro, state=None, faq=None):
    """Baut die Bot-Antwort. Rückgabe: {text, topic, menu, escalate, clear, feedback, intake, intake_clear, head}."""
    state = state or {}
    faq = faq or _faq()
    now = _now_ms()
    t = _norm(text)
    toks = t.split()
    head = [_intro(ctx, cfg)] if intro else []
    out = {"topic": None, "menu": False, "escalate": None, "clear": False, "feedback": None,
           "intake": None, "intake_clear": False, "head": list(head)}

    def done(*parts):
        out["text"] = "\n\n".join(head + [p for p in parts if p])[:MAX_TEXT]
        return out

    def safe(e):
        try:
            return _render(e, ctx, cfg)
        except Exception as ex:   # eine kaputte Antwort darf den Bot nicht stoppen
            print("Bot-Antwort fehlgeschlagen:", e.get("title"), ex)
            return ""

    def log_fb(kind, body, help_entries=()):
        out["feedback"] = (kind, str(body).strip())
        out["intake_clear"] = True
        h = "\n\n".join(p for p in (safe(e) for e in help_entries[:1]) if p)
        return done(_fb_confirm(kind, body, ctx, cfg, h))

    answers, weak_only, top = pick_answers(text, faq)
    has_strong = bool(answers) and not weak_only
    help_ok = has_strong and top >= 2.5

    # 0) Bot wartet auf die Beschreibung eines Bugs / einer Idee / von Feedback
    pending = state.get("intake")
    if pending in KIND_OF and now - int(state.get("intake_ts") or 0) < INTAKE_VALID_MS:
        if any(w in CANCEL_W for w in toks) and len(toks) <= 5:
            out["intake_clear"] = True
            return done("Alles klar, ich habe nichts gespeichert. 👍 Tippe MENÜ, wenn du etwas anderes brauchst.")
        if not (len(toks) <= 3 and any(w in MENU_W for w in toks)):
            if len(toks) < 3 or len(t) < 12:
                out["intake"] = pending
                return done("Magst du das etwas genauer beschreiben? Ein bis zwei Sätze reichen. (Zum Abbrechen: „abbrechen“)")
            return log_fb(KIND_OF[pending], text, answers if help_ok else ())

    # 1) Zahl aus dem Menü
    if state.get("menu_ts") and now - int(state["menu_ts"]) < MENU_VALID_MS:
        m = re.fullmatch(r"(?:nummer |nr |punkt |option |zahl )?(\d{1,2})", t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= len(MENU):
                _label, titles, act = MENU[n - 1]
                if act:
                    out["intake"] = act
                    return done(_intake_prompt(act))
                parts = [safe(_BY_TITLE[x]) for x in titles if x in _BY_TITLE]
                first = _BY_TITLE.get(titles[0]) if titles else None
                out["topic"] = first["title"] if first and first.get("ask") else None
                return done(*parts)
            if n == len(MENU) + 1:
                out["escalate"] = "Will mit dem Support sprechen"
                return done(_handoff(cfg))

    # 2) ja / nein auf "Hat das geholfen?"
    lt = state.get("last_topic")
    if lt and now - int(state.get("last_topic_ts") or 0) < TOPIC_VALID_MS and len(toks) <= 8:
        neg = any(w in NO_W for w in toks) or any(p in t for p in NO_P)
        pos = any(w in YES_W for w in toks)
        if neg:
            out["escalate"] = f"Hat nicht geholfen: {lt}"
            out["clear"] = True
            return done("Schade, dann übergebe ich an den Support. 🙏 Ich habe „" + lt + "“ für ihn markiert, er "
                        "meldet sich " + _when(cfg) + ".\nHilfreich wäre noch: deine Version und die genaue "
                        "Fehlermeldung – schreib sie einfach hier rein. (Oder tippe „Bug“, dann trage ich es in "
                        "„Bugs & Ideen“ ein.)")
        if pos:
            out["clear"] = True
            return done("Super, freut mich! 🎉 Wenn noch etwas ist, schreib einfach – oder tippe MENÜ.")

    # 3) Befehle: Menü / Mensch / "verstehe nicht" (ein klares Thema in der Nachricht hat Vorrang)
    if not has_strong and ((len(toks) <= 3 and any(w in MENU_W for w in toks)) or t == ""):
        out["menu"] = True
        return done(_menu_text())
    if len(toks) <= 8 and any(p in t for p in HUMAN_P):
        out["escalate"] = "Will mit dem Support sprechen"
        return done(_handoff(cfg))
    if not has_strong and len(toks) <= 10 and any(p in t for p in CONFUSED_P):
        out["menu"] = True
        return done("Kein Problem, wir machen es ganz einfach! 😊",
                    _menu_text("Such dir ein Thema aus – antworte nur mit der Zahl:"))

    # 3b) Bug / Idee / Feedback
    kind = _classify(text)
    if kind:
        need = 4 if kind == "Feedback" else 6
        if len(toks) >= need:
            return log_fb(kind, text, answers if help_ok else ())
        act = {"Bug": "bug", "Feature-Wunsch": "idee", "Feedback": "feedback"}[kind]
        out["intake"] = act
        return done(_intake_prompt(act))

    # 4) FAQ / Wissensbasis
    if answers and weak_only and answers[0]["title"] == "Begrüßung":
        out["menu"] = True
        return done(_menu_text("Schön, dass du da bist! 👋 Wobei kann ich helfen? Antworte einfach mit einer Zahl:"))
    parts = [p for p in (safe(e) for e in answers) if p]
    if parts:
        first = answers[0]
        out["topic"] = first["title"] if first.get("ask") else None
        return done(*parts)

    # 4b) weiche Fehler-Hinweise ("geht nicht") ohne passendes Thema -> als Bug aufnehmen
    if _has(t, BUG_SOFT) and len(toks) >= 6:
        return log_fb("Bug", text)

    # 5) nichts erkannt -> Menü statt "verstehe ich nicht"
    out["menu"] = True
    return done("Das habe ich leider nicht ganz verstanden 🙈 – kein Problem! Deine Nachricht ist für den Support "
                "gespeichert (er meldet sich " + _when(cfg) + "). Tipp: Schreib mir einen Befehl wie !fish oder ein "
                "Thema wie „Overlay“.", _menu_text("Wobei kann ich dir sonst helfen? Antworte mit einer Zahl:"))

def build_reply(ctx, text, cfg, intro, faq=None, state=None):
    """Nur der Antworttext (für den Test im Panel)."""
    return compose(ctx, text, cfg, intro, state, faq)["text"]


# ----------------------------------------------------------------------------
# Worker
# ----------------------------------------------------------------------------
def _claim(tid, last_ts):
    """Atomar 'ich beantworte bis last_ts' eintragen -> kein Doppel-Antworten (auch bei mehreren Instanzen)."""
    def upd(cur):
        if isinstance(cur, (int, float)) and cur >= last_ts:
            raise _Skip()
        return last_ts
    try:
        db.reference(f"bot_state/{tid}/handled_ts").transaction(upd)
        return True
    except Exception:
        return False


def _chunks(text):
    """Teilt lange Antworten an Absatzgrenzen in Nachrichten à höchstens CHUNK Zeichen."""
    out, cur = [], ""
    for para in str(text).split("\n\n"):
        while len(para) > CHUNK:
            cut = para.rfind("\n", 0, CHUNK)
            cut = cut if cut > 200 else CHUNK
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:cut])
            para = para[cut:].lstrip("\n")
        if cur and len(cur) + len(para) + 2 > CHUNK:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return [c for c in out if c.strip()][:MAX_CHUNKS]


def _log_feedback(tid, ctx, kind, body, state, now):
    """Trägt Bug/Feature-Wunsch/Feedback in feedback_inbox ein (gleiches Format wie die App -> Admin 'Bugs & Ideen').
    Rückgabe: ('ok'|'dup'|'limit', state-update)."""
    h = hashlib.sha1((str(tid) + _norm(body)).encode("utf-8")).hexdigest()[:16]
    if state.get("fb_last_hash") == h and now - int(state.get("fb_last_ts") or 0) < 24 * 3600 * 1000:
        return "dup", {}
    hs, n = int(state.get("fb_hour_start") or 0), int(state.get("fb_n") or 0)
    if now - hs > 3600 * 1000:
        hs, n = now, 0
    if n >= FB_MAX_PER_HOUR:
        return "limit", {}
    txt = ("🤖 [über StreamDex Bot gemeldet] " + body.strip())[:1800]
    db.reference("feedback_inbox").push({
        "kind": kind, "text": txt, "streamer": str(ctx.get("name") or tid), "tid": str(tid),
        "version": str(ctx.get("version") or "unbekannt"), "status": "neu", "ts": SERVER_TS})
    _STATE["feedback"] += 1
    return "ok", {"fb_hour_start": hs, "fb_n": n + 1, "fb_last_hash": h, "fb_last_ts": now}


def _reply_to(tid, last_ts, handled, since, state, cfg):
    msgs = _dict(db.reference(f"chats/{tid}/messages").order_by_child("ts").limit_to_last(15).get())
    msgs = sorted((m for m in msgs.values() if isinstance(m, dict)), key=lambda m: int(m.get("ts") or 0))
    floor = max(handled, since)
    new = [m for m in msgs if m.get("sender") == "streamer" and int(m.get("ts") or 0) > floor]
    if not new:
        return
    # hat der Support (Mensch) inzwischen selbst geantwortet? Dann hält sich der Bot raus.
    if any(m.get("sender") == "admin" and int(m.get("ts") or 0) >= int(new[-1].get("ts") or 0) for m in msgs):
        return
    now = _now_ms()
    hour_start, n = int(state.get("hour_start") or 0), int(state.get("n") or 0)
    if now - hour_start > 3600 * 1000:
        hour_start, n = now, 0
    if n >= MAX_REPLIES_PER_HOUR:
        return
    intro = now - int(state.get("intro_ts") or 0) > INTRO_EVERY_S * 1000
    text = " ".join(str(m.get("text") or "") for m in new)
    ctx = _ctx(tid)
    res = compose(ctx, text, cfg, intro, state)
    fbupd = {}
    if res.get("feedback"):
        kind, body = res["feedback"]
        try:
            st, fbupd = _log_feedback(tid, ctx, kind, body, state, now)
        except Exception as ex:
            st = "error"
            _STATE["last_error"] = f"{tid}: Feedback-Eintrag: {type(ex).__name__}: {ex}"
            print("Feedback-Eintrag fehlgeschlagen:", tid, ex)
        if st != "ok":
            msg = {"dup": "ℹ️ Das habe ich vorhin schon so von dir eingetragen – doppelt brauche ich es nicht. 👍",
                   "limit": "⏸️ Du hast in der letzten Stunde schon mehrere Meldungen geschickt, mein Limit ist erreicht. "
                            "Deine Nachricht bleibt trotzdem hier im Chat für den Support gespeichert (er meldet sich "
                            + _when(cfg) + ").",
                   "error": "⚠️ Ich konnte deine Meldung gerade nicht in „Bugs & Ideen“ eintragen. Sie bleibt hier im "
                            "Chat für den Support gespeichert (er meldet sich " + _when(cfg) + ")."}[st]
            res["text"] = "\n\n".join(res.get("head", []) + [msg])
            if st != "dup":
                res["escalate"] = f"{kind} konnte nicht eingetragen werden ({st})"
    for part in _chunks(res["text"]):
        db.reference(f"chats/{tid}/messages").push({"sender": "bot", "name": BOT_NAME, "text": part, "ts": SERVER_TS})
    upd = {"hour_start": hour_start, "n": n + 1, "menu_ts": now if res["menu"] else 0}
    upd.update(fbupd)
    if intro:
        upd["intro_ts"] = now
    if res["topic"]:
        upd["last_topic"], upd["last_topic_ts"] = res["topic"], now
    elif res["clear"] or res["escalate"]:
        upd["last_topic"], upd["last_topic_ts"] = None, None
    if res.get("intake"):
        upd["intake"], upd["intake_ts"] = res["intake"], now
    elif res.get("intake_clear"):
        upd["intake"], upd["intake_ts"] = None, None
    db.reference(f"bot_state/{tid}").update(upd)
    if res["escalate"]:
        db.reference(f"bot_escalations/{tid}").set({"name": ctx.get("name") or tid, "topic": res["escalate"],
                                                     "text": text[:200], "ts": SERVER_TS})
    _STATE["replies"] += 1


def _scan(cfg):
    since = int(cfg.get("since") or cfg.get("updated") or 0)
    meta = _dict(db.reference("chat_meta").get())
    states = _dict(db.reference("bot_state").get())
    for tid, m in meta.items():
        if not isinstance(m, dict) or m.get("last_sender") != "streamer":
            continue
        last_ts = int(m.get("last_ts") or 0)
        state = _dict(states.get(tid))
        handled = int(state.get("handled_ts") or 0)
        if last_ts <= since or last_ts <= handled:
            continue
        if not _claim(tid, last_ts):
            continue
        try:
            _reply_to(tid, last_ts, handled, since, state, cfg)
        except Exception as e:
            _STATE["last_error"] = f"{tid}: {type(e).__name__}: {e}"
            print("Bot-Antwort fehlgeschlagen:", tid, e)


def _loop():
    while True:
        wait = POLL_IDLE_S
        try:
            cfg = _dict(db.reference("support_status").get())
            _STATE["last_run"] = time.time()
            if _active(cfg):
                _scan(cfg)
                wait = POLL_ACTIVE_S
        except Exception as e:
            _STATE["last_error"] = f"{type(e).__name__}: {e}"
            wait = 30
        time.sleep(wait)


def start_vacation_bot(games=None):
    """Startet den Bot-Thread (einmal pro Prozess; startet neu, falls er gestorben ist)."""
    if games:
        _CFG["games"] = dict(games)
    with _LOCK:
        t = _STATE["thread"]
        if t is None or not t.is_alive():
            t = threading.Thread(target=_loop, daemon=True, name="streamdex-vacation-bot")
            t.start()
            _STATE["thread"] = t


# ----------------------------------------------------------------------------
# Panel (Admin -> Support-Tab)
# ----------------------------------------------------------------------------
def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m. %H:%M")
    except Exception:
        return ""


def vacation_panel(me):
    import pandas as pd
    import streamlit as st

    start_vacation_bot()
    cur = _dict(db.reference("support_status").get())
    esc = _dict(db.reference("bot_escalations").get())
    on_now = cur.get("vacation") is True
    live = _active(cur)
    label = ("🏖️ Urlaubsmodus · AN (StreamDex Bot antwortet)" if live
             else "🏖️ Urlaubsmodus · abgelaufen" if on_now else "🏖️ Urlaubsmodus · aus")
    if esc:
        label += f" · 🚨 {len(esc)} vom Bot übergeben"
    with st.expander(label, expanded=on_now or bool(esc)):
        if esc:
            st.markdown("**🚨 Der Bot hat diese Streamer an dich übergeben**")
            for tid, e in sorted(esc.items(), key=lambda kv: -int(_dict(kv[1]).get("ts") or 0)):
                e = _dict(e)
                c1, c2 = st.columns([6, 1], vertical_alignment="center")
                c1.write(f"**{e.get('name') or tid}** · {e.get('topic', '')} · {_fmt_ts(e.get('ts'))}\n\n"
                         f"> {e.get('text', '')}")
                if c2.button("Erledigt", key=f"vac_esc_{tid}"):
                    db.reference(f"bot_escalations/{tid}").delete()
                    st.rerun()
            st.divider()

        st.caption("Solange der Urlaubsmodus an ist, antwortet der StreamDex Bot automatisch auf neue Support-"
                   "Nachrichten (versteht Tippfehler, Menü mit Zahlen, Live-Daten wie Spiele-Freigaben/Sperre). "
                   "Die Chats bleiben für dich ungelesen. Antwortest du selbst, hält sich der Bot raus. Bugs, Ideen und Feedback, "
                   "die Streamer dem Bot schreiben, landen automatisch in „Bugs & Ideen“ (feedback_inbox).")
        on = st.toggle("Urlaubsmodus an", value=on_now, key="vac_on")
        until = st.text_input("Zurück am (optional, z. B. 20.10.2026)", value=str(cur.get("until") or ""),
                              max_chars=20, key="vac_until")
        auto_end = st.checkbox("Am Rückkehr-Datum (00:00 Uhr) automatisch ausschalten",
                               value=bool(cur.get("auto_end", True)), key="vac_auto_end")
        text = st.text_area("Zusatznachricht für die Begrüßung (optional, max. 300 Zeichen)",
                            value=str(cur.get("text") or ""), max_chars=300, height=80, key="vac_text")
        if st.button("💾 Speichern", key="vac_save"):
            payload = {"vacation": bool(on), "until": until.strip(), "text": text.strip(),
                       "auto_end": bool(auto_end), "updated": SERVER_TS, "by": me}
            if on and not on_now:
                payload["since"] = SERVER_TS   # nur Nachrichten NACH dem Einschalten werden beantwortet
            db.reference("support_status").update(payload)
            st.success("Urlaubsmodus ist jetzt " + ("AN." if on else "aus."))
            st.rerun()

        t = _STATE["thread"]
        alive = bool(t and t.is_alive())
        ago = int(time.time() - _STATE["last_run"]) if _STATE["last_run"] else None
        st.caption(f"🤖 Bot-Worker: {'läuft' if alive else 'gestoppt'}"
                   + (f" · letzter Durchlauf vor {ago} s" if ago is not None else "")
                   + f" · {_STATE['replies']} Antworten, {_STATE['feedback']} Bug/Ideen/Feedback eingetragen seit Start"
                   + (f" · 📚 Wissensbasis: {len(WISSEN)} Einträge (Stand {WISSEN_STAND})" if WISSEN
                      else " · ⚠️ bot_wissen.py fehlt (neben vacation.py ablegen!)")
                   + (f" · ⚠️ {_STATE['last_error']}" if _STATE["last_error"] else ""))

        st.markdown("**🧠 Eigene Antworten (FAQ)**")
        st.caption("Stichwörter mit Komma trennen (Treffer am Wortanfang, Tippfehler werden verziehen, „ban$“ = ganzes "
                   "Wort). Platzhalter: {name}, {zurueck}, {seite}, {releases}. Eigene Einträge haben Vorrang vor den "
                   "eingebauten.")
        cols = ["Aktiv", "Titel", "Stichwörter", "Antwort"]
        rows = [{"Aktiv": it.get("on", True) is not False, "Titel": it.get("title", ""),
                 "Stichwörter": it.get("kw", ""), "Antwort": it.get("answer", "")} for it in _custom_raw()]
        df = pd.DataFrame(rows, columns=cols)
        df["Aktiv"] = df["Aktiv"].astype(bool)
        edited = st.data_editor(
            df, num_rows="dynamic", use_container_width=True, hide_index=True, key="vac_faq_editor",
            column_config={"Aktiv": st.column_config.CheckboxColumn(default=True),
                           "Antwort": st.column_config.TextColumn(width="large", max_chars=700)})
        if st.button("💾 FAQ speichern", key="vac_faq_save"):
            def s(v):
                return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()
            out = []
            for r in edited.to_dict("records"):
                if s(r.get("Stichwörter")) and s(r.get("Antwort")):
                    out.append({"on": bool(r.get("Aktiv", True)), "title": s(r.get("Titel"))[:60],
                                "kw": s(r.get("Stichwörter"))[:200], "answer": s(r.get("Antwort"))[:700]})
            ref = db.reference("support_faq")
            ref.set(out) if out else ref.delete()
            st.success(f"{len(out)} eigene Antwort(en) gespeichert.")
            st.rerun()

        test = st.text_input("🧪 Test: Was würde der Bot auf diese Nachricht antworten?", key="vac_test")
        if test.strip():
            st.info(build_reply(_ctx(None), test, cur, intro=False))


if __name__ == "__main__":      # eigenständiger Betrieb ohne Streamlit
    import os
    import firebase_admin
    from firebase_admin import credentials

    firebase_admin.initialize_app(
        credentials.Certificate(os.environ.get("SERVICE_ACCOUNT", "serviceAccount.json")),
        {"databaseURL": os.environ["DATABASE_URL"]})
    print("StreamDex Bot läuft (Strg+C zum Beenden) …")
    _loop()
