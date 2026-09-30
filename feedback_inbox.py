"""Bugs, Feedback und Ideen: Eingang im Admin- und Supporter-Panel (statt Discord).

Firebase-Struktur (die App schreibt per push):
  feedback_inbox/{id} = {kind, text, streamer, tid, version, status, ts, note, handled_by}
      kind:   "Bug" | "Feedback" | "Feature-Wunsch"
      status: "neu" | "in Arbeit" | "erledigt" | "abgelehnt"
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
KINDS = {"Bug": "🐞 Bug", "Feature-Wunsch": "💡 Idee", "Feedback": "💬 Feedback"}
STATUSES = ["neu", "in Arbeit", "erledigt", "abgelehnt"]
STATUS_ICON = {"neu": "🆕", "in Arbeit": "🛠️", "erledigt": "✅", "abgelehnt": "🚫"}
LIMIT = 300


def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _load():
    data = db.reference("feedback_inbox").order_by_child("ts").limit_to_last(LIMIT).get() or {}
    items = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    items.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]), reverse=True)
    return items


@st.cache_data(ttl=30, show_spinner=False)
def new_count():
    """Anzahl neuer Einträge für das Tab-Label."""
    try:
        return sum(1 for m in _load() if m.get("status", "neu") == "neu")
    except Exception:
        return 0


def feedback_panel(me, is_admin=False):
    st.subheader("🐞 Bugs, Feedback & Ideen")
    st.caption("Kommt direkt aus der App der Streamer (Reiter „Feedback & Bugs“). Status und Notiz sind für alle im Team sichtbar.")
    if st.button("🔄 Aktualisieren", key="fb_refresh"):
        new_count.clear()
    try:
        items = _load()
    except Exception as e:
        st.error(f"Firebase-Fehler: {e}")
        return

    c = st.columns(4)
    c[0].metric("🆕 Neu", sum(1 for m in items if m.get("status", "neu") == "neu"))
    c[1].metric("🐞 Bugs offen", sum(1 for m in items if m.get("kind") == "Bug" and m.get("status", "neu") in ("neu", "in Arbeit")))
    c[2].metric("💡 Ideen offen", sum(1 for m in items if m.get("kind") == "Feature-Wunsch" and m.get("status", "neu") in ("neu", "in Arbeit")))
    c[3].metric("Gesamt", len(items))

    f1, f2, f3 = st.columns([2, 2, 3])
    kinds = f1.multiselect("Art", list(KINDS), default=list(KINDS), format_func=KINDS.get, key="fb_kinds")
    stats = f2.multiselect("Status", STATUSES, default=["neu", "in Arbeit"], key="fb_stats")
    q = f3.text_input("Suchen", placeholder="Streamer oder Text ...", key="fb_q").strip().lower()
    shown = [m for m in items if m.get("kind", "Feedback") in kinds and m.get("status", "neu") in stats
             and (not q or q in str(m.get("text", "")).lower() or q in str(m.get("streamer", "")).lower())]
    if not shown:
        st.info("Keine Einträge in dieser Ansicht.")
    for m in shown:
        status = m.get("status", "neu")
        label = (f"{STATUS_ICON.get(status, '')} {KINDS.get(m.get('kind'), '💬 Feedback')} · "
                 f"{m.get('streamer', '?')} · {_fmt_ts(m.get('ts'))}")
        with st.expander(label):
            st.write(m.get("text", ""))
            st.caption(f"Streamer `{m.get('streamer', '?')}` · Twitch-ID `{m.get('tid', '?')}` · Version {m.get('version', '?')}"
                       + (f" · zuletzt von {m['handled_by']} bearbeitet" if m.get("handled_by") else ""))
            k = m["id"]
            s1, s2 = st.columns([1, 2])
            new_status = s1.selectbox("Status", STATUSES, index=STATUSES.index(status) if status in STATUSES else 0, key=f"fb_st_{k}")
            note = s2.text_input("Interne Notiz", value=str(m.get("note") or ""), max_chars=500, key=f"fb_note_{k}")
            b1, b2 = st.columns([1, 4])
            if b1.button("💾 Speichern", key=f"fb_save_{k}"):
                db.reference(f"feedback_inbox/{k}").update({"status": new_status, "note": note.strip() or None, "handled_by": me})
                new_count.clear()
                st.rerun()
            if is_admin:
                ok = b2.checkbox("Ja, löschen", key=f"fb_delok_{k}")
                if b2.button("🗑️ Löschen", disabled=not ok, key=f"fb_del_{k}"):
                    db.reference(f"feedback_inbox/{k}").delete()
                    new_count.clear()
                    st.rerun()
