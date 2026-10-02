"""Beta-Bewerbung: öffentliche Bewerbungsseite (/?beta=1) und Verwaltung für Admin/Supporter.

Firebase-Struktur:
  beta_applications/{twitchname} = {name, reason, agreed, code_hash, status, ts, decided_by, decided_ts,
                                    reject_reason, tid, applied}
      status: pending | approved | rejected
      applied: True, sobald der Beta-Status (shop/beta) in der App-Kennung gesetzt wurde
  beta_codes/{twitchname} = Klartext-Zugangscode (nur Admin-Ansicht; Bewerber haben ihn vergessen)
  beta/settings = {open: bool, download_url: str}
"""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db

from downloads import REPO_RE, beta_link, notify_beta_testers, render_public_downloads
from shop import remove_beta, set_beta

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}
NAME_RE = re.compile(r"^[a-z0-9_]{3,25}$")
MIN_REASON = 30
MAX_REASON = 1000
STATUS_LABEL = {"pending": "⏳ In Prüfung", "approved": "✅ Freigeschaltet", "rejected": "❌ Abgelehnt"}
FILTERS = {"⏳ In Prüfung": "pending", "✅ Freigeschaltet": "approved", "❌ Abgelehnt": "rejected", "Alle": None}


def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _hash(code):
    return hashlib.sha256(code.strip().encode()).hexdigest()


def _key(name):
    return (name or "").strip().lstrip("@").lower()


def _settings():
    s = db.reference("beta/settings").get()
    return s if isinstance(s, dict) else {}


def _find_tid(name):
    """Twitch-ID, sobald die Person die App mindestens einmal gestartet hat."""
    for tid, p in (db.reference("presence").get() or {}).items():
        if isinstance(p, dict) and str(p.get("twitch_username", "")).lower() == _key(name):
            return tid
    return None


# ----------------------------------------------------------------------------
# Öffentliche Seite
# ----------------------------------------------------------------------------
def _apply_form(cfg):
    if cfg.get("open", True) is False:
        st.info("Die Bewerbungen sind gerade geschlossen. Schau bald wieder vorbei!")
        return
    st.markdown("Bewirb dich als Beta-Tester. Wenn du freigeschaltet wirst, bekommst du Zugang zum Download "
                "und den **Beta-Status** (Games ohne Kauf freigeschaltet).")
    with st.form("beta_apply"):
        name = st.text_input("Dein Twitch-Name", max_chars=25, placeholder="z.B. meinkanal")
        reason = st.text_area(f"Warum möchtest du Beta-Tester sein? (min. {MIN_REASON} Zeichen)",
                              max_chars=MAX_REASON, height=140)
        a1 = st.checkbox("Ich gebe die Beta-Version und ihre Inhalte **nicht an Dritte weiter**.")
        a2 = st.checkbox("Mir ist bewusst, dass die Beta noch **Bugs enthalten kann**.")
        a3 = st.checkbox("Ich **melde Bugs, Feedback und Ideen**, damit das System verbessert werden kann.")
        if st.form_submit_button("📨 Bewerbung absenden", type="primary"):
            k = _key(name)
            if not NAME_RE.match(k):
                st.error("Bitte einen gültigen Twitch-Namen eingeben (a-z, 0-9, _, 3-25 Zeichen).")
            elif len(reason.strip()) < MIN_REASON:
                st.error(f"Bitte erzähl uns etwas mehr (mindestens {MIN_REASON} Zeichen).")
            elif not (a1 and a2 and a3):
                st.error("Bitte bestätige alle drei Punkte.")
            else:
                code = secrets.token_urlsafe(9)
                rec = {"name": k, "reason": reason.strip()[:MAX_REASON], "agreed": True, "status": "pending",
                       "code_hash": _hash(code), "ts": SERVER_TS}
                res = db.reference(f"beta_applications/{k}").transaction(lambda cur: cur if cur is not None else rec)
                if isinstance(res, dict) and res.get("code_hash") == rec["code_hash"]:
                    try:
                        db.reference(f"beta_codes/{k}").set(code)    # nur für die Admin-Ansicht (Code vergessen)
                    except Exception:
                        pass
                    st.success("Bewerbung gesendet! Wir prüfen sie so schnell wie möglich.")
                    st.warning("**Dein Zugangscode (wird nur jetzt angezeigt, bitte speichern):**")
                    st.code(code, language=None)
                    st.caption("Mit Twitch-Name und Code siehst du unter „Status & Download“, ob du freigeschaltet bist.")
                else:
                    st.error("Für diesen Twitch-Namen gibt es schon eine Bewerbung. Prüfe den Status im Reiter „Status & Download“.")


def _status_view(cfg):
    st.markdown("Gib deinen Twitch-Namen und den Zugangscode aus deiner Bewerbung ein.")
    with st.form("beta_status"):
        name = st.text_input("Twitch-Name", max_chars=25)
        code = st.text_input("Zugangscode", type="password")
        go = st.form_submit_button("🔎 Status prüfen")
    if not go:
        return
    k = _key(name)
    rec = db.reference(f"beta_applications/{k}").get() if NAME_RE.match(k) else None
    if not (isinstance(rec, dict) and code.strip() and hmac.compare_digest(_hash(code), str(rec.get("code_hash", "")))):
        time.sleep(1.0)
        st.error("Name oder Zugangscode stimmt nicht.")
        return
    status = rec.get("status", "pending")
    st.subheader(STATUS_LABEL.get(status, status))
    if status == "pending":
        st.info("Deine Bewerbung wird noch geprüft. Schau später noch einmal vorbei.")
    elif status == "rejected":
        st.error("Leider haben wir dich diesmal nicht für die Beta ausgewählt."
                 + (f"\n\nHinweis: {rec['reject_reason']}" if rec.get("reject_reason") else ""))
    else:
        st.success("🧪 Du bist **Beta-Tester**! Danke, dass du hilfst.")
        url = beta_link(cfg)
        if url:
            st.link_button("⬇️ Beta herunterladen", url, type="primary")
        else:
            st.info("Der Download-Link folgt in Kürze.")
        st.markdown("**So geht's weiter:**\n"
                    "1. Beta herunterladen und die App mit deinem Twitch-Account starten.\n"
                    "2. Nach ca. 1 Minute ist dein Beta-Status in der App aktiv.\n"
                    "3. Bugs, Feedback und Ideen meldest du direkt in der App unter **Feedback & Bugs**.")
        st.caption("Bitte gib die Beta nicht weiter. Danke!")


def render_beta_apply():
    st.markdown("# 🧪 Streamdex Beta")
    st.caption("Hilf mit, Streamdex besser zu machen.")
    try:
        cfg = _settings()
        st.markdown("**Einfach nur ausprobieren?** Die öffentliche Version kann jeder laden:")
        render_public_downloads(cfg)
        st.divider()
        t_apply, t_status = st.tabs(["📝 Bewerben", "🔎 Status & Download"])
        with t_apply:
            _apply_form(cfg)
        with t_status:
            _status_view(cfg)
    except Exception as e:
        st.error(f"Gerade nicht erreichbar, bitte später erneut versuchen. ({e})")


# ----------------------------------------------------------------------------
# Verwaltung (Admin + Supporter)
# ----------------------------------------------------------------------------
def _approve(k, rec, games, me):
    upd = {"status": "approved", "decided_by": me, "decided_ts": SERVER_TS, "reject_reason": None}
    tid = _find_tid(rec.get("name", k))
    if tid:
        set_beta(tid, rec.get("name", k), list(games), "all", "Beta-Bewerbung")
        upd.update({"tid": tid, "applied": True})
    else:
        upd["applied"] = False
    db.reference(f"beta_applications/{k}").update(upd)


def _revoke_beta(rec):
    if rec.get("applied") and rec.get("tid"):
        remove_beta(rec["tid"])


def _sync_pending(apps, games):
    """Freigegebene, die die App noch nie gestartet hatten: Beta-Status setzen, sobald sie auftauchen."""
    n = 0
    for k, rec in apps.items():
        if rec.get("status") == "approved" and not rec.get("applied"):
            tid = _find_tid(rec.get("name", k))
            if tid:
                set_beta(tid, rec.get("name", k), list(games), "all", "Beta-Bewerbung")
                db.reference(f"beta_applications/{k}").update({"tid": tid, "applied": True})
                n += 1
    return n


def admin_beta_applications(games, me, is_admin=False):
    st.subheader("📝 Beta-Bewerbungen")
    st.caption("Öffentliche Seite: `/?beta=1`. Mit **Freigeben** bekommt die Person Zugang zum Download und den Beta-Status "
               "(alle Games). Hat sie die App noch nie gestartet, wird der Status automatisch gesetzt, sobald sie erscheint.")
    cfg = _settings()
    if is_admin:
        with st.expander("⚙️ Einstellungen"):
            open_ = st.toggle("Bewerbungen offen", value=cfg.get("open", True), key="beta_open")
            url = st.text_input("Download-Link (https://…) für freigeschaltete Tester",
                                value=str(cfg.get("download_url") or ""), key="beta_url")
            pub = st.text_input("Öffentlicher Download (optional, sonst automatisch neueste GitHub-Release)",
                                value=str(cfg.get("public_url") or ""), key="beta_pub_url")
            lurk_url = st.text_input("StreamDex Lurk: direkter Download-Link (https://…)",
                                     value=str(cfg.get("lurk_url") or ""), key="beta_lurk_url")
            lurk_repo = st.text_input("… oder GitHub-Repo der Lurk-App (owner/repo, nutzt die neueste Release)",
                                      value=str(cfg.get("lurk_repo") or ""), key="beta_lurk_repo")
            notify = st.checkbox("Bei neuem Beta-Link alle Beta-Tester benachrichtigen (Support-Chat + Dashboard)",
                                 value=True, key="beta_notify")
            note = st.text_input("Hinweis für die Tester (optional, z.B. Version oder was neu ist)",
                                 max_chars=300, key="beta_note")
            if st.button("💾 Speichern", key="beta_cfg_save"):
                links = [url, pub, lurk_url]
                if any(u.strip() and not u.strip().startswith("https://") for u in links):
                    st.error("Links müssen mit https:// beginnen.")
                elif lurk_repo.strip() and not REPO_RE.match(lurk_repo.strip()):
                    st.error("Repo bitte als owner/repo angeben.")
                else:
                    changed = bool(url.strip()) and url.strip() != str(cfg.get("download_url") or "").strip()
                    upd = {"open": bool(open_), "download_url": url.strip(), "public_url": pub.strip(),
                           "lurk_url": lurk_url.strip(), "lurk_repo": lurk_repo.strip()}
                    if changed:
                        upd.update({"beta_rev": int(cfg.get("beta_rev") or 0) + 1, "beta_note": note.strip(),
                                    "beta_link_ts": SERVER_TS})
                    db.reference("beta/settings").update(upd)
                    st.success("Gespeichert.")
                    if changed and notify:
                        st.success(f"{notify_beta_testers(url.strip(), note, me)} Beta-Tester benachrichtigt.")
            if beta_link(cfg) and st.button("📣 Beta-Tester jetzt erneut benachrichtigen", key="beta_renotify"):
                st.success(f"{notify_beta_testers(beta_link(cfg), str(cfg.get('beta_note') or ''), me)} Beta-Tester benachrichtigt.")

    apps = {k: v for k, v in (db.reference("beta_applications").get() or {}).items() if isinstance(v, dict)}
    synced = _sync_pending(apps, games)
    if synced:
        st.toast(f"{synced} Beta-Status nachträglich gesetzt.")
        apps = {k: v for k, v in (db.reference("beta_applications").get() or {}).items() if isinstance(v, dict)}

    codes = (db.reference("beta_codes").get() or {}) if is_admin else {}
    cnt = {s: sum(1 for v in apps.values() if v.get("status", "pending") == s) for s in STATUS_LABEL}
    c = st.columns(3)
    for col, s in zip(c, STATUS_LABEL):
        col.metric(STATUS_LABEL[s], cnt[s])
    pick = st.radio("Anzeigen", list(FILTERS), horizontal=True, key="beta_filter")
    want = FILTERS[pick]
    shown = sorted(((k, v) for k, v in apps.items() if want is None or v.get("status", "pending") == want),
                   key=lambda kv: -int(kv[1].get("ts") or 0) if isinstance(kv[1].get("ts"), (int, float)) else 0)
    if not shown:
        st.info("Keine Bewerbungen in dieser Ansicht.")
    for k, v in shown:
        status = v.get("status", "pending")
        with st.expander(f"{STATUS_LABEL.get(status, status)} · {v.get('name', k)} · {_fmt_ts(v.get('ts'))}"):
            st.markdown(f"**Twitch:** `{v.get('name', k)}`")
            st.markdown("**Warum Beta-Tester?**")
            st.write(v.get("reason", ""))
            st.caption("Geheimhaltung, Bug-Hinweis und Melde-Pflicht bestätigt ✅" if v.get("agreed") else "Zustimmung fehlt ⚠️")
            if is_admin:
                code = codes.get(k)
                c_a, c_b = st.columns([3, 2])
                with c_a:
                    if code:
                        st.markdown("**Zugangscode:**")
                        st.code(str(code), language=None)
                    else:
                        st.caption("Zugangscode nicht gespeichert (ältere Bewerbung). Mit „Neuen Code erzeugen“ bekommt die Person einen neuen.")
                if c_b.button("🔑 Neuen Code erzeugen", key=f"ba_newcode_{k}"):
                    new = secrets.token_urlsafe(9)
                    db.reference(f"beta_applications/{k}").update({"code_hash": _hash(new)})
                    db.reference(f"beta_codes/{k}").set(new)
                    st.rerun()
            if status == "approved":
                st.caption(f"Freigegeben von {v.get('decided_by', '?')} am {_fmt_ts(v.get('decided_ts'))} · "
                           + ("Beta-Status in der App aktiv." if v.get("applied")
                              else "Beta-Status wartet auf den ersten App-Start."))
            elif status == "rejected" and v.get("reject_reason"):
                st.caption(f"Grund: {v['reject_reason']}")
            b1, b2, b3 = st.columns(3)
            if status != "approved" and b1.button("✅ Freigeben", key=f"ba_ok_{k}", type="primary"):
                _approve(k, v, games, me)
                st.rerun()
            if status == "approved" and b1.button("⛔ Beta widerrufen", key=f"ba_rev_{k}"):
                _revoke_beta(v)
                db.reference(f"beta_applications/{k}").update(
                    {"status": "rejected", "applied": False, "decided_by": me, "decided_ts": SERVER_TS})
                st.rerun()
            if status != "rejected":
                why = b2.text_input("Ablehnungsgrund (optional, sieht der Bewerber)", key=f"ba_why_{k}", max_chars=200)
                if b2.button("❌ Ablehnen", key=f"ba_no_{k}"):
                    db.reference(f"beta_applications/{k}").update(
                        {"status": "rejected", "reject_reason": why.strip() or None,
                         "decided_by": me, "decided_ts": SERVER_TS})
                    st.rerun()
            if is_admin:
                ok = b3.checkbox("Ja, löschen", key=f"ba_delok_{k}")
                if b3.button("🗑️ Löschen", disabled=not ok, key=f"ba_del_{k}"):
                    _revoke_beta(v)
                    db.reference(f"beta_applications/{k}").delete()
                    db.reference(f"beta_codes/{k}").delete()
                    st.rerun()
