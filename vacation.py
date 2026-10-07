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
  * merkt sich pro Streamer das letzte Thema (bot_state/{tid}).

Firebase-Knoten:
  support_status    = {vacation, until, text, auto_end, since, updated, by}
  support_faq       = [{on, title, kw, answer}, ...]       (eigene Antworten, Vorrang vor den eingebauten)
  bot_state/{tid}   = {handled_ts, intro_ts, hour_start, n, last_topic, last_topic_ts, menu_ts}
  bot_escalations/{tid} = {name, topic, text, ts}           (vom Bot an dich übergeben)

Eigenständig starten (falls die Streamlit-App schläft):
  DATABASE_URL=https://...firebasedatabase.app SERVICE_ACCOUNT=serviceAccount.json python vacation.py
"""
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
MAX_TEXT = 1800

_CFG = {"games": {}}
_STATE = {"thread": None, "last_run": 0.0, "last_error": "", "replies": 0}
_LOCK = threading.Lock()


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
     "kw": ["spiel", "game", "freigab", "freigeschaltet", "freischalt", "slot", "gambel", "hilo", "hi lo",
            "angeln", "kraken", "minen", "mining", "farm", "arena", "raffel", "raffle", "sim racing", "taschenraub"]},
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
     "kw": ["update", "version", "aktualisier", "neue version", "download", "installer", "herunterladen", "exe$",
            "runterladen"]},
    {"title": "OBS / Overlays", "ask": True,
     "answer": ("🎬 Wenn ein Overlay nichts anzeigt:\n1) Ist das Tool gestartet? (Overlays laufen über dein Tool)\n"
                "2) Stimmt die Overlay-URL (http://localhost:8765/…)? Am besten im Tool neu kopieren\n"
                "3) In OBS: Rechtsklick auf die Quelle → „Cache der aktuellen Seite leeren“ bzw. neu laden"),
     "kw": ["overlay", "obs", "browserquelle", "browser quelle", "browser source", "localhost", "8765",
            "subathon", "streams24", "stempeluhr", "alert", "schwarz", "leer"]},
    {"title": "Beta",
     "answer": "🧪 Beta-Zugang beantragst du hier: {seite}/?beta=1 – der Support prüft Bewerbungen nach dem Urlaub.",
     "kw": ["beta", "bewerb", "tester"]},
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
            "installier", "wie funktioniert", "wie benutze", "tutorial", "komme nicht klar", "neu hier", "anfaenger"]},
    {"title": "Bug / Fehler",
     "answer": ("🐞 Danke für die Meldung! Damit der Support es schnell nachstellen kann, schreib mir bitte:\n"
                "1) deine Version\n2) was genau passiert ist\n3) was du erwartet hast\n4) die Fehlermeldung (abtippen)\n"
                "Alles bleibt für den Support gespeichert."),
     "kw": ["bug", "fehler", "absturz", "crash", "stuerzt", "funktioniert nicht", "geht nicht", "problem",
            "error", "haengt", "friert", "kaputt", "klappt nicht"]},
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
_BY_TITLE = {e["title"]: e for e in DEFAULT_FAQ}

# Menü: (Label, [Titel der FAQ-Einträge]). Zahl N+1 = "Mit dem Support sprechen".
MENU = [
    ("🎮 Spiele sehen / freischalten", ["Spiele-Freigaben"]),
    ("🔑 Twitch-Login klappt nicht", ["Twitch-Login / Token"]),
    ("🎬 OBS / Overlay zeigt nichts", ["OBS / Overlays"]),
    ("🔄 Update / Version", ["Updates / Version"]),
    ("🐞 Fehler / Absturz melden", ["Bug / Fehler"]),
    ("💻 Neuer PC / „Kein Zugriff“", ["Geräte-Bindung"]),
    ("🧪 Beta, Dashboard oder Shop", ["Beta", "Dashboard", "Shop / Gutscheine"]),
    ("🚀 Erste Schritte / Anleitung", ["Erste Schritte"]),
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
    return items + DEFAULT_FAQ


def _score(entry, t):
    s = 0.0
    toks = t.split()
    for k in entry["kw"]:
        exact = k.endswith("$")
        k2 = _norm(k.rstrip("$"))
        if not k2:
            continue
        pat = r"(?<![a-z0-9])" + re.escape(k2) + (r"(?![a-z0-9])" if exact else "")
        if re.search(pat, t):
            s += 1 + len(k2) / 12
        elif not exact and _fuzzy(k2, toks):
            s += 0.8 * (1 + len(k2) / 12)
    return s * (1.5 if entry.get("custom") else 1)


def pick_answers(text, faq):
    t = _norm(text)
    scored = sorted(((_score(e, t), i, e) for i, e in enumerate(faq)), key=lambda x: (-x[0], x[1]))
    strong = [(s, e) for s, _, e in scored if s > 0 and not e.get("weak")]
    if strong:
        top = strong[0][0]
        return [e for s, e in strong[:2] if s >= top * 0.6], False
    weak = [e for s, _, e in scored if s > 0]
    return weak[:1], True


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
    for i, (label, _) in enumerate(MENU, 1):
        lines.append(f"{i}) {label}")
    lines.append(f"{len(MENU) + 1}) 👤 Mit dem Support sprechen")
    return "\n".join(lines)


def _render(e, ctx, cfg):
    a = e["answer"]
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


def compose(ctx, text, cfg, intro, state=None, faq=None):
    """Baut die Bot-Antwort. Rückgabe: {text, topic, menu, escalate, clear}."""
    state = state or {}
    faq = faq or _faq()
    now = _now_ms()
    t = _norm(text)
    toks = t.split()
    head = [_intro(ctx, cfg)] if intro else []
    out = {"topic": None, "menu": False, "escalate": None, "clear": False}

    def done(*parts):
        out["text"] = "\n\n".join(head + [p for p in parts if p])[:MAX_TEXT]
        return out

    def safe(e):
        try:
            return _render(e, ctx, cfg)
        except Exception as ex:   # eine kaputte Antwort darf den Bot nicht stoppen
            print("Bot-Antwort fehlgeschlagen:", e.get("title"), ex)
            return ""

    # 1) Zahl aus dem Menü
    if state.get("menu_ts") and now - int(state["menu_ts"]) < MENU_VALID_MS:
        m = re.fullmatch(r"(?:nummer |nr |punkt |option |zahl )?(\d{1,2})", t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= len(MENU):
                titles = MENU[n - 1][1]
                parts = [safe(_BY_TITLE[x]) for x in titles]
                first = _BY_TITLE[titles[0]]
                out["topic"] = first["title"] if first.get("ask") else None
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
                        "Fehlermeldung – schreib sie einfach hier rein.")
        if pos:
            out["clear"] = True
            return done("Super, freut mich! 🎉 Wenn noch etwas ist, schreib einfach – oder tippe MENÜ.")

    # 3) Befehle: Menü / Mensch / "verstehe nicht" (ein klares Thema in der Nachricht hat Vorrang)
    answers, weak_only = pick_answers(text, faq)
    has_strong = bool(answers) and not weak_only
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

    # 4) FAQ
    if answers and weak_only and answers[0]["title"] == "Begrüßung":
        out["menu"] = True
        return done(_menu_text("Schön, dass du da bist! 👋 Wobei kann ich helfen? Antworte einfach mit einer Zahl:"))
    parts = [p for p in (safe(e) for e in answers) if p]
    if parts:
        first = answers[0]
        out["topic"] = first["title"] if first.get("ask") else None
        return done(*parts)

    # 5) nichts erkannt -> Menü statt "verstehe ich nicht"
    out["menu"] = True
    return done("Das habe ich leider nicht ganz verstanden 🙈 – kein Problem! Deine Nachricht ist für den Support "
                "gespeichert (er meldet sich " + _when(cfg) + ").", _menu_text("Wobei kann ich dir sonst helfen? Antworte mit einer Zahl:"))


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
    db.reference(f"chats/{tid}/messages").push({"sender": "bot", "name": BOT_NAME, "text": res["text"], "ts": SERVER_TS})
    upd = {"hour_start": hour_start, "n": n + 1, "menu_ts": now if res["menu"] else 0}
    if intro:
        upd["intro_ts"] = now
    if res["topic"]:
        upd["last_topic"], upd["last_topic_ts"] = res["topic"], now
    elif res["clear"] or res["escalate"]:
        upd["last_topic"], upd["last_topic_ts"] = None, None
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
                   "Die Chats bleiben für dich ungelesen. Antwortest du selbst, hält sich der Bot raus.")
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
                   + f" · {_STATE['replies']} Antworten seit Start"
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
