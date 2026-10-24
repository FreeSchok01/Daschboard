"""Admin user overview: Twitch accounts, website login metadata and persisted tool usage."""
from datetime import datetime
import json
import time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
ONLINE_STALE_SECONDS = 150
TOOLS = [
    ("ideas", "💡 StreamDex Ideas"), ("bracket", "🏆 StreamDex Bracket"),
    ("wheel", "🎡 StreamDex Wheel"), ("wishlist", "🎁 StreamDex Wishlist"),
    ("feedback", "💬 StreamDex Feedback"), ("quiz", "🧠 StreamDex Quiz"),
    ("clips", "🎬 StreamDex Clips"), ("goals", "🎯 StreamDex Goals"),
    ("modlog", "🛡️ StreamDex ModLog"), ("modteam", "👥 StreamDex ModTeam"),
    ("radar", "📡 StreamDex Radar"), ("planner", "▣ Planner"),
    ("profile", "♙ Creator-Profil"), ("events", "🎉 Events"), ("legacy", "📜 Legacy"),
]


def _read(path):
    try:
        value = db.reference(path).get()
        return value if value is not None else {}
    except Exception:
        return {}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _count(value):
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list):
        return sum(item is not None for item in value)
    return 0


def _number(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _fmt_ts(value):
    try:
        n = _number(value)
        if not n:
            return "—"
        if n < 10_000_000_000:
            n *= 1000
        return datetime.fromtimestamp(n / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _fmt_age(value):
    n = _number(value)
    if not n:
        return "Noch nie"
    delta = max(0, int(time.time() * 1000 - n) // 1000)
    if delta < 60:
        return f"vor {delta} Sek."
    if delta < 3600:
        return f"vor {delta // 60} Min."
    if delta < 86400:
        return f"vor {delta // 3600} Std."
    return f"vor {delta // 86400} Tagen"


@st.cache_data(ttl=45, show_spinner=False)
def _read_user_index():
    """Read compact account metadata only; never read tokens or secrets."""
    presence = _dict(_read("presence"))
    web_auth = _dict(_read("streamdex_web_auth"))
    stats = _dict(_read("stats"))
    game_flags = _dict(_read("game_flags/streamers"))
    beta = _dict(_read("shop/beta"))
    now_ms = int(time.time() * 1000)
    user_ids = set(presence) | set(web_auth) | set(stats) | set(game_flags) | set(beta)
    rows = []
    for tid in user_ids:
        p = _dict(presence.get(tid))
        web = _dict(web_auth.get(tid))
        stat = _dict(stats.get(tid))
        seen = _number(p.get("last_seen"))
        online = p.get("status") == "online" and seen > 0 and now_ms - seen <= ONLINE_STALE_SECONDS * 1000
        web_login = bool(web) or p.get("registered_via") == "twitch_web_login"
        last_web = _number(web.get("last_login_ms"))
        rows.append({
            "tid": str(tid),
            "name": str(p.get("twitch_username") or web.get("display_name") or web.get("login") or tid),
            "web_login": web_login,
            "login_count": _number(web.get("login_count"), 1 if web_login else 0),
            "last_web_login_ms": last_web, "last_seen_ms": seen, "online": online,
            "status": "Online" if online else ("Blockiert" if p.get("status") == "blocked" else "Offline"),
            "version": str(p.get("app_version") or "—"),
            "registered_via": str(p.get("registered_via") or ("Twitch Web" if web_login else "Desktop / Altbestand")),
            "giveaways": _number(stat.get("giveaways")),
            "participants": _number(stat.get("giveaway_participants")),
            "checkins": _number(stat.get("checkins")),
            "slot_spins": _number(stat.get("slot_spins")),
            "beta": bool(_dict(beta.get(tid))),
            "unlocked_overrides": sum(isinstance(v, bool) and v for v in _dict(game_flags.get(tid)).values()),
        })
    rows.sort(key=lambda row: (row["last_web_login_ms"], row["last_seen_ms"], row["name"].lower()), reverse=True)
    return rows


def _tool_row(label, key, records, usage, note=""):
    visit = _dict(usage.get(key))
    return {
        "Werkzeug": label, "Gespeicherte Einträge": int(records or 0),
        "Direkte Seitenaufrufe": _number(visit.get("visit_count")),
        "Zuletzt direkt geöffnet": _fmt_ts(visit.get("last_used_ms")),
        "Datenspur": note or ("Daten vorhanden" if records else "Keine gespeicherten Einträge gefunden"),
    }


def _load_user_detail(tid):
    p = _dict(_read(f"presence/{tid}"))
    web = _dict(_read(f"streamdex_web_auth/{tid}"))
    stat = _dict(_read(f"stats/{tid}"))
    profile = _dict(_read(f"creator_profiles/{tid}"))
    flags = _dict(_read(f"game_flags/streamers/{tid}"))
    global_flags = _dict(_read("game_flags/global"))
    beta = _dict(_read(f"shop/beta/{tid}"))
    usage = _dict(_read(f"streamdex_tool_usage/{tid}"))

    ideas = _read(f"streamdex_ideas/{tid}/items")
    bracket = _dict(_read(f"streamdex_brackets/{tid}/active"))
    wheel_options = _read(f"streamdex_wheel/{tid}/options")
    wheel_runs = _read(f"streamdex_wheel/{tid}/runs")
    wish_root = _dict(_read("streamdex_community_wishlist"))
    wishes = [v for v in wish_root.values() if isinstance(v, dict) and str(v.get("author_tid") or "") == str(tid)]
    wish_votes = sum(1 for v in wish_root.values() if isinstance(v, dict) and str(tid) in _dict(v.get("votes")))
    feedback_root = _dict(_read("feedback_inbox"))
    feedback = [v for v in feedback_root.values() if isinstance(v, dict) and str(v.get("tid") or "") == str(tid)]
    feedback_votes = sum(1 for v in feedback_root.values() if isinstance(v, dict) and v.get("community_visible") and str(tid) in _dict(v.get("votes")))
    poll_root = _dict(_read("community_polls"))
    polls_created = [v for v in poll_root.values() if isinstance(v, dict) and str(v.get("created_by") or "") == str(tid)]
    poll_votes = sum(1 for v in poll_root.values() if isinstance(v, dict) and str(tid) in _dict(v.get("votes")))
    quiz_root = _dict(_read("streamdex_quiz_rooms"))
    quiz_created = [v for v in quiz_root.values() if isinstance(v, dict) and str(v.get("created_by") or "") == str(tid)]
    quiz_answers = sum(1 for v in quiz_root.values() if isinstance(v, dict) and _count(_dict(v.get("answers")).get(str(tid))))
    clips_root = _dict(_read(f"streamdex_clips/{tid}"))
    clips_suite = _dict(clips_root.get("items"))
    clips_legacy = {k: v for k, v in clips_root.items() if k != "items" and isinstance(v, dict) and (v.get("url") or v.get("id"))}
    goals = _read(f"streamdex_goals/{tid}/items")
    modlog = _read(f"streamdex_modlog/{tid}/entries")
    modteam = _dict(_read(f"streamdex_modteam/{tid}"))
    members, tasks = _dict(modteam.get("members")), _dict(modteam.get("tasks"))
    planner = _dict(_read(f"streamdex_planner/{tid}"))
    planner_streams = _dict(planner.get("streams"))
    radar = _dict(_read(f"radar_watchlists/{tid}"))
    radar_names = radar.get("names", []) if isinstance(radar.get("names", []), list) else []
    events_root = _dict(_read("streamdex_events"))
    own_events = [v for v in events_root.values() if isinstance(v, dict) and str(v.get("owner_tid") or "") == str(tid)]
    chats = _read(f"chats/{tid}/messages")
    stats_history = _read(f"stats_history/{tid}")
    giveaway_log = _read(f"giveaway_log/{tid}")

    tool_rows = [
        _tool_row("StreamDex Ideas", "ideas", _count(ideas), usage),
        _tool_row("StreamDex Bracket", "bracket", int(bool(bracket.get("title"))), usage),
        _tool_row("StreamDex Wheel", "wheel", _count(wheel_runs), usage, f"{_count(wheel_options)} Rad-Einträge · {_count(wheel_runs)} Drehungen"),
        _tool_row("StreamDex Wishlist", "wishlist", len(wishes), usage, f"{len(wishes)} eigene Wünsche · {wish_votes} Stimmen abgegeben"),
        _tool_row("StreamDex Feedback", "feedback", len(feedback), usage, f"{len(feedback)} Einreichungen · {feedback_votes} Stimmen für Vorschläge"),
        _tool_row("StreamDex Quiz", "quiz", len(quiz_created) + quiz_answers, usage, f"{len(quiz_created)} Räume erstellt · {quiz_answers} Antwortsätze"),
        _tool_row("StreamDex Clips", "clips", len(clips_suite) + len(clips_legacy), usage),
        _tool_row("StreamDex Goals", "goals", _count(goals), usage),
        _tool_row("StreamDex ModLog", "modlog", _count(modlog), usage),
        _tool_row("StreamDex ModTeam", "modteam", _count(members) + _count(tasks), usage, f"{_count(members)} Mitglieder · {_count(tasks)} Aufgaben"),
        _tool_row("StreamDex Radar", "radar", len(radar_names), usage, f"{len(radar_names)} Kanäle in der Watchlist"),
        _tool_row("Planner", "planner", _count(planner_streams), usage, f"{_count(planner_streams)} geplante Streams"),
        _tool_row("Creator-Profil", "profile", int(bool(profile)), usage, "Öffentlich" if profile.get("published") else ("Entwurf vorhanden" if profile else "Kein Profil")),
        _tool_row("Community-Events", "events", len(own_events), usage),
        _tool_row("Legacy / Verlauf", "legacy", _count(stats_history), usage),
    ]
    return {
        "presence": p, "web_auth": web, "stats": stat, "profile": profile, "flags": flags,
        "global_flags": global_flags, "beta": beta, "tool_usage": usage, "tool_rows": tool_rows,
        "counts": {
            "ideas": _count(ideas), "bracket": int(bool(bracket.get("title"))),
            "wheel_runs": _count(wheel_runs), "wishlist": len(wishes), "feedback": len(feedback),
            "quiz_created": len(quiz_created), "quiz_answers": quiz_answers,
            "clips": len(clips_suite) + len(clips_legacy), "goals": _count(goals),
            "modlog": _count(modlog), "modteam_members": _count(members), "modteam_tasks": _count(tasks),
            "planner_streams": _count(planner_streams), "events": len(own_events),
            "support_messages": _count(chats), "giveaway_log": _count(giveaway_log),
        },
    }


def render_user_admin():
    """Admin-only account overview; called only from the password-protected admin route."""
    st.markdown("""
    <div class="sd-users-hero"><div class="sd-users-kicker">STREAMDEX OS / ADMIN CONSOLE</div>
    <h1>👤 User-Verwaltung</h1>
    <p>Registrierte Konten, Website-Login-Verlauf und vorhandene Tool-Daten – zentral pro Twitch-Konto.</p></div>
    <style>
    .sd-users-hero{border:1px solid rgba(139,92,246,.34);border-radius:18px;padding:22px 25px;margin-bottom:18px;
      background:radial-gradient(ellipse at 85% 15%,rgba(34,211,238,.12),transparent 38%),linear-gradient(115deg,rgba(15,23,42,.98),rgba(35,25,71,.94) 60%,rgba(8,47,73,.9))}
    .sd-users-kicker{font:700 .67rem 'JetBrains Mono',monospace;letter-spacing:.14em;color:#c4b5fd}
    .sd-users-hero h1{font-size:clamp(1.7rem,2.7vw,2.35rem);font-weight:800;letter-spacing:-.045em;margin:9px 0;color:#f8fafc}
    .sd-users-hero p{font-size:.86rem;line-height:1.65;color:#cbd5e1;margin:0;max-width:850px}
    </style>
    """, unsafe_allow_html=True)
    if st.button("🔄 User-Daten aktualisieren", key="admin_users_refresh"):
        _read_user_index.clear()
        st.rerun()
    try:
        users = _read_user_index()
    except Exception:
        st.error("Die Benutzerliste konnte nicht aus Firebase geladen werden.")
        return

    now_ms = int(time.time() * 1000)
    website_users = [u for u in users if u["web_login"]]
    online_users = [u for u in users if u["online"]]
    recent_logins = [u for u in website_users if u["last_web_login_ms"] and now_ms - u["last_web_login_ms"] <= 30 * 86400 * 1000]
    a, b, c, d = st.columns(4)
    a.metric("Erfasste Konten", len(users))
    b.metric("Website-Logins erfasst", len(website_users))
    c.metric("Aktuell online", len(online_users))
    d.metric("Website-Logins (30 Tage)", len(recent_logins))
    st.caption("Website-Login-Zähler werden ab Aktivierung dieser Funktion erfasst. Ältere Konten können bereits existieren, ohne dass frühere Web-Anmeldungen gezählt wurden.")

    f1, f2, f3 = st.columns([2, 1.4, 1.2])
    query = f1.text_input("User suchen", placeholder="Twitch-Name oder Twitch-ID", key="admin_users_search").strip().casefold()
    account_filter = f2.selectbox("Kontotyp", ["Alle Konten", "Website-Login erfasst", "Aktuell online"], key="admin_users_type")
    sort_order = f3.selectbox("Sortieren nach", ["Letzter Website-Login", "Letzte Aktivität", "Name"], key="admin_users_sort")
    visible = users[:]
    if account_filter == "Website-Login erfasst":
        visible = [u for u in visible if u["web_login"]]
    elif account_filter == "Aktuell online":
        visible = [u for u in visible if u["online"]]
    if query:
        visible = [u for u in visible if query in u["name"].casefold() or query in u["tid"]]
    if sort_order == "Name":
        visible.sort(key=lambda u: u["name"].casefold())
    elif sort_order == "Letzte Aktivität":
        visible.sort(key=lambda u: u["last_seen_ms"], reverse=True)
    else:
        visible.sort(key=lambda u: (u["last_web_login_ms"], u["last_seen_ms"]), reverse=True)

    view = pd.DataFrame([{
        "Twitch-Name": u["name"], "Twitch-ID": u["tid"],
        "Website-Login": "Ja" if u["web_login"] else "Nicht erfasst",
        "Web-Logins": u["login_count"], "Letzter Website-Login": _fmt_ts(u["last_web_login_ms"]),
        "Status": u["status"], "Letzte Aktivität": _fmt_age(u["last_seen_ms"]),
        "App-Version": u["version"], "Giveaways": u["giveaways"],
        "Teilnahmen": u["participants"], "Beta": "Ja" if u["beta"] else "Nein",
    } for u in visible])
    st.markdown(f"### Konten als Karten ({len(visible)})")
    if view.empty:
        st.info("Keine Konten entsprechen den aktuellen Filtern.")
    else:
        st.download_button("⬇️ Diese User-Liste als CSV", data=view.to_csv(index=False).encode("utf-8-sig"),
                           file_name="streamdex-user-liste.csv", mime="text/csv", key="admin_users_csv")
        st.caption("Klicke bei einem Konto auf „Details anzeigen“, um die zugehörigen Nutzungsdaten, Statistiken und Tool-Einträge zu öffnen.")
        st.markdown("""
        <style>
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(139,92,246,.34);
            border-radius: 15px;
            background: linear-gradient(145deg, rgba(30,41,59,.45), rgba(49,29,87,.22));
        }
        </style>
        """, unsafe_allow_html=True)
        card_columns = st.columns(3)
        for index, user in enumerate(visible):
            with card_columns[index % len(card_columns)]:
                with st.container(border=True):
                    st.markdown(f"#### 👤 {user['name']}")
                    st.caption(f"Twitch-ID: {user['tid']}")
                    status_col, login_col = st.columns(2)
                    status_col.metric("Status", user["status"])
                    login_col.metric("Web-Logins", user["login_count"] if user["web_login"] else "—")
                    st.caption(f"Letzte Aktivität: {_fmt_age(user['last_seen_ms'])}")
                    st.caption(f"Letzter Website-Login: {_fmt_ts(user['last_web_login_ms'])}")
                    badges = []
                    if user["beta"]:
                        badges.append("🧪 Beta-Tester")
                    if user["web_login"]:
                        badges.append("🌐 Website-Login")
                    if user["version"] != "—":
                        badges.append(f"📦 Version {user['version']}")
                    if badges:
                        st.caption(" · ".join(badges))
                    if st.button("📂 Details anzeigen", key=f"admin_user_card_{user['tid']}",
                                 use_container_width=True,
                                 type="primary" if st.session_state.get("admin_user_selected_tid") == user["tid"] else "secondary"):
                        st.session_state["admin_user_selected_tid"] = user["tid"]
                        st.rerun()

        selected_tid = st.session_state.get("admin_user_selected_tid")
        visible_ids = {u["tid"] for u in visible}
        if selected_tid not in visible_ids:
            selected_tid = None
            st.session_state.pop("admin_user_selected_tid", None)
        if selected_tid and st.button("✕ Detailansicht schließen", key="admin_user_close_detail"):
            st.session_state.pop("admin_user_selected_tid", None)
            st.rerun()
        if selected_tid:
        with st.spinner("Tool-Daten werden zusammengeführt …"):
            detail = _load_user_detail(selected_tid)
        selected = next((u for u in visible if u["tid"] == selected_tid), {})
        st.divider()
        st.markdown(f"## 👤 {str(selected.get('name') or selected_tid)}")
        st.caption(f"Twitch-ID: {selected_tid} · {selected.get('status', 'Unbekannt')} · Version {selected.get('version', '—')}")
        login_col, active_col, profile_col, beta_col = st.columns(4)
        login_col.metric("Website-Logins", _number(detail["web_auth"].get("login_count"), 1 if selected.get("web_login") else 0))
        active_col.metric("Letzter Website-Login", _fmt_ts(detail["web_auth"].get("last_login_ms")))
        profile_col.metric("Creator-Profil", "Öffentlich" if detail["profile"].get("published") else ("Vorhanden" if detail["profile"] else "Keins"))
        beta_col.metric("Beta-Tester", "Ja" if detail["beta"] else "Nein")
        if detail["profile"]:
            with st.expander("Creator-Profil-Metadaten"):
                st.write(f"**Creator-Name:** {detail['profile'].get('display_name') or selected.get('name') or '—'}")
                st.write(f"**Slug:** {detail['profile'].get('slug') or '—'}")
                st.write(f"**Aktualisiert:** {_fmt_ts(detail['profile'].get('updated_at'))}")
        st.markdown("### 🧰 Tool-Nutzung & gespeicherte Daten")
        st.caption("Gespeicherte Einträge zeigen, ob ein Werkzeug genutzt wurde. Direkte Seitenaufrufe werden ab jetzt gezählt; normale Streamlit-Tabs melden keine zuverlässige Auswahl und werden daher nicht als Aufruf gewertet.")
        tools_df = pd.DataFrame(detail["tool_rows"])
        st.dataframe(tools_df, hide_index=True, use_container_width=True)
        st.download_button("⬇️ Tool-Übersicht als CSV", data=tools_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"streamdex-tools-{selected_tid}.csv", mime="text/csv", key="admin_user_tools_csv")
        st.markdown("### 📊 Vorhandene StreamDex-Statistiken")
        stats = detail["stats"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Giveaways", _number(stats.get("giveaways")))
        m2.metric("Giveaway-Teilnahmen", _number(stats.get("giveaway_participants")))
        m3.metric("Check-ins", _number(stats.get("checkins")))
        m4.metric("Slot-Spins", _number(stats.get("slot_spins")))
        m5, m6, m7, m8 = st.columns(4)
        m5.metric("Mega-Slot-Spins", _number(stats.get("megaslot_spins")))
        m6.metric("Fänge", _number(stats.get("fish_catches")))
        m7.metric("Ernten", _number(stats.get("harvests")))
        m8.metric("Raids", _number(stats.get("raids")))
        st.markdown("### 🎮 Game-Freigaben")
        game_keys = sorted(set(detail["global_flags"]) | set(detail["flags"]))
        if game_keys:
            game_df = pd.DataFrame([{
                "Game": key,
                "Global": "Frei" if detail["global_flags"].get(key) is True else ("Gesperrt" if detail["global_flags"].get(key) is False else "Standard"),
                "User-Override": "Frei" if detail["flags"].get(key) is True else ("Gesperrt" if detail["flags"].get(key) is False else "Standard"),
            } for key in game_keys])
            st.dataframe(game_df, hide_index=True, use_container_width=True)
        else:
            st.caption("Keine individuellen Game-Freigaben gefunden.")
        st.markdown("### 🕘 Website-Aktivität")
        visit_rows = []
        for key, label in TOOLS:
            entry = _dict(detail["tool_usage"].get(key))
            if _number(entry.get("visit_count")) or entry.get("last_used_ms"):
                visit_rows.append({"Werkzeug": label, "Aufrufe": _number(entry.get("visit_count")), "Zuletzt geöffnet": _fmt_ts(entry.get("last_used_ms"))})
        if visit_rows:
            st.dataframe(pd.DataFrame(visit_rows), hide_index=True, use_container_width=True)
        else:
            st.info("Direkte Tool-Aufrufe werden ab jetzt erfasst. Für frühere Besuche gibt es keine verlässliche Verlaufshistorie.")
        report = {
            "twitch_id": selected_tid, "name": selected.get("name"), "status": selected.get("status"),
            "website_login": bool(selected.get("web_login")), "login_count": _number(detail["web_auth"].get("login_count")),
            "last_web_login": _fmt_ts(detail["web_auth"].get("last_login_ms")), "version": selected.get("version"),
            "stats": stats, "tool_usage": detail["tool_rows"], "game_flags_global": detail["global_flags"],
            "game_flags_user": detail["flags"], "profile_published": bool(detail["profile"].get("published")),
            "beta_tester": bool(detail["beta"]), "record_counts": detail["counts"],
        }
        st.download_button("⬇️ User-Bericht als JSON", data=json.dumps(report, ensure_ascii=False, indent=2, default=str),
                           file_name=f"streamdex-user-{selected_tid}.json", mime="application/json", key="admin_user_report_json")
