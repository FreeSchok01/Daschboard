"""StreamDex Device Manager: Übersicht und sichere Geräteaktionen."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db
from admin_audit import write_admin_audit

TZ = ZoneInfo("Europe/Berlin")
STALE_SECONDS = 150


def _read(path):
    value = db.reference(path).get()
    return value if isinstance(value, dict) else {}


def _ns(namespace):
    return namespace or "streamdex"


def _device_rows():
    rows = []
    now_ms = int(time.time() * 1000)
    for namespace, label in (("", "StreamDex"), ("lurk", "Lurk")):
        prefix = f"{namespace}/" if namespace else ""
        for key, payload in _read(f"{prefix}presence").items():
            if not isinstance(payload, dict):
                continue
            key = str(key)
            tid = str(payload.get("twitch_id") or (key[4:] if key.startswith("mod_") else key))
            if not tid.isdigit():
                continue
            last_seen = int(payload.get("last_seen") or 0)
            age = max(0, (now_ms - last_seen) / 1000) if last_seen else None
            raw_status = str(payload.get("status") or "").lower()
            online = raw_status == "online" and age is not None and age <= STALE_SECONDS
            product = str(payload.get("product") or payload.get("app_name") or ("StreamDex Mod Control" if key.startswith("mod_") else label))
            label_record = _read(f"admin_device_labels/{_ns(namespace)}/{key}")
            rows.append({
                "path": f"{prefix}presence/{key}", "namespace": namespace, "namespace_label": label,
                "presence_key": key, "tid": tid, "name": str(payload.get("twitch_username") or tid),
                "device_label": str(label_record.get("name") or ""), "product": product,
                "version": str(payload.get("app_version") or "?"), "online": online,
                "status": "Online" if online else ("Blockiert" if raw_status == "blocked" else "Offline"),
                "last_seen": last_seen, "age": age, "uid_present": bool(payload.get("uid")), "payload": payload,
            })
    return sorted(rows, key=lambda row: (not row["online"], row["name"].casefold(), row["product"]))


def _fmt_age(seconds):
    if seconds is None:
        return "Kein Kontaktzeitpunkt gespeichert"
    if seconds < 60:
        return f"vor {int(seconds)} Sekunden"
    if seconds < 3600:
        return f"vor {int(seconds // 60)} Minuten"
    if seconds < 86400:
        return f"vor {int(seconds // 3600)} Stunden"
    return f"vor {int(seconds // 86400)} Tagen"


def render_device_manager():
    st.subheader("🖥️ Geräte- und Verbindungsverwaltung")
    st.caption("Erkannte StreamDex-Presence-Einträge. Online bedeutet: letzter Heartbeat höchstens 150 Sekunden alt.")
    try:
        devices = _device_rows()
    except Exception:
        st.error("Gerätedaten konnten nicht aus Firebase geladen werden. Bitte Verbindung und Berechtigungen prüfen.")
        return

    online = sum(1 for d in devices if d["online"])
    bound = sum(1 for d in devices if d["uid_present"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Erkannte Geräte", len(devices))
    c2.metric("Online", online)
    c3.metric("Offline / blockiert", len(devices) - online)
    c4.metric("Mit Gerätebindung", bound)

    f1, f2, f3 = st.columns([2, 1, 1])
    query = f1.text_input("Gerät oder Nutzer suchen", placeholder="Twitch-Name, ID oder Produkt", key="device_manager_search").strip().casefold()
    status_filter = f2.selectbox("Verbindungsstatus", ["Alle", "Online", "Offline", "Blockiert"], key="device_manager_status")
    product_filter = f3.selectbox("Produkt", ["Alle"] + sorted({d["product"] for d in devices}), key="device_manager_product")
    filtered = [d for d in devices if (not query or query in d["name"].casefold() or query in d["tid"] or query in d["product"].casefold() or query in d["device_label"].casefold()) and (status_filter == "Alle" or d["status"] == status_filter) and (product_filter == "Alle" or d["product"] == product_filter)]

    if filtered:
        table = []
        for d in filtered:
            seen = datetime.fromtimestamp(d["last_seen"] / 1000, TZ).strftime("%d.%m.%Y %H:%M:%S") if d["last_seen"] else "Unbekannt"
            table.append({"Status": "🟢 Online" if d["online"] else ("⛔ Blockiert" if d["status"] == "Blockiert" else "⚪ Offline"), "Gerätename": d["device_label"] or "—", "Nutzer": d["name"], "Produkt": d["product"], "Version": d["version"], "Letzter Kontakt": seen, "Gerätebindung": "Vorhanden" if d["uid_present"] else "Nicht gesetzt"})
        st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
    else:
        st.info("Keine Geräte passend zu den Filtern gefunden.")
        return

    st.divider()
    st.subheader("🔎 Gerätedetails und Aktionen")
    labels = {f"{d['device_label'] + ' · ' if d['device_label'] else ''}{d['name']} · {d['product']} · {d['namespace_label']} · {d['presence_key']}": d for d in filtered}
    selected_label = st.selectbox("Gerät auswählen", list(labels), key="device_manager_selected")
    selected = labels[selected_label]
    payload = selected["payload"]
    a, b, c = st.columns(3)
    a.metric("Status", selected["status"])
    b.metric("Version", selected["version"])
    c.metric("Letzter Kontakt", _fmt_age(selected["age"]))
    st.write(f"**Twitch-ID:** `{selected['tid']}`")
    st.write(f"**Firebase-Presence:** `{selected['path']}`")
    st.write(f"**Installations-ID:** `{payload.get('install_id') or payload.get('device_id') or 'Vom Client nicht separat übermittelt'}`")
    st.write(f"**Gerätebindung:** {'Vorhanden' if selected['uid_present'] else 'Nicht gesetzt'}")
    with st.expander("Technische Presence-Daten"):
        st.json({k: v for k, v in payload.items() if k not in ("uid", "hw_machine", "hw_board")})

    left, right = st.columns(2)
    with left:
        confirmed = st.checkbox("Gerätebindung dieses Eintrags wirklich erneuern", key=f"device_reset_confirm_{selected['namespace']}_{selected['presence_key']}")
        if st.button("🔧 Gerätebindung zurücksetzen", disabled=not confirmed, type="primary", key="device_reset_one"):
            try:
                db.reference(f"{selected['path']}/uid").delete()
            except Exception:
                st.error("Reset fehlgeschlagen: Die Gerätebindung konnte in Firebase nicht gelöscht werden.")
            else:
                try:
                    write_admin_audit("Gerätebindung zurückgesetzt", selected["product"], f"{selected['name']} ({selected['tid']}) · {selected['path']}")
                except Exception:
                    pass
                st.success("Gerätebindung zurückgesetzt. Das Desktop-Tool muss sich erneut verbinden.")
                st.rerun()
    with right:
        label_value = st.text_input("Interner Gerätename (nur Admin)", value=selected["device_label"], placeholder="z. B. Gaming-PC", key=f"device_label_{selected['namespace']}_{selected['presence_key']}")
        if st.button("Gerätenamen speichern", key="device_label_save"):
            try:
                label_path = f"admin_device_labels/{_ns(selected['namespace'])}/{selected['presence_key']}"
                if label_value.strip():
                    db.reference(label_path).set({"name": label_value.strip()[:80], "updated_at": {".sv": "timestamp"}})
                else:
                    db.reference(label_path).delete()
                write_admin_audit("Admin-Gerätename geändert", selected["product"], f"{selected['tid']} · {label_value.strip()[:80]}")
                st.success("Interner Gerätename gespeichert.")
                st.rerun()
            except Exception:
                st.error("Der Gerätename konnte nicht gespeichert werden.")

    with st.expander("⚠️ Massenaktionen"):
        st.warning("Der Massen-Reset löscht ausschließlich uid bei allen aktuell erkannten Presence-Einträgen. Nutzer, Statistiken, Chats, Käufe und Hardware-Sperren bleiben erhalten.")
        st.metric("Betroffene Presence-Einträge", len(devices))
        mass_confirm = st.checkbox(f"Ich bestätige den Reset für alle {len(devices)} erkannten Geräte.", key="device_manager_mass_confirm", disabled=not devices)
        if st.button("⚠️ Gerätebindungen für ALLE zurücksetzen", type="primary", disabled=not devices or not mass_confirm, key="device_manager_mass_reset"):
            success = failed = 0
            for device in devices:
                try:
                    db.reference(f"{device['path']}/uid").delete()
                    success += 1
                except Exception:
                    failed += 1
            try:
                write_admin_audit("Globaler Geräte-Reset über Device Manager", "Alle StreamDex-Produkte", f"{success} Presence-Einträge zurückgesetzt; {failed} fehlgeschlagen.")
            except Exception:
                pass
            if failed:
                st.warning(f"{success} zurückgesetzt, {failed} fehlgeschlagen.")
            else:
                st.success(f"Alle {success} erkannten Gerätebindungen wurden zurückgesetzt.")
            st.info("Die Desktop-Tools müssen anschließend neu gestartet werden, um ihre Verbindung neu aufzubauen.")
