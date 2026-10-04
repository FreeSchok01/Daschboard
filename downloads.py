"""Download-Buttons: öffentlich (neueste GitHub-Release) und nur für Beta-Tester. (Lurk-Download-Button ist entfernt.)

Firebase: beta/settings = {open, download_url,            <- Beta-Download (nur Freigeschaltete)
                           public_url,                    <- optional: eigener öffentlicher Link (sonst GitHub-Release)
                           lurk_url, lurk_repo}           <- Lurk: direkter Link ODER "owner/repo" (neueste Release)
"""
import json
import re
import urllib.request

import streamlit as st
from firebase_admin import db

SERVER_TS = {".sv": "timestamp"}

GITHUB_REPO = "FreeSchok01/Givewaytool"      # öffentliche StreamDex-Version
LURK_REPO = "FreeSchok01/Twitch-Auto-Lurk"   # StreamDex Lurk (Standard, in den Admin-Einstellungen überschreibbar)
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def settings():
    s = db.reference("beta/settings").get()
    return s if isinstance(s, dict) else {}


@st.cache_data(ttl=900, show_spinner=False)
def latest_release(repo):
    """Neueste Release eines GitHub-Repos: {tag, page, file}. file = direkter Download (.exe bevorzugt)."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"User-Agent": "StreamdexDashboard", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        assets = [a for a in (d.get("assets") or [])
                  if str(a.get("browser_download_url", "")).startswith("https://github.com/")]
        pick = (next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)
                or next((a for a in assets if str(a.get("name", "")).lower().endswith(".zip")), None)
                or (assets[0] if assets else None))
        page = str(d.get("html_url") or "")
        if not page.startswith("https://github.com/"):
            page = f"https://github.com/{repo}/releases/latest"
        return {"tag": str(d.get("tag_name") or ""), "page": page,
                "file": pick["browser_download_url"] if pick else None}
    except Exception:
        return None


def _https(u):
    u = str(u or "").strip()
    return u if u.startswith("https://") else ""


def public_link(cfg=None):
    """(url, version) der öffentlichen StreamDex-Version."""
    cfg = cfg if cfg is not None else settings()
    if _https(cfg.get("public_url")):
        return _https(cfg["public_url"]), ""
    rel = latest_release(GITHUB_REPO)
    if rel:
        return rel["file"] or rel["page"], rel["tag"]
    return f"https://github.com/{GITHUB_REPO}/releases/latest", ""


def lurk_link(cfg=None):
    """(url, version) von StreamDex Lurk: eigener Link > konfiguriertes Repo > Standard-Repo (neueste Release)."""
    cfg = cfg if cfg is not None else settings()
    if _https(cfg.get("lurk_url")):
        return _https(cfg["lurk_url"]), ""
    repo = str(cfg.get("lurk_repo") or "").strip()
    repo = repo if REPO_RE.match(repo) else LURK_REPO
    rel = latest_release(repo)
    if rel:
        return rel["file"] or rel["page"], rel["tag"]
    return f"https://github.com/{repo}", ""      # noch keine Release: Repo-Seite statt 404


def beta_link(cfg=None):
    cfg = cfg if cfg is not None else settings()
    return _https(cfg.get("download_url")) or None


def render_public_downloads(cfg=None):
    """Öffentlicher Download-Button (für alle sichtbar): StreamDex."""
    cfg = cfg if cfg is not None else settings()
    url, ver = public_link(cfg)
    st.link_button(f"⬇️ StreamDex herunterladen{f' ({ver})' if ver else ''}", url, type="primary", use_container_width=True)
    st.caption("Öffentliche Version")


def render_member_downloads(cfg=None):
    """Für Beta-Tester im Dashboard: Beta-Download."""
    cfg = cfg if cfg is not None else settings()
    b = beta_link(cfg)
    if b:
        st.link_button("🧪 Beta herunterladen", b, type="primary", use_container_width=True)
    else:
        st.info("Der Beta-Download-Link folgt in Kürze.")


def lurk_repo(cfg=None):
    cfg = cfg if cfg is not None else settings()
    repo = str(cfg.get("lurk_repo") or "").strip()
    return repo if REPO_RE.match(repo) else LURK_REPO


def _version_tuple(v):
    """Wie parse_v() in den Apps: alles außer Ziffern und Punkten entfernen ("Lurk v4.8.2" -> (4, 8, 2))."""
    try:
        return tuple(int(x) for x in re.sub(r"[^0-9.]", "", str(v)).split(".") if x)
    except ValueError:
        return ()


def update_notice(repo, app_version):
    """(neueste_version, release_seite), wenn auf GitHub eine neuere Release als app_version existiert, sonst None."""
    rel = latest_release(repo)
    if not rel or not rel["tag"]:
        return None
    cur, new = _version_tuple(app_version), _version_tuple(rel["tag"])
    if cur and new and new > cur:
        return rel["tag"], rel["page"]
    return None


def notify_beta_testers(url, note="", sender="Support"):
    """Schickt allen Beta-Testern (shop/beta/*) eine Support-Chat-Nachricht mit dem neuen Beta-Link.
    Erscheint in der App (Live-Support) und im Dashboard als ungelesene Support-Antwort. Gibt die Anzahl zurück."""
    testers = [t for t, v in (db.reference("shop/beta").get() or {}).items() if isinstance(v, dict)]
    text = "🧪 Neuer Beta-Build verfügbar!"
    if note.strip():
        text += f"\n{note.strip()[:300]}"
    text += f"\nDownload: {url}"
    text = text[:2000]
    for tid in testers:
        db.reference(f"chats/{tid}/messages").push({"sender": "admin", "name": sender, "text": text, "ts": SERVER_TS})
        db.reference(f"chat_meta/{tid}").update({"last_ts": SERVER_TS, "last_sender": "admin", "last_text": text[:100]})
    return len(testers)
