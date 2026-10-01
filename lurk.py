"""StreamDex Lurk: eigener Bereich im Streamdex OS (Reiter-Gerüst, Funktionen folgen)."""
import streamlit as st


def lurk_panel():
    t_over, t_chan = st.tabs(["📊 Übersicht", "📡 Kanäle"])
    with t_over:
        st.subheader("👁️ StreamDex Lurk")
        st.info("Dieser Bereich ist angelegt, es sind aber noch keine Funktionen angebunden.")
    with t_chan:
        st.caption("Hier kommen die Kanäle des Lurk-Tools hin.")
