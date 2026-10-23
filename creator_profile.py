"""Creator profiles for StreamDex: private editor and public creator pages."""
import re
from urllib.parse import quote

import streamlit as st
from firebase_admin import db

PROFILE_ROOT = "creator_profiles"
SLUG_ROOT = "creator_profile_slugs"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
URL_FIELDS = ("twitch_url", "youtube_url", "tiktok_url", "instagram_url",
              "discord_url", "website_url", "x_url", "bluesky_url")


def _profile_ref(tid):
    return db.reference(f"{PROFILE_ROOT}/{str(tid)}")


def _slug_from_name(name, tid):
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    base = base[:28].strip("-") or "creator"
    suffix = re.sub(r"[^0-9]", "", str(tid))[-6:] or "stream"
    return f"{base}-{suffix}"


def _safe_https(value):
    value = str(value or "").strip()
    if not value:
        return True
    return value.startswith("https://") and len(value) <= 500


def render_creator_profile(tid, twitch_username=""):
    """Private profile editor. All edits are scoped to the authenticated Twitch ID."""
    tid = str(tid or "")
    try:
        ref = _profile_ref(tid)
        saved = ref.get() or {}
        if not isinstance(saved, dict):
            saved = {}
    except Exception:
        st.error("Dein Creator-Profil konnte nicht geladen werden. Bitte prüfe die Firebase-Verbindung.")
        return

    account_name = str(twitch_username or saved.get("display_name") or "")
    default_slug = str(saved.get("slug") or _slug_from_name(account_name, tid))
    st.markdown(
        "<div style='padding:22px 24px;margin:0 0 18px;border:1px solid rgba(139,92,246,.35);border-radius:20px;"
        "background:linear-gradient(120deg,rgba(30,27,75,.96),rgba(8,47,73,.88));'>"
        "<div style='color:#c4b5fd;font-weight:800;font-size:.72rem;letter-spacing:.13em'>STREAMDEX OS / CREATOR IDENTITY</div>"
        "<h1 style='margin:.35rem 0;color:#fff'>♙ Dein Creator-Profil</h1>"
        "<p style='margin:0;color:#cbd5e1'>Gestalte deine öffentliche Seite – du entscheidest, welche Informationen sichtbar sind.</p>"
        "</div>", unsafe_allow_html=True)
    is_published = bool(saved.get("published"))
    st.caption("Status: " + ("🟢 Öffentlich" if is_published else "🔒 Nicht veröffentlicht"))
    with st.form(f"creator_profile_form_{tid}", clear_on_submit=False):
        st.markdown("### Basisinformationen")
        col1, col2 = st.columns(2)
        with col1:
            display_name = st.text_input("Creator-Name", value=str(saved.get("display_name") or account_name), max_chars=80)
            headline = st.text_input("Kurzer Slogan", value=str(saved.get("headline") or ""), placeholder="Gaming, Community und gute Laune", max_chars=120)
            slug = st.text_input("Dein öffentlicher Profil-Link (Slug)", value=default_slug, max_chars=40,
                                 help="Kleinbuchstaben, Zahlen und Bindestriche; mindestens 3 Zeichen.")
            location = st.text_input("Ort / Region (optional)", value=str(saved.get("location") or ""), max_chars=100)
        with col2:
            avatar_url = st.text_input("Avatar-Bild URL (optional)", value=str(saved.get("avatar_url") or ""), placeholder="https://…", max_chars=500)
            banner_url = st.text_input("Banner-Bild URL (optional)", value=str(saved.get("banner_url") or ""), placeholder="https://…", max_chars=500)
            languages = st.text_input("Sprachen", value=str(saved.get("languages") or "Deutsch"), placeholder="Deutsch, English", max_chars=100)
            pronouns = st.text_input("Pronomen (optional)", value=str(saved.get("pronouns") or ""), max_chars=60)
        about = st.text_area("Über mich", value=str(saved.get("about") or ""), placeholder="Wer bist du, was streamst du und was macht deine Community aus?", max_chars=2500, height=150)
        col3, col4 = st.columns(2)
        with col3:
            categories = st.text_input("Games / Kategorien", value=str(saved.get("categories") or ""), placeholder="Minecraft, Just Chatting, Variety", max_chars=300)
            schedule = st.text_area("Stream-Zeitplan", value=str(saved.get("schedule") or ""), placeholder="Mo 19:00 – Minecraft\nFr 20:00 – Community-Abend", max_chars=800, height=110)
            content_style = st.text_input("Stream-Stil", value=str(saved.get("content_style") or ""), placeholder="Chillig, kompetitiv, Community …", max_chars=180)
        with col4:
            twitch_url = st.text_input("Twitch-Link", value=str(saved.get("twitch_url") or (f"https://www.twitch.tv/{account_name}" if account_name else "")), placeholder="https://www.twitch.tv/…", max_chars=500)
            youtube_url = st.text_input("YouTube", value=str(saved.get("youtube_url") or ""), placeholder="https://youtube.com/…", max_chars=500)
            tiktok_url = st.text_input("TikTok", value=str(saved.get("tiktok_url") or ""), placeholder="https://tiktok.com/@…", max_chars=500)
            instagram_url = st.text_input("Instagram", value=str(saved.get("instagram_url") or ""), placeholder="https://instagram.com/…", max_chars=500)
            discord_url = st.text_input("Discord-Invite", value=str(saved.get("discord_url") or ""), placeholder="https://discord.gg/…", max_chars=500)
            website_url = st.text_input("Eigene Website", value=str(saved.get("website_url") or ""), placeholder="https://…", max_chars=500)
            x_url = st.text_input("X / Twitter (optional)", value=str(saved.get("x_url") or ""), placeholder="https://x.com/…", max_chars=500)
            bluesky_url = st.text_input("Bluesky (optional)", value=str(saved.get("bluesky_url") or ""), placeholder="https://bsky.app/profile/…", max_chars=500)
        published = st.checkbox("Profil öffentlich veröffentlichen", value=is_published,
                                help="Wenn deaktiviert, ist das Profil über den öffentlichen Link nicht sichtbar.")
        submitted = st.form_submit_button("💾 Profil speichern", type="primary", use_container_width=True)

    if submitted:
        slug = str(slug or "").strip().lower()
        if not display_name.strip():
            st.error("Bitte trage einen Creator-Namen ein.")
            return
        if not SLUG_RE.fullmatch(slug):
            st.error("Der Profil-Link muss 3–40 Zeichen haben und nur Kleinbuchstaben, Zahlen und Bindestriche enthalten.")
            return
        values = {
            "twitch_url": twitch_url, "youtube_url": youtube_url, "tiktok_url": tiktok_url,
            "instagram_url": instagram_url, "discord_url": discord_url, "website_url": website_url,
            "x_url": x_url, "bluesky_url": bluesky_url, "avatar_url": avatar_url, "banner_url": banner_url,
        }
        invalid = [key for key, value in values.items() if not _safe_https(value)]
        if invalid:
            st.error("Bitte nutze für alle Profil- und Social-Links eine vollständige HTTPS-Adresse.")
            return

        try:
            slug_ref = db.reference(f"{SLUG_ROOT}/{slug}")
            claimed_by = slug_ref.get()
            if claimed_by and str(claimed_by) != tid:
                st.error("Dieser Profil-Link ist bereits vergeben. Bitte wähle einen anderen Slug.")
                return

            profile = {
                "owner_tid": tid,
                "slug": slug,
                "display_name": display_name.strip(),
                "headline": headline.strip(),
                "location": location.strip(),
                "avatar_url": avatar_url.strip(),
                "banner_url": banner_url.strip(),
                "languages": languages.strip(),
                "pronouns": pronouns.strip(),
                "about": about.strip(),
                "categories": categories.strip(),
                "schedule": schedule.strip(),
                "content_style": content_style.strip(),
                **{key: str(value or "").strip() for key, value in values.items() if key not in ("avatar_url", "banner_url")},
                "published": bool(published),
                "updated_at": db.SERVER_TIMESTAMP,
            }
            updates = {f"{PROFILE_ROOT}/{tid}": profile}
            old_slug = str(saved.get("slug") or "")
            if old_slug and old_slug != slug and str(db.reference(f"{SLUG_ROOT}/{old_slug}").get() or "") == tid:
                updates[f"{SLUG_ROOT}/{old_slug}"] = None
            updates[f"{SLUG_ROOT}/{slug}"] = tid if published else None
            db.reference("/").update(updates)
            st.session_state[f"creator_profile_saved_{tid}"] = True
            st.success("Dein Creator-Profil wurde gespeichert.")
            st.rerun()
        except Exception:
            st.error("Das Profil konnte nicht gespeichert werden. Bitte versuche es erneut und prüfe die Firebase-Verbindung.")

    # After a save, show a shareable URL only when publication is active.
    current = _profile_ref(tid).get() or {}
    if isinstance(current, dict) and current.get("published") and current.get("slug"):
        url = f"https://streamdex.streamlit.app/?profile={quote(str(current['slug']))}"
        st.markdown("### 🔗 Dein öffentlicher Profil-Link")
        st.code(url, language=None)
        st.link_button("👁️ Öffentliches Profil ansehen", url, use_container_width=True)
    else:
        st.info("Dein Profil ist noch privat. Aktiviere „Profil öffentlich veröffentlichen“ und speichere es, um einen öffentlichen Link zu erhalten.")


def render_public_profile(slug):
    """Render only profiles explicitly published in StreamDex."""
    slug = str(slug or "").strip().lower()
    if not SLUG_RE.fullmatch(slug):
        st.title("♙ Creator-Profil")
        st.error("Dieser Profil-Link ist ungültig.")
        return
    try:
        tid = db.reference(f"{SLUG_ROOT}/{slug}").get()
        if not tid or not re.fullmatch(r"[0-9]{1,15}", str(tid)):
            st.title("♙ Creator-Profil")
            st.info("Dieses Creator-Profil wurde nicht gefunden oder ist nicht öffentlich.")
            return
        profile = _profile_ref(str(tid)).get()
    except Exception:
        st.error("Das Creator-Profil ist gerade nicht erreichbar. Bitte versuche es später erneut.")
        return
    if not isinstance(profile, dict) or not profile.get("published") or profile.get("slug") != slug:
        st.title("♙ Creator-Profil")
        st.info("Dieses Creator-Profil wurde nicht gefunden oder ist nicht öffentlich.")
        return

    name = str(profile.get("display_name") or "Creator")
    st.markdown(
        "<div style='padding:26px;margin:0 0 18px;border:1px solid rgba(139,92,246,.35);border-radius:22px;"
        "background:linear-gradient(120deg,rgba(30,27,75,.96),rgba(8,47,73,.88));'>"
        "<div style='color:#c4b5fd;font-weight:800;font-size:.72rem;letter-spacing:.13em'>STREAMDEX OS / CREATOR PROFILE</div>"
        f"<h1 style='margin:.5rem 0;color:#fff'>{__import__('html').escape(name)}</h1>"
        f"<p style='margin:0;color:#cbd5e1'>{__import__('html').escape(str(profile.get('headline') or ''))}</p>"
        "</div>", unsafe_allow_html=True)
    banner = str(profile.get("banner_url") or "")
    if banner.startswith("https://"):
        st.image(banner, use_container_width=True)
    avatar = str(profile.get("avatar_url") or "")
    left, right = st.columns([1, 3], gap="large")
    with left:
        if avatar.startswith("https://"):
            st.image(avatar, use_container_width=True)
        st.markdown("### 🔗 Socials")
        social_labels = (
            ("twitch_url", "🟣 Twitch"), ("youtube_url", "▶️ YouTube"),
            ("tiktok_url", "🎵 TikTok"), ("instagram_url", "📸 Instagram"),
            ("discord_url", "💬 Discord"), ("website_url", "🌐 Website"),
            ("x_url", "𝕏 X / Twitter"), ("bluesky_url", "🦋 Bluesky"),
        )
        for key, label in social_labels:
            url = str(profile.get(key) or "")
            if url.startswith("https://"):
                st.link_button(label, url, use_container_width=True)
    with right:
        tags = [x.strip() for x in str(profile.get("categories") or "").split(",") if x.strip()]
        if tags:
            st.markdown("### 🎮 Games & Kategorien")
            st.markdown(" · ".join(f"`{tag}`" for tag in tags[:20]))
        if profile.get("about"):
            st.markdown("### 👋 Über mich")
            st.write(profile["about"])
        meta = []
        if profile.get("location"):
            meta.append(f"📍 {profile['location']}")
        if profile.get("languages"):
            meta.append(f"🗣️ {profile['languages']}")
        if profile.get("pronouns"):
            meta.append(f"💬 {profile['pronouns']}")
        if profile.get("content_style"):
            meta.append(f"✨ {profile['content_style']}")
        if meta:
            st.markdown(" · ".join(meta))
        if profile.get("schedule"):
            st.markdown("### 📅 Stream-Zeitplan")
            st.text(str(profile["schedule"]))
        st.caption("Creator-Profil bei StreamDex OS")
    st.divider()
    st.markdown("[⚡ StreamDex – dein Creator Control Center](https://streamdex.streamlit.app/?dashboard=1)")
