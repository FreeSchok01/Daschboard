"""Öffentlicher Streamdex-Shop (bezahlt per StreamElements-Tip) + Admin-Panel für Katalog und Bestellungen.
Kauf -> Bestellcode -> Tip mit Code in der Nachricht -> Server gleicht per SE-API ab -> game_flags/streamers/{tid}/{game}=True.
Die App übernimmt die Freischaltung beim nächsten Heartbeat (~60 s), ohne App-Änderung."""
import secrets
from decimal import Decimal

import pandas as pd
import requests
import streamlit as st
from firebase_admin import db


class _Skip(Exception):
    pass


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


def _se():
    return {"Authorization": f"Bearer {st.secrets['streamelements']['jwt']}"}


def create_order(tid, name, item_id, item):
    code = "SDX-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    price = _price(item["price"])
    db.reference(f"shop/orders/{code}").set({"tid": tid, "name": name, "item": item_id, "item_name": item["name"],
                                            "games": item.get("games", []), "price": price, "status": "pending",
                                            "ts": {".sv": "timestamp"}})
    return code, item_id, price


def _find_tip(code, price):
    h = _se()
    api = "https://api.streamelements.com/kappa/v2"
    r = requests.get(f"{api}/channels/me", headers=h, timeout=15)
    r.raise_for_status()
    r = requests.get(f"{api}/tips/{r.json()['_id']}", params={"limit": 100}, headers=h, timeout=20)
    r.raise_for_status()
    cur = st.secrets["streamelements"].get("currency", "EUR").upper()
    for t in r.json().get("docs", []):
        d = t.get("donation") or {}
        if (code in str(d.get("message", "")).upper() and t.get("status", "success") == "success"
                and str(d.get("currency", "")).upper() == cur and Decimal(str(d.get("amount", 0))) >= Decimal(price)):
            return t
    return None


def fulfill(code, manual=False):
    """Gibt (ok, Text) zurück. Ein Tip und eine Bestellung werden höchstens einmal verbucht."""
    ref = db.reference(f"shop/orders/{code.strip().upper()}")
    order = ref.get()
    if not isinstance(order, dict):
        return False, "Unbekannter Bestellcode."
    if order.get("status") == "paid":
        return True, f"Bereits verbucht: **{order['item_name']}** für {order['name']}."
    tip_id = "manuell"
    if not manual:
        try:
            tip = _find_tip(ref.key, order["price"])
        except Exception as e:
            return False, f"StreamElements-Abfrage fehlgeschlagen: {e}"
        if not tip:
            return False, "Noch keine passende Zahlung gefunden. Prüfe Betrag und Code in der Nachricht und versuche es in ein paar Sekunden erneut."
        tip_id = str(tip["_id"])

        def use(cur):
            if cur:
                raise _Skip()
            return ref.key
        try:
            db.reference(f"shop/used_tips/{tip_id}").transaction(use)
        except _Skip:
            return False, "Diese Zahlung wurde schon einer anderen Bestellung zugeordnet."

    def claim(cur):
        if not cur or cur.get("status") != "pending":
            raise _Skip()
        return dict(cur, status="paid", tip_id=tip_id, paid_ts={".sv": "timestamp"})
    try:
        ref.transaction(claim)
    except _Skip:
        return False, "Die Bestellung wird gerade verarbeitet oder ist schon verbucht."
    for g in order.get("games", []):
        db.reference(f"game_flags/streamers/{order['tid']}/{g}").set(True)
    return True, f"✅ Zahlung erhalten! **{order['item_name']}** ist für **{order['name']}** freigeschaltet (in der App nach ca. 1 Minute aktiv)."


def render_shop():
    st.title("🛒 Streamdex Shop")
    st.caption("Schalte zusätzliche Funktionen für deinen Twitch-Kanal frei. Bezahlung per StreamElements-Tip (PayPal, Karte u.a.).")
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
                st.session_state["order"] = create_order(tid, p.get("twitch_username"), iid, it)
            o = st.session_state.get("order")
            if o and o[1] == iid:
                st.info(f"1️⃣ Öffne die [Tip-Seite]({st.secrets['streamelements']['tip_url']})  \n"
                        f"2️⃣ Betrag: **{o[2]} €** (oder mehr)  \n3️⃣ Nachricht: **`{o[0]}`** (genau so eintragen!)  \n"
                        "4️⃣ Nach dem Bezahlen hier auf „Zahlung prüfen“ klicken.")
                if st.button("🔍 Zahlung prüfen", key=f"chk_{iid}"):
                    ok, msg = fulfill(o[0])
                    (st.success if ok else st.warning)(msg)
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
    pend = df[df["status"] == "pending"]["order_id"].tolist()
    if pend:
        c1, c2 = st.columns([3, 1])
        code = c1.selectbox("Offene Bestellung manuell verbuchen (Tip ohne/mit falschem Code)", pend)
        if c2.button("✅ Verbuchen"):
            st.info(fulfill(code, manual=True)[1])
    df["price"] = df["price"].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert("Europe/Berlin").dt.strftime("%d.%m.%Y %H:%M")
    paid = df[df["status"] == "paid"]
    c1, c2 = st.columns(2)
    c1.metric("Umsatz (brutto, vor Gebühren)", f"{paid['price'].sum():.2f} €")
    c2.metric("Bezahlte Bestellungen", len(paid))
    st.dataframe(df[["ts", "name", "item_name", "price", "status", "order_id"]].sort_values("ts", ascending=False),
                 hide_index=True, use_container_width=True)
