"""Download-Buttons: öffentlich (neueste GitHub-Release), nur für Beta-Tester, StreamDex Lurk.

Firebase: beta/settings = {open, download_url,            <- Beta-Download (nur Freigeschaltete)
                           public_url,                    <- optional: eigener öffentlicher Link (sonst GitHub-Release)
                           lurk_url, lurk_repo}           <- Lurk: direkter Link ODER "owner/repo" (neueste Release)
"""
import json
import re
import urllib.request

import streamlit as st
from firebase_admin import db

GITHUB_REPO = "FreeSchok01/Givewaytool"      # öffentliche StreamDex-Version
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
    """(url, version) von StreamDex Lurk oder (None, "") wenn noch nichts hinterlegt ist."""
    cfg = cfg if cfg is not None else settings()
    if _https(cfg.get("lurk_url")):
        return _https(cfg["lurk_url"]), ""
    repo = str(cfg.get("lurk_repo") or "").strip()
    if REPO_RE.match(repo):
        rel = latest_release(repo)
        if rel:
            return rel["file"] or rel["page"], rel["tag"]
        return f"https://github.com/{repo}/releases/latest", ""
    return None, ""


def beta_link(cfg=None):
    cfg = cfg if cfg is not None else settings()
    return _https(cfg.get("download_url")) or None


def render_public_downloads(cfg=None):
    """Öffentliche Download-Buttons (für alle sichtbar): StreamDex + Lurk."""
    cfg = cfg if cfg is not None else settings()
    c1, c2 = st.columns(2)
    url, ver = public_link(cfg)
    c1.link_button(f"⬇️ StreamDex herunterladen{f' ({ver})' if ver else ''}", url, type="primary", use_container_width=True)
    c1.caption("Öffentliche Version")
    lurk, lver = lurk_link(cfg)
    if lurk:
        c2.link_button(f"⬇️ StreamDex Lurk herunterladen{f' ({lver})' if lver else ''}", lurk, use_container_width=True)
        c2.caption("Lurk-App")
    else:
        c2.button("⬇️ StreamDex Lurk (folgt)", disabled=True, use_container_width=True)


def render_member_downloads(cfg=None):
    """Für Beta-Tester im Dashboard: Beta-Download + Lurk."""
    cfg = cfg if cfg is not None else settings()
    b = beta_link(cfg)
    lurk, lver = lurk_link(cfg)
    c1, c2 = st.columns(2)
    if b:
        c1.link_button("🧪 Beta herunterladen", b, type="primary", use_container_width=True)
    else:
        c1.info("Der Beta-Download-Link folgt in Kürze.")
    if lurk:
        c2.link_button(f"⬇️ StreamDex Lurk{f' ({lver})' if lver else ''}", lurk, use_container_width=True)
