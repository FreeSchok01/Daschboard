"""Zentrale Download-Verwaltung für StreamDex-Produkte."""
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

from admin_audit import write_admin_audit
from downloads import GITHUB_REPO, LURK_REPO, latest_release, notify_beta_testers, settings as download_settings
from public_products import load_public_products

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _dict(value):
    return value if isinstance(value, dict) else {}


def _https(value):
    value = str(value or "").strip()
    parsed = urlparse(value)
    if not value:
        return ""
    if parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password:
        return value
    return None


def _save_audit(action, target, detail):
    try:
        write_admin_audit(action, target, detail)
    except Exception:
        pass


def _format_bytes(value):
    try:
        size = max(0, int(value or 0))
    except (TypeError, ValueError):
        return "—"
    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f} GB"
    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _release_stats(repo, product):
    release = latest_release(repo)
    if not release:
        return {
            "Produkt": product, "Repository": repo, "Version": "Nicht erreichbar",
            "Assets": 0, "Downloads laut GitHub": "—", "Veröffentlicht": "—",
            "Download-Link": "Nicht verfügbar",
        }, []
    rows = []
    for asset in release.get("assets") or []:
        rows.append({
            "Produkt": product,
            "Version": release.get("tag") or "—",
            "Datei": str(asset.get("name") or "Unbenannt"),
            "Downloads": int(asset.get("download_count") or 0),
            "Größe": _format_bytes(asset.get("size")),
            "Download": str(asset.get("url") or ""),
        })
    summary = {
        "Produkt": product,
        "Repository": repo,
        "Version": release.get("tag") or "—",
        "Assets": len(rows),
        "Downloads laut GitHub": int(release.get("download_count") or 0),
        "Veröffentlicht": str(release.get("published_at") or "—")[:10],
        "Download-Link": "Release vorhanden" if release.get("file") else "Kein EXE-/ZIP-Asset",
    }
    return summary, rows


def render_download_manager():
    st.markdown("## 📥 Zentrale Download-Verwaltung")
    st.caption(
        "Verwalte öffentliche Downloads, Beta-Builds, Produkt-Downloads und Shop-Dateien zentral. "
        "Bestehende Twitch-Freigaben und Bestellprüfungen bleiben bestehen."
    )

    cfg = _dict(download_settings())
    try:
        products = load_public_products()
    except Exception:
        products = []
        st.warning("Der öffentliche Produktkatalog konnte gerade nicht geladen werden.")
    try:
        shop_items = _dict(db.reference("shop/items").get())
        shop_read_ok = True
    except Exception:
        shop_items = {}
        shop_read_ok = False
        st.warning("Die Shop-Artikel konnten gerade nicht aus Firebase geladen werden. Shop-Änderungen sind vorübergehend deaktiviert.")

    # Live-Übersicht: echte GitHub-Release-Asset-Zähler, keine erfundenen Klickzahlen.
    st.markdown("### 📊 Release- und Download-Übersicht")
    repositories = [
        (GITHUB_REPO, "StreamDex OS"),
        (str(cfg.get("lurk_repo") or LURK_REPO), "StreamDex Lurk"),
    ]
    unique_repos = {}
    for repo, label in repositories:
        if REPO_RE.fullmatch(repo):
            unique_repos[repo] = label
    release_results = [_release_stats(repo, label) for repo, label in unique_repos.items()]
    release_rows = [item[0] for item in release_results]
    asset_rows = [asset for item in release_results for asset in item[1]]
    if release_rows:
        total_downloads = sum(
            int(row["Downloads laut GitHub"]) for row in release_rows
            if isinstance(row["Downloads laut GitHub"], int)
        )
        total_assets = sum(int(row["Assets"]) for row in release_rows)
        m1, m2, m3 = st.columns(3)
        m1.metric("GitHub-Downloads (aktuelle Releases)", total_downloads)
        m2.metric("Release-Dateien", total_assets)
        m3.metric("Verwaltete Shop-Artikel", len(shop_items) if shop_read_ok else "—")
        st.dataframe(pd.DataFrame(release_rows), hide_index=True, use_container_width=True)
        if asset_rows:
            with st.expander("📄 Einzelne Dateien und Download-Zahlen", expanded=True):
                st.dataframe(pd.DataFrame(asset_rows), hide_index=True, use_container_width=True,
                             column_config={"Download": st.column_config.LinkColumn("Download-Link", display_text="Öffnen")})
        st.caption(
            "GitHub-Zähler stammen aus den Asset-Downloads der jeweils neuesten Releases. "
            "Sie zeigen keine eindeutigen Nutzer und keine Installationen. Eigene externe Links "
            "und Firebase-Link-Klicks werden derzeit nicht gezählt."
        )
    st.divider()
    st.markdown("### 📈 StreamDex-Download-Tracking")
    st.caption("Hier siehst du Aufrufe der öffentlichen Download-Buttons. Es werden keine IP-Adressen, Twitch-IDs oder Gerätekennungen gespeichert.")
    try:
        tracked = db.reference("download_analytics/events").order_by_child("ts").limit_to_last(5000).get() or {}
        events = [event for event in tracked.values() if isinstance(event, dict)]
    except Exception:
        events = []
        st.warning("Die Download-Ereignisse konnten gerade nicht geladen werden.")
    # Firebase-Server-Timestamps sind Millisekunden seit Unix-Epoch.
    # Die Tagesgrenzen und Diagramm-Tage werden bewusst in deutscher Ortszeit berechnet.
    local_tz = ZoneInfo("Europe/Berlin")
    now_local = datetime.now(local_tz)
    today_start_ms = int(now_local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    last_30_start_ms = int((now_local - timedelta(days=30)).timestamp() * 1000)

    valid_events = []
    for event in events:
        try:
            stamp = int(event.get("ts"))
            if stamp > 0:
                valid_events.append((event, stamp))
        except (TypeError, ValueError, OverflowError):
            # Beschädigte oder unvollständige Firebase-Einträge überspringen.
            continue

    today_events = [(event, stamp) for event, stamp in valid_events if stamp >= today_start_ms]
    month_events = [(event, stamp) for event, stamp in valid_events if stamp >= last_30_start_ms]
    a1, a2, a3 = st.columns(3)
    a1.metric("Download-Klicks heute", len(today_events))
    a2.metric("Download-Klicks (30 Tage)", len(month_events))
    a3.metric("Erfasste Ereignisse", len(valid_events))

    export_rows = []
    for event, stamp in sorted(valid_events, key=lambda item: item[1], reverse=True):
        export_rows.append({
            "Zeit (Europe/Berlin)": datetime.fromtimestamp(stamp / 1000, tz=local_tz).strftime("%Y-%m-%d %H:%M:%S"),
            "Produkt": str(event.get("product_name") or event.get("product_key") or "Unbekannt"),
            "Produkt-Key": str(event.get("product_key") or ""),
            "Version": str(event.get("version") or ""),
            "Quelle": str(event.get("source") or ""),
        })
    if export_rows:
        export_csv = pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📄 Tracking-Daten als CSV exportieren",
            data=export_csv,
            file_name="streamdex-download-statistik.csv",
            mime="text/csv",
            key="download_tracking_export",
        )
    st.caption("Der Export enthält maximal die letzten 5.000 gespeicherten Ereignisse und keine IP-, Twitch- oder Gerätekennungen.")

    if month_events:
        counts = {}
        for event, _stamp in month_events:
            label = str(event.get("product_name") or event.get("product_key") or "Unbekannt")
            counts[label] = counts.get(label, 0) + 1
        st.markdown("**Downloads nach Produkt · letzte 30 Tage**")
        st.dataframe(
            pd.DataFrame([{"Produkt": key, "Klicks": value} for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)]),
            hide_index=True,
            use_container_width=True,
        )
        daily = {}
        for _event, stamp in month_events:
            day = datetime.fromtimestamp(stamp / 1000, tz=local_tz).date()
            daily[day] = daily.get(day, 0) + 1
        daily_rows = [
            {"Tag": day.strftime("%d.%m."), "Klicks": daily[day]}
            for day in sorted(daily)
        ]
        st.bar_chart(pd.DataFrame(daily_rows).set_index("Tag"))
    else:
        st.info("Noch keine öffentlichen Download-Klicks erfasst. Neue Klicks erscheinen hier, sobald die aktualisierte Seite live ist.")
    st.caption("Hinweis: Das Tracking zählt das Öffnen des Download-Weiterleitungslinks, nicht den erfolgreichen Abschluss oder die Installation der Datei.")

    if st.button("🔄 Download- und Release-Daten aktualisieren", key="download_manager_refresh"):
        latest_release.clear()
        st.rerun()

    st.divider()
    st.markdown("### ⚡ StreamDex OS & Beta")
    st.caption("Diese Einstellungen verwenden weiterhin die bestehenden Firebase-Pfade beta/settings.")
    with st.form("download_manager_core_form"):
        public_url = st.text_input(
            "Öffentlicher StreamDex-Download (HTTPS, leer = neueste GitHub-Release)",
            value=str(cfg.get("public_url") or ""),
            help="Wenn leer, wird automatisch das neueste Release aus FreeSchok01/Givewaytool verwendet.",
        )
        beta_url = st.text_input(
            "Beta-Download-Link (HTTPS)",
            value=str(cfg.get("download_url") or ""),
        )
        beta_note = st.text_area(
            "Hinweis zum Beta-Build",
            value=str(cfg.get("beta_note") or ""),
            max_chars=300,
        )
        beta_open = st.checkbox(
            "Beta-Bewerbungen geöffnet",
            value=cfg.get("open", True) is not False,
        )
        notify_testers = st.checkbox(
            "Freigeschaltete Beta-Tester nach dem Speichern über den Beta-Link informieren",
            value=False,
        )
        save_core = st.form_submit_button("💾 StreamDex- und Beta-Einstellungen speichern", type="primary")
    if save_core:
        safe_public = _https(public_url)
        safe_beta = _https(beta_url)
        if safe_public is None:
            st.error("Der öffentliche Download-Link muss leer sein oder eine gültige HTTPS-Adresse enthalten.")
        elif safe_beta is None:
            st.error("Der Beta-Link muss leer sein oder eine gültige HTTPS-Adresse enthalten.")
        elif notify_testers and not safe_beta:
            st.error("Zum Benachrichtigen der Beta-Tester muss ein gültiger Beta-Link hinterlegt sein.")
        else:
            patch = {
                "public_url": safe_public,
                "download_url": safe_beta,
                "beta_note": beta_note.strip()[:300],
                "open": bool(beta_open),
            }
            if notify_testers:
                patch["beta_rev"] = int(cfg.get("beta_rev") or 0) + 1
            db.reference("beta/settings").update(patch)
            _save_audit(
                "Download-Einstellungen geändert",
                "StreamDex OS / Beta",
                f"Öffentlicher Link {'gesetzt' if safe_public else 'GitHub-Fallback'}; Beta-Link {'gesetzt' if safe_beta else 'leer'}; Bewerbungen {'offen' if beta_open else 'geschlossen'}.",
            )
            if notify_testers:
                try:
                    count = notify_beta_testers(safe_beta, beta_note)
                    st.success(f"Einstellungen gespeichert. {count} Beta-Tester wurden im StreamDex-Support benachrichtigt.")
                except Exception:
                    st.warning("Einstellungen gespeichert, aber die Benachrichtigung der Beta-Tester ist fehlgeschlagen.")
            else:
                st.success("StreamDex- und Beta-Einstellungen gespeichert.")
            st.rerun()

    st.divider()
    st.markdown("### 👁️ StreamDex Lurk")
    with st.form("download_manager_lurk_form"):
        lurk_url = st.text_input(
            "Direkter Lurk-Download-Link (HTTPS, optional)",
            value=str(cfg.get("lurk_url") or ""),
        )
        lurk_repository = st.text_input(
            "GitHub-Repository (owner/name)",
            value=str(cfg.get("lurk_repo") or LURK_REPO),
            help="Wird genutzt, wenn kein direkter Download-Link eingetragen ist.",
        )
        save_lurk = st.form_submit_button("💾 Lurk-Download speichern")
    if save_lurk:
        safe_lurk = _https(lurk_url)
        repo = lurk_repository.strip()
        if safe_lurk is None:
            st.error("Der Lurk-Download-Link muss leer sein oder eine gültige HTTPS-Adresse enthalten.")
        elif not REPO_RE.fullmatch(repo):
            st.error("Bitte ein gültiges GitHub-Repository im Format owner/name eintragen.")
        else:
            db.reference("beta/settings").update({"lurk_url": safe_lurk, "lurk_repo": repo})
            _save_audit("Download-Einstellungen geändert", "StreamDex Lurk", f"Repository: {repo}; direkter Link {'gesetzt' if safe_lurk else 'nicht gesetzt'}.")
            st.success("Lurk-Download-Einstellungen gespeichert.")
            st.rerun()

    st.divider()
    st.markdown("### 🛡️ Weitere StreamDex-Produkte")
    st.caption("Hier steuerst du den Download-Button auf der öffentlichen Produktseite und im eingeloggten Dashboard.")
    editable_products = [p for p in products if p.get("key") != "streamdex"]
    if editable_products:
        product_map = {p["key"]: p for p in editable_products}
        chosen_key = st.selectbox(
            "Produkt auswählen",
            list(product_map),
            format_func=lambda key: product_map[key].get("name", key),
            key="download_manager_public_product",
        )
        chosen = product_map[chosen_key]
        with st.form(f"download_manager_product_{chosen_key}"):
            button_label = st.text_input("Button-Beschriftung", value=str(chosen.get("button_label") or "Download starten"))
            product_url = st.text_input("Produkt-Download-Link (HTTPS)", value=str(chosen.get("button_url") or ""))
            product_status = st.selectbox(
                "Produktstatus",
                ["available", "coming_soon"],
                index=1 if chosen.get("status_key") == "coming_soon" else 0,
                format_func=lambda value: "Coming Soon" if value == "coming_soon" else "Verfügbar",
            )
            save_product = st.form_submit_button("💾 Produkt-Download speichern")
        if save_product:
            safe_product_url = _https(product_url)
            if safe_product_url is None:
                st.error("Der Produkt-Download muss leer sein oder eine gültige HTTPS-Adresse enthalten.")
            elif product_status == "available" and not safe_product_url:
                st.error("Für ein als verfügbar markiertes Produkt muss ein Download-Link hinterlegt sein.")
            else:
                db.reference(f"public_product_catalog/{chosen_key}").update({
                    "button_label": button_label.strip()[:60] or "Download starten",
                    "button_url": safe_product_url,
                    "status_key": product_status,
                    "status": "Coming Soon" if product_status == "coming_soon" else "Verfügbar",
                })
                _save_audit("Produkt-Download geändert", chosen.get("name", chosen_key), f"Status: {product_status}; Link {'gesetzt' if safe_product_url else 'leer'}.")
                st.success("Produkt-Download gespeichert.")
                st.rerun()

    st.divider()
    st.markdown("### 🎮 Shop-Downloads")
    st.caption(
        "Diese Links bleiben an die bestehende Bestellprüfung gebunden. "
        "Käufer sehen sie weiterhin nur bei einer passenden bezahlten Bestellung."
    )
    if not shop_items:
        st.info("Im Shop ist derzeit kein Artikelkatalog hinterlegt.")
    else:
        rows = []
        for item_id, item in shop_items.items():
            if not isinstance(item, dict):
                continue
            url = str(item.get("download_url") or "")
            rows.append({
                "Artikel": str(item.get("name") or item_id),
                "Artikel-ID": str(item_id),
                "Typ": "Paket" if item.get("kind") == "pack" else "Einzel-Game",
                "Download": "Konfiguriert" if url else "Fehlt",
                "Aktiv": "Ja" if item.get("active", True) else "Nein",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        choices = [key for key, item in shop_items.items() if isinstance(item, dict) and item.get("kind", "game") == "game"] if shop_read_ok else []
        if choices:
            item_id = st.selectbox(
                "Einzel-Game auswählen",
                choices,
                format_func=lambda key: str(shop_items[key].get("name") or key),
                key="download_manager_shop_item",
            )
            current = _dict(shop_items.get(item_id))
            with st.form(f"download_manager_shop_{item_id}"):
                shop_url = st.text_input("HTTPS-Download-Link", value=str(current.get("download_url") or ""))
                save_shop = st.form_submit_button("💾 Shop-Download speichern")
            if save_shop:
                safe_shop = _https(shop_url)
                if safe_shop is None:
                    st.error("Der Shop-Download muss leer sein oder eine gültige HTTPS-Adresse enthalten.")
                else:
                    db.reference(f"shop/items/{item_id}").update({"download_url": safe_shop})
                    _save_audit("Shop-Download geändert", str(current.get("name") or item_id), f"Artikel-ID: {item_id}; Link {'gesetzt' if safe_shop else 'entfernt'}.")
                    st.success("Shop-Download gespeichert. Die bestehende Bestellprüfung bleibt aktiv.")
                    st.rerun()
    st.info(
        "Hinweis: Direkte Download-Links werden als HTTPS-URLs gespeichert. "
        "Für geschützte Dateien solltest du keine privaten Tokens oder Zugangsdaten in die URL einbauen."
    )
