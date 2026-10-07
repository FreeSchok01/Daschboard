"""Urlaubsmodus: Ist er an, antwortet der "StreamDex Bot" in der App automatisch im Support-Chat.

Firebase: support_status = {vacation: bool, until: "TT.MM.JJJJ" (optional), text: str (optional), updated, by}
Die App (ab Beta V3) liest den Knoten mit den normalen Streamer-Rechten und schreibt die Bot-Antwort selbst
in chats/{twitch_id}/messages (sender = "bot", name = "StreamDex Bot").
"""
import streamlit as st
from firebase_admin import db

SERVER_TS = {".sv": "timestamp"}


def vacation_panel(me):
    """Kleiner Schalter oben im Admin-Support-Tab."""
    cur = db.reference("support_status").get()
    cur = cur if isinstance(cur, dict) else {}
    on_now = cur.get("vacation") is True
    label = "🏖️ Urlaubsmodus · AN (StreamDex Bot antwortet)" if on_now else "🏖️ Urlaubsmodus · aus"
    with st.expander(label, expanded=on_now):
        st.caption("Wenn an, antwortet der StreamDex Bot nach jeder Support-Nachricht aus der App (ab Beta V3) "
                   "mit Hilfe zu den häufigsten Problemen und einem Urlaubshinweis. Die Nachrichten bleiben für dich ungelesen.")
        on = st.toggle("Urlaubsmodus an", value=on_now, key="vac_on")
        until = st.text_input("Zurück am (optional, z. B. 20.10.2026)", value=str(cur.get("until") or ""),
                              max_chars=20, key="vac_until")
        text = st.text_area("Zusatznachricht (optional, max. 300 Zeichen)", value=str(cur.get("text") or ""),
                            max_chars=300, height=80, key="vac_text")
        if st.button("💾 Speichern", key="vac_save"):
            db.reference("support_status").set({
                "vacation": bool(on), "until": until.strip(), "text": text.strip(),
                "updated": SERVER_TS, "by": me})
            st.success("Urlaubsmodus ist jetzt " + ("AN." if on else "aus."))
            st.rerun()
