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
STATUS_HELP = {"neu": "Eingegangen – noch nicht in Bearbeitung.", "in Arbeit": "Das Team prüft den Bug oder arbeitet an der Idee.", "erledigt": "Umgesetzt oder behoben.", "abgelehnt": "Wird nicht weiterverfolgt."}
SERVER_TS = {".sv": "timestamp"}
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


def _for_tool(items, tool):
    """Reports der Lurk-App tragen "Lurk ..." in der Version. tool: None (alle), "lurk" oder "streamdex"."""
    if tool == "lurk":
        return [m for m in items if str(m.get("version", "")).startswith("Lurk")]
    if tool == "streamdex":
        return [m for m in items if not str(m.get("version", "")).startswith("Lurk")]
    return items


@st.cache_data(ttl=30, show_spinner=False)
def new_count(tool=None):
    """Anzahl neuer Einträge für das Tab-Label."""
    try:
        return sum(1 for m in _for_tool(_load(), tool) if m.get("status", "neu") == "neu")
    except Exception:
        return 0


def feedback_panel(me, is_admin=False, tool=None):
    st.subheader("🐞 Bugs, Feedback & Ideen")
    st.caption("Bugs, Ideen und Feedback übersichtlich nach Status sortiert. Interne Notizen bleiben im Admin-/Team-Bereich." + (" · nur Lurk-App" if tool == "lurk" else ""))
    if st.button("🔄 Aktualisieren", key="fb_refresh"):
        new_count.clear()
    try:
        items = _for_tool(_load(), tool)
    except Exception as e:
        st.error(f"Firebase-Fehler: {e}")
        return

    c = st.columns(4)
    c[0].metric("🆕 Neu", sum(1 for m in items if m.get("status", "neu") == "neu"))
    c[1].metric("🐞 Bugs offen", sum(1 for m in items if m.get("kind") == "Bug" and m.get("status", "neu") in ("neu", "in Arbeit")))
    c[2].metric("💡 Offene Ideen", sum(1 for m in items if m.get("kind") == "Feature-Wunsch" and m.get("status", "neu") in ("neu", "in Arbeit")))
    c[3].metric("Abgeschlossen", sum(1 for m in items if m.get("status") in ("erledigt", "abgelehnt")))

    f1, f2, f3 = st.columns([2, 2, 3])
    kinds = f1.multiselect("Art", list(KINDS), default=list(KINDS), format_func=KINDS.get, key="fb_kinds")
    stats = f2.multiselect("Status", STATUSES, default=list(STATUSES), key="fb_stats")
    q = f3.text_input("Suchen", placeholder="Titel, Streamer oder Beschreibung …", key="fb_q").strip().lower()
    shown = [m for m in items if m.get("kind", "Feedback") in kinds and m.get("status", "neu") in stats
             and (not q or q in str(m.get("title", "")).lower() or q in str(m.get("text", "")).lower() or q in str(m.get("streamer", "")).lower())]
    st.caption(f"{len(shown)} von {len(items)} Einträgen · neueste zuerst")
    if not shown:
        st.info("Keine Einträge in dieser Ansicht.")
    for m in shown:
        status = m.get("status", "neu")
        title = str(m.get("title") or str(m.get("text") or "Feedback").splitlines()[0])[:120]
        label = f"{STATUS_ICON.get(status, '')} {KINDS.get(m.get('kind'), '💬 Feedback')} · {title}"
        with st.expander(label, expanded=(status == "neu")):
            st.markdown(f"### {title}")
            meta = f"{m.get('streamer', '?')} · {_fmt_ts(m.get('ts'))}"
            if m.get("category"):
                meta += f" · {m['category']}"
            st.caption(meta)
            body = str(m.get("text") or "")
            if "\n\n" in body:
                body = body.split("\n\n", 1)[1]
            st.write(body or "Keine Beschreibung angegeben.")
            st.caption(f"Status: {STATUS_ICON.get(status, '')} **{status}** — {STATUS_HELP.get(status, '')}")
            with st.expander("Technische Details und interne Notiz"):
                st.caption(f"Streamer `{m.get('streamer', '?')}` · Twitch-ID `{m.get('tid', '?')}` · Version {m.get('version', '?')}"
                           + (f" · zuletzt von {m['handled_by']} bearbeitet" if m.get("handled_by") else ""))
            k = m["id"]
            s1, s2 = st.columns([1, 2])
            new_status = s1.selectbox("Status ändern", STATUSES, index=STATUSES.index(status) if status in STATUSES else 0, key=f"fb_st_{k}")
            note = s2.text_input("Interne Notiz (nur Team)", value=str(m.get("note") or ""), max_chars=500, key=f"fb_note_{k}")
            b1, b2 = st.columns([1, 4])
            if b1.button("💾 Änderungen speichern", key=f"fb_save_{k}"):
                changed = new_status != status
                updates = {"status": new_status, "note": note.strip() or None, "handled_by": me}
                if changed:
                    updates["status_changed_at"] = SERVER_TS
                db.reference(f"feedback_inbox/{k}").update(updates)
                new_count.clear()
                st.rerun()
            if is_admin:
                ok = b2.checkbox("Ja, löschen", key=f"fb_delok_{k}")
                if b2.button("🗑️ Löschen", disabled=not ok, key=f"fb_del_{k}"):
                    db.reference(f"feedback_inbox/{k}").delete()
                    new_count.clear()
                    st.rerun()
