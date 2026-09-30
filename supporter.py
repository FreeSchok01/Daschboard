"""Supporter-Bereich: Login, Verwaltung (nur Admin), Team-Chat, Partner-Codes (nur lesen).

Firebase-Struktur:
  supporters/{benutzername} = {name, salt, pw_hash, active, created, last_login, fails, lock_until}
  team_chat/messages/{id}   = {name, text, important, marked_by, ts}
"""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}
TEAM_REFRESH_SECONDS = 4
MAX_FAILS = 5
LOCK_SECONDS = 300
MIN_PW = 8
USER_RE = re.compile(r"^[a-z0-9_-]{3,24}$")


def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def _set_password(user, pw):
    salt = secrets.token_hex(16)
    db.reference(f"supporters/{user}").update(
        {"salt": salt, "pw_hash": _hash(pw, salt), "fails": 0, "lock_until": 0})


# ----------------------------------------------------------------------------
# Login (Supporter)
# ----------------------------------------------------------------------------
def _try_login(username, pw):
    """Gibt den Benutzernamen, 'locked' oder None zurück."""
    u = (username or "").strip().lower()
    if not USER_RE.match(u):
        return None
    rec = db.reference(f"supporters/{u}").get()
    if not isinstance(rec, dict):
        return None
    if float(rec.get("lock_until") or 0) > time.time():
        return "locked"
    ok = (rec.get("active", True) and rec.get("salt") and rec.get("pw_hash")
          and hmac.compare_digest(_hash(pw, rec["salt"]), str(rec["pw_hash"])))
    ref = db.reference(f"supporters/{u}")
    if ok:
        ref.update({"fails": 0, "lock_until": 0, "last_login": SERVER_TS})
        return u
    fails = int(rec.get("fails") or 0) + 1
    if fails >= MAX_FAILS:
        ref.update({"fails": 0, "lock_until": time.time() + LOCK_SECONDS})
    else:
        ref.update({"fails": fails})
    return None


def supporter_login():
    """Zeigt das Login, bis sich ein aktiver Supporter angemeldet hat. Gibt {'user','name'} zurück."""
    u = st.session_state.get("sup_user")
    if u:
        rec = db.reference(f"supporters/{u}").get()        # Deaktivierung wirkt sofort
        if isinstance(rec, dict) and rec.get("active", True):
            return {"user": u, "name": rec.get("name") or u}
        st.session_state.clear()
    st.title("🛟 Streamdex Support")
    with st.form("sup_login"):
        user = st.text_input("Benutzername")
        pw = st.text_input("Passwort", type="password")
        if st.form_submit_button("Anmelden"):
            res = _try_login(user, pw)
            if res == "locked":
                st.error(f"Zu viele Fehlversuche. Bitte in {LOCK_SECONDS // 60} Minuten erneut versuchen.")
            elif res:
                st.session_state["sup_user"] = res
                st.rerun()
            else:
                time.sleep(1.0)
                st.error("Benutzername oder Passwort falsch (oder Zugang deaktiviert).")
    st.stop()


# ----------------------------------------------------------------------------
# Verwaltung (nur Admin-Ansicht)
# ----------------------------------------------------------------------------
def admin_supporter_panel():
    st.subheader("👥 Supporter")
    st.caption("Supporter melden sich unter `/?support=1` an und sehen nur: Live-Chat, Freigaben, Partner-Codes, "
               "Beta-Tester und den Team-Chat. Deaktivieren wirkt sofort.")
    sups = {k: v for k, v in (db.reference("supporters").get() or {}).items() if isinstance(v, dict)}
    if sups:
        st.dataframe(pd.DataFrame([{
            "Benutzername": k, "Anzeigename": v.get("name", k), "Aktiv": v.get("active", True),
            "Letzter Login": _fmt_ts(v.get("last_login")),
            "Gesperrt (Fehlversuche)": float(v.get("lock_until") or 0) > time.time(),
        } for k, v in sups.items()]), hide_index=True, use_container_width=True)

    with st.form("sup_new", clear_on_submit=True):
        st.markdown("**➕ Neuer Supporter**")
        user = st.text_input("Benutzername (a-z, 0-9, - _, 3-24 Zeichen)")
        name = st.text_input("Anzeigename (sieht der Streamer im Chat)")
        pw = st.text_input(f"Start-Passwort (min. {MIN_PW} Zeichen)", type="password")
        if st.form_submit_button("Anlegen"):
            u = user.strip().lower()
            if not USER_RE.match(u):
                st.error("Benutzername ungültig.")
            elif u in sups:
                st.error("Den Benutzernamen gibt es schon.")
            elif len(pw) < MIN_PW:
                st.error(f"Passwort zu kurz (min. {MIN_PW} Zeichen).")
            else:
                db.reference(f"supporters/{u}").set({"name": (name.strip() or u)[:40], "active": True, "created": SERVER_TS})
                _set_password(u, pw)
                st.success(f"Supporter {u} angelegt.")
                st.rerun()

    if not sups:
        return
    st.markdown("**✏️ Bearbeiten**")
    pick = st.selectbox("Supporter", list(sups), key="sup_pick")
    cur = sups[pick]
    c1, c2 = st.columns(2)
    with c1:
        new_pw = st.text_input("Neues Passwort", type="password", key=f"sup_pw_{pick}")
        if st.button("🔑 Passwort setzen", disabled=len(new_pw) < MIN_PW, key=f"sup_setpw_{pick}"):
            _set_password(pick, new_pw)
            st.success("Passwort geändert, Sperre aufgehoben.")
    with c2:
        active = cur.get("active", True)
        if st.button("⏸️ Deaktivieren" if active else "▶️ Aktivieren", key=f"sup_toggle_{pick}"):
            db.reference(f"supporters/{pick}/active").set(not active)
            st.rerun()
        ok = st.checkbox("Ja, wirklich löschen", key=f"sup_delok_{pick}")
        if st.button("🗑️ Supporter löschen", disabled=not ok, key=f"sup_del_{pick}"):
            db.reference(f"supporters/{pick}").delete()
            st.rerun()


# ----------------------------------------------------------------------------
# Partner-Codes (nur lesen, ohne Umsätze und Guthaben)
# ----------------------------------------------------------------------------
def partner_codes_view():
    st.subheader("🎟️ Partner-Codes")
    st.caption("Nur Ansicht. Wert-Gutscheine, Umsätze und Nutzungszahlen sind für Supporter ausgeblendet.")
    cps = {k: v for k, v in (db.reference("shop/coupons").get() or {}).items()
           if isinstance(v, dict) and v.get("type") != "amount"}
    q = st.text_input("Suchen", placeholder="Code oder Partner ...", key="pc_search").strip().lower()
    rows = [{"Code": k, "Partner": v.get("partner", ""), "Rabatt": f"{v.get('percent')} %",
             "Läuft ab": v.get("expires") or "–", "Aktiv": v.get("active", True)}
            for k, v in cps.items() if not q or q in k.lower() or q in str(v.get("partner", "")).lower()]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Keine Partner-Codes gefunden.")


# ----------------------------------------------------------------------------
# Team-Chat (Supporter + Admin), wichtige Nachrichten markierbar
# ----------------------------------------------------------------------------
def _load_team():
    data = db.reference("team_chat/messages").order_by_child("ts").limit_to_last(300).get() or {}
    msgs = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    msgs.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]))
    return msgs


def _send_team(name, text, important):
    text = text.strip()[:2000]
    if text:
        db.reference("team_chat/messages").push(
            {"name": name, "text": text, "important": bool(important), "ts": SERVER_TS})


def _toggle_important(m, me):
    ref = db.reference(f"team_chat/messages/{m['id']}")
    now = not m.get("important")
    ref.update({"important": now, "marked_by": me if now else None})


@st.fragment(run_every=TEAM_REFRESH_SECONDS)
def _team_messages(me, only_important):
    try:
        msgs = _load_team()
    except Exception as e:
        st.error(f"Team-Chat konnte nicht geladen werden: {e}")
        return
    important = [m for m in msgs if m.get("important")]
    if important:
        with st.expander(f"📌 Wichtig ({len(important)})"):
            for m in important[-10:][::-1]:
                st.markdown(f"**{m.get('name', '?')}** · {_fmt_ts(m.get('ts'))}  \n{m.get('text', '')}")
    shown = important if only_important else msgs
    box = st.container(height=480, border=True)
    with box:
        if not shown:
            st.caption("Noch keine Nachrichten.")
        for m in shown:
            with st.chat_message("user" if m.get("name") == me else "assistant"):
                flag = "❗ " if m.get("important") else ""
                by = f" · markiert von {m['marked_by']}" if m.get("important") and m.get("marked_by") else ""
                st.caption(f"{flag}{m.get('name', '?')} · {_fmt_ts(m.get('ts'))}{by}")
                st.write(m.get("text", ""))
                label = "❗ Markierung entfernen" if m.get("important") else "❗ Als wichtig markieren"
                if st.button(label, key=f"imp_{m['id']}"):
                    try:
                        _toggle_important(m, me)
                    except Exception as e:
                        st.error(f"Fehlgeschlagen: {e}")
                    st.rerun(scope="fragment")


def team_chat_panel(me):
    st.subheader("💭 Team-Chat")
    only = st.toggle("Nur wichtige Nachrichten", key="team_only_imp")
    area = st.container()
    with st.form("team_send", clear_on_submit=True):
        text = st.text_area("Nachricht an das Team", height=80, max_chars=2000)
        imp = st.checkbox("❗ Als wichtig markieren")
        if st.form_submit_button("Senden"):
            try:
                _send_team(me, text, imp)
            except Exception as e:
                st.error(f"Senden fehlgeschlagen: {e}")
    with area:
        _team_messages(me, only)
