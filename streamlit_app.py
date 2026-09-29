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
            # Versuche, Firebase über st.secrets zu initialisieren
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
                'databaseURL': st.secrets["firebase"]["database_url"]
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
            # Prüft gegen secrets.toml (admin_password)
            if "admin_password" in st.secrets and password == st.secrets["admin_password"]:
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
    dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
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
    """Lädt alle aktiven Streamer aus der Firebase Realtime Database."""
    ref = db.reference("presence")
    data = ref.get()
    if not data:
        return []
    
    streamers = []
    now = time.time()
    for tid, info in data.items():
        last_seen = info.get("last_seen", 0)
        # Beispielhafter Online-Status (wenn innerhalb der letzten 2 Minuten aktiv)
        age = int(now - (last_seen / 1000)) if last_seen else 9999
        is_online = age < 120

        streamers.append({
            "tid": tid,
            "name": info.get("name", tid),
            "version": info.get("version", "?"),
            "online": is_online,
            "age": age
        })
    return streamers

def streamer_list(search_query, only_online):
    """Zeigt die Liste der Streamer in der linken Spalte an."""
    try:
        streamers = load_streamers()
    except Exception as e:
        st.error(f"Fehler beim Laden der Streamer: {e}")
        return

    # Filter anwenden
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
    """Lädt und zeigt die Chat-Nachrichten für einen ausgewählten Streamer an."""
    chat_ref = db.reference(f"chats/{tid}")
    messages_data = chat_ref.get()
    
    if not messages_data:
        st.info("Noch keine Nachrichten in diesem Chat.")
        return []

    msgs = []
    for msg_id, m in messages_data.items():
        if isinstance(m, dict):
            msgs.append(m)
    
    # Nach Timestamp sortieren
    msgs.sort(key=lambda x: int(x.get("ts", 0)))

    for m in msgs:
        is_admin = m.get("sender") == "admin"
        with st.chat_message("assistant" if is_admin else "user"):
            st.caption(f"{m.get('name') or ('Support' if is_admin else 'Streamer')} · {fmt_ts(m.get('ts'))}")
            st.write(m.get("text", ""))
            
    return msgs

def mark_read(tid, max_ts):
    """Markiert Nachrichten als gelesen (optional anpassbar)."""
    # Hier kann Firebase-Logik zum Aktualisieren des Lesestatus implementiert werden
    pass

def send_admin_message(tid, text):
    """Sendet eine Nachricht vom Admin an den Streamer in Firebase."""
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
