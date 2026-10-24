"""Guided StreamDex OS onboarding and first-success shortcuts."""
import html

import streamlit as st


GUIDED_TOUR_STEPS = (
    {
        "id": "overview",
        "icon": "⌂",
        "title": "Dein persönliches Control Center",
        "benefit": "Alles Wichtige auf einen Blick",
        "description": (
            "Die Übersicht zeigt deinen Anmeldestatus, freigeschaltete Games und verfügbare "
            "Kanalstatistiken. Leere Statistiken sind normal, bis StreamDex Aktivität erfasst hat."
        ),
        "route": "dashboard",
        "action": "Übersicht öffnen",
    },
    {
        "id": "first_idea",
        "icon": "💡",
        "title": "Erreiche deinen ersten Erfolg",
        "benefit": "Speichere deine erste Idee",
        "description": (
            "Lege eine Idee für einen Stream, ein Community-Event oder eine Verbesserung an. "
            "In StreamDex Ideas kannst du sie später priorisieren und als erledigt markieren."
        ),
        "route": "ideas",
        "action": "Erste Idee anlegen",
    },
    {
        "id": "planner",
        "icon": "▦",
        "title": "Plane deinen nächsten Stream",
        "benefit": "Termine und Erinnerungen an einem Ort",
        "description": (
            "Im Planner kannst du Streams in deinen Kalender eintragen, Erinnerungen verwalten "
            "und – nach passender Twitch-Freigabe – deinen Twitch-Zeitplan synchronisieren."
        ),
        "route": "planner",
        "action": "Planner öffnen",
    },
    {
        "id": "profile",
        "icon": "♙",
        "title": "Mach dein Profil bereit",
        "benefit": "Du entscheidest, was öffentlich sichtbar ist",
        "description": (
            "Ergänze dein Creator-Profil und prüfe die Sichtbarkeit, bevor du es veröffentlichst. "
            "Du musst dein Profil nicht öffentlich machen, um StreamDex zu benutzen."
        ),
        "route": "profile",
        "action": "Creator-Profil öffnen",
    },
)


def _navigate(route):
    """Navigate via the existing query-parameter router without losing login state."""
    st.query_params.clear()
    st.query_params[str(route)] = "1"
    st.rerun()


def render_guided_tour(authenticated=False, username=""):
    """Render a short, keyboard-friendly step-by-step tour, also available to logged-out visitors."""
    state_key = "sd_guided_tour_step"
    step_index = int(st.session_state.get(state_key, 0) or 0)
    step_index = max(0, min(step_index, len(GUIDED_TOUR_STEPS) - 1))
    step = GUIDED_TOUR_STEPS[step_index]

    st.markdown(
        """
        <style>
        .sd-tour-hero{padding:clamp(18px,3vw,28px);border:1px solid rgba(139,92,246,.4);
          border-radius:17px;margin-bottom:16px;
          background:radial-gradient(ellipse at 90% 12%,rgba(34,211,238,.12),transparent 35%),
          linear-gradient(115deg,rgba(15,23,42,.98),rgba(35,25,71,.94) 63%,rgba(8,47,73,.88))}
        .sd-tour-kicker{color:#c4b5fd;font:700 .68rem 'JetBrains Mono',monospace;letter-spacing:.13em}
        .sd-tour-hero h1{font-size:clamp(1.65rem,3vw,2.35rem);font-weight:800;line-height:1.15;
          letter-spacing:-.04em;color:#f8fafc;margin:.65rem 0}
        .sd-tour-hero p{color:#cbd5e1;line-height:1.7;max-width:780px;margin:0}
        .sd-tour-step{display:flex;align-items:flex-start;gap:16px;padding:clamp(18px,3vw,30px)}
        .sd-tour-icon{display:grid;place-items:center;flex:0 0 54px;width:54px;height:54px;border-radius:15px;
          border:1px solid rgba(139,92,246,.4);background:rgba(139,92,246,.15);font-size:1.6rem}
        .sd-tour-step h2{font-size:clamp(1.2rem,2.5vw,1.65rem)!important;margin:0 0 8px!important}
        .sd-tour-benefit{font-weight:750;color:#a5f3fc;margin:0 0 10px;font-size:.87rem}
        .sd-tour-description{color:#b5c1dd;line-height:1.8;font-size:.9rem}
        .sd-tour-foot{color:#95a4c7;font-size:.78rem;line-height:1.6}
        @media(max-width:520px){.sd-tour-step{gap:11px;padding:15px;flex-direction:column}.sd-tour-icon{width:44px;height:44px;flex-basis:44px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    greeting = f" Schön, dass du da bist, {html.escape(str(username))}." if username else ""
    st.markdown(
        '<div class="sd-tour-hero"><div class="sd-tour-kicker">STREAMDEX OS · DEIN ERSTER START</div>'
        '<h1>In wenigen Schritten startklar.</h1>'
        '<p>StreamDex bündelt Planung, Ideen, Creator-Profil und Community-Werkzeuge. '
        'Dieser kurze Rundgang zeigt dir einen sinnvollen Weg zum ersten Ergebnis.'
        + greeting
        + "</p></div>",
        unsafe_allow_html=True,
    )
    st.progress((step_index + 1) / len(GUIDED_TOUR_STEPS), text=f"Schritt {step_index + 1} von {len(GUIDED_TOUR_STEPS)}")
    with st.container(border=True):
        st.markdown(
            '<div class="sd-tour-step"><div class="sd-tour-icon" aria-hidden="true">'
            + html.escape(step["icon"])
            + '</div><div><h2>'
            + html.escape(step["title"])
            + '</h2><div class="sd-tour-benefit">'
            + html.escape(step["benefit"])
            + '</div><div class="sd-tour-description">'
            + html.escape(step["description"])
            + "</div></div></div>",
            unsafe_allow_html=True,
        )
        st.divider()
        left, right, action_col = st.columns([1, 1, 2], gap="small")
        if left.button("← Zurück", disabled=step_index == 0, use_container_width=True, key="sd_tour_prev"):
            st.session_state[state_key] = step_index - 1
            st.rerun()
        if step_index < len(GUIDED_TOUR_STEPS) - 1:
            if right.button("Weiter →", type="primary", use_container_width=True, key="sd_tour_next"):
                st.session_state[state_key] = step_index + 1
                st.rerun()
        elif right.button("Rundgang beenden", type="primary", use_container_width=True, key="sd_tour_finish"):
            st.session_state.pop(state_key, None)
            _navigate("dashboard")
        if authenticated:
            if action_col.button(step["action"] + " ↗", use_container_width=True, key=f"sd_tour_action_{step['id']}"):
                st.session_state.pop(state_key, None)
                _navigate(step["route"])
        elif action_col.button("Mit Twitch anmelden ↗", type="primary", use_container_width=True, key=f"sd_tour_login_{step['id']}"):
            st.session_state.pop(state_key, None)
            _navigate("dashboard")

    st.caption(
        "Du kannst den Rundgang jederzeit erneut über „Rundgang“ in der Schnellnavigation öffnen."
        if authenticated
        else "Du kannst den Rundgang ansehen, ohne dich anzumelden. Zum Ausprobieren der Werkzeuge ist ein Twitch-Login nötig."
    )


def render_first_steps(tid):
    """Prominent but dismissible first-success checklist on the authenticated home tab."""
    dismiss_key = f"sd_quickstart_dismissed_{str(tid)}"
    if st.session_state.get(dismiss_key):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.markdown("**Dein Schnellstart ist eingeklappt.**")
            if c2.button("Anzeigen", key=f"sd_quickstart_show_{tid}", use_container_width=True):
                st.session_state[dismiss_key] = False
                st.rerun()
        return

    st.markdown("## 👋 Dein Schnellstart")
    st.caption("Starte mit einer kleinen, konkreten Aufgabe. Die Extras kannst du später in Ruhe entdecken.")
    cols = st.columns(3, gap="medium")
    cards = (
        ("💡", "1. Erste Idee speichern", "Notiere einen Einfall für Stream oder Community.", "ideas", "Idee anlegen"),
        ("▦", "2. Stream planen", "Lege einen Termin an und behalte deine Planung im Blick.", "planner", "Planner öffnen"),
        ("♙", "3. Profil vorbereiten", "Ergänze Infos und entscheide selbst über die Veröffentlichung.", "profile", "Profil bearbeiten"),
    )
    for col, (icon, title, description, route, label) in zip(cols, cards):
        with col:
            with st.container(border=True):
                st.markdown(f"### {icon} {title}")
                st.caption(description)
                if st.button(label + " →", key=f"sd_quickstart_{route}_{tid}", type="primary" if route == "ideas" else "secondary", use_container_width=True):
                    _navigate(route)

    tour_col, hide_col = st.columns([4, 1])
    if tour_col.button("✦ Geführten Rundgang starten", key=f"sd_quickstart_tour_{tid}", use_container_width=True):
        st.session_state["sd_guided_tour_step"] = 0
        _navigate("tour")
    if hide_col.button("Ausblenden", key=f"sd_quickstart_hide_{tid}", use_container_width=True):
        st.session_state[dismiss_key] = True
        st.rerun()
