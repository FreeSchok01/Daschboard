"""Streamdex-Shop: Einzel-Games, 4 Packs, Warenkorb. Bezahlung per StreamElements-Tip mit Bestellcode.
Freischaltung: game_flags/streamers/{tid}/{game}=True (die App übernimmt es nach ~60 s). Preise/Einstellungen: Admin-Tab 🛒 Shop."""
import html
import re
import secrets
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

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
    it = {k: {"kind": "game", "name": games[k], "desc": DESC.get(k, ""), "price": p, "games": [k], "active": True, "sort": n, "download_url": ""}
          for n, (k, p) in enumerate(PRICES.items()) if k in games}
    for n, (k, (nm, ds, gm, p)) in enumerate(PACKS.items()):
        it[k] = {"kind": "pack", "name": nm, "desc": ds, "price": p, "games": [g for g in gm if g in games], "active": True, "sort": 100 + n}
    return it


def _price(x):
    return str(Decimal(str(x)).quantize(Decimal("0.01")))


def _safe_download_url(value):
    """Accept only ordinary HTTPS download links; reject schemes like javascript: or file:."""
    url = str(value or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return url


def _order_downloads(code, tid, items):
    """Return downloadable game modules only for a paid order belonging to the current Twitch account."""
    code = str(code or "").strip().upper()
    if not re.fullmatch(r"SDX-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}", code):
        return None, []
    order = db.reference(f"shop/orders/{code}").get()
    if not isinstance(order, dict) or order.get("status") != "paid" or str(order.get("tid") or "") != str(tid):
        return None, []

    ordered_games = set(order.get("games", [])) if isinstance(order.get("games"), list) else set()
    links = []
    for game in sorted(ordered_games):
        product = next(
            (item for item in items.values()
             if item.get("kind", "game") == "game" and game in item.get("games", [])),
            None,
        )
        url = _safe_download_url(product.get("download_url")) if isinstance(product, dict) else ""
        if url:
            links.append({
                "game": game,
                "name": str(product.get("name") or game),
                "url": url,
            })
    return order, links


def _render_order_downloads(tid, items):
    """Order-code lookup for repeat downloads, scoped to the currently selected Twitch account."""
    expanded = bool(st.session_state.get("download_order_code"))
    with st.expander("📥 Gekaufte Game-Module herunterladen", expanded=expanded):
        st.caption("Du brauchst den Bestellcode und musst das zugehörige Twitch-Konto im Shop ausgewählt haben.")
        with st.form("shop_download_lookup"):
            candidate = st.text_input("Bestellcode", placeholder="z. B. SDX-ABC234", max_chars=10)
            submitted = st.form_submit_button("Downloads anzeigen")
        if submitted:
            order, _ = _order_downloads(candidate, tid, items)
            if order is None:
                st.error("Bestellung nicht gefunden, noch nicht bezahlt oder sie gehört zu einem anderen Twitch-Konto.")
            else:
                st.session_state["download_order_code"] = candidate.strip().upper()
                st.rerun()

        code = st.session_state.get("download_order_code")
        if code:
            order, links = _order_downloads(code, tid, items)
            if order is None:
                st.session_state.pop("download_order_code", None)
                st.warning("Der gespeicherte Download-Aufruf passt nicht zu diesem Konto. Gib deinen Bestellcode erneut ein.")
            elif not links:
                st.info("Die Bestellung ist bezahlt, aber für diese Games sind noch keine gültigen HTTPS-Download-Links hinterlegt. Bitte im Shop-Admin die Download-Links der einzelnen Games eintragen.")
            else:
                st.caption(f"Downloads für Bestellung **{code}** · {len(links)} Modul(e)")
                for link in links:
                    st.link_button(
                        f"⬇️ {link['name']} herunterladen",
                        link["url"],
                        use_container_width=True,
                    )


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
    if c.get("type") == "amount" and float(c.get("balance") or 0) <= 0:
        return False, None, "Dieser Gutschein ist aufgebraucht."
    return True, dict(c, code=code), ""


def apply_coupon(total, c):
    """Prozent-Code: min. 0,50 € Restpreis. Wert-Gutschein: zieht Guthaben ab, darf bis 0 € gehen (dann kostenlos)."""
    if not c:
        return total, Decimal(0)
    if c.get("type") == "amount":
        d = min(Decimal(str(c.get("balance") or 0)).quantize(Decimal("0.01")), total)
        return total - d, d
    final = max(Decimal("0.50"), (total * (Decimal(100) - Decimal(str(c.get("percent", 0)))) / 100).quantize(Decimal("0.01")))
    return final, max(Decimal(0), total - final)


def release_credit(o):
    """Reserviertes Gutschein-Guthaben einer NICHT bezahlten Bestellung zurückbuchen."""
    if o.get("coupon_type") == "amount" and o.get("status") != "paid" and o.get("coupon"):
        d = float(o.get("discount") or 0)
        if d > 0:
            db.reference(f"shop/coupons/{o['coupon']}").transaction(
                lambda c: dict(c, balance=round(float(c.get("balance") or 0) + d, 2)) if c else c)


def cancel_order(code):
    o = db.reference(f"shop/orders/{code}").get()
    if isinstance(o, dict) and o.get("status") == "pending":
        release_credit(o)
        db.reference(f"shop/orders/{code}").delete()


def create_cart_order(tid, name, ids, items, coupon="", gift=None):
    code = "SDX-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    games = sorted({g for i in ids for g in items[i].get("games", [])})
    total = sum(Decimal(_price(items[i]["price"])) for i in ids)
    ok, c, _ = validate_coupon(coupon) if coupon else (False, None, "")   # serverseitig neu geprüft
    final, disc = apply_coupon(total, c if ok else None)
    if ok and c.get("type") == "amount" and disc > 0:                      # Guthaben reservieren (atomar)
        def take(cur):
            if not cur or Decimal(str(cur.get("balance") or 0)) < disc:
                raise _Skip()
            return dict(cur, balance=round(float(Decimal(str(cur["balance"])) - disc), 2))
        try:
            db.reference(f"shop/coupons/{c['code']}").transaction(take)
        except _Skip:
            raise ValueError("Das Guthaben dieses Gutscheins reicht nicht mehr.")
    order = {"tid": tid, "name": name, "item": "cart", "item_name": " + ".join(items[i]["name"] for i in ids)[:200],
             "items": ids, "games": games, "price": _price(final), "gross": _price(total), "status": "pending", "ts": {".sv": "timestamp"}}
    if ok:
        order.update(coupon=c["code"], coupon_type=c.get("type", "percent"), partner=c.get("partner", ""), discount=_price(disc))
    if gift:
        order.update(gift_from=str(gift.get("from", ""))[:40], gift_msg=str(gift.get("msg", ""))[:100])
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
    if order.get("item") == "tourskip":        # Rundgang-Überspringen: Freigabe für die App (tour_skip/{tid})
        db.reference(f"tour_skip/{order['tid']}").set({"order": ref.key, "ts": {".sv": "timestamp"}})
        return True, f"✅ Zahlung erhalten! Danke für deine Spende. Das Überspringen ist für **{order['name']}** freigeschaltet. Klicke in der App auf „Ich habe bezahlt – prüfen“."
    for g in order.get("games", []):
        db.reference(f"game_flags/streamers/{order['tid']}/{g}").set(True)
    if "gift_from" in order:      # Geschenk: Nachricht für den Streamer (wird in der App angezeigt)
        try:
            db.reference(f"gifts/{order['tid']}/{ref.key}").set({"from": order.get("gift_from", ""), "msg": order.get("gift_msg", ""),
                                                                 "items": order.get("item_name", ""), "ts": {".sv": "timestamp"}})
        except Exception:
            pass
    if order.get("coupon"):
        try:
            db.reference(f"shop/coupons/{order['coupon']}").transaction(
                lambda c: dict(c, uses=int(c.get("uses") or 0) + 1, revenue=round(float(c.get("revenue") or 0) + float(order["price"]), 2)) if c else c)
        except Exception:
            pass
    return True, f"✅ Zahlung erhalten! **{order['item_name']}** ist für **{order['name']}** freigeschaltet (in der App nach ca. 1 Minute aktiv)."


CSS = """<style>
.block-container{max-width:1320px;padding-top:1.35rem;padding-bottom:3rem}
:root{--shop-purple:#8b5cf6;--shop-cyan:#22d3ee;--shop-line:rgba(148,163,184,.18);--shop-muted:#9aa8c7}
.sd-shop-hero{position:relative;overflow:hidden;border-radius:24px;padding:clamp(1.4rem,4vw,3rem);margin:0 0 1.4rem;color:#fff;
background:radial-gradient(ellipse at 88% 12%,rgba(34,211,238,.22),transparent 34%),radial-gradient(ellipse at 2% 100%,rgba(139,92,246,.26),transparent 40%),linear-gradient(125deg,#0e142b 0%,#161538 56%,#0d243b 100%);
border:1px solid rgba(167,139,250,.28);box-shadow:0 24px 60px rgba(3,7,18,.28),inset 0 1px 0 rgba(255,255,255,.06)}
.sd-shop-eyebrow{display:flex;align-items:center;gap:9px;font-size:.7rem;letter-spacing:.17em;text-transform:uppercase;font-weight:800;color:#c4b5fd}
.sd-shop-dot{width:8px;height:8px;background:#22d3ee;border-radius:50%;box-shadow:0 0 14px #22d3ee;display:inline-block}
.sd-shop-hero h1{font-size:clamp(2rem,4vw,3.25rem)!important;line-height:1.05!important;letter-spacing:-.055em!important;color:#fff!important;margin:.8rem 0 .7rem!important;padding:0!important}
.sd-shop-hero h1 span{background:linear-gradient(100deg,#c4b5fd,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
.sd-shop-hero p{max-width:760px;color:#c2cce3;font-size:1rem;line-height:1.7;margin:0}
.sd-shop-hero-foot{display:flex;gap:8px;flex-wrap:wrap;margin-top:1.35rem}
.sd-shop-hero-foot span{padding:7px 11px;border-radius:999px;background:rgba(255,255,255,.055);border:1px solid rgba(203,213,225,.14);font-size:.76rem;color:#dbeafe;font-weight:700}
.sd-shop-section-title{display:flex;align-items:center;gap:10px;margin:.4rem 0 .25rem;font-size:1.12rem;font-weight:800;letter-spacing:-.02em}
.sd-shop-section-sub{color:var(--shop-muted);font-size:.86rem;margin:0 0 1rem}
.sd-shop-account{background:linear-gradient(135deg,rgba(20,28,52,.94),rgba(12,24,42,.92));border:1px solid var(--shop-line);border-radius:18px;padding:1rem 1.1rem;margin-bottom:1.15rem}
.sd-shop-account-tag{display:inline-flex;align-items:center;gap:7px;padding:5px 9px;border-radius:999px;background:rgba(34,197,94,.09);border:1px solid rgba(34,197,94,.23);color:#86efac;font-size:.72rem;font-weight:800}
.sd-shop-account-copy{color:#aab8d4;font-size:.82rem;line-height:1.55}
.sd-shop-step-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:1.25rem 0}
.sd-shop-step{background:rgba(15,23,42,.62);border:1px solid var(--shop-line);border-radius:14px;padding:12px 13px}
.sd-shop-step b{display:block;font-size:.82rem;color:#edf2ff;margin-bottom:3px}
.sd-shop-step span{font-size:.74rem;line-height:1.45;color:#94a3c8}
.ct{font-size:1.14rem;font-weight:800;letter-spacing:-.02em;line-height:1.35;margin:.7rem 0 .3rem;color:#f4f5ff}
.cd{font-size:.84rem;line-height:1.6;color:#aab6d0;min-height:2.8em}
.sd-shop-card-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.sd-shop-kind{display:inline-block;padding:4px 9px;border-radius:999px;font-size:.66rem;letter-spacing:.1em;font-weight:900;text-transform:uppercase;background:rgba(139,92,246,.15);border:1px solid rgba(167,139,250,.27);color:#c4b5fd}
.sd-shop-kind.pack{background:rgba(34,211,238,.09);border-color:rgba(34,211,238,.25);color:#67e8f9}
.sd-shop-state{font-size:.7rem;color:#86efac;font-weight:800}
.sd-shop-icon{display:flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:16px;margin:.9rem 0 .55rem;
font-size:1.65rem;background:radial-gradient(circle at 35% 20%,rgba(196,181,253,.22),transparent 60%),linear-gradient(135deg,rgba(139,92,246,.18),rgba(34,211,238,.07));border:1px solid rgba(167,139,250,.23)}
.price{font-size:1.72rem;line-height:1.3;font-weight:900;letter-spacing:-.04em;color:#c4b5fd;margin:.8rem 0 .45rem}
.price .unit{font-size:.77rem;font-weight:600;letter-spacing:0;color:#9aa8c7}
.old{text-decoration:line-through;opacity:.58;font-size:.86rem;margin-left:.45rem;font-weight:500;color:#b9c3d9;letter-spacing:0}
.badge{display:inline-flex;align-items:center;gap:4px;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.22);color:#86efac;border-radius:999px;padding:4px 9px;font-size:.7rem;font-weight:800}
.badge.save{background:rgba(245,179,1,.1);border-color:rgba(245,179,1,.24);color:#fcd34d}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin:.55rem 0}
.chips span{display:inline-block;background:rgba(255,255,255,.045);border:1px solid rgba(148,163,184,.14);border-radius:7px;padding:4px 7px;font-size:.68rem;color:#c7d2e8}
.sd-shop-price-row{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap}
.sd-shop-filter-note{font-size:.75rem;color:#a6b5d2;margin:.15rem 0 .7rem}
.sd-shop-empty{border:1px dashed rgba(148,163,184,.28);background:rgba(15,23,42,.45);border-radius:15px;padding:1.1rem;color:#aab6d0;font-size:.86rem;line-height:1.6}
.sd-shop-cart-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:.7rem}
.sd-shop-cart-count{display:inline-flex;align-items:center;justify-content:center;min-width:25px;height:25px;padding:0 7px;border-radius:99px;background:rgba(139,92,246,.18);border:1px solid rgba(167,139,250,.25);color:#ddd6fe;font-weight:800;font-size:.72rem}
.sd-shop-cart-line{padding:9px 0;border-bottom:1px solid rgba(148,163,184,.13)}
.sd-shop-total-label{font-size:.76rem;color:#9aa8c7;text-transform:uppercase;letter-spacing:.08em;font-weight:800}
.sd-shop-total{font-size:1.8rem;font-weight:900;letter-spacing:-.045em;color:#d8b4fe;margin:.1rem 0 .35rem}
.sd-shop-checkout-note{font-size:.75rem;line-height:1.55;color:#9eacc8}
.sd-shop-checkout-step{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid rgba(148,163,184,.12)}
.sd-shop-checkout-step b{display:block;font-size:.82rem;color:#eef2ff}
.sd-shop-checkout-step span{font-size:.76rem;color:#a5b4cf;line-height:1.5}
.sd-shop-checkout-num{flex:0 0 27px;height:27px;border-radius:9px;display:flex;align-items:center;justify-content:center;background:rgba(139,92,246,.16);border:1px solid rgba(167,139,250,.2);color:#ddd6fe;font-weight:900;font-size:.75rem}
.banner{background:linear-gradient(110deg,rgba(120,53,15,.24),rgba(245,158,11,.08));border:1px solid rgba(245,179,1,.3);color:#fde68a;border-radius:13px;padding:.8rem 1rem;margin:0 0 1.1rem}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:17px}
.stButton>button,.stLinkButton>a,.stFormSubmitButton>button{border-radius:11px;font-weight:800}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{box-shadow:0 6px 19px rgba(139,92,246,.18)}
div[data-testid="stExpander"] details{background:rgba(12,18,37,.74);border:1px solid var(--shop-line);border-radius:13px}
.sd-shop-legal{font-size:.8rem;color:#9aa8c7;margin-top:.5rem}
@media(max-width:760px){.sd-shop-step-row{grid-template-columns:1fr}.sd-shop-hero{border-radius:18px}.sd-shop-account{padding:.8rem}.ct{font-size:1.02rem}}
</style>"""


def _add(i):
    c = st.session_state.setdefault("cart", [])
    if i not in c:
        c.append(i)


def _rm(i):
    st.session_state["cart"] = [x for x in st.session_state.get("cart", []) if x != i]


def _card(iid, it, items, have, cart):
    games = it.get("games", [])
    pack = it.get("kind") == "pack"
    with st.container(border=True):
        label_map = {
            k: v["name"] for v in items.values()
            if v.get("kind", "game") == "game" for k in v.get("games", [])
        }
        chips = ""
        if pack:
            chips = '<div class="chips">' + "".join(
                f"<span>{html.escape(label_map.get(game, game))}</span>" for game in games
            ) + "</div>"
        single_value = sum(
            Decimal(_price(item["price"]))
            for item in items.values()
            if item.get("kind", "game") == "game"
            and set(item.get("games", [])) <= set(games)
        )
        item_price = Decimal(_price(it["price"]))
        old = f'<span class="old">{single_value:.2f} €</span>' if pack and single_value > item_price else ""
        savings = (
            f'<span class="badge save">↘ Spare {(single_value - item_price):.2f} €</span>'
            if old else ""
        )
        category = "PACK" if pack else "EINZEL-GAME"
        category_class = "sd-shop-kind pack" if pack else "sd-shop-kind"
        icon = "🎁" if pack else next(
            (char for char in str(it.get("name", ""))[:4] if ord(char) > 255),
            "🎮",
        )
        title = html.escape(str(it.get("name") or iid))
        description = html.escape(str(it.get("desc") or ""))
        status = (
            '<span class="sd-shop-state">✓ Freigeschaltet</span>'
            if games and set(games) <= have else ""
        )
        st.markdown(
            f'<div class="sd-shop-card-top"><span class="{category_class}">{category}</span>{status}</div>'
            f'<div class="sd-shop-icon">{html.escape(icon)}</div>'
            f'<div class="ct">{title}</div><div class="cd">{description}</div>{chips}'
            f'<div class="sd-shop-price-row"><div class="price">{item_price:.2f} <span class="unit">EUR</span></div>{old}</div>'
            f'{savings}',
            unsafe_allow_html=True,
        )
        if games and set(games) <= have:
            st.caption("Dieses Angebot ist für deinen Kanal bereits freigeschaltet.")
        elif iid in cart:
            st.button(
                "✓ Im Warenkorb · entfernen",
                key=f"rm_c_{iid}",
                on_click=_rm,
                args=(iid,),
                use_container_width=True,
            )
        else:
            st.button(
                "Zum Warenkorb  →",
                key=f"add_{iid}",
                on_click=_add,
                args=(iid,),
                type="primary",
                use_container_width=True,
            )

def _order_box():
    key = "skip_order" if st.session_state.get("skip_order") else "order"
    code, price = st.session_state[key]
    with st.container(border=True):
        st.markdown(
            '<div class="sd-shop-eyebrow"><span class="sd-shop-dot"></span> CHECKOUT</div>'
            '<div class="ct">Bestellung abschließen</div>'
            '<div class="cd">Noch ein Schritt – dann sind deine Module bereit.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="sd-shop-checkout-step"><span class="sd-shop-checkout-num">1</span>'
            '<div><b>Tip-Seite öffnen</b><span>Öffne deine StreamElements-Tip-Seite und sende den angezeigten Betrag.</span></div></div>'
            '<div class="sd-shop-checkout-step"><span class="sd-shop-checkout-num">2</span>'
            '<div><b>Bestellcode eintragen</b><span>Füge den Code als Nachricht beim Tip exakt so ein.</span></div></div>'
            '<div class="sd-shop-checkout-step"><span class="sd-shop-checkout-num">3</span>'
            '<div><b>Zahlung bestätigen</b><span>Danach hier prüfen lassen und freischalten.</span></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sd-shop-total-label">Zu zahlen</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sd-shop-total">{html.escape(str(price))} €</div>', unsafe_allow_html=True)
        st.code(code, language=None)
        st.link_button(
            "Tip-Seite öffnen  ↗",
            st.secrets["streamelements"]["tip_url"],
            type="primary",
            use_container_width=True,
        )
        st.caption("Nach dem Tip hier auf „Zahlung prüfen“ klicken.")
        if st.button("Zahlung prüfen", type="primary", use_container_width=True):
            ok, msg = fulfill(code)
            if ok:
                if key == "order":
                    st.session_state["download_order_code"] = code
                st.session_state.pop(key)
                st.balloons()
                st.success(msg)
            else:
                st.warning(msg)
        if st.button("Bestellung abbrechen", use_container_width=True):
            cancel_order(code)
            st.session_state.pop(key)
            st.rerun()
def _cart_box(tid, name, items, have):
    ids, total, savings, _ = cart_view(st.session_state.get("cart", []), items, have)
    with st.container(border=True):
        st.markdown(
            f'<div class="sd-shop-cart-head"><div class="ct">Dein Warenkorb</div>'
            f'<span class="sd-shop-cart-count">{len(ids)}</span></div>',
            unsafe_allow_html=True,
        )
        if not ids:
            st.markdown(
                '<div class="sd-shop-empty"><strong>Noch ist hier Platz.</strong><br>'
                'Wähle ein einzelnes Game oder ein Pack aus. Deine Auswahl erscheint hier.</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="sd-shop-legal">🔒 Du bezahlst nur die Module, die du auswählst.</div>', unsafe_allow_html=True)
            return
        for item_id in ids:
            left, right = st.columns([5, 1])
            left.markdown(
                f'<div class="sd-shop-cart-line"><b>{html.escape(items[item_id]["name"])}</b><br>'
                f'<span class="sd-shop-total-label">{_price(items[item_id]["price"])} €</span></div>',
                unsafe_allow_html=True,
            )
            right.button("✕", key=f"x_{item_id}", on_click=_rm, args=(item_id,), help="Aus dem Warenkorb entfernen")
        st.divider()
        coupon_code = st.session_state.get("coupon")
        valid_coupon, coupon, _message = validate_coupon(coupon_code) if coupon_code else (False, None, "")
        if coupon_code and not valid_coupon:
            st.session_state.pop("coupon", None)
        if valid_coupon:
            col_text, col_remove = st.columns([4, 1])
            col_text.markdown(
                '<div class="sd-shop-cart-line">🎟️ <b>'
                + html.escape(str(coupon["code"]))
                + "</b><br><span class='sd-shop-total-label'>"
                + (f'Guthaben {float(coupon.get("balance") or 0):.2f} €' if coupon.get("type") == "amount"
                   else f'Rabatt {coupon.get("percent")} %')
                + "</span></div>",
                unsafe_allow_html=True,
            )
            col_remove.button("✕", key="x_coupon", on_click=lambda: st.session_state.pop("coupon", None), help="Gutschein entfernen")
        else:
            col_code, col_apply = st.columns([3, 1.5])
            code_input = col_code.text_input(
                "Gutschein- oder Partner-Code",
                key="coupon_in",
                placeholder="Code eingeben",
                label_visibility="collapsed",
            )
            if col_apply.button("Einlösen", use_container_width=True):
                good, _coupon, message = validate_coupon(code_input)
                if good:
                    st.session_state["coupon"] = code_input.strip().upper()
                    st.rerun()
                else:
                    st.error(message)
        final, discount = apply_coupon(total, coupon if valid_coupon else None)
        st.markdown('<div class="sd-shop-total-label">Gesamtsumme</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sd-shop-total">{final:.2f} €</div>'
            + (f'<span class="old">{total:.2f} €</span>' if discount > 0 else "")
            + (f'<div style="margin-top:.35rem"><span class="badge save">Du sparst {savings + discount:.2f} €</span></div>'
               if savings + discount > 0 else ""),
            unsafe_allow_html=True,
        )
        agree = st.checkbox(
            "Ich stimme der sofortigen Freischaltung zu und bestätige die Hinweise zum Widerrufsrecht."
        )
        if st.button(
            "🎁 Kostenlos freischalten" if final == 0 else "Sichere Bestellung erstellen",
            type="primary",
            disabled=not agree,
            use_container_width=True,
        ):
            try:
                order_code, order_price = create_cart_order(
                    tid, name, ids, items, coupon_code if valid_coupon else "",
                    st.session_state.get("gift_data"),
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["cart"] = []
                if Decimal(order_price) == 0:
                    st.session_state["flash"] = fulfill(order_code, manual=True)[1]
                    st.session_state["download_order_code"] = order_code
                else:
                    st.session_state["order"] = (order_code, order_price)
                st.rerun()
def render_shop(games):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="sd-shop-hero">'
        '<div class="sd-shop-eyebrow"><span class="sd-shop-dot"></span> STREAMDEX OS · MODUL-STORE</div>'
        '<h1>Mach deinen Stream <span>interaktiver.</span></h1>'
        '<p>Stelle dir deinen StreamDex zusammen: einzelne Chat-Games für deinen Kanal oder günstige Packs für das komplette Community-Erlebnis. Einmal auswählen, bequem per Tip bezahlen und direkt in der App nutzen.</p>'
        '<div class="sd-shop-hero-foot"><span>🎮 Einzelmodule</span><span>🎁 Bundle-Angebote</span><span>⚡ Freischaltung in ca. 1 Minute</span><span>🔐 Sichere Bestellprüfung</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
        st.balloons()
    if not db.reference("shop/items").get():
        db.reference("shop/items").set(default_items(games))
    cfg = shop_settings()
    if cfg.get("banner"):
        st.markdown(f'<div class="banner">📣 {html.escape(str(cfg["banner"]))}</div>', unsafe_allow_html=True)
    if cfg.get("open", True) is False:
        st.markdown(
            '<div class="sd-shop-empty"><strong>Shop gerade pausiert.</strong><br>'
            'Der Verkauf ist aktuell geschlossen. Bereits freigeschaltete Games bleiben erhalten. Schau später wieder vorbei.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="sd-shop-section-title">01 · Dein Twitch-Kanal</div>', unsafe_allow_html=True)
    st.markdown('<div class="sd-shop-section-sub">Damit deine Käufe beim richtigen Kanal landen, wähle zuerst dein registriertes Konto aus.</div>', unsafe_allow_html=True)
    with st.container(border=True):
        account_col, helper_col = st.columns([1.1, 1], gap="large", vertical_alignment="center")
        with account_col:
            name = st.text_input(
                "Twitch-Name",
                value=str(st.query_params.get("u", "")),
                placeholder="z. B. mein_twitchkanal",
                help="Verwende den Twitch-Namen, mit dem du StreamDex bereits einmal gestartet hast.",
            )
        with helper_col:
            st.markdown(
                '<div class="sd-shop-account-copy"><span class="sd-shop-account-tag">● KANAL-ZUORDNUNG</span>'
                '<p>Dein Kauf wird deinem Streamer-Konto zugeordnet. Du musst dich nicht mit deinem Twitch-Passwort im Shop anmelden.</p>'
                '<p>Dein Kanal muss StreamDex mindestens einmal gestartet haben, damit er hier gefunden wird.</p></div>',
                unsafe_allow_html=True,
            )
    if not name.strip():
        st.markdown(
            '<div class="sd-shop-empty"><strong>Starte mit deinem Twitch-Namen.</strong><br>'
            'Sobald dein registrierter Kanal erkannt wurde, kannst du Games auswählen und zum Warenkorb hinzufügen.</div>',
            unsafe_allow_html=True,
        )
        return
    tid, profile = find_streamer(name)
    if not tid:
        st.error("Kanal nicht gefunden. Starte StreamDex einmal mit diesem Twitch-Account und versuche es danach erneut.")
        return
    if st.session_state.get("cart_tid") != tid:
        st.session_state.update(cart=[], cart_tid=tid)
        st.session_state.pop("order", None)
        st.session_state.pop("download_order_code", None)
        st.session_state.pop("coupon", None)
    have, items = owned_games(tid), load_items()
    if not items:
        st.info("Aktuell gibt es keine aktiven Angebote.")
        return
    st.markdown(
        '<div class="sd-shop-account"><div class="sd-shop-account-tag">✓ KANAL ERKANNT</div>'
        f'<div class="ct">{html.escape(str(profile.get("twitch_username") or name))}</div>'
        f'<div class="sd-shop-account-copy">StreamDex-Version: {html.escape(str(profile.get("app_version", "?")))} · '
        f'{len(have)} Game(s) bereits freigeschaltet</div></div>',
        unsafe_allow_html=True,
    )

    gift = st.toggle(
        "🎁 Als Geschenk für diesen Kanal kaufen",
        value=str(st.query_params.get("gift", "")) == "1",
        help="Die gekauften Games werden für den oben ausgewählten Twitch-Kanal freigeschaltet.",
    )
    st.session_state["gift_data"] = None
    if gift:
        with st.container(border=True):
            st.markdown('<div class="ct">Eine kleine Nachricht mitschicken</div>', unsafe_allow_html=True)
            gift_from_col, gift_msg_col = st.columns(2)
            gift_from = gift_from_col.text_input("Dein Name (optional)", max_chars=40, placeholder="Dein Twitch-Name")
            gift_message = gift_msg_col.text_input("Grußnachricht (optional)", max_chars=100, placeholder="Viel Spaß mit den Games!")
            st.session_state["gift_data"] = {"from": gift_from.strip(), "msg": gift_message.strip()}
            st.caption("Der Empfänger bekommt die Freischaltung automatisch nach erfolgreicher Zahlung.")

    st.markdown('<div class="sd-shop-section-title">02 · Module entdecken</div>', unsafe_allow_html=True)
    st.markdown('<div class="sd-shop-section-sub">Einzelne Games nach Bedarf oder mehrere Module im Pack zum Vorteilspreis.</div>', unsafe_allow_html=True)
    search_col, hint_col = st.columns([1.2, 1], vertical_alignment="center")
    search_term = search_col.text_input(
        "Games suchen",
        placeholder="Name oder Funktion …",
        key="shop_search_term",
    ).strip().lower()
    hint_col.markdown(
        '<div class="sd-shop-account-copy">Tipp: Bereits freigeschaltete Module sind markiert und lassen sich nicht versehentlich erneut kaufen.</div>',
        unsafe_allow_html=True,
    )
    cart = st.session_state.get("cart", [])
    left, right = st.columns([2.15, 1], gap="large")
    with left:
        packs_tab, games_tab = st.tabs(["🎁 Packs & Bundles", "🎮 Einzelne Games"])
        for tab, kind, columns_count in ((packs_tab, "pack", 2), (games_tab, "game", 2)):
            with tab:
                catalog = [
                    (item_id, item) for item_id, item in items.items()
                    if item.get("kind", "game") == kind
                    and (
                        not search_term
                        or search_term in item_id.lower()
                        or search_term in str(item.get("name", "")).lower()
                        or search_term in str(item.get("desc", "")).lower()
                    )
                ]
                st.markdown(
                    f'<div class="sd-shop-filter-note">{len(catalog)} Angebot(e) · '
                    f'{"Bundle-Rabatte" if kind == "pack" else "Einzeln freischaltbare Module"}</div>',
                    unsafe_allow_html=True,
                )
                if not catalog:
                    st.markdown(
                        '<div class="sd-shop-empty">Keine passenden Angebote gefunden. Passe deine Suche an.</div>',
                        unsafe_allow_html=True,
                    )
                for row_start in range(0, len(catalog), columns_count):
                    cols = st.columns(columns_count, gap="medium")
                    for col, (item_id, item) in zip(cols, catalog[row_start:row_start + columns_count]):
                        with col:
                            _card(item_id, item, items, have, cart)
    with right:
        if st.session_state.get("order"):
            _order_box()
        else:
            _cart_box(tid, profile.get("twitch_username"), items, have)
    _render_order_downloads(tid, load_items(active_only=False))
    with st.expander("Rechtliches & Hilfe"):
        settings = st.secrets.get("shop", {})
        st.markdown(
            f"[Impressum]({settings.get('impressum_url', '#')}) · "
            f"[AGB]({settings.get('agb_url', '#')}) · "
            f"[Widerruf]({settings.get('widerruf_url', '#')})"
        )
        st.caption("Fragen zur Freischaltung? Prüfe zuerst den Bestellcode und den Status der Zahlung.")


SKIP_PRICE = "2.00"


def render_tour_skip():
    """Öffentliche Seite /?skip=1&u=<twitchname>: 2 € Spende, um den Rundgang in der App zu überspringen."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero"><h1>⏭ Rundgang überspringen</h1><p>Einmalig 2 € Spende. Danach kannst du jeden Rundgang in der App überspringen.</p>'
                '<div class="steps"><span>1 · Twitch-Name eingeben</span><span>2 · Code erzeugen</span><span>3 · Per Tip bezahlen</span><span>4 · In der App prüfen</span></div></div>',
                unsafe_allow_html=True)
    name = st.text_input("Dein Twitch-Name", value=str(st.query_params.get("u", "")), placeholder="z.B. meinkanal")
    if not name.strip():
        st.info("Gib deinen Twitch-Namen ein. Du musst die Streamdex-App mindestens einmal gestartet haben.")
        return
    tid, p = find_streamer(name)
    if not tid:
        st.error("Kein Konto mit diesem Namen gefunden. Starte die Streamdex-App einmal mit deinem Twitch-Account.")
        return
    if st.session_state.get("skip_tid") != tid:
        st.session_state.pop("skip_order", None)
        st.session_state["skip_tid"] = tid
    if db.reference(f"tour_skip/{tid}").get():
        st.success(f"✅ Für **{p.get('twitch_username')}** ist das Überspringen schon freigeschaltet. Klicke in der App auf „Ich habe bezahlt – prüfen“.")
        return
    if not st.session_state.get("skip_order"):
        st.caption(f"Konto: **{p.get('twitch_username')}**")
        if st.button(f"🧾 Bestellcode für {SKIP_PRICE} € erzeugen", type="primary"):
            code = "SDX-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
            db.reference(f"shop/orders/{code}").set({
                "tid": tid, "name": p.get("twitch_username"), "item": "tourskip", "item_name": "Rundgang überspringen",
                "items": [], "games": [], "price": SKIP_PRICE, "gross": SKIP_PRICE, "status": "pending", "ts": {".sv": "timestamp"}})
            st.session_state["skip_order"] = (code, SKIP_PRICE)
            st.rerun()
    else:
        _order_box()
    with st.expander("Rechtliches"):
        sec = st.secrets.get("shop", {})
        st.markdown(f"[Impressum]({sec.get('impressum_url', '#')}) · [AGB]({sec.get('agb_url', '#')}) · [Widerruf]({sec.get('widerruf_url', '#')})")


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
    game_items = [(k, v) for k, v in items.items() if v.get("kind", "game") == "game"]
    pack_items = [(k, v) for k, v in items.items() if v.get("kind") == "pack"]
    active_count = sum(1 for _, item in items.items() if item.get("active", True))
    links_count = sum(1 for _, item in game_items if _safe_download_url(item.get("download_url")))
    m1, m2, m3 = st.columns(3)
    m1.metric("Artikel gesamt", len(items))
    m2.metric("Im Shop aktiv", active_count)
    m3.metric("Download-Links", f"{links_count}/{len(game_items)}")
    st.caption("Jedes Game hat eine eigene Karte. Preis, Sichtbarkeit und Download-Link bearbeitest du direkt dort und speicherst nur diesen Artikel.")
    st.markdown("""
    <style>
    .st-key-shop_admin_card_slot [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_megaslot [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_steal [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_raffel [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_gambel [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_hilo [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_raffle [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_fishing [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_mining [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_farming [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_race [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_arena [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_pack_casino [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_pack_abenteuer [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_pack_action [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-shop_admin_card_pack_komplett [data-testid="stVerticalBlockBorderWrapper"] {
      border: 1px solid rgba(139,92,246,.28) !important;
      border-radius: 16px !important;
      box-shadow: 0 8px 24px rgba(3,7,18,.18), inset 0 1px 0 rgba(255,255,255,.025);
    }
    .shop-admin-pill { display:inline-block; border-radius:999px; padding:3px 9px; font-size:.72rem;
      font-weight:800; letter-spacing:.02em; background:rgba(139,92,246,.14); border:1px solid rgba(167,139,250,.25); color:#c4b5fd; }
    .shop-admin-ready { color:#86efac; background:rgba(34,197,94,.10); border-color:rgba(34,197,94,.24); }
    .shop-admin-missing { color:#fbbf24; background:rgba(245,158,11,.10); border-color:rgba(245,158,11,.24); }
    </style>
    """, unsafe_allow_html=True)
    if not items:
        st.info("Noch kein Katalog. Er wird beim ersten Shop-Aufruf angelegt oder unten über „Standard-Katalog“.")
    else:
        filter_col, search_col = st.columns([1, 2], vertical_alignment="bottom")
        item_filter = filter_col.selectbox(
            "Produkttyp",
            ["Alle Artikel", "🎮 Einzel-Games", "🎁 Packs"],
            key="shop_admin_item_filter",
        )
        search = search_col.text_input(
            "Artikel suchen",
            placeholder="Name oder Artikel-ID eingeben …",
            key="shop_admin_item_search",
        ).strip().lower()
        if item_filter == "🎮 Einzel-Games":
            visible_items = game_items
        elif item_filter == "🎁 Packs":
            visible_items = pack_items
        else:
            visible_items = list(items.items())
        if search:
            visible_items = [
                (item_id, item) for item_id, item in visible_items
                if search in item_id.lower()
                or search in str(item.get("name", "")).lower()
                or search in str(item.get("desc", "")).lower()
            ]
        if not visible_items:
            st.info("Keine Artikel passen zu deiner Suche.")
        else:
            for row_start in range(0, len(visible_items), 2):
                cols = st.columns(2, gap="medium")
                for col, (item_id, item) in zip(cols, visible_items[row_start:row_start + 2]):
                    with col:
                        with st.container(border=True, key=f"shop_admin_card_{item_id}"):
                            label = str(item.get("name", item_id))
                            kind = item.get("kind", "game")
                            kind_label = "🎁 PACK" if kind == "pack" else "🎮 EINZEL-GAME"
                            link_ready = bool(_safe_download_url(item.get("download_url")))
                            state_label = (
                                "Link hinterlegt" if link_ready else "Download-Link fehlt"
                            ) if kind == "game" else "Downloads der enthaltenen Games"
                            state_class = "shop-admin-ready" if link_ready else "shop-admin-missing"
                            if kind == "pack":
                                state_class = "shop-admin-pill"
                            st.markdown(
                                f"<div style='display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap'>"
                                f"<span class='shop-admin-pill'>{html.escape(kind_label)}</span>"
                                f"<span class='shop-admin-pill {state_class}'>{html.escape(state_label)}</span></div>"
                                f"<h3 style='margin:.65rem 0 .15rem;font-size:1.05rem'>{html.escape(label)}</h3>",
                                unsafe_allow_html=True,
                            )
                            description = str(item.get("desc") or "").strip()
                            if description:
                                st.caption(description)
                            with st.form(f"shop_admin_edit_{item_id}"):
                                price_col, active_col = st.columns([1, 1])
                                price = price_col.number_input(
                                    "Preis (€)",
                                    min_value=0.5,
                                    max_value=500.0,
                                    step=0.5,
                                    value=float(item.get("price", 4.99)),
                                    format="%.2f",
                                    key=f"shop_admin_price_{item_id}",
                                )
                                active = active_col.toggle(
                                    "Im Shop sichtbar",
                                    value=bool(item.get("active", True)),
                                    key=f"shop_admin_active_{item_id}",
                                )
                                if kind == "game":
                                    download_url = st.text_input(
                                        "Download-Link (HTTPS)",
                                        value=str(item.get("download_url") or ""),
                                        placeholder="https://…/game.zip",
                                        help="Direkter Link zur ZIP- oder EXE-Datei. Käufer sehen ihn nach erfolgreicher Zahlung.",
                                        key=f"shop_admin_download_{item_id}",
                                    ).strip()
                                else:
                                    download_url = ""
                                    st.caption("Ein Pack verwendet die Download-Links seiner einzelnen Games.")
                                saved = st.form_submit_button(
                                    "Änderungen speichern",
                                    type="primary",
                                    use_container_width=True,
                                )
                            if saved:
                                if not 0.5 <= float(price) <= 500:
                                    st.error("Der Preis muss zwischen 0,50 € und 500 € liegen.")
                                elif kind == "game" and download_url and not _safe_download_url(download_url):
                                    st.error("Bitte einen gültigen HTTPS-Link ohne Zugangsdaten eintragen.")
                                else:
                                    patch = {
                                        "price": float(price),
                                        "active": bool(active),
                                    }
                                    if kind == "game":
                                        patch["download_url"] = _safe_download_url(download_url)
                                    db.reference(f"shop/items/{item_id}").update(patch)
                                    st.toast(f"{label} gespeichert.", icon="✅")
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
            dl_url = st.text_input("Direkter Download-Link (HTTPS; nur Einzel-Games)", value=cur.get("download_url", ""), disabled=kd == "pack", help="Link zur ZIP- oder EXE-Datei dieses Games. Wird erst nach bezahlter Bestellung angezeigt.")
            if st.form_submit_button("💾 Speichern"):
                key = (iid if pick == "➕ Neu" else pick).strip().lower()
                if not key.replace("_", "").isalnum() or not nm.strip() or not gm:
                    st.error("ID, Name und mindestens ein Game sind Pflicht.")
                elif kd == "game" and len(gm) != 1:
                    st.error("Ein Einzel-Game-Artikel muss genau ein Game freischalten. Nutze für mehrere Games den Typ „pack“.")
                elif dl_url.strip() and kd == "game" and not _safe_download_url(dl_url):
                    st.error("Der Download-Link muss eine gültige HTTPS-Adresse ohne Zugangsdaten enthalten.")
                else:
                    db.reference(f"shop/items/{key}").set({"kind": kd, "name": nm.strip(), "desc": ds.strip(), "price": pr, "games": gm,
                                                          "active": act, "sort": cur.get("sort", 50 if kd == "game" else 150),
                                                          "download_url": _safe_download_url(dl_url) if kd == "game" else ""})
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
    st.dataframe(df[["ts", "name", "item_name", "price", "status", "order_id"] + [c for c in ("gift_from", "gift_msg") if c in df]].sort_values("ts", ascending=False), hide_index=True, use_container_width=True)
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
                release_credit(o)
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
    st.caption("**Prozent-Code**: X % Rabatt auf den Warenkorb (ideal für Partner). **Wert-Gutschein**: festes Guthaben, z. B. 19,99 €. "
               "Deckt er den ganzen Warenkorb, wird ohne Tip direkt freigeschaltet. Restguthaben bleibt für den nächsten Kauf erhalten.")
    cps = {k: v for k, v in (db.reference("shop/coupons").get() or {}).items() if isinstance(v, dict)}
    if cps:
        def wert(v):
            return f"{float(v.get('amount') or 0):.2f} € (Rest {float(v.get('balance') or 0):.2f} €)" if v.get("type") == "amount" else f"{v.get('percent')} %"
        cdf = pd.DataFrame([{"Code": k, "Typ": "Wert" if v.get("type") == "amount" else "Prozent", "Wert": wert(v), "Partner/Notiz": v.get("partner", ""),
                             "Benutzt": int(v.get("uses") or 0), "Limit": int(v.get("max_uses") or 0) or "∞", "Läuft ab": v.get("expires") or "–",
                             "Umsatz €": round(float(v.get("revenue") or 0), 2), "Aktiv": v.get("active", True)} for k, v in cps.items()])
        st.dataframe(cdf, hide_index=True, use_container_width=True)
        part = cdf[cdf["Partner/Notiz"] != ""].groupby("Partner/Notiz")[["Benutzt", "Umsatz €"]].sum()
        if not part.empty:
            st.markdown("**Partner-Übersicht**")
            st.dataframe(part, use_container_width=True)
    pick = st.selectbox("Code bearbeiten", ["➕ Neuer Code"] + list(cps))
    new, cur = pick.startswith("➕"), cps.get(pick, {})
    amt_mode = st.radio("Typ", ["Prozent-Rabatt", "Wert-Gutschein (€)"], index=1 if cur.get("type") == "amount" else 0,
                        horizontal=True, key=f"ctype_{pick}") != "Prozent-Rabatt"
    with st.form("coupon"):
        code = st.text_input("Code (A-Z, 0-9, - _). Leer = automatisch", value="" if new else pick, disabled=not new)
        partner = st.text_input("Partner / Notiz (optional)", value=cur.get("partner", ""))
        if amt_mode:
            val = st.number_input("Wert in €", 0.5, 1000.0, float(cur.get("amount") or 19.99), 0.5)
            bal = st.number_input("Restguthaben in €", 0.0, 1000.0, float(cur.get("balance", val) if not new else val), 0.5,
                                  help="Bei neuen Gutscheinen = Wert. Bei bestehenden: aktueller Rest.")
        else:
            val = st.number_input("Rabatt in %", 1, 90, int(cur.get("percent") or 10))
        mx = st.number_input("Max. Benutzungen (0 = unbegrenzt)", 0, 100000, int(cur.get("max_uses") or 0))
        exp = st.text_input("Läuft ab am (JJJJ-MM-TT, leer = nie)", value=cur.get("expires", ""))
        act = st.checkbox("Aktiv", value=cur.get("active", True))
        if st.form_submit_button("💾 Speichern"):
            key = (code if new else pick).strip().upper()
            if new and not key:
                base = "".join(ch for ch in partner.upper() if ch.isalnum())[:8]
                key = f"{base or ('GUT' if amt_mode else 'SDX')}{secrets.token_hex(2).upper()}" if amt_mode else f"{base or 'SDX'}{int(val)}"
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
                d = {"type": "amount" if amt_mode else "percent", "partner": partner.strip(), "max_uses": int(mx), "expires": exp.strip(),
                     "active": act, "uses": int(cur.get("uses") or 0), "revenue": float(cur.get("revenue") or 0)}
                d.update({"amount": float(val), "balance": float(bal)} if amt_mode else {"percent": int(val)})
                db.reference(f"shop/coupons/{key}").update(d)
                st.success(f"Gespeichert: {key}")
                st.rerun()
    if not new and st.button("🗑️ Code löschen"):
        db.reference(f"shop/coupons/{pick}").delete()
        st.rerun()
