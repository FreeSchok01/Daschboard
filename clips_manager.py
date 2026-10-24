"""StreamDex Clips – Twitch-Clips entdecken und privat in StreamDex importieren."""
import html
from datetime import datetime, timedelta, timezone
import urllib.parse

import streamlit as st
from firebase_admin import db
from streamdex_security import has_active_user_session

from radar import _app_token, _credentials, _http_json

CLIP_ROOT = "streamdex_clips"


@st.cache_data(ttl=180, show_spinner=False)
def _fetch_twitch_clips(tid, mode="recent"):
    client_id, client_secret = _credentials()
    token = _app_token(client_id, client_secret)
    now = datetime.now(timezone.utc)
    params = [("broadcaster_id", str(tid)), ("first", "50")]
    if mode == "recent":
        params.extend([
            ("started_at", (now - timedelta(days=7)).isoformat(timespec="seconds").replace("+00:00", "Z")),
            ("ended_at", now.isoformat(timespec="seconds").replace("+00:00", "Z")),
        ])
    url = "https://api.twitch.tv/helix/clips?" + urllib.parse.urlencode(params)
    result = _http_json(url, headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"})
    rows = result.get("data", [])
    return rows if isinstance(rows, list) else []


def _safe_clip_url(value):
    value = str(value or "").strip()
    return value if value.startswith(("https://clips.twitch.tv/", "https://www.twitch.tv/")) else ""


def _imported(tid):
    try:
        data = db.reference(f"{CLIP_ROOT}/{tid}").get() or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _clip_card(clip, tid, imported_ids, key_prefix):
    clip_id = str(clip.get("id") or "")
    if not clip_id or len(clip_id) > 100 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in clip_id):
        return
    thumb = str(clip.get("thumbnail_url") or "")
    url = _safe_clip_url(clip.get("url"))
    if not url:
        return
    with st.container(border=True):
        if thumb.startswith("https://"):
            st.image(thumb, use_container_width=True)
        st.markdown(f"**{html.escape(str(clip.get('title') or 'Twitch-Clip')[:180])}**")
        st.caption(f"{clip.get('creator_name') or 'Unbekannter Creator'} · {int(clip.get('view_count') or 0):,} Aufrufe · {int(float(clip.get('duration') or 0))} Sek.".replace(",", "."))
        created = str(clip.get("created_at") or "")
        if created:
            st.caption("Erstellt: " + created[:16].replace("T", " "))
        c1, c2 = st.columns(2)
        c1.link_button("▶ Clip ansehen", url, use_container_width=True)
        if clip_id in imported_ids:
            c2.button("✓ Importiert", key=f"{key_prefix}_{tid}_{clip_id}_done", disabled=True, use_container_width=True)
        elif c2.button("＋ Importieren", key=f"{key_prefix}_{tid}_{clip_id}_import", type="primary", use_container_width=True):
            try:
                db.reference(f"{CLIP_ROOT}/{tid}/{clip_id}").set({
                    "id": clip_id,
                    "title": str(clip.get("title") or "Twitch-Clip")[:180],
                    "url": url,
                    "embed_url": "https://clips.twitch.tv/embed?clip=" + urllib.parse.quote(clip_id, safe=""),
                    "thumbnail_url": thumb if thumb.startswith("https://") else "",
                    "creator_name": str(clip.get("creator_name") or "")[:100],
                    "view_count": int(clip.get("view_count") or 0),
                    "duration": float(clip.get("duration") or 0),
                    "created_at": created,
                    "imported_at": {".sv": "timestamp"},
                })
                st.success("Clip wurde in deiner privaten StreamDex-Sammlung gespeichert.")
                st.rerun()
            except Exception:
                st.error("Der Clip konnte nicht gespeichert werden. Bitte prüfe die Firebase-Verbindung.")


def render_clips_manager(tid, username=""):
    if not has_active_user_session(st.session_state, tid):
        st.error("Für Clips ist eine gültige Sitzung des Kontoinhabers erforderlich.")
        return
    st.markdown(
        "<div style='padding:24px;margin:0 0 18px;border:1px solid rgba(139,92,246,.3);border-radius:20px;"
        "background:linear-gradient(120deg,rgba(30,27,75,.96),rgba(8,47,73,.88));'>"
        "<div style='color:#c4b5fd;font-weight:800;font-size:.72rem;letter-spacing:.13em'>STREAMDEX OS / CLIP LIBRARY</div>"
        "<h1 style='margin:.4rem 0;color:#fff'>🎬 StreamDex Clips</h1>"
        "<p style='margin:0;color:#cbd5e1'>Importiere Twitch-Clips in deine private Sammlung, sortiere Highlights und öffne sie direkt auf Twitch.</p>"
        "</div>", unsafe_allow_html=True
    )
    st.caption(f"Clips für {username or 'deinen Twitch-Kanal'}. StreamDex speichert Metadaten und Links – keine Videodateien.")
    t_import, t_library = st.tabs(["🟣 Twitch-Clip-Import", "📚 Meine Clip-Sammlung"])
    with t_import:
        mode = st.radio("Clips laden", ["Letzte 7 Tage", "Meistgesehen"], horizontal=True, key=f"sd_clips_mode_{tid}")
        mode_key = "recent" if mode == "Letzte 7 Tage" else "popular"
        if st.button("🔄 Clips neu laden", key=f"sd_clips_refresh_{tid}"):
            _fetch_twitch_clips.clear()
            st.rerun()
        try:
            with st.spinner("Twitch-Clips werden geladen …"):
                clips = _fetch_twitch_clips(str(tid), mode_key)
        except Exception:
            st.error("Twitch-Clips konnten nicht geladen werden. Prüfe die Twitch-API-Zugangsdaten und versuche es erneut.")
            clips = []
        saved = _imported(str(tid))
        if not clips:
            st.info("Für diese Auswahl wurden keine Twitch-Clips gefunden. Bei „Letzte 7 Tage“ stammen die Ergebnisse aus der letzten Woche.")
        else:
            st.caption(f"{len(clips)} Twitch-Clips gefunden · Importiert werden nur die ausgewählten Clip-Metadaten und Links.")
            for offset in range(0, len(clips), 3):
                cols = st.columns(3, gap="medium")
                for col, clip in zip(cols, clips[offset:offset + 3]):
                    with col:
                        _clip_card(clip, str(tid), set(saved), "sd_clips_import")

    with t_library:
        saved = _imported(str(tid))
        if not saved:
            st.info("Deine Clip-Sammlung ist noch leer. Öffne den Twitch-Import und speichere deine ersten Highlights.")
        else:
            st.caption(f"{len(saved)} Clips in deiner privaten StreamDex-Sammlung.")
            rows = sorted(saved.items(), key=lambda item: str(item[1].get("created_at") or ""), reverse=True)
            for offset in range(0, len(rows), 3):
                cols = st.columns(3, gap="medium")
                for col, (clip_id, clip) in zip(cols, rows[offset:offset + 3]):
                    with col:
                        with st.container(border=True):
                            thumb = str(clip.get("thumbnail_url") or "")
                            if thumb.startswith("https://"):
                                st.image(thumb, use_container_width=True)
                            st.markdown(f"**{html.escape(str(clip.get('title') or 'Twitch-Clip')[:180])}**")
                            st.caption(f"{clip.get('creator_name') or 'Twitch'} · {int(clip.get('view_count') or 0):,} Aufrufe".replace(",", "."))
                            link = _safe_clip_url(clip.get("url"))
                            if link:
                                st.link_button("▶ Clip ansehen", link, use_container_width=True)
                            if st.button("Aus Sammlung entfernen", key=f"sd_clips_delete_{tid}_{clip_id}", use_container_width=True):
                                try:
                                    db.reference(f"{CLIP_ROOT}/{tid}/{clip_id}").delete()
                                    st.rerun()
                                except Exception:
                                    st.error("Der Clip konnte nicht entfernt werden.")
