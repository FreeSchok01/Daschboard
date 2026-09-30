"""Öffentlicher Streamdex-Shop (PayPal) + Admin-Panel für Katalog und Bestellungen.
Kauf -> PayPal-Order (serverseitig) -> Rückkehr -> Capture + Prüfung -> game_flags/streamers/{tid}/{game}=True.
Die App übernimmt die Freischaltung beim nächsten Heartbeat (~60 s), ohne App-Änderung."""
import time
from decimal import Decimal

import pandas as pd
import requests
import streamlit as st
from firebase_admin import db


class _Skip(Exception):
    pass


def _pp():
    c = st.secrets["paypal"]
    base = "https://api-m.sandbox.paypal.com" if c.get("mode", "sandbox") == "sandbox" else "https://api-m.paypal.com"
    r = requests.post(f"{base}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                      auth=(c["client_id"], c["client_secret"]), timeout=15)
    r.raise_for_status()
    return base, {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


def _price(x):
    return str(Decimal(str(x)).quantize(Decimal("0.01")))


@st.cache_data(ttl=60, show_spinner=False)
def _presence():
    return db.reference("presence").get() or {}


def find_streamer(name):
    n = name.strip().lstrip("@").lower()
    for tid, p in _presence().items():
        if isinstance(p, dict) and str(p.get("twitch_username", "")).lower() == n:
            return tid, p
    return None, None


def load_items(active_only=True):
    items = db.reference("shop/items").get() or {}
    return {k: v for k, v in items.items() if isinstance(v, dict) and (v.get("active", True) or not active_only)}


def owned_games(tid):
    own = db.reference(f"game_flags/streamers/{tid}").get() or {}
    glob = db.reference("game_flags/global").get() or {}
    return {g for g in set(own) | set(glob) if own.get(g) is True or (not isinstance(own.get(g), bool) and glob.get(g) is True)}


def create_order(tid, name, item_id, item):
    base, h = _pp()
    url = st.secrets["shop"]["base_url"].rstrip("/")
    price = _price(item["price"])
    body = {"intent": "CAPTURE",
            "purchase_units": [{"custom_id": f"{tid}:{item_id}", "description": str(item["name"])[:120],
                                "amount": {"currency_code": "EUR", "value": price}}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": f"{url}/?shop=return", "cancel_url": f"{url}/?shop=cancel",
                "user_action": "PAY_NOW", "brand_name": "Streamdex", "shipping_preference": "NO_SHIPPING"}}}}
    r = requests.post(f"{base}/v2/checkout/orders", json=body, headers=h, timeout=15)
    r.raise_for_status()
    j = r.json()
    link = next(l["href"] for l in j["links"] if l["rel"] in ("payer-action", "approve"))
    db.reference(f"shop/orders/{j['id']}").set({"tid": tid, "name": name, "item": item_id, "item_name": item["name"],
                                               "games": item.get("games", []), "price": price, "status": "created",
                                               "ts": {".sv": "timestamp"}})
    return link


def fulfill(oid):
    """Gibt (ok, Text) zurück. Idempotent: eine Bestellung wird höchstens einmal verbucht."""
    ref = db.reference(f"shop/orders/{oid}")
    order = ref.get()
    if not isinstance(order, dict):
        return False, "Unbekannte Bestellung."
    if order.get("status") == "paid":
        return True, f"Bestellung bereits verbucht: **{order['item_name']}** für {order['name']}."

    def claim(cur):
        if not cur or cur.get("status") not in ("created", "error"):
            raise _Skip()
        return dict(cur, status="processing")
    try:
        ref.transaction(claim)
    except _Skip:
        return False, "Die Bestellung wird gerade verarbeitet. Bitte kurz warten und neu laden."
    try:
        base, h = _pp()
        r = requests.post(f"{base}/v2/checkout/orders/{oid}/capture", headers={**h, "PayPal-Request-Id": oid}, timeout=20)
        if r.status_code == 422:      # z.B. bereits erfasst -> Order abfragen
            r = requests.get(f"{base}/v2/checkout/orders/{oid}", headers=h, timeout=15)
        r.raise_for_status()
        pu = r.json()["purchase_units"][0]
        cap = pu["payments"]["captures"][0]
        ok = (cap["status"] == "COMPLETED" and cap["amount"]["currency_code"] == "EUR"
              and Decimal(cap["amount"]["value"]) == Decimal(order["price"])
              and pu.get("custom_id") == f"{order['tid']}:{order['item']}")
        if not ok:
            raise ValueError(f"Zahlung nicht verifizierbar (Status {cap['status']}).")
    except Exception as e:
        ref.update({"status": "error", "error": str(e)[:300]})
        return False, f"Zahlung konnte nicht bestätigt werden: {e}"
    for g in order.get("games", []):
        db.reference(f"game_flags/streamers/{order['tid']}/{g}").set(True)
    ref.update({"status": "paid", "paid_ts": {".sv": "timestamp"}, "capture_id": cap["id"]})
    return True, f"✅ Zahlung erhalten! **{order['item_name']}** ist für **{order['name']}** freigeschaltet (in der App nach ca. 1 Minute aktiv)."


def render_shop():
    st.title("🛒 Streamdex Shop")
    st.caption("Schalte zusätzliche Funktionen für deinen Twitch-Kanal frei. Zahlung sicher per PayPal.")
    q = st.query_params
    if q.get("shop") == "return" and q.get("token"):
        ok, msg = fulfill(str(q["token"]))
        (st.success if ok else st.error)(msg)
        if st.button("Zurück zum Shop"):
            st.query_params.clear()
            st.rerun()
        return
    if q.get("shop") == "cancel":
        st.warning("Zahlung abgebrochen. Es wurde nichts abgebucht.")

    name = st.text_input("Dein Twitch-Name", placeholder="z.B. meinkanal")
    if not name.strip():
        st.info("Gib deinen Twitch-Namen ein. Du musst die Streamdex-App mindestens einmal gestartet haben.")
        return
    tid, p = find_streamer(name)
    if not tid:
        st.error("Kein Konto mit diesem Namen gefunden. Starte die Streamdex-App einmal mit deinem Twitch-Account.")
        return
    st.success(f"Konto gefunden: **{p.get('twitch_username')}** · App {p.get('app_version', '?')}")
    have = owned_games(tid)
    items = load_items()
    if not items:
        st.info("Aktuell gibt es keine Angebote.")
        return
    agree = st.checkbox("Ich stimme zu, dass die Freischaltung sofort erfolgt, und weiß, dass damit mein Widerrufsrecht erlischt.")
    for iid, it in items.items():
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.subheader(it["name"])
            c1.write(it.get("desc", ""))
            c2.metric("Preis", f"{_price(it['price'])} €")
            if it.get("games") and set(it["games"]) <= have:
                c2.success("✅ Freigeschaltet")
            elif c2.button("Kaufen", key=f"buy_{iid}", disabled=not agree, use_container_width=True):
                try:
                    st.session_state["pay_link"] = (iid, create_order(tid, p.get("twitch_username"), iid, it))
                except Exception as e:
                    st.error(f"PayPal-Fehler: {e}")
            pl = st.session_state.get("pay_link")
            if pl and pl[0] == iid:
                c2.link_button("➡️ Weiter zu PayPal", pl[1], use_container_width=True)
    with st.expander("Rechtliches"):
        s = st.secrets.get("shop", {})
        st.markdown(f"[Impressum]({s.get('impressum_url', '#')}) · [AGB]({s.get('agb_url', '#')}) · [Widerruf]({s.get('widerruf_url', '#')})")


def admin_shop_panel(games):
    items = load_items(active_only=False)
    st.subheader("📦 Katalog")
    pick = st.selectbox("Artikel bearbeiten", ["➕ Neu"] + list(items), key="shop_pick")
    cur = items.get(pick, {})
    with st.form("shop_item"):
        iid = st.text_input("Artikel-ID (a-z, 0-9, _)", value="" if pick == "➕ Neu" else pick, disabled=pick != "➕ Neu")
        nm = st.text_input("Name", value=cur.get("name", ""))
        ds = st.text_area("Beschreibung", value=cur.get("desc", ""))
        pr = st.number_input("Preis (€)", 0.5, 500.0, float(cur.get("price", 4.99)), 0.5)
        gm = st.multiselect("Schaltet frei", list(games), default=[g for g in cur.get("games", []) if g in games],
                            format_func=lambda k: games[k])
        act = st.checkbox("Aktiv (im Shop sichtbar)", value=cur.get("active", True))
        if st.form_submit_button("💾 Speichern"):
            key = (iid if pick == "➕ Neu" else pick).strip().lower()
            if not key.replace("_", "").isalnum() or not nm.strip() or not gm:
                st.error("ID, Name und mindestens ein Game sind Pflicht.")
            else:
                db.reference(f"shop/items/{key}").set({"name": nm.strip(), "desc": ds.strip(), "price": pr, "games": gm, "active": act})
                st.rerun()
    if pick != "➕ Neu" and st.button("🗑️ Artikel löschen"):
        db.reference(f"shop/items/{pick}").delete()
        st.rerun()

    st.subheader("🧾 Bestellungen")
    orders = db.reference("shop/orders").get() or {}
    df = pd.DataFrame([dict(o, order_id=k) for k, o in orders.items() if isinstance(o, dict)])
    if df.empty:
        st.info("Noch keine Bestellungen.")
        return
    df["price"] = df["price"].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert("Europe/Berlin").dt.strftime("%d.%m.%Y %H:%M")
    paid = df[df["status"] == "paid"]
    c1, c2 = st.columns(2)
    c1.metric("Umsatz (brutto, vor PayPal-Gebühren)", f"{paid['price'].sum():.2f} €")
    c2.metric("Bezahlte Bestellungen", len(paid))
    st.dataframe(df[["ts", "name", "item_name", "price", "status", "order_id"]].sort_values("ts", ascending=False),
                 hide_index=True, use_container_width=True)
