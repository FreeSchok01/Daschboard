"""TwitchHub Admin-Dashboard & Public Apps (Streamlit Community Cloud)

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

from admin_users import render_user_admin
from beta_apply import admin_beta_applications, render_beta_apply
from feedback_inbox import feedback_panel, new_count
from creator_profile import render_public_profile
from events import render_public_events, render_public_event
from lurk import lurk_panel
from shop import admin_beta_panel, admin_coupon_panel, admin_shop_panel, handle_paypal_return, render_shop, render_tour_skip
from stats_panel import stats_panel
from streamer_dashboard import handle_twitch_oauth_callback, has_active_streamer_login, render_streamer_dashboard
from privacy_security import admin_session_is_valid, safe_exception_label
from supporter import admin_supporter_panel, partner_codes_view, supporter_login, team_chat_panel
from theme import apply_theme, header_html
from vacation import start_vacation_bot, vacation_panel


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
    "raffel": "🎫 Raffel (!raffel)",
    "gambel": "🎲 Gambel",
    "hilo": "🃏 Hi-Lo",
    "raffle": "🎟️ Punkte-Raffle",
    "fishing": "🎣 Angeln/Kraken",
    "mining": "⛏️ Minen",
    "farming": "🌱 Farm",
    "race": "🏎️ Sim Racing",
    "arena": "🚶 Arena",
}
# Streamdex OS: Tools der oberen Leiste (weitere Tools hier ergänzen)
TOOLS = {"streamdex": "⚡ StreamDex", "lurk": "👁️ Lurk"}

OPT_DEFAULT = "➖ wie global"
OPT_ON = "✅ frei"
OPT_OFF = "⛔ gesperrt"


# ----------------------------------------------------------------------------
# Zugang: Passwort-Schutz (Streamlit-Community-Cloud-Apps sind sonst per URL erreichbar)
# ----------------------------------------------------------------------------
ADMIN_SESSION_TTL_S = 4 * 60 * 60
ADMIN_MAX_ATTEMPTS = 5
ADMIN_LOCKOUT_S = 5 * 60


def require_login():
    """Require a time-limited admin session and throttle repeated failures per browser session."""
    now = time.time()
    if st.session_state.get("auth_ok"):
        if admin_session_is_valid(
            st.session_state.get("admin_authenticated_at"), now, ADMIN_SESSION_TTL_S
        ):
            return
        st.session_state.pop("auth_ok", None)
        st.session_state.pop("admin_authenticated_at", None)

    try:
        locked_until = float(st.session_state.get("admin_lockout_until") or 0)
    except (TypeError, ValueError):
        locked_until = 0
    if locked_until > now:
        st.error("Zu viele Fehlversuche. Bitte warte einige Minuten und versuche es erneut.")
        st.stop()
    if locked_until:
        st.session_state.pop("admin_lockout_until", None)
        st.session_state.pop("admin_failed_attempts", None)

    try:
        expected = str(st.secrets["admin"]["password"])
    except Exception:
        st.error("Die Admin-Anmeldung ist nicht konfiguriert. Bitte prüfe die Server-Secrets.")
        st.stop()
    apply_theme()
    st.markdown(header_html("ADMIN LOGIN", "LOCKED"), unsafe_allow_html=True)
    with st.form("login"):
        pw = st.text_input("Passwort", type="password")
        if st.form_submit_button("Anmelden"):
            if hmac.compare_digest(pw.encode("utf-8"), expected.encode("utf-8")):
                st.session_state["auth_ok"] = True
                st.session_state["admin_authenticated_at"] = now
                st.session_state.pop("admin_failed_attempts", None)
                st.session_state.pop("admin_lockout_until", None)
                st.rerun()
            attempts = int(st.session_state.get("admin_failed_attempts") or 0) + 1
            if attempts >= ADMIN_MAX_ATTEMPTS:
                st.session_state["admin_failed_attempts"] = 0
                st.session_state["admin_lockout_until"] = now + ADMIN_LOCKOUT_S
                st.error("Zu viele Fehlversuche. Die Anmeldung ist für fünf Minuten gesperrt.")
            else:
                st.session_state["admin_failed_attempts"] = attempts
                st.error("Falsches Passwort.")
            time.sleep(0.35)
    st.stop()


# ----------------------------------------------------------------------------
# Firebase
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _connect_firebase():
    try:
        return firebase_admin.get_app()
    except ValueError:
        if "firebase_json" in st.secrets:
            try:
                info = json.loads(st.secrets["firebase_json"])
            except Exception:
                st.error("`firebase_json` in den Secrets ist kein gültiges JSON. Den Dateiinhalt komplett und unverändert einfügen.")
                st.stop()
        else:
            info = dict(st.secrets["firebase"])
        pk = str(info.get("private_key", "")).strip().strip('"').strip("'")
        pk = pk.replace("\\n", "\n").replace("\r\n", "\n")
        info["private_key"] = pk + "\n" if not pk.endswith("\n") else pk
        if not (pk.startswith("-----BEGIN PRIVATE KEY-----") and "-----END PRIVATE KEY-----" in pk):
            st.error("Der `private_key` in den Secrets ist unvollständig oder beschädigt.")
            st.stop()
        try:
            cred = credentials.Certificate(info)
        except ValueError:
            st.error("Der `private_key` konnte nicht gelesen werden.")
            st.stop()
        return firebase_admin.initialize_app(cred, {"databaseURL": st.secrets["firebase_db"]["database_url"]})


def init_firebase():
    """Verbindet Firebase und stellt sicher, dass der StreamDex Bot (Urlaubsmodus) im Hintergrund läuft."""
    app = _connect_firebase()
    try:
        start_vacation_bot(GAMES)
    except Exception as e:
        print(f"StreamDex Bot konnte nicht gestartet werden ({safe_exception_label(e)})")
    return app


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


def _p(ns=""):
    return f"{ns}/" if ns else ""


def load_streamers(ns=""):
    presence = db.reference(f"{_p(ns)}presence").get() or {}
    meta = db.reference(f"{_p(ns)}chat_meta").get() or {}
    read = db.reference(f"{_p(ns)}admin_state/read").get() or {}
    bans_tw = db.reference("bans/twitch").get() or {}
    bans_hw = db.reference("bans/hwid").get() or {}
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
        hw = [h for h in (p.get("hw_machine"), p.get("hw_board")) if isinstance(h, str) and len(h) == 64]
        banned = tid in bans_tw
        hw_banned = any(h in bans_hw for h in hw)
        rows.append({
            "banned": banned,
            "hw_banned": hw_banned and not banned,
            "blocked": p.get("status") == "blocked",
            "hw": hw,
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


def load_messages(tid, ns=""):
    data = db.reference(f"{_p(ns)}chats/{tid}/messages").order_by_child("ts").limit_to_last(300).get() or {}
    msgs = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    msgs.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]))
    return msgs


def send_admin_message(tid, text, name=ADMIN_NAME, ns=""):
    text = text.strip()[:2000]
    if not text:
        return
    db.reference(f"{_p(ns)}chats/{tid}/messages").push({"sender": "admin", "name": name, "text": text, "ts": SERVER_TS})
    db.reference(f"{_p(ns)}chat_meta/{tid}").update({"last_ts": SERVER_TS, "last_sender": "admin", "last_text": text[:100]})


def mark_read(tid, up_to_ts, ns=""):
    if up_to_ts:
        db.reference(f"{_p(ns)}admin_state/read/{tid}").set(int(up_to_ts))


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
@st.fragment(run_every=LIST_REFRESH_SECONDS)
def streamer_list(search, only_online, ns=""):
    sel_key = f"selected_tid_{ns}" if ns else "selected_tid"
    try:
        rows = load_streamers(ns)
    except Exception as e:
        st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
        return
    online_count = sum(1 for r in rows if r["online"])
    st.caption(f"🟢 {online_count} online · {len(rows)} registriert")
    q = (search or "").strip().lower()
    shown = [r for r in rows if (not q or q in r["name"].lower()) and (r["online"] or not only_online)]
    if not shown:
        st.info("Keine Streamer gefunden.")
    for r in shown:
        icon = "🚫" if r["banned"] else "⚠️" if r["hw_banned"] else "🟢" if r["online"] else "⚪"
        badge = " 🔴" if r["unread"] else ""
        label = f"{icon} {r['name']}{badge} · {r['version']} · {fmt_ago(r['age'])}"
        selected = st.session_state.get(sel_key) == r["tid"]
        if st.button(label, key=f"sel_{ns}_{r['tid']}", use_container_width=True, type="primary" if selected else "secondary"):
            st.session_state[sel_key] = r["tid"]
            st.rerun(scope="app")


@st.fragment(run_every=CHAT_REFRESH_SECONDS)
def chat_messages(tid, ns=""):
    try:
        msgs = load_messages(tid, ns)
    except Exception as e:
        st.error("Der Support-Chat konnte nicht geladen werden. Bitte versuche es erneut.")
        return
    box = st.container(height=520, border=True)
    with box:
        if not msgs:
            st.caption("Noch keine Nachrichten.")
        for m in msgs:
            is_bot = m.get("sender") == "bot"        # automatische Antwort des StreamDex Bots (Urlaubsmodus)
            is_admin = m.get("sender") == "admin" or is_bot
            with st.chat_message("assistant" if is_admin else "user"):
                st.caption(f"{'🤖 ' if is_bot else ''}{m.get('name') or ('Support' if is_admin else 'Streamer')} · {fmt_ts(m.get('ts'))}" + (" · automatisch" if is_bot else ""))
                st.write(m.get("text", ""))
    if msgs:
        mark_read(tid, max(int(m.get("ts") or 0) for m in msgs), ns)


def chat_panel(rows_by_tid, sender_name=ADMIN_NAME, allow_actions=True, ns=""):
    tid = st.session_state.get(f"selected_tid_{ns}" if ns else "selected_tid")
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
            send_admin_message(tid, prompt, sender_name, ns)
        except Exception as e:
            st.error("Die Nachricht konnte nicht gesendet werden. Bitte versuche es erneut.")
    with messages_area:
        chat_messages(tid, ns)

    if allow_actions:
        with st.expander("⚙️ Aktionen"):
            st.caption("Setzt die Geräte-Bindung des Streamers zurück.")
            confirm = st.checkbox("Ja, Bindung wirklich zurücksetzen", key=f"confirm_{ns}_{tid}")
            if st.button("🔓 Geräte-Bindung zurücksetzen", disabled=not confirm, key=f"reset_{ns}_{tid}"):
                db.reference(f"{_p(ns)}presence/{tid}/uid").delete()
                st.success("Zurückgesetzt.")


def games_panel():
    st.caption("Alle Games sind standardmäßig **gesperrt**.")
    try:
        g_global = db.reference("game_flags/global").get() or {}
        g_streamers = db.reference("game_flags/streamers").get() or {}
        rows = load_streamers()
    except Exception as e:
        st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
        return

    st.subheader("🌍 Global")
    gl_df = pd.DataFrame([{k: bool(g_global.get(k, False)) for k in GAMES}])
    gl_edit = st.data_editor(gl_df, hide_index=True, use_container_width=True, key="gl_editor", column_config={k: st.column_config.CheckboxColumn(v) for k, v in GAMES.items()})
    if st.button("💾 Global speichern", key="save_global"):
        db.reference("game_flags/global").set({k: bool(gl_edit.iloc[0][k]) for k in GAMES})
        st.success("Global gespeichert.")
        st.rerun()

    st.subheader("👤 Pro Streamer")
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


def ban_streamer(row, reason, with_hw=True):
    reason = (reason or "").strip()[:300] or "Kein Grund angegeben."
    db.reference(f"bans/twitch/{row['tid']}").set({"reason": reason, "name": row["name"], "ts": SERVER_TS})
    if with_hw:
        for h in row["hw"]:
            db.reference(f"bans/hwid/{h}").set({"reason": reason, "tid": row["tid"], "name": row["name"], "ts": SERVER_TS})


def unban_streamer(tid):
    db.reference(f"bans/twitch/{tid}").delete()
    for h, v in (db.reference("bans/hwid").get() or {}).items():
        if isinstance(v, dict) and str(v.get("tid")) == str(tid):
            db.reference(f"bans/hwid/{h}").delete()


def bans_panel(ns=""):
    try:
        rows = load_streamers(ns)
        bans_tw = db.reference("bans/twitch").get() or {}
        bans_hw = db.reference("bans/hwid").get() or {}
    except Exception as e:
        st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
        return

    st.subheader("🚫 Streamer ausschließen")
    candidates = [r for r in rows if not r["banned"]]
    if not candidates:
        st.info("Keine Streamer zum Ausschließen vorhanden.")
    else:
        by_label = {f"{r['name']} ({r['tid']})": r for r in candidates}
        choice = st.selectbox("Streamer", list(by_label), key="ban_pick")
        row = by_label[choice]
        reason = st.text_input("Grund (sieht der Streamer)", key="ban_reason", max_chars=300)
        with_hw = st.checkbox("Hardware mitsperren", value=True, key="ban_hw")
        confirm = st.checkbox(f"Ja, {row['name']} wirklich ausschließen", key="ban_confirm")
        if st.button("🚫 Ausschließen", type="primary", disabled=not confirm, key="ban_go"):
            ban_streamer(row, reason, with_hw)
            st.success(f"{row['name']} wurde ausgeschlossen.")
            st.rerun()

    st.subheader("📋 Aktive Sperren")
    if not bans_tw:
        st.info("Keine aktiven Sperren.")
    for tid, b in bans_tw.items():
        b = b if isinstance(b, dict) else {}
        n_hw = sum(1 for v in bans_hw.values() if isinstance(v, dict) and str(v.get("tid")) == str(tid))
        c1, c2 = st.columns([5, 1])
        c1.write(f"🚫 **{b.get('name') or tid}** (`{tid}`) · seit {fmt_ts(b.get('ts'))} · {n_hw} Gerät(e) · Grund: {b.get('reason', '')}")
        if c2.button("Aufheben", key=f"unban_{tid}"):
            unban_streamer(tid)
            st.success("Sperre aufgehoben.")
            st.rerun()


def _fb_label(tool="streamdex"):
    n = new_count(tool)
    return f"🐞 Bugs & Ideen ({n})" if n else "🐞 Bugs & Ideen"


def support_main():
    st.set_page_config(page_title="Streamdex Support", page_icon="🛟", layout="wide")
    init_firebase()
    apply_theme()
    me = supporter_login()
    top_l, top_r = st.columns([6, 1], vertical_alignment="center")
    top_l.markdown(header_html(f"SUPPORT · {me['name']}"), unsafe_allow_html=True)
    if top_r.button("Abmelden"):
        st.session_state.clear()
        st.rerun()

    tab_chat, tab_games, tab_codes, tab_beta, tab_fb, tab_team = st.tabs(
        ["💬 Live-Chat", "🎮 Freigaben", "🎟️ Partner-Codes", "🧪 Beta", _fb_label(), "💭 Team-Chat"]
    )
    with tab_chat:
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
            chat_panel(rows_by_tid, sender_name=me["name"], allow_actions=False)
    with tab_games:
        games_panel()
    with tab_codes:
        try:
            partner_codes_view()
        except Exception as e:
            st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
    with tab_beta:
        try:
            t_apps, t_testers = st.tabs(["📝 Bewerbungen", "🧪 Beta-Tester"])
            with t_apps:
                admin_beta_applications(GAMES, me["name"], is_admin=False)
            with t_testers:
                admin_beta_panel(GAMES, load_streamers())
        except Exception as e:
            st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
    with tab_fb:
        feedback_panel(me["name"], is_admin=False, tool="streamdex")
    with tab_team:
        team_chat_panel(me["name"])


def main():
    # PayPal leitet den Käufer nach Freigabe oder Abbruch zurück zum StreamDex-Shop.
    # Capture und Freischaltung laufen serverseitig, bevor normale Seiten gerendert werden.
    if "shop" in st.query_params and "paypal_cancel" in st.query_params:
        st.set_page_config(page_title="StreamDex Shop", page_icon="🛒", layout="wide")
        init_firebase()
        order_code = str(st.query_params.get("order_ref", "") or "").strip().upper()
        username = str(st.query_params.get("u", "") or "")
        if order_code.startswith("SDX-") and len(order_code) == 10:
            pending = db.reference(f"shop/orders/{order_code}").get()
            if (isinstance(pending, dict) and pending.get("status") == "pending"
                    and pending.get("payment_provider") == "paypal"):
                st.session_state["cart_tid"] = str(pending.get("tid") or "")
                st.session_state["order"] = (order_code, str(pending.get("price") or "0.00"))
        st.session_state["flash"] = "Die PayPal-Zahlung wurde abgebrochen. Es wurde nichts freigeschaltet."
        st.query_params.clear()
        st.query_params["shop"] = "1"
        if username:
            st.query_params["u"] = username
        st.rerun()
        return

    if "shop" in st.query_params and "paypal_return" in st.query_params and "token" in st.query_params:
        st.set_page_config(page_title="StreamDex Shop", page_icon="🛒", layout="wide")
        init_firebase()
        paypal_order_id = str(st.query_params.get("token", "") or "")
        payer_id = str(st.query_params.get("PayerID", "") or "")
        order_code = str(st.query_params.get("order_ref", "") or "").strip().upper()
        username = str(st.query_params.get("u", "") or "")
        ok, message = handle_paypal_return(paypal_order_id, payer_id)
        st.session_state["flash"] = message
        if order_code.startswith("SDX-") and len(order_code) == 10:
            returned = db.reference(f"shop/orders/{order_code}").get()
            if isinstance(returned, dict) and str(returned.get("tid") or ""):
                st.session_state["cart_tid"] = str(returned.get("tid"))
                if ok and returned.get("status") == "paid":
                    st.session_state["download_order_code"] = order_code
                elif returned.get("status") == "pending":
                    st.session_state["order"] = (order_code, str(returned.get("price") or "0.00"))
        st.query_params.clear()
        st.query_params["shop"] = "1"
        if username:
            st.query_params["u"] = username
        st.rerun()
        return

    # Twitch leitet den Authorization-Code an die App-Startseite zurück.
    # Callback vor allen anderen Routen verarbeiten, damit Code und State nie als Shop-URL landen.
    if "code" in st.query_params or "error" in st.query_params:
        st.set_page_config(page_title="StreamDex Twitch Login", page_icon="🟣", layout="wide")
        # The one-time OAuth state is checked against Firebase before exchanging the code.
        init_firebase()
        if handle_twitch_oauth_callback():
            # Normalize the browser URL after Twitch has returned. The OAuth
            # redirect URI stays at the registered site root; the app then
            # always lands on the explicit dashboard route.
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        return

    if "profile" in st.query_params and str(st.query_params.get("profile", "")) != "1":
        # Öffentliche Creator-Seite: nur ausdrücklich veröffentlichte Profile anzeigen.
        st.set_page_config(page_title="StreamDex Creator-Profil", page_icon="♙", layout="wide")
        init_firebase()
        apply_theme()
        render_public_profile(str(st.query_params.get("profile", "")))
        return

    if "support" in st.query_params:           # Supporter: /?support=1
        support_main()
        return
    if "events" in st.query_params:             # Öffentlich: Eventübersicht /?events=1
        st.set_page_config(page_title="StreamDex Events", page_icon="🎉", layout="wide")
        init_firebase()
        apply_theme()
        render_public_events()
        return
    if "event" in st.query_params:               # Öffentlich: Eventseite /?event=<id>
        st.set_page_config(page_title="StreamDex Event", page_icon="🎉", layout="wide")
        init_firebase()
        apply_theme()
        render_public_event(str(st.query_params.get("event", "")))
        return
    if "beta" in st.query_params:              # Beta-Bewerbung nur nach Login
        st.set_page_config(page_title="StreamDex", page_icon="🧪", layout="wide")
        active_login = has_active_streamer_login()
        if not active_login:
            had_session = bool(st.session_state.get("authenticated_tid"))
            for key in (
                "authenticated_tid", "authenticated_at", "auth_method", "twitch_profile",
                "twitch_oauth_tid", "twitch_oauth_access_token", "twitch_oauth_refresh_token",
                "twitch_oauth_expires_at", "twitch_oauth_scopes",
                "acct_data", "dashboard_reauth_required",
            ):
                st.session_state.pop(key, None)
            if had_session:
                st.session_state["session_expired"] = True
        init_firebase()
        apply_theme()
        if active_login:
            render_beta_apply()
        else:
            # Ein direkter Aufruf von /?beta=1 zeigt nur die Login-Seite,
            # nicht das Bewerbungsformular oder Download-Links.
            render_streamer_dashboard(GAMES)
        return
    if "skip" in st.query_params:              # Öffentlich: Rundgang überspringen /?skip=1
        st.set_page_config(page_title="Streamdex Rundgang überspringen", page_icon="⏭")
        init_firebase()
        apply_theme()
        render_tour_skip()
        return
    # Öffentlicher Shop nur bei ausdrücklichem Aufruf oder für Shop-Kauf-/Freischaltlinks.
    # Die normale Startseite soll die Streamer-Funktion zeigen, nicht den Shop.
    if "shop" in st.query_params or "u" in st.query_params or "gift" in st.query_params:
        st.set_page_config(page_title="Streamdex Shop", page_icon="🛒")
        init_firebase()
        apply_theme()
        render_shop(GAMES)
        return

    # Standard-Startseite und /?dashboard=1: Streamer-Dashboard mit direktem Twitch-OAuth.
    # Der Callback wird oben verarbeitet; danach landen erfolgreiche Logins hier.
    if ("dashboard" in st.query_params
            or "streamer" in st.query_params
            or "admin" not in st.query_params):
        st.set_page_config(page_title="Streamdex Dashboard", page_icon="📊", layout="wide")
        init_firebase()
        apply_theme()
        render_streamer_dashboard(GAMES)
        return

    st.set_page_config(page_title="TwitchHub Admin", page_icon="🛟", layout="wide")
    require_login()
    init_firebase()
    apply_theme()

    top_l, top_r = st.columns([6, 1], vertical_alignment="center")
    top_l.markdown(header_html("ADMIN"), unsafe_allow_html=True)
    if top_r.button("Abmelden"):
        st.session_state.clear()
        st.rerun()

    with st.container(key="os_nav"):
        tool = st.radio("Tool", list(TOOLS), format_func=TOOLS.get, horizontal=True, label_visibility="collapsed", key="os_tool")
    if tool == "lurk":
        lurk_panel(
            load_streamers=load_streamers,
            streamer_list=streamer_list,
            chat_panel=chat_panel,
            bans_panel=bans_panel,
            fb_label=lambda: _fb_label("lurk"),
            me=ADMIN_NAME,
        )
        return

    tab_support, tab_users, tab_stats, tab_games, tab_shop, tab_coupons, tab_beta, tab_fb, tab_bans, tab_sups, tab_team = st.tabs(
        ["💬 Support", "👤 User", "📊 Statistiken", "🎮 Game-Freigaben", "🛒 Shop", "🎟️ Gutscheine", "🧪 Beta", _fb_label(), "🚫 Sperren", "👥 Supporter", "💭 Team-Chat"]
    )
    with tab_support:
        try:
            vacation_panel(ADMIN_NAME)
        except Exception as e:
            st.error("Der Urlaubsmodus ist gerade nicht verfügbar. Bitte versuche es erneut.")
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
    with tab_users:
        try:
            render_user_admin()
        except Exception as e:
            st.error(f"User-Übersicht konnte nicht geladen werden: {type(e).__name__}")
    with tab_stats:
        try:
            stats_panel(load_streamers(), GAMES)
        except Exception as e:
            st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
    with tab_games:
        games_panel()
    with tab_shop:
        admin_shop_panel(GAMES)
    with tab_coupons:
        admin_coupon_panel()
    with tab_beta:
        try:
            t_apps, t_testers = st.tabs(["📝 Bewerbungen", "🧪 Beta-Tester"])
            with t_apps:
                admin_beta_applications(GAMES, ADMIN_NAME, is_admin=True)
            with t_testers:
                admin_beta_panel(GAMES, load_streamers())
        except Exception as e:
            st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
    with tab_fb:
        feedback_panel(ADMIN_NAME, is_admin=True, tool="streamdex")
    with tab_bans:
        bans_panel()
    with tab_sups:
        try:
            admin_supporter_panel()
        except Exception as e:
            st.error("Die Aktion konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden. Bitte versuche es erneut.")
    with tab_team:
        team_chat_panel(ADMIN_NAME)


main()
