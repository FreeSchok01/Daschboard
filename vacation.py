"""Urlaubsmodus + StreamDex Bot (läuft serverseitig im Admin-Dashboard).

So funktioniert es:
  * Ein Hintergrund-Thread (start_vacation_bot) schaut alle paar Sekunden in Firebase nach neuen
    Streamer-Nachrichten (chat_meta.last_sender == "streamer").
  * Ist der Urlaubsmodus an, antwortet der Bot in chats/{twitch_id}/messages (sender = "bot").
    Er schreibt bewusst NICHT in chat_meta -> die Nachricht bleibt für dich "ungelesen" (roter Punkt).
  * Antworten kommen aus einer FAQ (Stichwort-Erkennung) + live berechneten Antworten
    (Spiele-Freigaben, Sperre, Version des Streamers).
  * Eigene FAQ-Einträge pflegst du direkt im Panel (Firebase: support_faq).

Firebase-Knoten:
  support_status = {vacation, until, text, auto_end, since, updated, by}
  support_faq    = [{on, title, kw, answer}, ...]
  bot_state/{tid} = {handled_ts, intro_ts, hour_start, n}   (Bot-intern, verhindert Doppel-Antworten)

Zusätzlich lässt sich die Datei eigenständig starten (falls die Streamlit-App schläft):
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
MAX_REPLIES_PER_HOUR = 8     # Spam-Schutz pro Streamer
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
    u = str(cfg.get("until") or "").strip()
    return u


def _when(cfg):
    u = _until_txt(cfg)
    return f"ab dem {u}" if u else "sobald er zurück ist"


def _fill(text, ctx, cfg):
    return (str(text).replace("{name}", ctx.get("name") or "")
            .replace("{zurueck}", _when(cfg)).replace("{seite}", SITE))


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
    lines.append("Spiele sind standardmäßig gesperrt und werden vom Support manuell freigeschaltet. "
                 "Schreib mir, welches du brauchst – es landet beim Support.")
    return "\n".join(lines)


def _a_ban(ctx, cfg):
    if ctx.get("ban"):
        reason = ctx["ban"].get("reason") or "Kein Grund angegeben."
        return ("🚫 Dein Konto ist aktuell ausgeschlossen. Grund: " + str(reason) +
                "\nDas kann nur der Support persönlich prüfen – deine Nachricht ist gespeichert.")
    if ctx["tid"]:
        return ("Bei dir ist keine Sperre eingetragen. Wenn das Tool „Kein Zugriff“ meldet, liegt es meistens "
                "an der Geräte-Bindung (siehe unten).\n" + _A_BINDING)
    return "Ich prüfe hier live, ob bei dir eine Sperre eingetragen ist. (Testmodus)"


def _a_update(ctx, cfg):
    s = ""
    if ctx.get("version"):
        s += f"Deine installierte Version: {ctx['version']}.\n"
    return s + ("🔄 Updates findest du unter " + RELEASES + " – das Tool prüft beim Start auch selbst auf eine "
                "neuere Version. Lade die neueste Version herunter und ersetze die alte.")


_A_BINDING = ("🔐 Dein Login ist an ein Gerät gebunden (Schutz vor Missbrauch). Bei neuem PC, Neuinstallation oder "
              "der Meldung „an ein anderes Gerät gebunden“ muss der Support die Bindung zurücksetzen – das mache "
              "ich aus Sicherheitsgründen nicht automatisch. Schreib hier kurz deinen Twitch-Namen und dass du "
              "ein neues Gerät hast; der Support erledigt es {zurueck}.")

# kw: Stichwörter (Teil-Treffer am Wortanfang; "$" am Ende = ganzes Wort). weak = nur wenn nichts anderes passt.
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
    {"title": "Twitch-Login / Token",
     "answer": ("🔑 Login-Probleme lösen sich meist so: Im Tool bei Twitch neu anmelden/verbinden (Token abgelaufen "
                "oder Berechtigungen fehlen). Im Reiter „StreamDex“ zeigt dir der Token-Wächter, ob dein "
                "Twitch-Login noch gültig ist. Hilft das nicht: schreib mir die genaue Fehlermeldung."),
     "kw": ["login", "anmeld", "einlogg", "token", "twitch verbinden", "neu verbinden", "authent", "abgelaufen",
            "scope", "berechtigung", "ausgeloggt"]},
    {"title": "Updates / Version", "answer": _a_update,
     "kw": ["update", "version", "aktualisier", "neue version", "download", "installer", "herunterladen", "exe$"]},
    {"title": "OBS / Overlays",
     "answer": ("🎬 Overlays laufen als OBS-Browser-Quelle über dein laufendes Tool (http://localhost:8765/…). "
                "Check: 1) Tool ist gestartet, 2) die Overlay-URL stimmt (im Tool kopieren), 3) in OBS Rechtsklick "
                "auf die Quelle → „Cache der aktuellen Seite leeren“ bzw. Quelle neu laden. Zeigt es nichts: "
                "schreib mir, welches Overlay und was du siehst."),
     "kw": ["overlay", "obs", "browserquelle", "browser quelle", "browser source", "localhost", "8765",
            "subathon", "streams24", "stempeluhr", "alert"]},
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
    {"title": "Bug / Fehler",
     "answer": ("🐞 Danke für die Meldung! Damit der Support es schnell nachstellen kann, schreib bitte: "
                "1) deine Version, 2) was genau passiert ist, 3) was du erwartet hast, 4) die Fehlermeldung. "
                "Im Tool gibt es außerdem die Funktion „Bug / Feedback / Feature-Wunsch“ und im Reiter "
                "„StreamDex“ das Fehler-Dashboard."),
     "kw": ["bug", "fehler", "absturz", "crash", "stuerzt", "funktioniert nicht", "geht nicht", "problem",
            "error", "haengt", "friert", "kaputt"]},
    {"title": "Wann kommt Antwort?",
     "answer": "⏳ Der Support ist im Urlaub und antwortet {zurueck}. Deine Nachricht ist gespeichert.",
     "kw": ["wann", "urlaub", "erreichbar", "dauert", "antwort", "zurueck"]},
    {"title": "Dringend", "weak": True,
     "answer": "⚠️ Verstanden, dass es dringend ist. Die Nachricht bleibt beim Support als ungelesen markiert.",
     "kw": ["dringend", "notfall", "eilt", "sofort", "wichtig"]},
    {"title": "Danke", "weak": True,
     "answer": "Gern geschehen! 😊 Wenn noch etwas ist, schreib einfach.",
     "kw": ["danke", "dankeschoen", "thx", "merci"]},
    {"title": "Begrüßung", "weak": True,
     "answer": "Frag einfach direkt – z. B. zu Spiele-Freigaben, Login, Overlays, Updates oder Bugs.",
     "kw": ["hallo", "hi$", "hey", "moin", "servus", "guten tag"]},
]


# ----------------------------------------------------------------------------
# FAQ laden / erkennen / Antwort bauen
# ----------------------------------------------------------------------------
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
    for k in entry["kw"]:
        exact = k.endswith("$")
        k2 = _norm(k.rstrip("$"))
        if not k2:
            continue
        pat = r"(?<![a-z0-9])" + re.escape(k2) + (r"(?![a-z0-9])" if exact else "")
        if re.search(pat, t):
            s += 1 + len(k2) / 12
    return s * (1.5 if entry.get("custom") else 1)


def pick_answers(text, faq):
    t = _norm(text)
    scored = sorted(((_score(e, t), i, e) for i, e in enumerate(faq)), key=lambda x: (-x[0], x[1]))
    strong = [(s, e) for s, _, e in scored if s > 0 and not e.get("weak")]
    if strong:
        top = strong[0][0]
        return [e for s, e in strong[:2] if s >= top * 0.6]
    weak = [e for s, _, e in scored if s > 0]
    return weak[:1]


def _intro(ctx, cfg):
    name = ctx.get("name") or ""
    u = _until_txt(cfg)
    s = (f"🏖️ Hi{' ' + name if name else ''}! Ich bin der StreamDex Bot. Der Support ist gerade im Urlaub"
         + (f" und ab dem {u} wieder da" if u else "") + ". Ich beantworte, was ich automatisch kann – "
         "deine Nachricht bleibt trotzdem für den Support gespeichert.")
    if cfg.get("text"):
        s += "\n" + str(cfg["text"])
    return s


def build_reply(ctx, text, cfg, intro, faq=None):
    faq = faq or _faq()
    parts = [_intro(ctx, cfg)] if intro else []
    got = 0
    for e in pick_answers(text, faq):
        a = e["answer"]
        try:
            a = a(ctx, cfg) if callable(a) else a
        except Exception as ex:  # eine kaputte Antwort darf den Bot nicht stoppen
            print("Bot-Antwort fehlgeschlagen:", e.get("title"), ex)
            continue
        if a:
            parts.append(_fill(a, ctx, cfg))
            got += 1
    if not got:
        if intro:
            parts.append("Dazu habe ich keine passende Antwort. Der Support meldet sich " + _when(cfg) +
                         ". Hilfreich: deine Version, was genau passiert und eine Fehlermeldung bzw. ein Screenshot.")
        else:
            parts.append("Das kann ich leider nicht automatisch beantworten – es ist gespeichert, der Support "
                         "meldet sich " + _when(cfg) + ".")
    return "\n\n".join(parts)[:MAX_TEXT]


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
    reply = build_reply(_ctx(tid), text, cfg, intro)
    db.reference(f"chats/{tid}/messages").push({"sender": "bot", "name": BOT_NAME, "text": reply, "ts": SERVER_TS})
    upd = {"hour_start": hour_start, "n": n + 1}
    if intro:
        upd["intro_ts"] = now
    db.reference(f"bot_state/{tid}").update(upd)
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
def vacation_panel(me):
    import pandas as pd
    import streamlit as st

    start_vacation_bot()
    cur = _dict(db.reference("support_status").get())
    on_now = cur.get("vacation") is True
    live = _active(cur)
    label = ("🏖️ Urlaubsmodus · AN (StreamDex Bot antwortet)" if live
             else "🏖️ Urlaubsmodus · abgelaufen" if on_now else "🏖️ Urlaubsmodus · aus")
    with st.expander(label, expanded=on_now):
        st.caption("Solange der Urlaubsmodus an ist, antwortet der StreamDex Bot automatisch auf neue Support-"
                   "Nachrichten (FAQ + Live-Daten wie Spiele-Freigaben/Sperre). Die Chats bleiben für dich "
                   "ungelesen. Antwortest du selbst, hält sich der Bot bei dieser Nachricht raus.")
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
        st.caption("Stichwörter mit Komma trennen (Teil-Treffer am Wortanfang, „ban$“ = ganzes Wort). "
                   "Platzhalter in der Antwort: {name}, {zurueck}, {seite}. Eigene Einträge haben Vorrang vor den "
                   "eingebauten (Spiele, Sperre, Geräte-Bindung, Login, Updates, OBS/Overlays, Beta, Dashboard, "
                   "Shop, Bugs, Wann-Antwort).")
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
