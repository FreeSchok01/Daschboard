import datetime
import time
import streamlit as st
import firebase_admin
from firebase_admin import credentials, db

# Seiten-Konfiguration
st.set_page_config(
    page_title="TwitchHub Admin Dashboard",
    page_icon="🛟",
    layout="wide"
)

# --- Hilfsfunktionen & Firebase Initialisierung ---

def init_firebase():
    """Initialisiert Firebase mit den Anmeldedaten aus den Streamlit Secrets."""
    if not firebase_admin._apps:
        try:
            firebase_config = {
                "type": st.secrets["firebase"]["type"],
                "project_id": st.secrets["firebase"]["project_id"],
                "private_key_id": st.secrets["firebase"]["private_key_id"],
                "private_key": st.secrets["firebase"]["private_key"].replace('\\n', '\n'),
                "client_email": st.secrets["firebase"]["client_email"],
                "client_id": st.secrets["firebase"]["client_id"],
                "auth_uri": st.secrets["firebase"]["auth_uri"],
                "token_uri": st.secrets["firebase"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["firebase"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"],
            }
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred, {
                'databaseURL': st.secrets["firebase_db"]["database_url"]
            })
        except Exception as e:
            st.error(f"Fehler bei der Firebase-Initialisierung: {e}")

def require_login():
    """Einfache passwortbasierte Authentifizierung über Streamlit Secrets."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 TwitchHub Admin Login")
        password = st.text_input("Admin-Passwort", type="password")
        if st.button("Anmelden"):
            if "admin" in st.secrets and password == st.secrets["admin"]["password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Falsches Passwort.")
        st.stop()

def fmt_ts(ts):
    """Formatiert einen Unix-Timestamp in eine lesbare Uhrzeit."""
    if not ts:
        return ""
    try:
        ts_int = int(ts)
        if ts_int < 10000000000:
            ts_int *= 1000
        dt = datetime.datetime.fromtimestamp(ts_int / 1000)
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ""

def fmt_ago(seconds):
    """Formatiert Sekunden in eine 'vor X Minuten'-Anzeige."""
    if seconds is None:
        return "unbekannt"
    try:
        sec = int(seconds)
        if sec < 60:
            return f"vor {sec}s"
        elif sec < 3600:
            return f"vor {sec // 60}m"
        else:
            return f"vor {sec // 3600}h"
    except Exception:
        return "unbekannt"

def load_streamers():
    """Lädt alle Streamer flexibel aus der Firebase Realtime Database."""
    ref = db.reference("presence")
    data = ref.get()
    if not data:
        return []
    
    streamers = []
    now = time.time()
    for tid, info in data.items():
        if not isinstance(info, dict):
            streamers.append({
                "tid": tid,
                "name": f"Streamer {tid}",
                "version": "?",
                "online": True,
                "age": 0
            })
            continue
            
        # Sucht nach allen gängigen Schlüssel-Varianten (Groß-/Kleinschreibung)
        name = (
            info.get("name") or 
            info.get("Name") or 
            info.get("username") or 
            info.get("Username") or 
            info.get("streamer") or 
            f"Streamer {tid}"
        )
        
        version = (
            info.get("version") or 
            info.get("Version") or 
            info.get("ver") or 
            "?"
        )
        
        last_seen = info.get("last_seen") or info.get("LastSeen") or info.get("ts") or 0
        try:
            ls_int = int(last_seen)
            last_seen_sec = ls_int / 1000 if ls_int > 9999999999 else ls_int
        except Exception:
            last_seen_sec = 0

        age = int(now - last_seen_sec) if last_seen_sec else 0
        is_online = age < 300  # 5 Minuten Puffer

        streamers.append({
            "tid": tid,
            "name": name,
            "version": version,
            "online": is_online,
            "age": age
        })
    return streamers

def streamer_list(search_query, only_online):
    """Zeigt die Streamer-Liste in der linken Spalte an."""
    try:
        streamers = load_streamers()
    except Exception as e:
        st.error(f"Fehler beim Laden der Streamer: {e}")
        return

    filtered = []
    for s in streamers:
        if only_online and not s["online"]:
            continue
        if search_query and search_query.lower() not in s["name"].lower() and search_query.lower() not in s["tid"].lower():
            continue
        filtered.append(s)

    if not filtered:
        st.info("Keine Streamer gefunden.")
        return

    for s in filtered:
        status_icon = "🟢" if s["online"] else "⚪"
        label = f"{status_icon} {s['name']} (`{s['tid']}`)"
        if st.button(label, key=f"btn_{s['tid']}", use_container_width=True):
            st.session_state["selected_tid"] = s["tid"]
            st.rerun()

def chat_messages(tid):
    """Lädt und zeigt Chat-Nachrichten flexibel an."""
    chat_ref = db.reference(f"chats/{tid}")
    messages_data = chat_ref.get()
    
    if not messages_data:
        st.info("Noch keine Nachrichten in diesem Chat.")
        return []

    msgs = []
    for msg_id, m in messages_data.items():
        if isinstance(m, dict):
            msgs.append(m)
        elif isinstance(m, list):
            for item in m:
                if isinstance(item, dict):
                    msgs.append(item)
    
    try:
        msgs.sort(key=lambda x: int(x.get("ts") or x.get("Timestamp") or 0))
    except Exception:
        pass

    for m in msgs:
        sender = str(m.get("sender") or m.get("Sender") or "").lower()
        is_admin = sender == "admin" or sender == "support"
        
        msg_name = m.get("name") or m.get("Name") or ("Support" if is_admin else "Streamer")
        msg_text = m.get("text") or m.get("Text") or m.get("message") or ""
        msg_ts = m.get("ts") or m.get("Timestamp") or 0

        with st.chat_message("assistant" if is_admin else "user"):
            st.caption(f"{msg_name} · {fmt_ts(msg_ts)}")
            st.write(msg_text)
            
    return msgs

def mark_read(tid, max_ts):
    pass

def send_admin_message(tid, text):
    """Sendet eine Nachricht vom Admin an den Streamer."""
    chat_ref = db.reference(f"chats/{tid}")
    new_msg_ref = chat_ref.push()
    new_msg_ref.set({
        "sender": "admin",
        "name": "Support",
        "text": text,
        "ts": int(time.time() * 1000)
    })

# --- Haupt-UI ---

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
    
    with messages_area:
        msgs = chat_messages(tid)

    prompt = st.chat_input(f"Antwort an {name} ...")
    if prompt:
        try:
            send_admin_message(tid, prompt)
            st.rerun()
        except Exception as e:
            st.error(f"Senden fehlgeschlagen: {e}")

    if msgs:
        try:
            mark_read(tid, max(int(m.get("ts") or 0) for m in msgs))
        except Exception:
            pass
 
    with st.expander("⚙️ Aktionen"):
        st.caption(
            "Setzt die Geräte-Bindung des Streamers zurück (z.B. nach Neuinstallation oder PC-Wechsel), "
            "sodass sich beim nächsten Start ein neues Gerät registrieren kann."
        )
        confirm = st.checkbox("Ja, Bindung wirklich zurücksetzen", key=f"confirm_{tid}")
        if st.button("🔓 Geräte-Bindung zurücksetzen", disabled=not confirm, key=f"reset_{tid}"):
            db.reference(f"presence/{tid}/uid").delete()
            st.success("Zurückgesetzt.")
 
def main():
    require_login()
    init_firebase()
 
    top_l, top_r = st.columns([6, 1])
    top_l.title("🛟 TwitchHub Admin")
    if top_r.button("Abmelden"):
        st.session_state.clear()
        st.rerun()
 
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
 
if __name__ == "__main__":
    main()
