"""StreamDex Feedback: Community-Vorschläge, Umfragen und Feedback-Einreichung."""
from datetime import datetime
from zoneinfo import ZoneInfo
import html
import time

import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}
MAX_TITLE = 100
MAX_TEXT = 1500
MAX_OPTIONS = 5
MAX_POLLS = 100
MAX_SUGGESTIONS = 200


def _fmt_ts(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, TZ).strftime("%d.%m.%Y · %H:%M")
    except Exception:
        return "Gerade eben"


def _load_suggestions():
    data = db.reference("feedback_inbox").order_by_child("ts").limit_to_last(MAX_SUGGESTIONS).get() or {}
    items = []
    for key, value in data.items():
        if not isinstance(value, dict) or not value.get("community_visible"):
            continue
        value = dict(value)
        value["id"] = key
        votes = value.get("votes") or {}
        value["votes"] = votes if isinstance(votes, dict) else {}
        value["vote_count"] = len(value["votes"])
        items.append(value)
    return sorted(items, key=lambda item: (item["vote_count"], int(item.get("ts") or 0)), reverse=True)


def _load_my_feedback(tid):
    data = db.reference("feedback_inbox").order_by_child("ts").limit_to_last(MAX_SUGGESTIONS).get() or {}
    items = []
    for key, value in data.items():
        if isinstance(value, dict) and str(value.get("tid") or "") == str(tid):
            value = dict(value)
            value["id"] = key
            items.append(value)
    return sorted(items, key=lambda item: int(item.get("ts") or 0), reverse=True)


def _load_polls():
    data = db.reference("community_polls").order_by_child("created_at").limit_to_last(MAX_POLLS).get() or {}
    result = []
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        value = dict(value)
        value["id"] = key
        options = value.get("options") or []
        if isinstance(options, dict):
            options = [options[k] for k in sorted(options, key=lambda x: int(x) if str(x).isdigit() else str(x))]
        value["options"] = [str(option)[:100] for option in options if str(option).strip()]
        votes = value.get("votes") or {}
        value["votes"] = votes if isinstance(votes, dict) else {}
        result.append(value)
    return sorted(result, key=lambda item: int(item.get("created_at") or 0), reverse=True)


def _submit_feedback(tid, username, kind, title, description, public=False, category="Allgemein"):
    title = str(title or "").strip()[:MAX_TITLE]
    description = str(description or "").strip()[:MAX_TEXT]
    if not title or not description:
        raise ValueError("Bitte fülle Titel und Beschreibung aus.")
    item = {
        "kind": kind,
        "title": title,
        "category": category,
        "text": f"{title}\n\n{description}",
        "streamer": str(username or tid)[:80],
        "tid": str(tid),
        "author_name": str(username or tid)[:80],
        "version": "StreamDex Web",
        "status": "neu",
        "community_visible": bool(public),
        "votes": {},
        "ts": SERVER_TS,
    }
    db.reference("feedback_inbox").push(item)


def _create_poll(tid, username, question, option_texts):
    question = str(question or "").strip()[:MAX_TITLE]
    options = []
    for value in option_texts:
        label = str(value or "").strip()[:100]
        if label and label not in options:
            options.append(label)
    if not question:
        raise ValueError("Bitte gib eine Frage für die Umfrage ein.")
    if len(options) < 2:
        raise ValueError("Eine Umfrage braucht mindestens zwei unterschiedliche Antwortmöglichkeiten.")
    if len(options) > MAX_OPTIONS:
        options = options[:MAX_OPTIONS]
    current = _load_polls()
    owned_open = sum(1 for poll in current if str(poll.get("created_by") or "") == str(tid) and not poll.get("closed"))
    if owned_open >= 5:
        raise ValueError("Du kannst maximal fünf gleichzeitig offene Umfragen erstellen.")
    db.reference("community_polls").push({
        "question": question,
        "options": options,
        "created_by": str(tid),
        "created_by_name": str(username or tid)[:80],
        "created_at": SERVER_TS,
        "closed": False,
        "votes": {},
    })


def render_feedback_hub(tid, username):
    """Einstiegspunkt für das angemeldete StreamDex-Feedback-Modul."""
    st.markdown(
        """
        <div class="sd-feedback-hero">
          <div class="sd-feedback-kicker">STREAMDEX OS / COMMUNITY VOICE</div>
          <h1>Dein Feedback. <span>Unsere Weiterentwicklung.</span></h1>
          <p>Teile Ideen, stimme über Vorschläge ab und starte Umfragen für die StreamDex-Community.</p>
        </div>
        <style>
        .sd-feedback-hero{border:1px solid rgba(139,92,246,.34);border-radius:18px;padding:24px 26px;margin:0 0 18px;
          background:radial-gradient(ellipse at 88% 18%,rgba(34,211,238,.12),transparent 38%),
          linear-gradient(115deg,rgba(15,23,42,.98),rgba(35,25,71,.94) 58%,rgba(8,47,73,.88));
          box-shadow:0 18px 45px rgba(0,0,0,.2)}
        .sd-feedback-kicker{font:700 .68rem 'JetBrains Mono',monospace;letter-spacing:.14em;color:#c4b5fd}
        .sd-feedback-hero h1{font-size:clamp(1.8rem,3vw,2.6rem);font-weight:800;letter-spacing:-.05em;margin:12px 0 9px;color:#f8fafc}
        .sd-feedback-hero h1 span{background:linear-gradient(90deg,#c084fc,#818cf8,#67e8f9);-webkit-background-clip:text;color:transparent}
        .sd-feedback-hero p{font-size:.9rem;line-height:1.7;color:#cbd5e1;max-width:780px;margin:0}
        .sd-feedback-count{font-size:.7rem;color:#c4b5fd}
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        suggestions = _load_suggestions()
        polls = _load_polls()
        my_items = _load_my_feedback(tid)
    except Exception:
        st.error("Feedback-Daten konnten gerade nicht geladen werden. Bitte versuche es erneut.")
        if st.button("🔄 Erneut laden", key="sd_feedback_reload_error"):
            st.rerun()
        return

    open_polls = [poll for poll in polls if not poll.get("closed")]
    active_suggestions = [item for item in suggestions if item.get("status", "neu") not in ("abgelehnt",)]
    voted_suggestions = sum(1 for item in suggestions if str(tid) in item["votes"])
    my_polls = sum(1 for poll in polls if str(poll.get("created_by") or "") == str(tid))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💡 Community-Ideen", len(active_suggestions))
    m2.metric("🗳️ Offene Umfragen", len(open_polls))
    m3.metric("👍 Deine Stimmen", voted_suggestions)
    m4.metric("✍️ Deine Vorschläge", sum(1 for item in my_items if item.get("community_visible")))

    t_send, t_ideas, t_polls, t_mine = st.tabs([
        "✍️ Feedback senden", "💡 Vorschläge", "🗳️ Umfragen", "📬 Meine Beiträge"
    ])

    with t_send:
        st.markdown("### Teile deine Idee mit uns")
        st.caption("Öffentliche Vorschläge erscheinen im Community-Board. Allgemeines Feedback und Bug-Meldungen gehen nur an das StreamDex-Team.")
        with st.form("sd_feedback_submit_form", clear_on_submit=True):
            kind_label = st.selectbox(
                "Was möchtest du einreichen?",
                ["Feature-Vorschlag für die Community", "Allgemeines Feedback (nur Team)", "Bug melden (nur Team)"],
                key="sd_feedback_kind",
            )
            category = st.selectbox(
                "Kategorie",
                ["Allgemein", "Dashboard", "Radar", "Events", "Games", "Lurk Tool", "Overlay", "Twitch-Integration", "Sonstiges"],
                key="sd_feedback_category",
            )
            title = st.text_input("Titel", max_chars=MAX_TITLE, placeholder="z. B. Streamer gemeinsam beobachten")
            description = st.text_area("Beschreibung", max_chars=MAX_TEXT, height=135, placeholder="Was schlägst du vor oder was ist dir aufgefallen?")
            submitted = st.form_submit_button("Feedback absenden", type="primary", use_container_width=True)
        if submitted:
            public = kind_label == "Feature-Vorschlag für die Community"
            kind = "Feature-Wunsch" if public else ("Bug" if kind_label.startswith("Bug") else "Feedback")
            try:
                _submit_feedback(tid, username, kind, title, description, public, category)
                st.success("Danke! Dein Vorschlag wurde veröffentlicht." if public else "Danke! Dein Feedback wurde an das StreamDex-Team gesendet.")
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
            except Exception:
                st.error("Dein Feedback konnte nicht gespeichert werden. Bitte versuche es erneut.")

        st.divider()
        st.markdown("### So funktioniert's")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**💡 Vorschlagen**")
            st.caption("Öffentliche Ideen sind für andere Mitglieder sichtbar und können unterstützt werden.")
        with c2:
            st.markdown("**🗳️ Abstimmen**")
            st.caption("Gib Vorschlägen und Umfragen deine Stimme.")
        with c3:
            st.markdown("**🔒 Direktes Feedback**")
            st.caption("Bugs und persönliche Rückmeldungen bleiben im Team-Posteingang.")

    with t_ideas:
        st.markdown("### Community-Vorschläge")
        st.caption("Sortiere die Ideen und unterstütze, was dir wichtig ist.")
        sort_by = st.radio("Sortierung", ["Beliebteste", "Neueste"], horizontal=True, key="sd_feedback_sort")
        shown = active_suggestions[:]
        if sort_by == "Neueste":
            shown.sort(key=lambda item: int(item.get("ts") or 0), reverse=True)
        if not shown:
            st.info("Noch keine öffentlichen Vorschläge. Sei der Erste und teile eine Idee im Tab „Feedback senden“!")
        for offset in range(0, len(shown), 2):
            cols = st.columns(2)
            for col, item in zip(cols, shown[offset:offset + 2]):
                with col:
                    with st.container(border=True):
                        title_text = str(item.get("title") or str(item.get("text") or "Vorschlag").splitlines()[0])[:MAX_TITLE]
                        category = str(item.get("category") or "Allgemein")
                        author = str(item.get("author_name") or item.get("streamer") or "Community")
                        st.markdown(f"#### {html.escape(title_text)}")
                        st.caption(f"📂 {html.escape(category)} · von {html.escape(author)} · {_fmt_ts(item.get('ts'))}")
                        body = str(item.get("text") or "")
                        if "\n\n" in body:
                            body = body.split("\n\n", 1)[1]
                        st.write(body)
                        status = str(item.get("status") or "neu")
                        status_label = {"neu": "🆕 Neu", "in Arbeit": "🛠️ In Arbeit", "erledigt": "✅ Umgesetzt", "abgelehnt": "🚫 Abgelehnt"}.get(status, status)
                        st.caption(f"Status: {status_label}")
                        votes = item["votes"]
                        has_voted = str(tid) in votes
                        b1, b2 = st.columns([1, 2])
                        if b1.button(
                            ("✅ Stimme zurücknehmen" if has_voted else "👍 Unterstützen"),
                            key=f"sd_feedback_vote_{item['id']}",
                            use_container_width=True,
                        ):
                            try:
                                vote_ref = db.reference(f"feedback_inbox/{item['id']}/votes/{tid}")
                                if has_voted:
                                    vote_ref.delete()
                                else:
                                    vote_ref.set(True)
                                st.rerun()
                            except Exception:
                                st.error("Deine Stimme konnte nicht gespeichert werden.")
                        b2.caption(f"👍 {item['vote_count']} Stimmen")

    with t_polls:
        st.markdown("### Community-Umfragen")
        st.caption("Jeder angemeldete StreamDex-Nutzer kann eine Umfrage erstellen. Pro Umfrage ist eine Stimme möglich; du kannst deine Antwort ändern.")
        with st.expander("＋ Neue Umfrage erstellen", expanded=False):
            with st.form("sd_feedback_poll_form", clear_on_submit=True):
                question = st.text_input("Frage", max_chars=MAX_TITLE, placeholder="Was sollen wir als Nächstes bauen?")
                st.markdown("**Antwortmöglichkeiten** (mindestens zwei)")
                opt1 = st.text_input("Antwort 1", max_chars=100, key="sd_feedback_poll_opt1")
                opt2 = st.text_input("Antwort 2", max_chars=100, key="sd_feedback_poll_opt2")
                opt3 = st.text_input("Antwort 3 (optional)", max_chars=100, key="sd_feedback_poll_opt3")
                opt4 = st.text_input("Antwort 4 (optional)", max_chars=100, key="sd_feedback_poll_opt4")
                opt5 = st.text_input("Antwort 5 (optional)", max_chars=100, key="sd_feedback_poll_opt5")
                create = st.form_submit_button("Umfrage veröffentlichen", type="primary", use_container_width=True)
            if create:
                try:
                    _create_poll(tid, username, question, [opt1, opt2, opt3, opt4, opt5])
                    st.success("Deine Umfrage ist online!")
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception:
                    st.error("Die Umfrage konnte nicht erstellt werden.")

        if not polls:
            st.info("Noch keine Umfragen vorhanden. Du kannst oben die erste starten.")
        for poll in polls:
            options = poll["options"]
            if len(options) < 2:
                continue
            with st.container(border=True):
                st.markdown(f"#### {html.escape(str(poll.get('question') or 'Community-Umfrage'))}")
                st.caption(f"Erstellt von {html.escape(str(poll.get('created_by_name') or 'Community'))} · {_fmt_ts(poll.get('created_at'))}")
                votes = poll["votes"]
                selected_vote = votes.get(str(tid))
                counts = [0] * len(options)
                for value in votes.values():
                    try:
                        index = int(value)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= index < len(counts):
                        counts[index] += 1
                total = sum(counts)
                closed = bool(poll.get("closed"))
                if not closed:
                    chosen = st.radio(
                        "Deine Antwort",
                        options,
                        index=int(selected_vote) if str(selected_vote).isdigit() and 0 <= int(selected_vote) < len(options) else None,
                        key=f"sd_feedback_poll_choice_{poll['id']}",
                        label_visibility="collapsed",
                    )
                    voted = str(tid) in votes
                    vote_label = "Stimme aktualisieren" if voted else "Abstimmen"
                    if st.button(vote_label, type="primary", key=f"sd_feedback_poll_submit_{poll['id']}"):
                        if chosen not in options:
                            st.warning("Bitte wähle eine Antwort aus.")
                        else:
                            try:
                                db.reference(f"community_polls/{poll['id']}/votes/{tid}").set(options.index(chosen))
                                st.rerun()
                            except Exception:
                                st.error("Deine Stimme konnte nicht gespeichert werden.")
                else:
                    st.caption("🔒 Diese Umfrage ist geschlossen.")
                if total:
                    st.markdown("**Ergebnis**")
                    for option, count in zip(options, counts):
                        ratio = count / total
                        st.caption(f"{option} · {count} Stimme(n) · {round(ratio * 100)} %")
                        st.progress(ratio)
                else:
                    st.caption("Noch keine Stimmen.")
                if str(poll.get("created_by") or "") == str(tid) and not closed:
                    if st.button("Umfrage schließen", key=f"sd_feedback_poll_close_{poll['id']}"):
                        try:
                            db.reference(f"community_polls/{poll['id']}").update({"closed": True, "closed_at": SERVER_TS})
                            st.rerun()
                        except Exception:
                            st.error("Die Umfrage konnte nicht geschlossen werden.")

    with t_mine:
        st.markdown("### Deine Beiträge")
        if not my_items and not my_polls:
            st.info("Du hast bisher noch kein Feedback und keine Umfrage eingereicht.")
        if my_items:
            st.markdown("**Feedback und Vorschläge**")
            for item in my_items[:25]:
                title_text = str(item.get("title") or str(item.get("text") or "Feedback").splitlines()[0])[:MAX_TITLE]
                status = str(item.get("status") or "neu")
                status_label = {"neu": "🆕 Neu", "in Arbeit": "🛠️ In Arbeit", "erledigt": "✅ Erledigt", "abgelehnt": "🚫 Abgelehnt"}.get(status, status)
                visibility = "Öffentlich" if item.get("community_visible") else "Nur Team"
                with st.container(border=True):
                    st.markdown(f"**{html.escape(title_text)}**")
                    st.caption(f"{visibility} · {status_label} · {_fmt_ts(item.get('ts'))}")
        if my_polls:
            st.markdown("**Deine Umfragen**")
            for poll in [p for p in polls if str(p.get("created_by") or "") == str(tid)]:
                state = "Geschlossen" if poll.get("closed") else "Offen"
                st.caption(f"🗳️ {html.escape(str(poll.get('question') or 'Umfrage'))} · {state}")

    st.caption("Danke, dass du StreamDex mitgestaltest. Bitte teile keine Passwörter, Tokens oder anderen privaten Zugangsdaten in deinem Feedback.")
