"""TwitchHub Admin-Dashboard (Streamlit Community Cloud)

Links: alle registrierten Streamer (Online/Offline, Version, letzte Aktivität)
Rechts: Live-Support-Chat mit dem ausgewählten Streamer

Firebase-Zugriff per Service-Account (nur hier, nie in der EXE) aus st.secrets.
"""
import hmac
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
import pandas as pd
import streamlit as st
from firebase_admin import credentials, db

st.set_page_config(page_title="TwitchHub Admin", page_icon="🛟", layout="wide")

TZ = ZoneInfo("Europe/Berlin")
ONLINE_STALE_SECONDS = 150      # 60-s-Heartbeat: >2,5 Intervalle ohne Ping = gilt als offline (z.B. Absturz)
LIST_REFRESH_SECONDS = 10
CHAT_REFRESH_SECONDS = 4
ADMIN_NAME = "Support"
SERVER_TS = {".sv": "timestamp"}

# Muss zu GAME_LABELS in app.py passen (gleiche Schlüssel!)
GAMES = {
    "slot": "🎰 Slot Machine",
    "megaslot": "🎡 Mega Slot",
    "steal": "🕵️ Taschenraub",
    "fishing": "🎣 Angeln/Kraken",
    "mining": "⛏️ Minen",
    "farming": "🌱 Farm",
    "race": "🏎️ Sim Racing",
    "arena": "🚶 Arena",
}
OPT_DEFAULT = "➖ wie global"
OPT_ON = "✅ frei"
OPT_OFF = "⛔ gesperrt"


# ----------------------------------------------------------------------------
# Zugang: Passwort-Schutz (Streamlit-Community-Cloud-Apps sind sonst per URL erreichbar)
# ----------------------------------------------------------------------------
def require_login():
    if st.session_state.get("auth_ok"):
        return
    try:
        expected = st.secrets["admin"]["password"]
    except Exception:
        st.error("`[admin] password` fehlt in den Secrets.")
        st.stop()
    st.title("🛟 TwitchHub Admin")
    with st.form("login"):
        pw = st.text_input("Passwort", type="password")
        if st.form_submit_button("Anmelden"):
            if hmac.compare_digest(pw.encode(), str(expected).encode()):
                st.session_state["auth_ok"] = True
                st.rerun()
            time.sleep(1.0)
            st.error("Falsches Passwort.")
    st.stop()


# ----------------------------------------------------------------------------
# Firebase
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def init_firebase():
    try:
        return firebase_admin.get_app()
    except ValueError:
        if "firebase_json" in st.secrets:
            # Empfohlen: komplette JSON-Datei unverändert als ein Text-Block in den Secrets
            try:
                info = json.loads(st.secrets["firebase_json"])
            except Exception:
                st.error("`firebase_json` in den Secrets ist kein gültiges JSON. Den Dateiinhalt komplett und unverändert einfügen.")
                st.stop()
        else:
            info = dict(st.secrets["firebase"])
        pk = str(info.get("private_key", "")).strip().strip('"').strip("'")
        pk = pk.replace("\\n", "\n").replace("\r\n", "\n")   # doppelt escapte \n und Windows-Zeilenenden reparieren
        info["private_key"] = pk + "\n" if not pk.endswith("\n") else pk
        if not (pk.startswith("-----BEGIN PRIVATE KEY-----") and "-----END PRIVATE KEY-----" in pk):
            st.error(
                "Der `private_key` in den Secrets ist unvollständig oder beschädigt "
                f"(Länge {len(pk)} Zeichen, sollte ca. 1600-1700 haben). "
                "Bitte den kompletten Wert aus der JSON-Datei neu kopieren."
            )
            st.stop()
        try:
            cred = credentials.Certificate(info)
        except ValueError:
            st.error(
                "Der `private_key` konnte nicht gelesen werden. Meist fehlt ein Stück oder es wurde "
                "ein Zeichen verändert. Neuen Schlüssel in Firebase generieren und komplett neu einfügen."
            )
            st.stop()
        return firebase_admin.initialize_app(cred, {"databaseURL": st.secrets["firebase_db"]["database_url"]})


def fmt_ago(seconds):
    if seconds is None:
        return "nie"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"vor {seconds} s"
    if seconds < 3600:
        return f"vor {seconds // 60} min"
    if seconds < 86400:
        return f"vor {seconds // 3600} h"
    return f"vor {seconds // 86400} d"


def fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def load_streamers():
    presence = db.reference("presence").get() or {}
    meta = db.reference("chat_meta").get() or {}
    read = db.reference("admin_state/read").get() or {}
    now_ms = int(time.time() * 1000)
    rows = []
    for tid, p in presence.items():
        if not isinstance(p, dict):
            continue
        last_seen = int(p.get("last_seen") or 0)
        age = (now_ms - last_seen) / 1000 if last_seen else None
        online = p.get("status") == "online" and age is not None and age <= ONLINE_STALE_SECONDS
        m = meta.get(tid) if isinstance(meta.get(tid), dict) else {}
        last_msg_ts = int(m.get("last_ts") or 0)
        unread = m.get("last_sender") == "streamer" and last_msg_ts > int(read.get(tid) or 0)
        rows.append({
            "tid": tid,
            "name": p.get("twitch_username") or tid,
            "version": p.get("app_version") or "?",
            "online": online,
            "age": age,
            "last_seen": last_seen,
            "unread": unread,
            "preview": m.get("last_text", ""),
        })
    rows.sort(key=lambda r: (not r["unread"], not r["online"], -r["last_seen"]))
    return rows


def load_messages(tid):
    data = db.reference(f"chats/{tid}/messages").order_by_child("ts").limit_to_last(300).get() or {}
    msgs = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    msgs.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]))
    return msgs


def send_admin_message(tid, text):
    text = text.strip()[:2000]
    if not text:
        return
    db.reference(f"chats/{tid}/messages").push({"sender": "admin", "name": ADMIN_NAME, "text": text, "ts": SERVER_TS})
    db.reference(f"chat_meta/{tid}").update({"last_ts": SERVER_TS, "last_sender": "admin", "last_text": text[:100]})


def mark_read(tid, up_to_ts):
    if up_to_ts:
        db.reference(f"admin_state/read/{tid}").set(int(up_to_ts))


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
@st.fragment(run_every=LIST_REFRESH_SECONDS)
def streamer_list(search, only_online):
    try:
        rows = load_streamers()
    except Exception as e:
        st.error(f"Firebase-Fehler: {e}")
        return
    online_count = sum(1 for r in rows if r["online"])
    st.caption(f"🟢 {online_count} online · {len(rows)} registriert")
    q = (search or "").strip().lower()
    shown = [r for r in rows if (not q or q in r["name"].lower()) and (r["online"] or not only_online)]
    if not shown:
        st.info("Keine Streamer gefunden.")
    for r in shown:
        icon = "🟢" if r["online"] else "⚪"
        badge = " 🔴" if r["unread"] else ""
        label = f"{icon} {r['name']}{badge} · {r['version']} · {fmt_ago(r['age'])}"
        selected = st.session_state.get("selected_tid") == r["tid"]
        if st.button(label, key=f"sel_{r['tid']}", use_container_width=True, type="primary" if selected else "secondary"):
            st.session_state["selected_tid"] = r["tid"]
            st.rerun(scope="app")


@st.fragment(run_every=CHAT_REFRESH_SECONDS)
def chat_messages(tid):
    try:
        msgs = load_messages(tid)
    except Exception as e:
        st.error(f"Chat konnte nicht geladen werden: {e}")
        return
    box = st.container(height=520, border=True)
    with box:
        if not msgs:
            st.caption("Noch keine Nachrichten.")
        for m in msgs:
            is_admin = m.get("sender") == "admin"
            with st.chat_message("assistant" if is_admin else "user"):
                st.caption(f"{m.get('name') or ('Support' if is_admin else 'Streamer')} · {fmt_ts(m.get('ts'))}")
                st.write(m.get("text", ""))
    if msgs:
        mark_read(tid, max(int(m.get("ts") or 0) for m in msgs))


def chat_panel(rows_by_tid):
    tid = st.session_state.get("selected_tid")
    if not tid:
        st.info("⬅️ Wähle links einen Streamer aus, um den Chat zu öffnen.")
        return
    info = rows_by_tid.get(tid, {})
    name = info.get("name", tid)
    st.subheader(f"💬 {name}")
    st.caption(
        f"Twitch-ID `{tid}` · Version {info.get('version', '?')} · "
        f"{'🟢 online' if info.get('online') else '⚪ offline'} · zuletzt aktiv {fmt_ago(info.get('age'))}"
    )

    messages_area = st.container()
    prompt = st.chat_input(f"Antwort an {name} ...")
    if prompt:
        try:
            send_admin_message(tid, prompt)
        except Exception as e:
            st.error(f"Senden fehlgeschlagen: {e}")
    with messages_area:
        chat_messages(tid)

    with st.expander("⚙️ Aktionen"):
        st.caption(
            "Setzt die Geräte-Bindung des Streamers zurück (z.B. nach Neuinstallation oder PC-Wechsel), "
            "sodass sich beim nächsten Start ein neues Gerät registrieren kann."
        )
        confirm = st.checkbox("Ja, Bindung wirklich zurücksetzen", key=f"confirm_{tid}")
        if st.button("🔓 Geräte-Bindung zurücksetzen", disabled=not confirm, key=f"reset_{tid}"):
            db.reference(f"presence/{tid}/uid").delete()
            st.success("Zurückgesetzt.")


def games_panel():
    st.caption(
        "Alle Games sind standardmäßig **gesperrt**. Freigaben wirken in der App nach spätestens ca. 60 Sekunden "
        "(beim nächsten Heartbeat), ohne Neustart und ohne Update."
    )
    try:
        g_global = db.reference("game_flags/global").get() or {}
        g_streamers = db.reference("game_flags/streamers").get() or {}
        rows = load_streamers()
    except Exception as e:
        st.error(f"Firebase-Fehler: {e}")
        return

    st.subheader("🌍 Global (gilt für alle, sofern nichts anderes eingestellt ist)")
    gl_df = pd.DataFrame([{k: bool(g_global.get(k, False)) for k in GAMES}])
    gl_edit = st.data_editor(
        gl_df, hide_index=True, use_container_width=True, key="gl_editor",
        column_config={k: st.column_config.CheckboxColumn(v) for k, v in GAMES.items()},
    )
    if st.button("💾 Global speichern", key="save_global"):
        db.reference("game_flags/global").set({k: bool(gl_edit.iloc[0][k]) for k in GAMES})
        st.success("Global gespeichert.")
        st.rerun()

    st.subheader("👤 Pro Streamer (überschreibt global)")
    if not rows:
        st.info("Noch keine Streamer registriert.")
        return
    q = st.text_input("Streamer suchen", key="games_search", placeholder="Twitch-Name ...")
    shown = [r for r in rows if not q.strip() or q.strip().lower() in r["name"].lower()]

    def to_opt(v):
        return OPT_ON if v is True else OPT_OFF if v is False else OPT_DEFAULT

    data = []
    for r in shown:
        own = g_streamers.get(r["tid"]) if isinstance(g_streamers.get(r["tid"]), dict) else {}
        row = {"Streamer": r["name"], "Twitch-ID": r["tid"]}
        for k, label in GAMES.items():
            row[label] = to_opt(own.get(k))
        data.append(row)
    df = pd.DataFrame(data)
    cfg = {"Streamer": st.column_config.TextColumn(disabled=True), "Twitch-ID": st.column_config.TextColumn(disabled=True)}
    for label in GAMES.values():
        cfg[label] = st.column_config.SelectboxColumn(label, options=[OPT_DEFAULT, OPT_ON, OPT_OFF], required=True)
    edited = st.data_editor(df, hide_index=True, use_container_width=True, column_config=cfg, key="streamer_games_editor")

    c1, c2 = st.columns([1, 3])
    if c1.button("💾 Streamer speichern", type="primary", key="save_streamers"):
        changed = 0
        for i, r in enumerate(shown):
            new_flags = {}
            for k, label in GAMES.items():
                v = edited.iloc[i][label]
                if v == OPT_ON:
                    new_flags[k] = True
                elif v == OPT_OFF:
                    new_flags[k] = False
            old = g_streamers.get(r["tid"]) if isinstance(g_streamers.get(r["tid"]), dict) else {}
            old = {k: v for k, v in old.items() if k in GAMES and isinstance(v, bool)}
            if new_flags != old:
                ref = db.reference(f"game_flags/streamers/{r['tid']}")
                ref.set(new_flags) if new_flags else ref.delete()
                changed += 1
        st.success(f"{changed} Streamer aktualisiert.")
        st.rerun()
    c2.caption("➖ = es gilt die globale Einstellung · ✅ = für diesen Streamer frei · ⛔ = für diesen Streamer gesperrt")


def main():
    require_login()
    init_firebase()

    top_l, top_r = st.columns([6, 1])
    top_l.title("🛟 TwitchHub Admin")
    if top_r.button("Abmelden"):
        st.session_state.clear()
        st.rerun()

    tab_support, tab_games = st.tabs(["💬 Support", "🎮 Game-Freigaben"])
    with tab_support:
        left, right = st.columns([1, 2], gap="large")
        with left:
            st.subheader("Streamer")
            search = st.text_input("Suche", placeholder="Twitch-Name ...", label_visibility="collapsed")
            only_online = st.toggle("Nur online", value=False)
            streamer_list(search, only_online)
        with right:
            try:
                rows_by_tid = {r["tid"]: r for r in load_streamers()}
            except Exception:
                rows_by_tid = {}
            chat_panel(rows_by_tid)
    with tab_games:
        games_panel()


main()
