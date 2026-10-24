"""StreamDex Ideas and creator tools suite."""
import csv
import html
import io
import secrets
from datetime import date, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db
from streamdex_security import has_active_user_session, is_valid_twitch_id

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}
MAX_TEXT = 2000
TOOLS = [
    ("ideas", "💡 StreamDex Ideas", "Ideen sammeln, priorisieren und umsetzen."),
    ("bracket", "🏆 StreamDex Bracket", "K.-o.-Turniere erstellen und verwalten."),
    ("wheel", "🎡 StreamDex Wheel", "Ein Glücksrad mit eigenen Optionen."),
    ("wishlist", "🎁 StreamDex Wishlist", "Community-Wünsche und Stimmen."),
    ("feedback", "💬 StreamDex Feedback", "Vorschläge, Rückmeldungen und Abstimmungen."),
    ("quiz", "🧠 StreamDex Quiz", "Quizräume erstellen und spielen."),
    ("clips", "🎬 StreamDex Clips", "Twitch-Clips sammeln und organisieren."),
    ("goals", "🎯 StreamDex Goals", "Ziele und Fortschritte verfolgen."),
    ("modlog", "🛡️ StreamDex ModLog", "Moderationsaktionen dokumentieren."),
    ("modteam", "👥 StreamDex ModTeam", "Teammitglieder und Aufgaben verwalten."),
]


def _uid(value):
    if not is_valid_twitch_id(value):
        raise ValueError("Ungültige Twitch-ID.")
    return str(value)


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _ts(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, TZ).strftime("%d.%m.%Y · %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "Gerade eben"


def _items(path, limit=200):
    data = db.reference(path).get() or {}
    if isinstance(data, list):
        items = [{"id": str(i), **v} for i, v in enumerate(data) if isinstance(v, dict)]
    elif isinstance(data, dict):
        items = [{"id": str(k), **v} for k, v in data.items() if isinstance(v, dict)]
    else:
        items = []
    items.sort(key=lambda item: _int(item.get("ts") or item.get("created_at")), reverse=True)
    return items[:limit]


def _err():
    st.error("Die Aktion ist fehlgeschlagen. Bitte versuche es erneut.")


def _header(title, kicker, desc):
    st.markdown(f"""
    <div class="sd-suite-hero"><small>{html.escape(kicker)}</small><h1>{html.escape(title)}</h1><p>{html.escape(desc)}</p></div>
    <style>
    .sd-suite-hero{{border:1px solid rgba(139,92,246,.34);border-radius:17px;padding:22px 24px;margin-bottom:18px;
    background:radial-gradient(ellipse at 88% 15%,rgba(34,211,238,.11),transparent 38%),linear-gradient(115deg,rgba(15,23,42,.98),rgba(35,25,71,.92) 60%,rgba(8,47,73,.86))}}
    .sd-suite-hero small{{font:700 .67rem 'JetBrains Mono',monospace;letter-spacing:.14em;color:#c4b5fd}}
    .sd-suite-hero h1{{font-size:clamp(1.65rem,2.8vw,2.35rem);font-weight:800;letter-spacing:-.045em;margin:10px 0 8px;color:#f8fafc}}
    .sd-suite-hero p{{font-size:.86rem;line-height:1.7;color:#cbd5e1;max-width:820px;margin:0}}
    </style>""", unsafe_allow_html=True)


def _navigate(param):
    st.query_params.clear()
    st.query_params[str(param)] = "1"
    st.rerun()


def _tool_grid():
    st.markdown("### Alle Werkzeuge")
    st.caption("Private Einträge bleiben deinem Streamer-Konto zugeordnet.")
    for start in range(0, len(TOOLS), 2):
        cols = st.columns(2)
        for col, (key, title, desc) in zip(cols, TOOLS[start:start + 2]):
            with col:
                with st.container(border=True):
                    st.markdown(f"#### {title}")
                    st.caption(desc)
                    if st.button("Werkzeug öffnen →", key=f"sd_suite_launch_{key}", use_container_width=True):
                        _navigate(key)


def _ideas(tid, username):
    root = f"streamdex_ideas/{_uid(tid)}/items"
    _header("StreamDex Ideas", "IDEENVERWALTUNG / DEIN BACKLOG", "Sammle Einfälle, setze Prioritäten und halte die nächsten Schritte fest.")
    try:
        items = _items(root, 250)
    except Exception:
        items = []
        st.error("Dein Ideen-Board konnte nicht geladen werden.")
    a, b, c = st.columns(3)
    a.metric("Ideen", len(items)); b.metric("Offen", sum(x.get("status") != "Erledigt" for x in items)); c.metric("Erledigt", sum(x.get("status") == "Erledigt" for x in items))
    with st.expander("＋ Neue Idee", expanded=not bool(items)):
        with st.form("sd_ideas_create", clear_on_submit=True):
            title = st.text_input("Idee", max_chars=120)
            detail = st.text_area("Beschreibung / nächster Schritt", max_chars=MAX_TEXT)
            priority = st.selectbox("Priorität", ["Normal", "Hoch", "Niedrig"])
            category = st.selectbox("Bereich", ["Stream", "Community", "Technik", "Content", "StreamDex", "Sonstiges"])
            submit = st.form_submit_button("Idee speichern", type="primary", use_container_width=True)
        if submit:
            if not title.strip():
                st.warning("Bitte gib einen Titel ein.")
            else:
                try:
                    db.reference(root).push({"title": title.strip()[:120], "detail": detail.strip()[:MAX_TEXT], "priority": priority, "category": category, "status": "Eingang", "created_by": _uid(tid), "created_by_name": str(username)[:80], "ts": SERVER_TS})
                    st.rerun()
                except Exception: _err()
    for item in items:
        key = item["id"]
        with st.container(border=True):
            st.markdown(f"#### {html.escape(str(item.get('title') or 'Idee'))}")
            st.caption(f"{html.escape(str(item.get('category') or 'Allgemein'))} · {html.escape(str(item.get('priority') or 'Normal'))} · {_ts(item.get('ts'))}")
            if item.get("detail"): st.write(str(item["detail"]))
            x, y, z = st.columns([2, 2, 1])
            states = ["Eingang", "Als Nächstes", "In Arbeit", "Erledigt"]
            state = str(item.get("status") or "Eingang")
            new_state = x.selectbox("Status", states, index=states.index(state) if state in states else 0, key=f"sd_idea_state_{key}")
            priorities = ["Niedrig", "Normal", "Hoch"]; prio = str(item.get("priority") or "Normal")
            new_prio = y.selectbox("Priorität", priorities, index=priorities.index(prio) if prio in priorities else 1, key=f"sd_idea_prio_{key}")
            if x.button("Speichern", key=f"sd_idea_save_{key}", use_container_width=True):
                try: db.reference(f"{root}/{key}").update({"status": new_state, "priority": new_prio}); st.rerun()
                except Exception: _err()
            if z.button("Löschen", key=f"sd_idea_delete_{key}", use_container_width=True):
                try: db.reference(f"{root}/{key}").delete(); st.rerun()
                except Exception: _err()
    st.divider(); _tool_grid()


def _bracket_rounds(tournament):
    current = list(tournament.get("slots") or [])
    wins = tournament.get("wins") if isinstance(tournament.get("wins"), dict) else {}
    rounds = []; ri = 0
    while len(current) > 1:
        matches, next_round = [], []
        for mi in range(0, len(current), 2):
            a, b = str(current[mi] or ""), str(current[mi + 1] or "")
            key = f"{ri}-{mi // 2}"; win = str(wins.get(key) or "")
            if win not in (a, b): win = a if a and not b else (b if b and not a else "")
            matches.append({"a": a, "b": b, "key": key, "winner": win, "bye": bool((a and not b) or (b and not a))})
            next_round.append(win)
        rounds.append(matches); current = next_round; ri += 1
    return rounds


def _bracket(tid, username):
    root = f"streamdex_brackets/{_uid(tid)}/active"
    _header("StreamDex Bracket", "TOURNAMENT ENGINE", "Erstelle einen K.-o.-Turnierbaum und trage Match-Sieger bis zum Finale ein.")
    tournament = db.reference(root).get() or {}
    if not isinstance(tournament, dict): tournament = {}
    with st.expander("＋ Turnier erstellen", expanded=not bool(tournament)):
        with st.form("sd_bracket_create", clear_on_submit=True):
            title = st.text_input("Turniername", max_chars=100, placeholder="Community-Cup")
            raw = st.text_area("Teilnehmer – ein Name pro Zeile", placeholder="Luna\nPixelPete\nNova\nGameFox", height=140)
            shuffle = st.checkbox("Teilnehmer zufällig mischen", value=True)
            submit = st.form_submit_button("Turnierbaum erstellen", type="primary", use_container_width=True)
        if submit:
            names = list(dict.fromkeys(x.strip()[:80] for x in raw.replace(",", "\n").splitlines() if x.strip()))
            if not 2 <= len(names) <= 32: st.warning("Bitte gib 2 bis 32 unterschiedliche Teilnehmer ein.")
            else:
                if shuffle: secrets.SystemRandom().shuffle(names)
                size = 1 << (len(names) - 1).bit_length()
                try:
                    db.reference(root).set({"title": title.strip()[:100] or "StreamDex Turnier", "participants": names, "slots": names + [""] * (size - len(names)), "wins": {}, "created_by": _uid(tid), "created_by_name": str(username)[:80], "created_at": SERVER_TS})
                    st.rerun()
                except Exception: _err()
    if not tournament: st.info("Erstelle dein erstes Turnier. Freilose werden automatisch übersprungen."); return
    rounds = _bracket_rounds(tournament); wins = tournament.get("wins") if isinstance(tournament.get("wins"), dict) else {}
    st.markdown(f"### {html.escape(str(tournament.get('title') or 'Turnier'))}")
    x, y, z = st.columns(3); x.metric("Teilnehmer", len(tournament.get("participants") or [])); y.metric("Runden", len(rounds)); z.metric("Status", "Abgeschlossen" if rounds and rounds[-1][0]["winner"] else "Läuft")
    cols = st.columns(len(rounds)); labels = {0: "1. Runde", 1: "Achtelfinale", 2: "Viertelfinale", 3: "Halbfinale", 4: "Finale"}
    for ri, (col, matches) in enumerate(zip(cols, rounds)):
        with col:
            st.markdown(f"#### {labels.get(ri, f'Runde {ri + 1}')}")
            for mi, match in enumerate(matches):
                with st.container(border=True):
                    st.caption(f"Match {mi + 1}"); st.write(match["a"] or "— Freilos —"); st.write(match["b"] or "— Freilos —")
                    if match["bye"]: st.success(f"Freilos: {match['winner']}")
                    elif match["a"] and match["b"]:
                        opts = ["— Sieger wählen —", match["a"], match["b"]]; current = match["winner"] if match["winner"] in opts else opts[0]
                        pick = st.selectbox("Sieger", opts, index=opts.index(current), key=f"sd_bracket_pick_{match['key']}")
                        if st.button("Ergebnis speichern", key=f"sd_bracket_save_{match['key']}", use_container_width=True) and pick in (match["a"], match["b"]):
                            try: wins[match["key"]] = pick; db.reference(f"{root}/wins").set(wins); st.rerun()
                            except Exception: _err()
                    else: st.caption("Warte auf vorherige Ergebnisse.")
                    if match["winner"]: st.caption(f"🏆 {html.escape(match['winner'])}")
    if rounds and rounds[-1][0]["winner"]: st.success(f"Turniersieger: {rounds[-1][0]['winner']}"); st.balloons()
    if st.button("Turnier zurücksetzen", key="sd_bracket_reset"): db.reference(root).delete(); st.rerun()


def _wheel(tid, username):
    root = f"streamdex_wheel/{_uid(tid)}"; _header("StreamDex Wheel", "RANDOM PICKER", "Dein Glücksrad für Giveaways, Entscheidungen und Community-Challenges.")
    config = db.reference(f"{root}/options"); options = config.get() or []
    if isinstance(options, dict): options = list(options.values())
    if not isinstance(options, list): options = []
    options = [str(x).strip()[:100] for x in options if str(x).strip()]
    with st.form("sd_wheel_options"):
        raw = st.text_area("Ein Eintrag pro Zeile", value="\n".join(options), height=150, placeholder="Bonus-Runde\nChat entscheidet\nNächster Song")
        submit = st.form_submit_button("Einträge speichern", type="primary", use_container_width=True)
    if submit:
        new_options = list(dict.fromkeys(x.strip()[:100] for x in raw.splitlines() if x.strip()))
        if len(new_options) < 2: st.warning("Das Rad braucht mindestens zwei unterschiedliche Einträge.")
        elif len(new_options) > 100: st.warning("Maximal 100 Einträge sind erlaubt.")
        else:
            try: config.set(new_options); st.rerun()
            except Exception: _err()
    if len(options) >= 2:
        st.markdown("### Deine Optionen"); st.write(" · ".join(options))
        if st.button("🎡 Glücksrad drehen", type="primary", key="sd_wheel_spin", use_container_width=True):
            result = secrets.choice(options)
            try: db.reference(f"{root}/runs").push({"result": result, "ts": SERVER_TS}); st.session_state["sd_wheel_result"] = {"tid": _uid(tid), "value": result}; st.rerun()
            except Exception: _err()
        last = st.session_state.get("sd_wheel_result") or {}
        if last.get("tid") == _uid(tid):
            st.markdown(f'<div class="sd-wheel-result"><small>DEIN ERGEBNIS</small><h2>{html.escape(str(last.get("value") or ""))}</h2></div><style>.sd-wheel-result{{padding:24px;text-align:center;border:1px solid rgba(34,211,238,.35);border-radius:16px;background:rgba(12,18,38,.9);margin:16px 0}}.sd-wheel-result small{{font:700 .68rem monospace;color:#67e8f9}}.sd-wheel-result h2{{font-size:clamp(1.7rem,4vw,3rem)!important;color:#f8fafc}}</style>', unsafe_allow_html=True)
            if st.button("🎉 Konfetti", key="sd_wheel_balloons"): st.balloons()
    else: st.info("Speichere mindestens zwei Einträge, um das Rad zu aktivieren.")
    st.markdown("### Letzte Drehungen")
    try:
        for run in _items(f"{root}/runs", 15): st.write(f"🎯 **{str(run.get('result') or '')}** · {_ts(run.get('ts'))}")
    except Exception: st.caption("Noch keine Drehungen vorhanden.")


def _wishlist(tid, username):
    root = "streamdex_community_wishlist"; _header("StreamDex Wishlist", "COMMUNITY REQUESTS", "Teile Wünsche und unterstütze Vorschläge, die auch andere StreamDex-Mitglieder sehen möchten.")
    with st.form("sd_wishlist_new", clear_on_submit=True):
        title = st.text_input("Wunsch", max_chars=120); desc = st.text_area("Details", max_chars=MAX_TEXT)
        category = st.selectbox("Kategorie", ["Feature", "Community", "Design", "Integration", "Quality of life", "Sonstiges"])
        submit = st.form_submit_button("Wunsch einreichen", type="primary", use_container_width=True)
    if submit:
        if not title.strip() or not desc.strip(): st.warning("Bitte fülle Wunsch und Details aus.")
        else:
            try: db.reference(root).push({"title": title.strip()[:120], "description": desc.strip()[:MAX_TEXT], "category": category, "author_tid": _uid(tid), "author": str(username)[:80], "status": "Neu", "votes": {}, "ts": SERVER_TS}); st.rerun()
            except Exception: _err()
    try: wishes = _items(root)
    except Exception: st.error("Community-Wünsche konnten nicht geladen werden."); return
    x, y, z = st.columns(3); x.metric("Wünsche", len(wishes)); y.metric("Noch offen", sum(w.get("status") != "Umgesetzt" for w in wishes)); z.metric("Deine Einträge", sum(str(w.get("author_tid")) == _uid(tid) for w in wishes))
    filt = st.selectbox("Status", ["Alle", "Neu", "Geplant", "In Arbeit", "Umgesetzt"], key="sd_wishlist_filter")
    shown = [w for w in wishes if filt == "Alle" or w.get("status", "Neu") == filt]; shown.sort(key=lambda w: (len(w.get("votes") or {}), _int(w.get("ts"))), reverse=True)
    for wish in shown:
        wid = wish["id"]; votes = wish.get("votes") if isinstance(wish.get("votes"), dict) else {}
        with st.container(border=True):
            st.markdown(f"#### {html.escape(str(wish.get('title') or 'Wunsch'))}"); st.caption(f"{html.escape(str(wish.get('category') or 'Allgemein'))} · {html.escape(str(wish.get('author') or 'Community'))} · {_ts(wish.get('ts'))}"); st.write(str(wish.get("description") or "")); st.caption(f"Status: {html.escape(str(wish.get('status') or 'Neu'))} · 👍 {len(votes)} Stimmen")
            vcol, scol, dcol = st.columns([1.5, 2, 1])
            if vcol.button("Stimme zurücknehmen" if _uid(tid) in votes else "👍 Unterstützen", key=f"sd_wishlist_vote_{wid}", use_container_width=True):
                try:
                    ref = db.reference(f"{root}/{wid}/votes/{_uid(tid)}"); ref.delete() if _uid(tid) in votes else ref.set(True); st.rerun()
                except Exception: _err()
            if str(wish.get("author_tid") or "") == _uid(tid):
                states = ["Neu", "Geplant", "In Arbeit", "Umgesetzt"]; current = str(wish.get("status") or "Neu")
                selected = scol.selectbox("Status ändern", states, index=states.index(current) if current in states else 0, key=f"sd_wishlist_status_{wid}")
                if scol.button("Status speichern", key=f"sd_wishlist_save_{wid}", use_container_width=True):
                    try: db.reference(f"{root}/{wid}/status").set(selected); st.rerun()
                    except Exception: _err()
                if dcol.button("Löschen", key=f"sd_wishlist_delete_{wid}", use_container_width=True):
                    try: db.reference(f"{root}/{wid}").delete(); st.rerun()
                    except Exception: _err()


def _parse_quiz(raw):
    questions = []
    for n, line in enumerate(raw.splitlines(), 1):
        if not line.strip(): continue
        parts = [p.strip()[:250] for p in line.split("|")]
        if len(parts) != 5 or any(not p for p in parts): raise ValueError(f"Zeile {n}: Frage | richtige Antwort | falsch 1 | falsch 2 | falsch 3")
        if len(set(parts[1:])) != 4: raise ValueError(f"Zeile {n}: Die vier Antworten müssen unterschiedlich sein.")
        correct, opts = parts[1], parts[1:]; secrets.SystemRandom().shuffle(opts)
        questions.append({"question": parts[0], "options": opts, "correct_index": opts.index(correct)})
    if not questions: raise ValueError("Bitte gib mindestens eine Frage ein.")
    if len(questions) > 30: raise ValueError("Maximal 30 Fragen pro Quiz.")
    return questions


def _quiz(tid, username):
    root = "streamdex_quiz_rooms"; _header("StreamDex Quiz", "COMMUNITY QUIZ ROOMS", "Erstelle einen Quizraum, teile den Code und beantworte Multiple-Choice-Fragen.")
    with st.expander("＋ Quizraum erstellen"):
        st.caption("Eine Frage pro Zeile: Frage | richtige Antwort | falsche Antwort 1 | falsche Antwort 2 | falsche Antwort 3")
        with st.form("sd_quiz_create", clear_on_submit=True):
            title = st.text_input("Quiz-Titel", max_chars=100); raw = st.text_area("Fragen", height=210, placeholder="Wie viele Bits hat ein Byte? | 8 | 4 | 16 | 32")
            submit = st.form_submit_button("Quizraum erstellen", type="primary", use_container_width=True)
        if submit:
            try:
                questions = _parse_quiz(raw); code = secrets.token_hex(3).upper(); attempts = 0
                while db.reference(f"{root}/{code}").get() and attempts < 5: code, attempts = secrets.token_hex(3).upper(), attempts + 1
                db.reference(f"{root}/{code}").set({"code": code, "title": title.strip()[:100] or "StreamDex Quiz", "created_by": _uid(tid), "created_by_name": str(username)[:80], "questions": questions, "created_at": SERVER_TS, "status": "open"})
                st.success(f"Quizraum erstellt – Code: {code}"); st.rerun()
            except ValueError as exc: st.warning(str(exc))
            except Exception: _err()
    try: rooms = [r for r in _items(root, 100) if isinstance(r.get("questions"), list) and r.get("status") != "closed"]
    except Exception: st.error("Quizräume konnten nicht geladen werden."); return
    if not rooms: st.info("Noch keine offenen Quizräume. Erstelle oben den ersten."); return
    by_code = {str(r.get("code") or r["id"]): r for r in rooms}; code = st.selectbox("Quizraum", list(by_code), format_func=lambda c: f"{by_code[c].get('title') or 'Quiz'} · {c}")
    room = by_code[code]; questions = room.get("questions") or []; answers_ref = db.reference(f"{root}/{code}/answers/{_uid(tid)}"); answers = answers_ref.get() or {}
    if not isinstance(answers, dict): answers = {}
    completed = sum(str(i) in answers for i in range(len(questions)))
    score = sum(1 for i, q in enumerate(questions) if str(i) in answers and _int(answers[str(i)].get("choice"), -1) == _int(q.get("correct_index"), -2))
    a, b, c = st.columns(3); a.metric("Fragen", len(questions)); b.metric("Beantwortet", completed); c.metric("Punkte", f"{score}/{len(questions)}")
    st.caption(f"Erstellt von {html.escape(str(room.get('created_by_name') or 'Community'))} · Code {code}")
    next_i = next((i for i in range(len(questions)) if str(i) not in answers), None)
    if next_i is None:
        st.success(f"Quiz abgeschlossen! Ergebnis: {score} von {len(questions)} Punkten.")
        if st.button("Quiz erneut spielen", key=f"sd_quiz_replay_{code}"): answers_ref.delete(); st.rerun()
    else:
        q = questions[next_i]; st.markdown(f"### Frage {next_i + 1} von {len(questions)}"); st.markdown(f"#### {html.escape(str(q.get('question') or 'Frage'))}")
        options = [str(v) for v in q.get("options") or []]
        with st.form(f"sd_quiz_answer_{code}_{next_i}"):
            choice = st.radio("Antwort", options); submit = st.form_submit_button("Antwort abgeben", type="primary", use_container_width=True)
        if submit:
            try: answers_ref.child(str(next_i)).set({"choice": options.index(choice), "ts": SERVER_TS}); st.rerun()
            except Exception: _err()
    if str(room.get("created_by") or "") == _uid(tid):
        with st.expander("Quizraum verwalten"):
            if st.button("Raum schließen", key=f"sd_quiz_close_{code}"): db.reference(f"{root}/{code}/status").set("closed"); st.rerun()
            if st.button("Raum löschen", key=f"sd_quiz_delete_{code}"): db.reference(f"{root}/{code}").delete(); st.rerun()


def _clips(tid, username):
    root = f"streamdex_clips/{_uid(tid)}/items"; _header("StreamDex Clips", "CLIP LIBRARY", "Speichere Twitch-Clips mit Tags, Notizen und Favoriten für spätere Highlights.")
    with st.form("sd_clips_add", clear_on_submit=True):
        title = st.text_input("Clip-Titel", max_chars=120); url = st.text_input("Twitch-Clip-URL", max_chars=500, placeholder="https://clips.twitch.tv/…"); tags = st.text_input("Spiel / Tags", max_chars=150); notes = st.text_area("Notizen", max_chars=1000)
        submit = st.form_submit_button("Clip hinzufügen", type="primary", use_container_width=True)
    if submit:
        p = urlparse(url.strip()); host = (p.hostname or "").lower(); valid = p.scheme in ("http", "https") and (host == "twitch.tv" or host.endswith(".twitch.tv"))
        if not title.strip() or not valid: st.warning("Bitte gib einen Titel und einen gültigen Twitch-Clip-Link ein.")
        else:
            try: db.reference(root).push({"title": title.strip()[:120], "url": url.strip()[:500], "tags": tags.strip()[:150], "notes": notes.strip()[:1000], "favorite": False, "created_by": _uid(tid), "ts": SERVER_TS}); st.rerun()
            except Exception: _err()
    try: clips = _items(root)
    except Exception: st.error("Deine Clips konnten nicht geladen werden."); return
    q = st.text_input("Sammlung durchsuchen", key="sd_clips_search").strip().casefold(); fav_only = st.checkbox("Nur Favoriten", key="sd_clips_fav_filter")
    shown = [clip for clip in clips if (not fav_only or clip.get("favorite")) and (not q or q in " ".join(str(clip.get(k) or "") for k in ("title", "tags", "notes")).casefold())]
    a, b, c = st.columns(3); a.metric("Clips", len(clips)); b.metric("Favoriten", sum(bool(v.get("favorite")) for v in clips)); c.metric("Treffer", len(shown))
    for clip in shown:
        key = clip["id"]
        with st.container(border=True):
            st.markdown(f"#### {html.escape(str(clip.get('title') or 'Clip'))}"); st.caption(f"{html.escape(str(clip.get('tags') or 'Ohne Tags'))} · {_ts(clip.get('ts'))}")
            if clip.get("notes"): st.write(str(clip["notes"]))
            x, y, z = st.columns([1.5, 1.5, 1]); x.link_button("▶ Clip öffnen", str(clip.get("url") or ""), use_container_width=True)
            if y.button("★ Favorit" if not clip.get("favorite") else "Favorit entfernen", key=f"sd_clip_fav_{key}", use_container_width=True):
                try: db.reference(f"{root}/{key}/favorite").set(not bool(clip.get("favorite"))); st.rerun()
                except Exception: _err()
            if z.button("Löschen", key=f"sd_clip_del_{key}", use_container_width=True):
                try: db.reference(f"{root}/{key}").delete(); st.rerun()
                except Exception: _err()


def _goals(tid, username):
    root = f"streamdex_goals/{_uid(tid)}/items"; _header("StreamDex Goals", "GOAL TRACKER", "Definiere messbare Ziele, setze Deadlines und aktualisiere den Fortschritt.")
    with st.form("sd_goals_new", clear_on_submit=True):
        title = st.text_input("Ziel", max_chars=120); category = st.selectbox("Bereich", ["Streaming", "Community", "Content", "Technik", "Persönlich", "Sonstiges"]); unit = st.text_input("Einheit", max_chars=30, placeholder="Stunden, Follower, Videos …")
        a, b = st.columns(2); target = a.number_input("Zielwert", min_value=1, max_value=10000000, value=10, step=1); current = b.number_input("Aktueller Stand", min_value=0, max_value=10000000, value=0, step=1); deadline = st.date_input("Deadline", value=date.today())
        submit = st.form_submit_button("Ziel erstellen", type="primary", use_container_width=True)
    if submit:
        if not title.strip(): st.warning("Bitte gib deinem Ziel einen Namen.")
        else:
            try: db.reference(root).push({"title": title.strip()[:120], "category": category, "unit": unit.strip()[:30], "target": int(target), "current": int(current), "deadline": deadline.isoformat(), "created_by": _uid(tid), "ts": SERVER_TS}); st.rerun()
            except Exception: _err()
    try: goals = _items(root)
    except Exception: st.error("Deine Ziele konnten nicht geladen werden."); return
    achieved = sum(_int(g.get("current")) >= max(1, _int(g.get("target"), 1)) for g in goals)
    a, b, c = st.columns(3); a.metric("Ziele", len(goals)); b.metric("Erreicht", achieved); c.metric("In Arbeit", len(goals) - achieved)
    for goal in goals:
        key = goal["id"]; target_n = max(1, _int(goal.get("target"), 1)); value = max(0, _int(goal.get("current"))); progress = min(1.0, value / target_n)
        with st.container(border=True):
            st.markdown(f"#### {html.escape(str(goal.get('title') or 'Ziel'))}"); st.caption(f"{html.escape(str(goal.get('category') or 'Allgemein'))} · Deadline: {html.escape(str(goal.get('deadline') or '–'))}")
            st.progress(progress, text=f"{value:,}".replace(",", ".") + f" / {target_n:,}".replace(",", ".") + (f" {goal.get('unit')}" if goal.get("unit") else "") + f" · {progress:.0%}")
            x, y, z = st.columns([2, 1, 1]); val = x.number_input("Fortschritt", min_value=0, max_value=max(target_n * 10, value, 1000000), value=value, step=1, key=f"sd_goal_value_{key}")
            if y.button("Aktualisieren", key=f"sd_goal_save_{key}", use_container_width=True):
                try: db.reference(f"{root}/{key}/current").set(int(val)); st.rerun()
                except Exception: _err()
            if z.button("Löschen", key=f"sd_goal_del_{key}", use_container_width=True):
                try: db.reference(f"{root}/{key}").delete(); st.rerun()
                except Exception: _err()


def _modlog(tid, username):
    root = f"streamdex_modlog/{_uid(tid)}/entries"; _header("StreamDex ModLog", "MODERATION / AUDIT TRAIL", "Protokolliere Timeouts, Banns, Warnungen und sonstige Moderationsaktionen.")
    with st.form("sd_modlog_new", clear_on_submit=True):
        a, b = st.columns(2); action = a.selectbox("Aktion", ["Timeout", "Ban", "Warnung", "Nachricht gelöscht", "Chat gereinigt", "Entbannt", "Sonstiges"]); target = b.text_input("Twitch-Name", max_chars=80); reason = st.text_input("Grund", max_chars=180); notes = st.text_area("Notizen / Kontext", max_chars=MAX_TEXT)
        submit = st.form_submit_button("Eintrag speichern", type="primary", use_container_width=True)
    if submit:
        if not target.strip() or not reason.strip(): st.warning("Bitte Zielnamen und Grund angeben.")
        else:
            try: db.reference(root).push({"action": action, "target": target.strip().lstrip("@")[:80], "reason": reason.strip()[:180], "notes": notes.strip()[:MAX_TEXT], "moderator": str(username)[:80], "moderator_tid": _uid(tid), "ts": SERVER_TS}); st.rerun()
            except Exception: _err()
    try: entries = _items(root)
    except Exception: st.error("Das ModLog konnte nicht geladen werden."); return
    q = st.text_input("Durchsuchen", key="sd_modlog_search").strip().casefold(); actions = ["Alle"] + sorted({str(e.get("action") or "Sonstiges") for e in entries}); filt = st.selectbox("Aktion filtern", actions, key="sd_modlog_filter")
    shown = [e for e in entries if (not q or q in " ".join(str(e.get(k) or "") for k in ("target", "reason", "notes", "action", "moderator")).casefold()) and (filt == "Alle" or e.get("action") == filt)]
    a, b, c = st.columns(3); a.metric("Einträge", len(entries)); b.metric("Treffer", len(shown)); c.metric("Timeouts / Banns", sum(e.get("action") in ("Timeout", "Ban") for e in entries))
    if shown:
        buf = io.StringIO(); writer = csv.writer(buf); writer.writerow(["Zeit", "Moderator", "Aktion", "Twitch-Name", "Grund", "Notiz"])
        for e in shown: writer.writerow([_ts(e.get("ts")), e.get("moderator", ""), e.get("action", ""), e.get("target", ""), e.get("reason", ""), e.get("notes", "")])
        st.download_button("⬇️ Gefiltertes ModLog als CSV", buf.getvalue().encode("utf-8-sig"), file_name="streamdex-modlog.csv", mime="text/csv", use_container_width=True)
    for entry in shown:
        key = entry["id"]
        with st.container(border=True):
            st.markdown(f"#### {html.escape(str(entry.get('action') or 'Moderation'))} · {html.escape(str(entry.get('target') or '–'))}"); st.caption(f"{html.escape(str(entry.get('moderator') or username))} · {_ts(entry.get('ts'))}"); st.write(f"**Grund:** {entry.get('reason') or ''}")
            if entry.get("notes"): st.write(str(entry["notes"]))
            if st.button("Eintrag löschen", key=f"sd_modlog_del_{key}"):
                try: db.reference(f"{root}/{key}").delete(); st.rerun()
                except Exception: _err()


def _modteam(tid, username):
    root = f"streamdex_modteam/{_uid(tid)}"; members_root = f"{root}/members"; tasks_root = f"{root}/tasks"
    _header("StreamDex ModTeam", "TEAM OPERATIONS", "Organisiere Teamrollen, Zuständigkeiten, Verfügbarkeit und gemeinsame Aufgaben.")
    t_members, t_tasks = st.tabs(["👥 Teammitglieder", "✅ Aufgaben"])
    with t_members:
        with st.form("sd_modteam_member", clear_on_submit=True):
            a, b = st.columns(2); name = a.text_input("Name / Anzeigename", max_chars=80); twitch = b.text_input("Twitch-Login", max_chars=40); role = st.selectbox("Rolle", ["Moderator", "Administrator", "VIP", "Editor", "Bot / Automation", "Sonstiges"]); responsibility = st.text_input("Hauptaufgabe", max_chars=120); contact = st.text_input("Kontakt / Verfügbarkeit", max_chars=180); notes = st.text_area("Notizen", max_chars=1000)
            submit = st.form_submit_button("Teammitglied hinzufügen", type="primary", use_container_width=True)
        if submit:
            if not name.strip(): st.warning("Bitte gib einen Namen an.")
            else:
                try: db.reference(members_root).push({"name": name.strip()[:80], "twitch": twitch.strip().lstrip("@")[:40], "role": role, "responsibility": responsibility.strip()[:120], "contact": contact.strip()[:180], "notes": notes.strip()[:1000], "active": True, "ts": SERVER_TS}); st.rerun()
                except Exception: _err()
        try: members = _items(members_root)
        except Exception: members = []; st.error("Teamliste konnte nicht geladen werden.")
        a, b = st.columns(2); a.metric("Mitglieder", len(members)); b.metric("Aktiv", sum(bool(m.get("active", True)) for m in members))
        for m in members:
            key = m["id"]
            with st.container(border=True):
                st.markdown(f"#### {html.escape(str(m.get('name') or 'Teammitglied'))}"); st.caption(f"{html.escape(str(m.get('role') or 'Moderator'))} · {html.escape(str(m.get('responsibility') or 'Keine Zuständigkeit'))}")
                if m.get("twitch"): st.write("Twitch: @" + str(m["twitch"]))
                if m.get("contact"): st.write("Kontakt / Verfügbarkeit: " + str(m["contact"]))
                if m.get("notes"): st.write(str(m["notes"]))
                x, y = st.columns([2, 1]); active = x.checkbox("Aktiv im Team", value=bool(m.get("active", True)), key=f"sd_modteam_active_{key}")
                if x.button("Status speichern", key=f"sd_modteam_save_{key}"):
                    try: db.reference(f"{members_root}/{key}/active").set(active); st.rerun()
                    except Exception: _err()
                if y.button("Entfernen", key=f"sd_modteam_del_{key}"):
                    try: db.reference(f"{members_root}/{key}").delete(); st.rerun()
                    except Exception: _err()
    with t_tasks:
        try: members, tasks = _items(members_root), _items(tasks_root)
        except Exception: members, tasks = [], []
        names = ["Nicht zugewiesen"] + [str(m.get("name") or m["id"]) for m in members if m.get("active", True)]; mapping = {str(m.get("name") or m["id"]): m["id"] for m in members if m.get("active", True)}
        with st.form("sd_modteam_task", clear_on_submit=True):
            title = st.text_input("Aufgabe", max_chars=120); assignee = st.selectbox("Verantwortlich", names); due = st.date_input("Fällig am", value=date.today()); detail = st.text_area("Details", max_chars=1000); submit = st.form_submit_button("Aufgabe erstellen", type="primary", use_container_width=True)
        if submit:
            if not title.strip(): st.warning("Bitte gib der Aufgabe einen Titel.")
            else:
                try:
                    who = "" if assignee == "Nicht zugewiesen" else assignee
                    db.reference(tasks_root).push({"title": title.strip()[:120], "assignee": who, "assignee_id": mapping.get(who, ""), "due": due.isoformat(), "detail": detail.strip()[:1000], "done": False, "created_by": str(username)[:80], "ts": SERVER_TS}); st.rerun()
                except Exception: _err()
        done = sum(bool(task.get("done")) for task in tasks); a, b, c = st.columns(3); a.metric("Aufgaben", len(tasks)); b.metric("Offen", len(tasks)-done); c.metric("Erledigt", done)
        for task in tasks:
            key = task["id"]
            with st.container(border=True):
                st.markdown(f"#### {'✅ ' if task.get('done') else '◻️ '}{html.escape(str(task.get('title') or 'Aufgabe'))}"); st.caption(f"Zuständig: {html.escape(str(task.get('assignee') or 'Nicht zugewiesen'))} · Fällig: {html.escape(str(task.get('due') or '–'))}")
                if task.get("detail"): st.write(str(task["detail"]))
                checked = st.checkbox("Erledigt", value=bool(task.get("done")), key=f"sd_modteam_taskdone_{key}"); a, b = st.columns([2, 1])
                if a.button("Status speichern", key=f"sd_modteam_task_save_{key}"):
                    try: db.reference(f"{tasks_root}/{key}/done").set(checked); st.rerun()
                    except Exception: _err()
                if b.button("Löschen", key=f"sd_modteam_task_del_{key}"):
                    try: db.reference(f"{tasks_root}/{key}").delete(); st.rerun()
                    except Exception: _err()


def render_streamdex_suite(tid, username, tool="ideas"):
    """Rendert ein StreamDex-Werkzeug nach erfolgreichem Twitch-Login."""
    if not has_active_user_session(st.session_state, tid):
        st.error("Für dieses Werkzeug ist eine gültige Sitzung des Kontoinhabers erforderlich.")
        return
    handlers = {"ideas": _ideas, "bracket": _bracket, "wheel": _wheel, "wishlist": _wishlist, "quiz": _quiz, "clips": _clips, "goals": _goals, "modlog": _modlog, "modteam": _modteam}
    handlers.get(str(tool or "ideas"), _ideas)(str(tid), str(username))
