"""Streamdex-Shop: Einzel-Games, 4 Packs, Warenkorb. Bezahlung per StreamElements-Tip mit Bestellcode.
Freischaltung: game_flags/streamers/{tid}/{game}=True (die App übernimmt es nach ~60 s). Preise/Einstellungen: Admin-Tab 🛒 Shop."""
import html
import secrets
from datetime import date
from decimal import Decimal

import pandas as pd
import requests
import streamlit as st
from firebase_admin import db


class _Skip(Exception):
    pass


PRICES = {"slot": 2.99, "megaslot": 3.99, "steal": 1.99, "raffel": 1.99, "gambel": 1.99, "hilo": 1.99, "raffle": 1.99,
          "fishing": 4.99, "mining": 3.49, "farming": 4.49, "race": 2.99, "arena": 5.99}
DESC = {"slot": "Der Klassiker: Walzen drehen, Coins gewinnen.", "megaslot": "Großes Raster, mehrere Gewinnlinien, Jackpot.",
        "steal": "Viewer klauen sich gegenseitig Coins. Chaos garantiert.", "raffel": "Lose kaufen und Punkte-Raffel im Chat.",
        "gambel": "Einsatz rein, Glück testen – schnell und simpel.", "hilo": "Höher oder tiefer? Kartenspiel im Chat.",
        "raffle": "Punkte-Verlosung mit !join für die ganze Community.", "fishing": "Angeln, Aquarium & Kraken mit Ruten und Gewässern.",
        "mining": "Minen mit !mine – Erze sammeln und aufsteigen.", "farming": "Pflanzen, wachsen lassen, ernten, Level aufsteigen.",
        "race": "Sim-Racing-Rennen im Chat mit Overlay.", "arena": "Duelle, Pets, Reittiere, Skins und Hausbau in der Arena."}
PACKS = {
    "pack_casino": ("🎰 Casino-Pack", "Slot, Mega Slot, Gambel, Hi-Lo & Raffel: alles fürs Glücksspiel im Chat.", ["slot", "megaslot", "gambel", "hilo", "raffel"], 9.99),
    "pack_abenteuer": ("🌾 Abenteuer-Pack", "Angeln, Minen & Farm: Fortschritt und Sammeln für deine Community.", ["fishing", "mining", "farming"], 9.99),
    "pack_action": ("⚔️ Action-Pack", "Arena, Taschenraub, Sim Racing & Punkte-Raffle.", ["arena", "steal", "race", "raffle"], 9.99),
    "pack_komplett": ("👑 Komplett-Pack", "Alle 12 Games auf einmal: der beste Preis.", list(PRICES), 24.99),
}


def default_items(games):
    it = {k: {"kind": "game", "name": games[k], "desc": DESC.get(k, ""), "price": p, "games": [k], "active": True, "sort": n}
          for n, (k, p) in enumerate(PRICES.items()) if k in games}
    for n, (k, (nm, ds, gm, p)) in enumerate(PACKS.items()):
        it[k] = {"kind": "pack", "name": nm, "desc": ds, "price": p, "games": [g for g in gm if g in games], "active": True, "sort": 100 + n}
    return it


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
    items = {k: v for k, v in items.items() if isinstance(v, dict) and (v.get("active", True) or not active_only)}
    return dict(sorted(items.items(), key=lambda kv: (kv[1].get("sort", 50), kv[1].get("name", ""))))


def shop_settings():
    return db.reference("shop/settings").get() or {}


def owned_games(tid):
    own = db.reference(f"game_flags/streamers/{tid}").get() or {}
    glob = db.reference("game_flags/global").get() or {}
    return {g for g in set(own) | set(glob) if own.get(g) is True or (not isinstance(own.get(g), bool) and glob.get(g) is True)}


def _se():
    return {"Authorization": f"Bearer {st.secrets['streamelements']['jwt']}"}


def cart_view(cart, items, have):
    """Bereinigt den Warenkorb: nichts doppelt kaufen (schon Besessenes oder von einem Pack Abgedecktes fliegt raus)."""
    ids = [i for i in dict.fromkeys(cart) if i in items and not set(items[i].get("games", [])) <= have]
    ids.sort(key=lambda i: -len(items[i].get("games", [])))
    kept, covered = [], set()
    for i in ids:
        g = set(items[i].get("games", []))
        if not g <= covered:
            kept.append(i)
            covered |= g
    total = sum(Decimal(_price(items[i]["price"])) for i in kept)
    single = {g: Decimal(_price(v["price"])) for v in items.values() if v.get("kind") == "game" for g in v.get("games", [])}
    worth = sum(single.get(g, Decimal(0)) for g in covered - have)
    return kept, total, max(Decimal(0), worth - total), covered


def validate_coupon(code):
    code = (code or "").strip().upper()
    c = db.reference(f"shop/coupons/{code}").get() if code and code.replace("-", "").replace("_", "").isalnum() else None
    if not isinstance(c, dict) or not c.get("active", True):
        return False, None, "Code ungültig."
    if c.get("expires") and str(c["expires"]) < date.today().isoformat():
        return False, None, "Dieser Code ist abgelaufen."
    if int(c.get("max_uses") or 0) and int(c.get("uses") or 0) >= int(c["max_uses"]):
        return False, None, "Dieser Code wurde schon zu oft benutzt."
    return True, dict(c, code=code), ""


def apply_coupon(total, c):
    if not c:
        return total, Decimal(0)
    final = max(Decimal("0.50"), (total * (Decimal(100) - Decimal(str(c["percent"]))) / 100).quantize(Decimal("0.01")))
    return final, max(Decimal(0), total - final)


def create_cart_order(tid, name, ids, items, coupon=""):
    code = "SDX-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    games = sorted({g for i in ids for g in items[i].get("games", [])})
    total = sum(Decimal(_price(items[i]["price"])) for i in ids)
    ok, c, _ = validate_coupon(coupon) if coupon else (False, None, "")   # serverseitig neu geprüft
    final, disc = apply_coupon(total, c if ok else None)
    order = {"tid": tid, "name": name, "item": "cart", "item_name": " + ".join(items[i]["name"] for i in ids)[:200],
             "items": ids, "games": games, "price": _price(final), "gross": _price(total), "status": "pending", "ts": {".sv": "timestamp"}}
    if ok:
        order.update(coupon=c["code"], partner=c.get("partner", ""), discount=_price(disc))
    db.reference(f"shop/orders/{code}").set(order)
    return code, _price(final)


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
    if order.get("coupon"):
        try:
            db.reference(f"shop/coupons/{order['coupon']}").transaction(
                lambda c: dict(c, uses=int(c.get("uses") or 0) + 1, revenue=round(float(c.get("revenue") or 0) + float(order["price"]), 2)) if c else c)
        except Exception:
            pass
    return True, f"✅ Zahlung erhalten! **{order['item_name']}** ist für **{order['name']}** freigeschaltet (in der App nach ca. 1 Minute aktiv)."


CSS = """<style>
.block-container{max-width:1180px;padding-top:1.5rem}
.hero{background:linear-gradient(135deg,#9146FF 0%,#5b21b6 55%,#1e1b4b 100%);border-radius:22px;padding:2.4rem 2.2rem;color:#fff;margin-bottom:1.2rem;box-shadow:0 10px 40px #9146ff33}
.hero h1{margin:0;font-size:2.4rem;color:#fff;padding:0}.hero p{margin:.5rem 0 0;opacity:.92;font-size:1.05rem}
.steps{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1rem}.steps span{background:#ffffff22;border-radius:999px;padding:.25rem .8rem;font-size:.85rem}
.banner{background:#3b2a05;border:1px solid #f5b301;color:#ffd166;border-radius:12px;padding:.7rem 1rem;margin-bottom:1rem}
.ct{font-size:1.15rem;font-weight:700;margin-bottom:.2rem}.cd{opacity:.72;font-size:.9rem;min-height:2.7em}
.price{font-size:1.6rem;font-weight:800;color:#b388ff;margin:.4rem 0}.old{text-decoration:line-through;opacity:.5;font-size:.95rem;margin-left:.5rem;font-weight:400;color:#aaa}
.badge{display:inline-block;background:#22c55e22;color:#4ade80;border-radius:999px;padding:.1rem .7rem;font-size:.8rem;font-weight:700}
.badge.save{background:#f5b30126;color:#fbbf24}
.chips span{display:inline-block;background:#ffffff14;border-radius:8px;padding:.05rem .5rem;margin:.1rem .2rem 0 0;font-size:.78rem}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:16px}
.stButton>button,.stLinkButton>a{border-radius:12px;font-weight:600}
</style>"""


def _add(i):
    c = st.session_state.setdefault("cart", [])
    if i not in c:
        c.append(i)


def _rm(i):
    st.session_state["cart"] = [x for x in st.session_state.get("cart", []) if x != i]


def _card(iid, it, items, have, cart):
    g = it.get("games", [])
    pack = it.get("kind") == "pack"
    with st.container(border=True):
        chips = ""
        if pack:
            lab = {k: v["name"] for v in items.values() if v.get("kind") == "game" for k in v.get("games", [])}
            chips = '<div class="chips">' + "".join(f"<span>{html.escape(lab.get(x, x))}</span>" for x in g) + "</div>"
        single = sum(Decimal(_price(v["price"])) for v in items.values() if v.get("kind") == "game" and set(v.get("games", [])) <= set(g))
        old = f'<span class="old">{single} €</span>' if pack and single > Decimal(_price(it["price"])) else ""
        save = f'<span class="badge save">Spare {single - Decimal(_price(it["price"]))} €</span>' if old else ""
        st.markdown(f'<div class="ct">{html.escape(it["name"])}</div><div class="cd">{html.escape(it.get("desc", ""))}</div>{chips}'
                    f'<div class="price">{_price(it["price"])} €{old}</div>{save}', unsafe_allow_html=True)
        if g and set(g) <= have:
            st.markdown('<span class="badge">✅ Freigeschaltet</span>', unsafe_allow_html=True)
        elif iid in cart:
            st.button("✔ Im Warenkorb (entfernen)", key=f"rm_c_{iid}", on_click=_rm, args=(iid,), use_container_width=True)
        else:
            st.button("🛒 In den Warenkorb", key=f"add_{iid}", on_click=_add, args=(iid,), type="primary" if pack else "secondary", use_container_width=True)


def _order_box():
    code, price = st.session_state["order"]
    with st.container(border=True):
        st.markdown("### 💳 Jetzt bezahlen")
        st.markdown(f"**1.** Öffne die Tip-Seite  \n**2.** Betrag: **{price} €** (oder mehr)  \n**3.** Nachricht: exakt diesen Code")
        st.code(code, language=None)
        st.link_button("➡️ Zur Tip-Seite", st.secrets["streamelements"]["tip_url"], use_container_width=True)
        st.caption("Danach hier auf „Zahlung prüfen“ klicken.")
        if st.button("🔍 Zahlung prüfen", type="primary", use_container_width=True):
            ok, msg = fulfill(code)
            if ok:
                st.session_state.pop("order")
                st.balloons()
                st.success(msg)
            else:
                st.warning(msg)
        if st.button("Abbrechen", use_container_width=True):
            st.session_state.pop("order")
            st.rerun()


def _cart_box(tid, name, items, have):
    ids, total, save, _ = cart_view(st.session_state.get("cart", []), items, have)
    with st.container(border=True):
        st.markdown("### 🛒 Warenkorb")
        if not ids:
            st.caption("Noch leer. Wähle links Packs oder einzelne Games.")
            return
        for i in ids:
            a, b = st.columns([5, 1])
            a.markdown(f"{html.escape(items[i]['name'])}  \n**{_price(items[i]['price'])} €**")
            b.button("✕", key=f"x_{i}", on_click=_rm, args=(i,))
        st.divider()
        cc = st.session_state.get("coupon")
        ok, cp, _m = validate_coupon(cc) if cc else (False, None, "")
        if cc and not ok:
            st.session_state.pop("coupon", None)
        if ok:
            x, y = st.columns([4, 1])
            x.markdown(f'🎟️ **{cp["code"]}** (−{cp["percent"]} %)')
            y.button("✕", key="x_coupon", on_click=lambda: st.session_state.pop("coupon", None))
        else:
            x, y = st.columns([3, 2])
            code_in = x.text_input("Code", key="coupon_in", label_visibility="collapsed", placeholder="Gutschein / Partner-Code")
            if y.button("Einlösen", use_container_width=True):
                good, _c, msg = validate_coupon(code_in)
                if good:
                    st.session_state["coupon"] = code_in.strip().upper()
                    st.rerun()
                else:
                    st.error(msg)
        final, disc = apply_coupon(total, cp if ok else None)
        old = f'<span class="old">{total} €</span>' if disc > 0 else ""
        st.markdown(f'<div class="price">Gesamt: {final} €{old}</div>' + (f'<span class="badge save">Du sparst {save + disc} €</span>' if save + disc > 0 else ""), unsafe_allow_html=True)
        agree = st.checkbox("Ich stimme zu, dass die Freischaltung sofort erfolgt und mein Widerrufsrecht damit erlischt.")
        if st.button("Bestellung anlegen", type="primary", disabled=not agree, use_container_width=True):
            st.session_state["order"] = create_cart_order(tid, name, ids, items, cc if ok else "")
            st.session_state["cart"] = []
            st.rerun()


def render_shop(games):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero"><h1>🛒 Streamdex Shop</h1><p>Schalte Chat-Games für deinen Twitch-Kanal frei: einzeln oder im Pack.</p>'
                '<div class="steps"><span>1 · Twitch-Name eingeben</span><span>2 · Warenkorb füllen</span><span>3 · Per Tip bezahlen</span><span>4 · Nach ca. 1 Min. aktiv</span></div></div>',
                unsafe_allow_html=True)
    if not db.reference("shop/items").get():
        db.reference("shop/items").set(default_items(games))
    cfg = shop_settings()
    if cfg.get("banner"):
        st.markdown(f'<div class="banner">📢 {html.escape(str(cfg["banner"]))}</div>', unsafe_allow_html=True)
    if cfg.get("open", True) is False:
        st.info("Der Shop ist gerade geschlossen. Schau bald wieder vorbei!")
        return
    name = st.text_input("Dein Twitch-Name", value=str(st.query_params.get("u", "")), placeholder="z.B. meinkanal")
    if not name.strip():
        st.info("Gib deinen Twitch-Namen ein. Du musst die Streamdex-App mindestens einmal gestartet haben.")
        return
    tid, p = find_streamer(name)
    if not tid:
        st.error("Kein Konto mit diesem Namen gefunden. Starte die Streamdex-App einmal mit deinem Twitch-Account.")
        return
    if st.session_state.get("cart_tid") != tid:
        st.session_state.update(cart=[], cart_tid=tid)
        st.session_state.pop("order", None)
    have, items = owned_games(tid), load_items()
    if not items:
        st.info("Aktuell gibt es keine Angebote.")
        return
    st.caption(f"✅ Konto: **{p.get('twitch_username')}** · App {p.get('app_version', '?')} · {len(have)} Game(s) freigeschaltet")
    cart = st.session_state.get("cart", [])
    left, right = st.columns([3, 1.3], gap="large")
    with left:
        t_packs, t_games = st.tabs(["🎁 Packs (sparen)", "🎮 Einzelne Games"])
        for tab, kind, n in ((t_packs, "pack", 2), (t_games, "game", 3)):
            with tab:
                lst = [(k, v) for k, v in items.items() if v.get("kind", "game") == kind]
                for r in range(0, len(lst), n):
                    for col, (k, v) in zip(st.columns(n), lst[r:r + n]):
                        with col:
                            _card(k, v, items, have, cart)
    with right:
        if st.session_state.get("order"):
            _order_box()
        else:
            _cart_box(tid, p.get("twitch_username"), items, have)
    with st.expander("Rechtliches"):
        s = st.secrets.get("shop", {})
        st.markdown(f"[Impressum]({s.get('impressum_url', '#')}) · [AGB]({s.get('agb_url', '#')}) · [Widerruf]({s.get('widerruf_url', '#')})")


def admin_shop_panel(games):
    items = load_items(active_only=False)
    cfg = shop_settings()
    st.subheader("⚙️ Shop-Einstellungen (global)")
    with st.form("shop_cfg"):
        op = st.toggle("Shop geöffnet", value=cfg.get("open", True))
        bn = st.text_input("Banner-Hinweis (optional, oben im Shop)", value=cfg.get("banner", ""), max_chars=200)
        if st.form_submit_button("💾 Speichern"):
            db.reference("shop/settings").set({"open": op, "banner": bn.strip()})
            st.success("Gespeichert.")
    st.caption("Welche Games standardmäßig für ALLE frei sind, stellst du im Tab „🎮 Game-Freigaben“ unter „Global“ ein.")

    st.subheader("💶 Preise & Sichtbarkeit")
    if not items:
        st.info("Noch kein Katalog. Er wird beim ersten Shop-Aufruf angelegt oder unten über „Standard-Katalog“.")
    else:
        df = pd.DataFrame([{"ID": k, "Name": v["name"], "Typ": v.get("kind", "game"), "Preis €": float(v["price"]), "Aktiv": bool(v.get("active", True))} for k, v in items.items()])
        ed = st.data_editor(df, hide_index=True, use_container_width=True, key="price_editor", disabled=["ID", "Name", "Typ"],
                            column_config={"Preis €": st.column_config.NumberColumn(min_value=0.5, max_value=500.0, step=0.5, format="%.2f")})
        if st.button("💾 Preise speichern", type="primary"):
            n = 0
            for _, r in ed.iterrows():
                o = items[r["ID"]]
                if float(r["Preis €"]) != float(o["price"]) or bool(r["Aktiv"]) != bool(o.get("active", True)):
                    db.reference(f"shop/items/{r['ID']}").update({"price": float(r["Preis €"]), "active": bool(r["Aktiv"])})
                    n += 1
            st.success(f"{n} Artikel aktualisiert.")
            st.rerun()
    with st.expander("🧰 Artikel bearbeiten / neu anlegen / Standard-Katalog"):
        pick = st.selectbox("Artikel", ["➕ Neu"] + list(items), key="shop_pick")
        cur = items.get(pick, {})
        with st.form("shop_item"):
            iid = st.text_input("Artikel-ID (a-z, 0-9, _)", value="" if pick == "➕ Neu" else pick, disabled=pick != "➕ Neu")
            nm = st.text_input("Name", value=cur.get("name", ""))
            ds = st.text_area("Beschreibung", value=cur.get("desc", ""))
            kd = st.selectbox("Typ", ["game", "pack"], index=1 if cur.get("kind") == "pack" else 0)
            pr = st.number_input("Preis (€)", 0.5, 500.0, float(cur.get("price", 4.99)), 0.5)
            gm = st.multiselect("Schaltet frei", list(games), default=[g for g in cur.get("games", []) if g in games], format_func=lambda k: games[k])
            act = st.checkbox("Aktiv", value=cur.get("active", True))
            if st.form_submit_button("💾 Speichern"):
                key = (iid if pick == "➕ Neu" else pick).strip().lower()
                if not key.replace("_", "").isalnum() or not nm.strip() or not gm:
                    st.error("ID, Name und mindestens ein Game sind Pflicht.")
                else:
                    db.reference(f"shop/items/{key}").set({"kind": kd, "name": nm.strip(), "desc": ds.strip(), "price": pr, "games": gm,
                                                          "active": act, "sort": cur.get("sort", 50 if kd == "game" else 150)})
                    st.rerun()
        if pick != "➕ Neu" and st.button("🗑️ Artikel löschen"):
            db.reference(f"shop/items/{pick}").delete()
            st.rerun()
        st.divider()
        ok = st.checkbox("Standard-Katalog (12 Games + 4 Packs) neu anlegen. Überschreibt ALLE Artikel und Preise!")
        if st.button("♻️ Standard-Katalog anlegen", disabled=not ok):
            db.reference("shop/items").set(default_items(games))
            st.rerun()

    st.subheader("🧾 Bestellungen")
    orders = db.reference("shop/orders").get() or {}
    df = pd.DataFrame([dict(o, order_id=k) for k, o in orders.items() if isinstance(o, dict)])
    if df.empty:
        st.info("Noch keine Bestellungen.")
        return
    df["price"] = df["price"].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert("Europe/Berlin").dt.strftime("%d.%m.%Y %H:%M")
    pend = df[df["status"] == "pending"]["order_id"].tolist()
    if pend:
        c1, c2 = st.columns([3, 1])
        code = c1.selectbox("Offene Bestellung manuell verbuchen (Tip ohne/mit falschem Code)", pend)
        if c2.button("✅ Verbuchen"):
            st.info(fulfill(code, manual=True)[1])
    paid = df[df["status"] == "paid"]
    c1, c2 = st.columns(2)
    c1.metric("Umsatz (brutto, vor Gebühren)", f"{paid['price'].sum():.2f} €")
    c2.metric("Bezahlte Bestellungen", len(paid))
    st.dataframe(df[["ts", "name", "item_name", "price", "status", "order_id"]].sort_values("ts", ascending=False), hide_index=True, use_container_width=True)
    with st.expander("🗑️ Bestellungen löschen"):
        lab = {r.order_id: f"{r.order_id} · {r.name} · {str(r.item_name)[:40]} · {r.price:.2f} € · {r.status}" for r in df.itertuples()}
        sel = st.multiselect("Bestellungen", list(lab), format_func=lab.get)
        rv = st.checkbox("Bei bezahlten Bestellungen auch die Freischaltung entziehen (z. B. Rückerstattung)")
        sure = st.checkbox("Ja, endgültig löschen")
        if st.button("🗑️ Löschen", disabled=not (sel and sure)):
            for code in sel:
                o = orders.get(code) or {}
                if rv and o.get("status") == "paid":
                    for g in set(o.get("games", [])) - protected_games(o["tid"], exclude=set(sel)):
                        db.reference(f"game_flags/streamers/{o['tid']}/{g}").delete()
                db.reference(f"shop/orders/{code}").delete()
            st.rerun()


def protected_games(tid, exclude=()):
    """Games, die ein Streamer durch andere bezahlte Bestellungen oder Beta-Status behalten muss."""
    keep = set()
    for k, o in (db.reference("shop/orders").get() or {}).items():
        if isinstance(o, dict) and o.get("tid") == tid and o.get("status") == "paid" and k not in exclude:
            keep |= set(o.get("games", []))
    b = db.reference(f"shop/beta/{tid}").get()
    return keep | set(b.get("games", [])) if isinstance(b, dict) else keep


def set_beta(tid, name, games, scope, note):
    old = db.reference(f"shop/beta/{tid}/games").get() or []
    for g in games:
        db.reference(f"game_flags/streamers/{tid}/{g}").set(True)
    db.reference(f"shop/beta/{tid}").set({"name": name, "games": games, "scope": scope, "note": note, "ts": {".sv": "timestamp"}})
    for g in set(old) - set(games) - protected_games(tid):
        db.reference(f"game_flags/streamers/{tid}/{g}").delete()


def remove_beta(tid):
    old = db.reference(f"shop/beta/{tid}/games").get() or []
    db.reference(f"shop/beta/{tid}").delete()
    for g in set(old) - protected_games(tid):
        db.reference(f"game_flags/streamers/{tid}/{g}").delete()


def admin_beta_panel(games, rows):
    st.subheader("🧪 Beta-Tester")
    st.caption("Beta-Tester bekommen Games ohne Kauf freigeschaltet. Beim Entfernen verschwinden nur die Beta-Freigaben, Gekauftes bleibt. "
               "„Alles“ gilt für die aktuell vorhandenen Games. Bei neuen Games den Status erneut setzen.")
    names = {r["tid"]: r["name"] for r in rows}
    with st.form("beta"):
        sel = st.multiselect("Streamer (mehrere möglich)", list(names), format_func=names.get)
        scope = st.radio("Umfang", ["Alles (alle Games)", "Nur ausgewählte Games"], horizontal=True)
        gm = st.multiselect("Games (bei „Nur ausgewählte“)", list(games), format_func=lambda k: games[k])
        note = st.text_input("Notiz (z. B. testet die neue Arena)")
        if st.form_submit_button("🧪 Beta-Status setzen"):
            allg = scope.startswith("Alles")
            g = list(games) if allg else gm
            if not sel or not g:
                st.error("Bitte Streamer und (bei „Nur ausgewählte“) mindestens ein Game wählen.")
            else:
                for t in sel:
                    set_beta(t, names[t], g, "all" if allg else "some", note.strip())
                st.success(f"{len(sel)} Streamer als Beta-Tester gesetzt. Aktiv in der App nach ca. 1 Minute.")
    beta = db.reference("shop/beta").get() or {}
    if not beta:
        return
    st.dataframe(pd.DataFrame([{"Streamer": names.get(t, v.get("name", t)), "Umfang": "Alles" if v.get("scope") == "all" else ", ".join(games.get(g, g) for g in v.get("games", [])),
                                "Notiz": v.get("note", "")} for t, v in beta.items() if isinstance(v, dict)]), hide_index=True, use_container_width=True)
    rm = st.multiselect("Beta-Status entfernen bei", list(beta), format_func=lambda t: names.get(t, beta[t].get("name", t)))
    if st.button("Beta-Status entfernen", disabled=not rm):
        for t in rm:
            remove_beta(t)
        st.rerun()


def admin_coupon_panel():
    st.subheader("🎟️ Gutscheine & Partner-Codes")
    st.caption("Jeder Code gibt X % Rabatt auf den Warenkorb. Mit einem Partner-Namen siehst du unten, wie viel jeder Partner einbringt.")
    cps = {k: v for k, v in (db.reference("shop/coupons").get() or {}).items() if isinstance(v, dict)}
    if cps:
        cdf = pd.DataFrame([{"Code": k, "Partner": v.get("partner", ""), "Rabatt %": v.get("percent"), "Benutzt": int(v.get("uses") or 0),
                             "Limit": int(v.get("max_uses") or 0) or "∞", "Läuft ab": v.get("expires") or "–",
                             "Umsatz €": round(float(v.get("revenue") or 0), 2), "Aktiv": v.get("active", True)} for k, v in cps.items()])
        st.dataframe(cdf, hide_index=True, use_container_width=True)
        part = cdf[cdf["Partner"] != ""].groupby("Partner")[["Benutzt", "Umsatz €"]].sum()
        if not part.empty:
            st.markdown("**Partner-Übersicht**")
            st.dataframe(part, use_container_width=True)
    pick = st.selectbox("Code bearbeiten", ["➕ Neuer Code"] + list(cps))
    new, cur = pick.startswith("➕"), cps.get(pick, {})
    with st.form("coupon"):
        code = st.text_input("Code (A-Z, 0-9, - _). Leer = automatisch", value="" if new else pick, disabled=not new)
        partner = st.text_input("Partner (optional)", value=cur.get("partner", ""))
        pc = st.number_input("Rabatt in %", 1, 90, int(cur.get("percent", 10)))
        mx = st.number_input("Max. Benutzungen (0 = unbegrenzt)", 0, 100000, int(cur.get("max_uses") or 0))
        exp = st.text_input("Läuft ab am (JJJJ-MM-TT, leer = nie)", value=cur.get("expires", ""))
        act = st.checkbox("Aktiv", value=cur.get("active", True))
        if st.form_submit_button("💾 Speichern"):
            key = (code if new else pick).strip().upper()
            if new and not key:
                base = "".join(ch for ch in partner.upper() if ch.isalnum())[:8] or "SDX"
                key = f"{base}{pc}"
            try:
                if exp.strip():
                    date.fromisoformat(exp.strip())
                bad = not key.replace("-", "").replace("_", "").isalnum()
            except ValueError:
                bad = True
            if bad:
                st.error("Code oder Datum ungültig (Datum: JJJJ-MM-TT).")
            elif new and key in cps:
                st.error(f"Den Code {key} gibt es schon.")
            else:
                db.reference(f"shop/coupons/{key}").update({"percent": int(pc), "partner": partner.strip(), "max_uses": int(mx), "expires": exp.strip(),
                                                          "active": act, "uses": int(cur.get("uses") or 0), "revenue": float(cur.get("revenue") or 0)})
                st.success(f"Gespeichert: {key}")
                st.rerun()
    if not new and st.button("🗑️ Code löschen"):
        db.reference(f"shop/coupons/{pick}").delete()
        st.rerun()
