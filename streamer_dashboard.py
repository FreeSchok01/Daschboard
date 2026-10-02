"""Streamer-Dashboard mit geschütztem Zugriff über Einmal-Tokens."""
import html
import json
import re
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

from beta_apply import _apply_form, _status_view
from downloads import (beta_link, lurk_repo, render_member_downloads, render_public_downloads,
                       settings as download_settings, update_notice)
from shop import owned_games, CSS

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}

STAT_KEYS = {
    "giveaways": "Giveaways gesamt",
    "giveaway_participants": "Teilnahmen",
    "giveaways_7d": "Giveaways (7 Tage)",
    "giveaways_30d": "Giveaways (30 Tage)",
    "viewers": "Viewer erfasst",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "fish_catches": "Fänge (Angeln)",
    "harvests": "Ernten (Farm)",
    "raids": "Raids empfangen",
}


def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _fmt_ago(ms):
    if not ms:
        return "nie"
    diff = max(0, int((time.time() * 1000 - int(ms)) / 1000))
    if diff < 60:
        return f"vor {diff} s"
    if diff < 3600:
        return f"vor {diff // 60} min"
    if diff < 86400:
        return f"vor {diff // 3600} h"
    return f"vor {diff // 86400} d"


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}$")   # genau das Format, das die App erzeugt (token_urlsafe(24))
TID_RE = re.compile(r"^[0-9]{1,15}$")
TOKEN_MAX_AGE_MS = 5 * 60 * 1000
SESSION_MAX_AGE_S = 2 * 60 * 60   # nach 2 Stunden ist ein neuer Login über die App nötig


def _verify_and_consume_token(token: str):
    """Prüft einen Login-Token und löscht ihn atomar (Einmal-Nutzung).
    Gibt die Twitch-ID zurück oder None. Der Grund einer Ablehnung wird nur auf der Serverkonsole geloggt."""
    def _fail(reason):
        print(f"[dashboard] Token abgelehnt: {reason}")   # nur Streamlit-Log, nicht im Browser sichtbar
        return None

    if not isinstance(token, str) or not TOKEN_RE.match(token):
        return _fail(f"Format falsch (Länge {len(token) if isinstance(token, str) else '-'})")

    consumed = {}

    def _take(current):
        # firebase_admin erlaubt in transaction() KEIN None als Ergebnis ("Value must not be none").
        # Deshalb wird der Eintrag atomar auf eine Markierung gesetzt; nur wer noch die echten Daten
        # (ohne "used") sieht, hat den Token eingelöst. Danach wird der Knoten gelöscht.
        if isinstance(current, dict) and not current.get("used"):
            consumed["data"] = current
        else:
            consumed["data"] = None
        return {"used": True}

    ref = db.reference(f"dash_tokens/{token}")
    try:
        ref.transaction(_take)
    except Exception as e:
        return _fail(f"Transaktion fehlgeschlagen: {type(e).__name__}: {e}")
    try:
        ref.delete()   # Markierung entfernen (Token ist ohnehin schon unbrauchbar)
    except Exception:
        pass

    data = consumed.get("data")
    if not isinstance(data, dict):
        return _fail(f"Kein Eintrag gefunden (data={data!r}). Token schon eingelöst, "
                     "oder das Dashboard liest in einer anderen Datenbank.")

    try:
        created_at = int(data.get("ts") or 0)
    except (TypeError, ValueError):
        return _fail(f"ts ungültig: {data!r}")
    age_ms = int(time.time() * 1000) - created_at
    if not created_at or age_ms > TOKEN_MAX_AGE_MS:
        return _fail(f"Abgelaufen: Alter {age_ms / 1000:.0f} s (erlaubt {TOKEN_MAX_AGE_MS // 1000} s), ts={created_at}")

    tid = str(data.get("tid") or "")
    if not TID_RE.match(tid):
        return _fail(f"tid ungültig: {tid!r}")
    return tid


def cleanup_old_entries(token_max_age_hours=1, history_days=400):
    """Admin-Aufräumen (im Admin-Panel per Knopf aufrufen):
    - dash_tokens: abgelaufene und halb eingelöste Einträge entfernen
    - stats_history: Tageseinträge älter als history_days entfernen
    Gibt {"tokens": n, "history_days": n} zurück."""
    now_ms = int(time.time() * 1000)
    removed_tokens = removed_days = 0

    try:
        tokens = db.reference("dash_tokens").get() or {}
    except Exception:
        tokens = {}
    if isinstance(tokens, dict):
        for key, val in list(tokens.items()):
            try:
                ts = int(val.get("ts") or 0) if isinstance(val, dict) else 0
            except (TypeError, ValueError):
                ts = 0
            if not ts or now_ms - ts > token_max_age_hours * 3600 * 1000:
                try:
                    db.reference(f"dash_tokens/{key}").delete()
                    removed_tokens += 1
                except Exception:
                    pass

    cutoff = (datetime.now(TZ).date() - timedelta(days=history_days)).isoformat()
    try:
        tids = list((db.reference("stats_history").get(shallow=True) or {}).keys())
    except Exception:
        tids = []
    for tid in tids:
        try:
            days = list((db.reference(f"stats_history/{tid}").get(shallow=True) or {}).keys())
        except Exception:
            continue
        for day in days:
            if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", str(day)) and str(day) < cutoff:
                try:
                    db.reference(f"stats_history/{tid}/{day}").delete()
                    removed_days += 1
                except Exception:
                    pass
    return {"tokens": removed_tokens, "history_days": removed_days}


def _load_messages(tid):
    data = db.reference(f"chats/{tid}/messages").order_by_child("ts").limit_to_last(100).get() or {}
    msgs = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    msgs.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]))
    return msgs


def _send_message(tid, name, text):
    text = text.strip()[:2000]
    if not text:
        return
    db.reference(f"chats/{tid}/messages").push({"sender": "streamer", "name": name, "text": text, "ts": SERVER_TS})
    db.reference(f"chat_meta/{tid}").update({"last_ts": SERVER_TS, "last_sender": "streamer", "last_text": text[:100]})


def _support_last_read(tid):
    """Zeitstempel (ms) der zuletzt als gelesen markierten Support-Antwort. Liegt unter support_read/{tid}."""
    try:
        return int(db.reference(f"support_read/{tid}").get() or 0)
    except Exception:
        return 0


def _unread_admin(msgs, last_read):
    """Antworten vom Support, die neuer sind als der Gelesen-Stand."""
    out = []
    for m in msgs:
        try:
            ts = int(m.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        if m.get("sender") == "admin" and ts > last_read:
            out.append(m)
    return out


def _mark_support_read(tid, msgs):
    """Markiert alles bis zur neuesten bekannten Support-Antwort als gelesen. Bewusst NICHT die aktuelle Zeit:
    sonst würde eine Antwort, die gerade erst eingetroffen ist, ungesehen als gelesen gelten."""
    latest = 0
    for m in msgs:
        if m.get("sender") == "admin":
            try:
                latest = max(latest, int(m.get("ts") or 0))
            except (TypeError, ValueError):
                pass
    if latest:
        try:
            db.reference(f"support_read/{tid}").set(latest)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# 🏠 Übersicht (echte Daten aus Firebase: presence, stats, game_flags, shop/beta)
# Hinweis: Live-Zuschauer und Coins im Umlauf werden von der App aktuell nicht
# nach Firebase gemeldet und deshalb bewusst NICHT angezeigt (keine Dummy-Werte).
# ----------------------------------------------------------------------------
OVERVIEW_CSS = """<style>
.sdx-grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:4px 0 16px}
.sdx-grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-bottom:16px}
.sdx-metric,.sdx-card{background:rgba(15,23,42,.85);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:16px}
.sdx-label{font-family:'JetBrains Mono',monospace;font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.5px}
.sdx-value{font-size:1.7rem;font-weight:800;margin-top:4px;color:#f8fafc}
.sdx-sub{font-size:.78rem;color:#64748b;margin-top:2px}
.sdx-ok{color:#22c55e}.sdx-off{color:#94a3b8}
.sdx-title{font-weight:800;font-size:1rem;margin-bottom:10px;color:#f8fafc}
.sdx-bar-row{margin:9px 0}
.sdx-bar-head{display:flex;justify-content:space-between;font-size:.82rem;color:#cbd5e1;margin-bottom:3px}
.sdx-bar{height:8px;border-radius:6px;background:rgba(255,255,255,.06);overflow:hidden}
.sdx-bar>div{height:100%;border-radius:6px;background:linear-gradient(90deg,#a855f7,#06b6d4)}
.sdx-chips{display:flex;flex-wrap:wrap;gap:8px}
.sdx-chip{padding:4px 10px;border-radius:20px;font-size:.78rem;font-weight:700;border:1px solid}
.sdx-chip.on{color:#22c55e;background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.3)}
.sdx-chip.off{color:#f87171;background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.25)}
.sdx-kv{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.06);font-size:.85rem;color:#f8fafc}
.sdx-kv:last-child{border-bottom:0}.sdx-kv span:first-child{color:#64748b}
.sdx-empty{font-size:.85rem;color:#64748b}
</style>"""

ACTIVITY_KEYS = ["checkins", "slot_spins", "megaslot_spins", "fish_catches", "harvests", "raids", "viewers"]


def _num(v):
    try:
        return max(0, int(float(v)))
    except Exception:
        return 0


def _de(n):
    return f"{n:,}".replace(",", ".")


def _overview_html(presence, stats, games, have_games, beta_info, is_online):
    """Baut das Übersichts-HTML. Alles Dynamische wird escaped; bewusst ohne Zeilenumbrüche/Einrückung,
    damit Streamlit-Markdown den Block nicht als Code interpretiert."""
    e = html.escape
    g_total = _num(stats.get("giveaways"))
    g_part = _num(stats.get("giveaway_participants"))
    n_unlocked = len([g for g in games if g in have_games])
    avg = f"Ø {round(g_part / g_total)} pro Giveaway" if g_total else "noch keine Giveaways"

    def metric(label, value, sub="", cls=""):
        sub_html = f'<div class="sdx-sub">{e(sub)}</div>' if sub else ""
        return (f'<div class="sdx-metric"><div class="sdx-label">{e(label)}</div>'
                f'<div class="sdx-value {cls}">{e(value)}</div>{sub_html}</div>')

    metrics = "".join([
        metric("Status", "🟢 Online" if is_online else "⚪ Offline",
               f"Aktiv {_fmt_ago(presence.get('last_seen'))}", "sdx-ok" if is_online else "sdx-off"),
        metric("Giveaways", _de(g_total),
               f"{_de(_num(stats.get('giveaways_7d')))} in 7 Tagen · {_de(_num(stats.get('giveaways_30d')))} in 30 Tagen"),
        metric("Teilnahmen", _de(g_part), avg),
        metric("Freigeschaltete Games", f"{n_unlocked} / {len(games)}",
               "alle frei" if n_unlocked == len(games) else f"{len(games) - n_unlocked} noch gesperrt"),
    ])

    # Aktivitäts-Balken (relativ zum größten Wert)
    rows = [(STAT_KEYS.get(k, k), _num(stats.get(k))) for k in ACTIVITY_KEYS]
    top = max([v for _, v in rows] + [0])
    if top == 0:
        bars = '<div class="sdx-empty">Noch keine Aktivität erfasst.</div>'
    else:
        bars = "".join(
            f'<div class="sdx-bar-row"><div class="sdx-bar-head"><span>{e(label)}</span><span>{_de(v)}</span></div>'
            f'<div class="sdx-bar"><div style="width:{max(2, round(v / top * 100)) if v else 0}%"></div></div></div>'
            for label, v in rows)
    activity = f'<div class="sdx-card"><div class="sdx-title">📈 Aktivität</div>{bars}</div>'

    def kv(k, v):
        return f'<div class="sdx-kv"><span>{e(k)}</span><span>{e(str(v))}</span></div>'

    account_rows = [
        kv("Twitch-Name", presence.get("twitch_username", "?")),
        kv("App-Version", presence.get("app_version", "?")),
        kv("Beta-Status", "🧪 Aktiv" if beta_info else "Nein"),
        kv("Statistik aktualisiert", _fmt_ago(stats.get("updated_at"))),
    ]
    if is_online and presence.get("session_start"):
        account_rows.append(kv("Online seit", _fmt_ts(presence.get("session_start"))))
    account = f'<div class="sdx-card"><div class="sdx-title">🧾 Konto</div>{"".join(account_rows)}</div>'

    chips = "".join(
        f'<span class="sdx-chip {"on" if g_key in have_games else "off"}">'
        f'{"✅" if g_key in have_games else "🔒"} {e(g_name)}</span>'
        for g_key, g_name in games.items())
    games_card = f'<div class="sdx-card"><div class="sdx-title">🎮 Deine Games</div><div class="sdx-chips">{chips}</div></div>'

    return f'<div class="sdx-grid4">{metrics}</div><div class="sdx-grid2">{activity}{account}</div>{games_card}'


# ----------------------------------------------------------------------------
# 📅 Verlauf: tägliche Zuwächse aus den Tagesständen stats_history/{tid}/{YYYY-MM-DD}
# (die App speichert dort einmal pro Tag den letzten Stand der kumulativen Zähler)
# ----------------------------------------------------------------------------
HISTORY_LABELS = {
    "giveaways": "Giveaways",
    "giveaway_participants": "Teilnahmen",
    "viewers": "Neue Viewer",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "raids": "Raids",
    "fish_catches": "Fänge (Angeln)",
    "harvests": "Ernten (Farm)",
}


@st.cache_data(ttl=120, show_spinner=False)
def _load_history(tid):
    """Letzte ~120 Tagesstände (Schlüssel = Datum, sortiert sich von selbst). Einer mehr als der größte Zeitraum dient als Basis."""
    data = db.reference(f"stats_history/{tid}").order_by_key().limit_to_last(121).get() or {}
    return data if isinstance(data, dict) else {}


def _daily_series(history, key, days, today=None):
    """Tägliche Zuwächse eines kumulativen Zählers als pandas-Serie (lückenlos, fehlende Tage = 0).
    Basis ist der höchste bisher gesehene Stand: so erzeugt ein Ausreißer nach unten (z.B. leere lokale DB)
    keine falschen Spitzen. Tage ohne App-Start werden dem nächsten Tag mit Daten zugerechnet."""
    today = today or datetime.now(TZ).date()
    deltas, base = {}, None
    for day in sorted(history):
        entry = history[day]
        if not isinstance(entry, dict):
            continue
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        val = _num(entry.get(key))
        if base is not None and val > base:
            deltas[d] = val - base
        base = val if base is None else max(base, val)
    idx = pd.date_range(today - timedelta(days=days - 1), today)
    return pd.Series([deltas.get(i.date(), 0) for i in idx], index=idx, name=HISTORY_LABELS.get(key, key))


# ----------------------------------------------------------------------------
# 🧾 Konto & Datenschutz: Daten ansehen, exportieren, Konto-Daten löschen
# ----------------------------------------------------------------------------
# Wird beim Löschen entfernt (alles, was unter der eigenen Twitch-ID liegt). presence ZULETZT,
# damit der Login bei einem Fehler mittendrin noch funktioniert und man es erneut versuchen kann.
_DELETE_PATHS = [
    "stats/{t}", "stats_history/{t}", "chats/{t}", "chat_meta/{t}", "gifts/{t}",
    "lurk/stats/{t}", "lurk/chats/{t}", "lurk/chat_meta/{t}", "lurk/presence/{t}",
    "support_read/{t}", "giveaway_log/{t}",
    "presence/{t}",
]
# Wird angezeigt und exportiert, aber NICHT gelöscht (Kauf-/Freischaltungsdaten)
_KEEP_PATHS = ["tour_skip/{t}", "shop/beta/{t}", "game_flags/streamers/{t}"]

ACCOUNT_DATA_TABLE = """
| Was | Wozu |
|---|---|
| Twitch-ID, Benutzername, App-Version, Online-Status, letzte Aktivität, technische Anmelde-Kennung | Login, Status-Anzeige, Zuordnung deiner Daten |
| Hardware-Kennungen (nur als Hash) | Sperrliste gegen Missbrauch |
| Zähler (Giveaways, Check-ins, Spins, …) und Tagesstände | Statistiken und Verlauf im Dashboard |
| Giveaway-Verlauf: Datum, Preis, Teilnehmerzahl (ohne Gewinner) | Giveaway-Verlauf im Dashboard |
| Support-Nachrichten und Feedback | Support |
| Freischaltungen und Kaufstatus | Games und Features, die du freigeschaltet hast |
"""


def _safe_get(path):
    try:
        return db.reference(path).get()
    except Exception as e:
        return {"_fehler": f"{type(e).__name__}"}


def _load_feedback(tid):
    """Feedback-Einträge dieser Twitch-ID. Mit Index auf 'tid' direkt, sonst Fallback über 'ts' (letzte 1000)."""
    ref = db.reference("feedback_inbox")
    try:
        data = ref.order_by_child("tid").equal_to(str(tid)).get() or {}
    except Exception:
        data = ref.order_by_child("ts").limit_to_last(1000).get() or {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and str(v.get("tid")) == str(tid)}


def _collect_account_data(tid):
    """Alle gespeicherten Daten dieser Twitch-ID (nur nicht-leere Bereiche)."""
    out = {}
    for path in _KEEP_PATHS + _DELETE_PATHS:
        p = path.format(t=tid)
        val = _safe_get(p)
        if val not in (None, {}, []):
            out[p] = val
    fb = _load_feedback(tid)
    if fb:
        out["feedback_inbox (nur deine Einträge)"] = fb
    return out


def _delete_account_data(tid):
    """Löscht alle Daten unter der eigenen Twitch-ID. Gibt (Anzahl gelöschter Bereiche, Fehlerliste) zurück."""
    removed, errors = 0, []
    try:
        for key in list(_load_feedback(tid)):
            db.reference(f"feedback_inbox/{key}").delete()
            removed += 1
    except Exception as e:
        errors.append(f"feedback_inbox: {type(e).__name__}")
    for path in _DELETE_PATHS:
        p = path.format(t=tid)
        try:
            ref = db.reference(p)
            if ref.get() is not None:
                ref.delete()
                removed += 1
        except Exception as e:
            errors.append(f"{p}: {type(e).__name__}")
    return removed, errors


def _render_account_tab(tid, username, is_online):
    st.subheader("🧾 Konto & Datenschutz")
    st.caption("Hier siehst du, welche Daten Streamdex unter deiner Twitch-ID gespeichert hat, kannst sie exportieren "
               "oder löschen.")
    with st.expander("Was wird gespeichert und wozu?"):
        st.markdown(ACCOUNT_DATA_TABLE)

    # --- Daten ansehen & exportieren (wird erst auf Klick geladen) ---
    st.markdown("### 📥 Meine Daten")
    if st.button("Meine Daten laden", key="acct_load"):
        st.session_state["acct_data"] = {"tid": tid, "data": _collect_account_data(tid)}
    cached = st.session_state.get("acct_data")
    if cached and cached.get("tid") == tid:
        data = cached["data"]
        if not data:
            st.info("Unter deiner Twitch-ID sind keine Daten gespeichert.")
        else:
            payload = {
                "exportiert_am": datetime.now(TZ).isoformat(timespec="seconds"),
                "twitch_id": tid,
                "hinweis": "Zeitstempel (ts, last_seen, …) sind Millisekunden seit 1970 (UTC).",
                "daten": data,
            }
            st.download_button(
                "⬇️ Alles als JSON herunterladen",
                data=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                file_name=f"streamdex_daten_{tid}.json",
                mime="application/json",
                key="acct_dl",
            )
            for path, val in data.items():
                with st.expander(path):
                    st.json(val)

    st.divider()

    # --- Löschen ---
    st.markdown("### 🗑️ Meine Daten löschen")
    st.warning(
        "Gelöscht werden Status, Statistiken, Verlauf, Support-Chat und deine Feedback-Einträge auf dem Server. "
        "Das lässt sich **nicht rückgängig machen**."
    )
    st.markdown(
        "**Bleibt bestehen:** Kauf- und Freischaltungsdaten (damit bezahlte Games erhalten bleiben), "
        "die Sperrliste (Missbrauchsschutz) und alles, was nur auf deinem PC liegt (Einstellungen, Logs). "
        "Dein Twitch-Konto ist nicht betroffen. Startest du die App danach wieder, legt sie neue Einträge an."
    )
    if is_online:
        st.info("Deine Desktop-App läuft gerade und würde die Daten sofort neu anlegen. "
                "Schließe die App zuerst, warte etwa 3 Minuten, bis dein Status „Offline“ ist, und lade diese Seite neu.")
    confirm = st.checkbox("Ich habe verstanden, dass meine Daten dauerhaft gelöscht werden.", key="acct_confirm")
    typed = st.text_input(f"Zur Bestätigung deinen Twitch-Namen eingeben: **{username}**", key="acct_typed")
    ready = confirm and typed.strip().lower() == str(username).strip().lower() and not is_online
    if st.button("🗑️ Endgültig löschen", type="primary", disabled=not ready, key="acct_delete"):
        removed, errors = _delete_account_data(tid)
        if errors:
            st.error("Nicht alles konnte gelöscht werden. Bitte versuche es erneut oder melde dich beim Support. "
                     f"(Betroffen: {', '.join(errors)})")
        else:
            st.session_state.pop("authenticated_tid", None)
            st.session_state.pop("acct_data", None)
            st.session_state["acct_deleted"] = removed
            st.rerun()


# ----------------------------------------------------------------------------
# 🔔 Update-Hinweis: App-Version des Streamers mit der neuesten GitHub-Release vergleichen
# ----------------------------------------------------------------------------
GITHUB_REPO = "FreeSchok01/Givewaytool"   # dasselbe Repo, das auch die Desktop-App für Updates nutzt


def _version_tuple(v):
    """Gleiche Logik wie parse_v() in der App: alles außer Ziffern und Punkten entfernen ("BETA VERSION V2" -> (2,))."""
    try:
        return tuple(int(x) for x in re.sub(r"[^0-9.]", "", str(v)).split(".") if x)
    except ValueError:
        return ()


@st.cache_data(ttl=900, show_spinner=False)
def _latest_release():
    """Neueste Release von GitHub (15 Minuten zwischengespeichert, damit das API-Limit nicht erreicht wird)."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"User-Agent": "StreamdexDashboard", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        url = str(d.get("html_url") or "")
        if not url.startswith("https://github.com/"):
            url = f"https://github.com/{GITHUB_REPO}/releases/latest"
        return {"tag": str(d.get("tag_name") or ""), "url": url}
    except Exception:
        return None   # offline, Limit erreicht, kein Release: dann einfach keinen Hinweis zeigen


def _update_notice(app_version):
    """Gibt (neueste_version, link) zurück, wenn eine neuere Version existiert, sonst None."""
    rel = _latest_release()
    if not rel or not rel["tag"]:
        return None
    cur, new = _version_tuple(app_version), _version_tuple(rel["tag"])
    if cur and new and new > cur:
        return rel["tag"], rel["url"]
    return None


# ----------------------------------------------------------------------------
# 🎁 Giveaway-Verlauf (Datum, Preis, Teilnehmerzahl - Gewinnernamen werden bewusst NICHT hochgeladen)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _load_giveaway_log(tid):
    try:
        data = db.reference(f"giveaway_log/{tid}").get() or {}
    except Exception:
        return []
    if isinstance(data, list):   # Firebase liefert Schlüssel 1,2,3,… als Liste zurück
        data = {str(i): v for i, v in enumerate(data) if v is not None}
    rows = []
    for v in data.values():
        if not isinstance(v, dict):
            continue
        d = str(v.get("date") or "")
        if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$", d):
            continue
        rows.append({"date": d, "Preis": str(v.get("prize") or ""), "Teilnehmer": int(_num(v.get("participants")))})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:1000]


def _csv_safe(text):
    """Schützt vor Formel-Einschleusung in Excel (Zellen, die mit = + - @ beginnen)."""
    text = str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _render_giveaway_tab(tid):
    st.subheader("🎁 Giveaway-Verlauf")
    rows = _load_giveaway_log(tid)
    if not rows:
        st.info("Noch kein Giveaway-Verlauf vorhanden. Die App lädt neue und frühere Giveaways alle 10 Minuten hoch "
                "(ältere nach und nach, höchstens 50 pro Durchlauf).")
        return
    df = pd.DataFrame(rows)
    df.insert(0, "Datum", df["date"].map(lambda d: f"{d[8:10]}.{d[5:7]}.{d[0:4]} {d[11:]}"))
    df = df.drop(columns=["date"])
    search = st.text_input("Preis suchen", key="gw_search")
    if search.strip():
        df = df[df["Preis"].str.contains(search.strip(), case=False, regex=False)]
    m1, m2, m3 = st.columns(3)
    m1.metric("Giveaways", _de(len(df)))
    m2.metric("Teilnahmen gesamt", _de(int(df["Teilnehmer"].sum())))
    m3.metric("Ø Teilnehmer", f"{df['Teilnehmer'].mean():.1f}".replace(".", ",") if len(df) else "–")
    st.dataframe(df, use_container_width=True, hide_index=True)
    out = df.copy()
    out["Preis"] = out["Preis"].map(_csv_safe)
    st.download_button("⬇️ Als CSV herunterladen", out.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name="giveaway_verlauf.csv", mime="text/csv", key="gw_csv")
    st.caption("Gewinnernamen werden bewusst nicht ins Dashboard hochgeladen. Sie bleiben nur in deiner App.")


def _render_landing():
    """Startseite ohne Token: Downloads und Beta-Bewerbung (statt nur 'Zugriff gesperrt')."""
    st.info("🔒 Dein persönliches Dashboard öffnest du direkt in der **Streamdex Desktop-App** (sicherer Login per Token). "
            "Noch keine App? Hier kannst du sie laden oder dich für die Beta bewerben.")
    try:
        cfg = download_settings()
        t_dl, t_apply, t_status = st.tabs(["⬇️ Downloads", "📝 Für Beta bewerben", "🔎 Beta-Status & Download"])
        with t_dl:
            render_public_downloads(cfg)
        with t_apply:
            _apply_form(cfg)
        with t_status:
            _status_view(cfg)
    except Exception as e:
        st.error(f"Gerade nicht erreichbar, bitte später erneut versuchen. ({e})")
    if st.session_state.get("authenticated_tid") and st.button("Sitzung zurücksetzen"):
        st.session_state.pop("authenticated_tid", None)
        st.rerun()


def render_streamer_dashboard(games):
    st.markdown(CSS, unsafe_allow_html=True)
    hero = st.empty()   # Kopfbereich wird erst gefüllt, wenn klar ist, ob jemand angemeldet ist


    # 1. Token aus URL verarbeiten (falls vorhanden)
    token_arg = st.query_params.get("token")
    if token_arg:
        valid_tid = _verify_and_consume_token(token_arg)
        if valid_tid:
            st.session_state["authenticated_tid"] = valid_tid
            st.session_state["authenticated_at"] = time.time()
            # Token aus URL entfernen für saubere Adresse
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        else:
            st.error("Der Zugriffs-Link ist ungültig oder abgelaufen. Bitte öffne das Dashboard erneut über deine Streamdex Desktop-App.")

    # 2. Prüfen ob Streamer eingeloggt ist
    authed_tid = st.session_state.get("authenticated_tid")
    if authed_tid:
        started = st.session_state.setdefault("authenticated_at", time.time())
        if time.time() - started > SESSION_MAX_AGE_S:
            for k in ("authenticated_tid", "authenticated_at", "acct_data"):
                st.session_state.pop(k, None)
            st.session_state["session_expired"] = True
            authed_tid = None

    if authed_tid:
        hero.markdown(
            '<div class="hero"><h1>📊 Streamer Dashboard</h1><p>Verwalte deine Freischaltungen, Statistiken und Support-Tickets.</p></div>',
            unsafe_allow_html=True,
        )
    else:
        hero.markdown(
            '<div class="hero"><h1>👋 Willkommen bei StreamDex OS</h1>'
            '<p>Dein Toolkit für Streams: Games, Giveaways, Statistiken und Support. '
            'Lade die App herunter oder bewirb dich für die Beta.</p></div>',
            unsafe_allow_html=True,
        )

    if not authed_tid:
        if st.session_state.pop("session_expired", False):
            st.warning(f"⏱️ Deine Sitzung ist nach {SESSION_MAX_AGE_S // 3600} Stunden aus Sicherheitsgründen abgelaufen. "
                       "Bitte öffne das Dashboard erneut über deine Streamdex Desktop-App.")
        elif st.session_state.get("acct_deleted") is not None:
            st.session_state.pop("acct_deleted", None)
            st.success("✅ Deine Daten wurden gelöscht und du wurdest abgemeldet.")
        _render_landing()
        return

    # Daten des authentifizierten Streamers laden
    presence = db.reference(f"presence/{authed_tid}").get() or {}
    if not presence:
        st.error("Konto-Daten konnten nicht geladen werden.")
        return

    twitch_username = presence.get("twitch_username", authed_tid)
    app_version = presence.get("app_version", "?")
    last_seen = presence.get("last_seen")
    is_online = presence.get("status") == "online" and last_seen and (time.time() * 1000 - last_seen) < 150000

    have_games = owned_games(authed_tid)
    beta_info = db.reference(f"shop/beta/{authed_tid}").get() or {}
    stats_data = db.reference(f"stats/{authed_tid}").get() or {}

    # Header & Abmelden-Button
    top_col1, top_col2 = st.columns([5, 1])
    top_col1.caption(f"Angemeldet als: **{twitch_username}** (`{authed_tid}`)")
    if top_col2.button("🚪 Abmelden", key="dash_logout"):
        st.session_state.pop("authenticated_tid", None)
        st.rerun()

    st.divider()

    # Support-Nachrichten einmal laden (Banner oben und Tab "Support-Chat" nutzen dieselben Daten).
    # Bewusst ein Banner statt Zähler im Tab-Titel: ändert sich der Titel, springt Streamlit zurück auf den ersten Tab.
    msgs = _load_messages(authed_tid)
    support_last_read = _support_last_read(authed_tid)
    unread = _unread_admin(msgs, support_last_read)
    if unread:
        n_un = len(unread)
        b_text, b_btn = st.columns([4, 1])
        b_text.info(f"💬 **{n_un} neue {'Antwort' if n_un == 1 else 'Antworten'}** vom Support – "
                    "lies sie im Tab „Support-Chat“.")
        if b_btn.button("✔ Gelesen", key="support_mark_read", use_container_width=True):
            _mark_support_read(authed_tid, msgs)
            st.rerun()

    t_over, t_games, t_stats, t_hist, t_gw, t_support, t_acct = st.tabs(["🏠 Übersicht", "🎮 Freigeschaltete Games", "📈 Kanal-Statistiken", "📅 Verlauf", "🎁 Giveaways", "💬 Support-Chat", "🧾 Konto & Datenschutz"])

    # --- Tab 0: Übersicht ---
    with t_over:
        # Beta-Builds ("BETA VERSION V2") haben keine Release-Nummer: Vergleich mit der öffentlichen Release würde falsch warnen
        _upd = None if "beta" in str(app_version).lower() else _update_notice(app_version)
        if _upd:
            st.info(f"🔔 **Neue Version verfügbar: {_upd[0]}** (du nutzt {app_version}). "
                    "Die App bietet das Update beim Start an, oder du lädst es hier herunter.")
            st.link_button("⬇️ Zur neuen Version", _upd[1])
        try:    # Lurk-App: gleiche Prüfung gegen die neueste Lurk-Release
            _lp = db.reference(f"lurk/presence/{authed_tid}").get()
            if isinstance(_lp, dict):
                _lupd = update_notice(lurk_repo(), _lp.get("app_version"))
                if _lupd:
                    st.info(f"🔔 **Neue Lurk-Version verfügbar: {_lupd[0]}** (du nutzt {_lp.get('app_version', '?')}). "
                            "Die Lurk-App bietet das Update beim Start an, oder du lädst es hier herunter.")
                    st.link_button("⬇️ Zur neuen Lurk-Version", _lupd[1])
        except Exception:
            pass
        st.markdown(OVERVIEW_CSS + _overview_html(presence, stats_data, games, have_games, beta_info, is_online),
                    unsafe_allow_html=True)
        if beta_info:
            try:
                _cfg = download_settings()
                _rev = int(_cfg.get("beta_rev") or 0)
                if _rev and _rev > int(db.reference(f"beta_seen/{authed_tid}").get() or 0):
                    _n = str(_cfg.get("beta_note") or "").strip()
                    st.success("🧪 **Neuer Beta-Build verfügbar!**" + (f" {_n}" if _n else ""))
                    _b1, _b2 = st.columns(2)
                    if beta_link(_cfg):
                        _b1.link_button("⬇️ Neuen Beta-Build laden", beta_link(_cfg), type="primary", use_container_width=True)
                    if _b2.button("✔ Gelesen", key="beta_seen_btn", use_container_width=True):
                        db.reference(f"beta_seen/{authed_tid}").set(_rev)
                        st.rerun()
            except Exception:
                pass
            st.markdown("**🧪 Downloads für Beta-Tester**")
            try:
                render_member_downloads()
            except Exception:
                st.caption("Download-Links gerade nicht erreichbar.")
        if any(g not in have_games for g in games):
            st.link_button("🛒 Weitere Games im Shop freischalten", f"/?u={urllib.parse.quote(str(twitch_username))}")

    # --- Tab 1: Games ---
    with t_games:
        st.subheader("🎮 Deine Games & Features")
        cols = st.columns(3)
        for idx, (g_key, g_name) in enumerate(games.items()):
            is_unlocked = g_key in have_games
            with cols[idx % 3]:
                with st.container(border=True):
                    if is_unlocked:
                        st.markdown(f"### {g_name}")
                        st.markdown('<span class="badge">✅ Freigeschaltet</span>', unsafe_allow_html=True)
                    else:
                        st.markdown(f"### {g_name}")
                        st.markdown('<span class="badge save" style="background:#ef444422;color:#f87171;">🔒 Gesperrt</span>', unsafe_allow_html=True)
                        st.link_button("🛒 Im Shop freischalten", f"/?u={twitch_username}", use_container_width=True)

    # --- Tab 2: Stats ---
    with t_stats:
        st.subheader("📈 Deine Streamdex-Statistiken")
        if not stats_data:
            st.info("Noch keine statistischen Daten vorhanden.")
        else:
            s_cols = st.columns(3)
            for i, (k, label) in enumerate(STAT_KEYS.items()):
                val = int(stats_data.get(k) or 0)
                s_cols[i % 3].metric(label, f"{val:,}".replace(",", "."))

    # --- Tab 3: Verlauf ---
    with t_hist:
        st.subheader("📅 Verlauf")
        history = _load_history(authed_tid)
        if len(history) < 2:
            st.info("Noch kein Verlauf vorhanden. Die App speichert ab jetzt täglich deinen Stand – "
                    "nach dem zweiten Tag erscheinen hier die ersten Balken.")
        else:
            col_a, col_b = st.columns([2, 1])
            h_key = col_a.selectbox("Kennzahl", list(HISTORY_LABELS), format_func=lambda k: HISTORY_LABELS[k], key="hist_key")
            h_days = col_b.radio("Zeitraum", [7, 30, 90], index=1, format_func=lambda d: f"{d} Tage", horizontal=True, key="hist_days")
            series = _daily_series(history, h_key, h_days)
            total = int(series.sum())
            m1, m2, m3 = st.columns(3)
            m1.metric(f"Summe ({h_days} Tage)", _de(total))
            m2.metric("Ø pro Tag", f"{total / h_days:.1f}".replace(".", ","))
            m3.metric("Bester Tag", f"{series.idxmax():%d.%m.} · {_de(int(series.max()))}" if total else "–")
            st.bar_chart(series, height=300)
            st.caption("Tage, an denen die App nicht lief, zeigen 0 – ihre Aktivität wird dem nächsten Tag mit Daten zugerechnet.")

    # --- Tab: Giveaway-Verlauf ---
    with t_gw:
        _render_giveaway_tab(authed_tid)

    # --- Tab 4: Support ---
    with t_support:
        st.subheader("💬 Direkt-Support")
        chat_box = st.container(height=400, border=True)
        with chat_box:
            if not msgs:
                st.caption("Noch keine Nachrichten vorhanden.")
            for m in msgs:
                is_admin = m.get("sender") == "admin"
                with st.chat_message("assistant" if is_admin else "user"):
                    _is_new = m in unread
                    st.caption(f"{'🆕 ' if _is_new else ''}{'Support' if is_admin else twitch_username} · {_fmt_ts(m.get('ts'))}")
                    st.write(m.get("text", ""))

        prompt = st.chat_input("Nachricht an den Support senden ...")
        if prompt:
            _send_message(authed_tid, twitch_username, prompt)
            _mark_support_read(authed_tid, msgs)   # wer antwortet, hat die bisherigen Antworten gelesen
            st.rerun()

    # --- Tab 5: Konto & Datenschutz ---
    with t_acct:
        _render_account_tab(authed_tid, twitch_username, bool(is_online))
