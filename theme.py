"""STREAMDEX OS Look: Cyber-Dark-Design (Lila/Cyan) für alle Seiten des Dashboards.

Nutzung:  apply_theme()  einmal pro Seite aufrufen,  header_html(...)  für die Kopfzeile.
Rein visuell, keine Funktion wird verändert.
"""
import html

import streamlit as st

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
:root{--bg:#030712;--panel:rgba(15,23,42,.85);--primary:#a855f7;--glow:rgba(168,85,247,.5);--accent:#06b6d4;
--muted:#64748b;--ok:#22c55e;--bad:#ef4444;--line:rgba(255,255,255,.08)}

html,body,[class*="css"],.stApp{font-family:'Plus Jakarta Sans',sans-serif}
.stApp{background-color:var(--bg);
 background-image:radial-gradient(circle at 10% 10%,rgba(168,85,247,.08) 0%,transparent 40%),
                  radial-gradient(circle at 90% 90%,rgba(6,182,212,.08) 0%,transparent 40%);
 background-attachment:fixed}
header[data-testid="stHeader"]{background:rgba(3,7,18,.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.block-container,[data-testid="stMainBlockContainer"]{padding-top:4.5rem!important;max-width:1400px}
h1,h2,h3{font-weight:800;letter-spacing:-.01em}
h2,h3{font-size:1.15rem!important}
[data-testid="stCaptionContainer"],.stCaption{color:var(--muted)}

/* ---------- Kopfzeile ---------- */
.sd-head{display:flex;align-items:center;justify-content:space-between;gap:12px;
 background:rgba(3,7,18,.9);border:1px solid var(--line);border-radius:14px;padding:10px 16px;
 backdrop-filter:blur(20px);box-shadow:0 8px 25px rgba(0,0,0,.4)}
.sd-logo{font-family:'JetBrains Mono',monospace;font-weight:700;font-size:1.05rem;display:flex;align-items:center;gap:8px;
 background:linear-gradient(135deg,#c084fc,#38bdf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sd-logo small{font-size:.6rem;color:var(--accent);-webkit-text-fill-color:var(--accent)}
.sd-sub{color:var(--muted);font-size:.75rem;font-family:'JetBrains Mono',monospace}
.sd-status{display:flex;align-items:center;gap:6px;font-size:.7rem;font-family:'JetBrains Mono',monospace;
 background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);padding:4px 10px;border-radius:20px;color:var(--ok);white-space:nowrap}
.sd-pulse{width:6px;height:6px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok);animation:sdp 1.5s infinite}
@keyframes sdp{0%{transform:scale(1);opacity:1}50%{transform:scale(1.5);opacity:.4}100%{transform:scale(1);opacity:1}}

/* ---------- Reiter als wischbare Pillen ---------- */
div[data-baseweb="tab-list"],div[role="tablist"]{gap:8px!important;overflow-x:auto;scrollbar-width:none;padding:4px 2px 10px;border:none!important}
div[data-baseweb="tab-list"]::-webkit-scrollbar,div[role="tablist"]::-webkit-scrollbar{display:none}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none!important;background:transparent!important;height:0!important}
button[data-baseweb="tab"],button[role="tab"]{background:rgba(30,41,59,.6)!important;border:1px solid var(--line)!important;border-radius:8px!important;
 padding:8px 14px!important;height:auto!important;white-space:nowrap;transition:all .2s;color:var(--muted)!important}
button[role="tab"] p,button[role="tab"] span,button[role="tab"] div{font-size:.82rem;font-weight:600;color:inherit!important}
button[role="tab"][aria-selected="true"]{background:var(--primary)!important;border-color:var(--primary)!important;box-shadow:0 0 12px var(--glow);color:#fff!important}
button[role="tab"]:hover{border-color:var(--primary)!important}
/* verschachtelte Reiter (Beta) dezenter */
div[role="tabpanel"] div[role="tablist"] button[role="tab"][aria-selected="true"]{background:rgba(168,85,247,.25)!important;box-shadow:none}

/* ---------- Karten ---------- */
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--panel);border:1px solid var(--line)!important;
 border-radius:14px;backdrop-filter:blur(20px);box-shadow:0 8px 25px rgba(0,0,0,.4)}
div[data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;
 box-shadow:0 8px 25px rgba(0,0,0,.3)}
div[data-testid="stMetricLabel"] p{font-family:'JetBrains Mono',monospace;font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}
div[data-testid="stMetricValue"]{font-weight:800}
details[data-testid="stExpander"],div[data-testid="stExpander"] details{background:var(--panel);border:1px solid var(--line);border-radius:12px}
div[data-testid="stExpander"] summary:hover{color:var(--accent)}
div[data-testid="stAlert"]{border-radius:12px;border:1px solid var(--line)}
div[data-testid="stDataFrame"],div[data-testid="stDataEditor"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}

/* ---------- Eingaben & Buttons ---------- */
.stTextInput input,.stTextArea textarea,.stSelectbox div[data-baseweb="select"]>div,.stNumberInput input,
div[data-testid="stChatInput"] textarea{background:rgba(3,7,18,.8)!important;border:1px solid rgba(255,255,255,.1)!important;
 border-radius:8px!important;color:#fff}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:var(--primary)!important;box-shadow:0 0 0 1px var(--primary)!important}
div[data-testid="stChatInput"]{background:rgba(3,7,18,.8);border:1px solid var(--line);border-radius:12px}
.stButton>button,.stLinkButton>a,.stFormSubmitButton>button{border-radius:8px;font-weight:700;border:1px solid var(--line);
 background:rgba(30,41,59,.7);color:#f8fafc;transition:all .2s}
.stButton>button:hover,.stFormSubmitButton>button:hover{border-color:var(--primary);color:#fff;box-shadow:0 0 10px var(--glow)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"],.stLinkButton>a[kind="primary"]{
 background:var(--primary);border-color:var(--primary);color:#fff;box-shadow:0 0 12px var(--glow)}
.stButton>button:disabled{opacity:.4;box-shadow:none}

/* ---------- Chat: Streamer links dunkel, Support rechts lila ---------- */
div[data-testid="stChatMessage"]{background:rgba(30,41,59,.8);border:1px solid rgba(255,255,255,.05);border-radius:10px;
 padding:10px 14px;max-width:88%}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]){
 flex-direction:row-reverse;margin-left:auto;background:linear-gradient(135deg,#7c3aed,#9333ea);border:none;color:#fff}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stCaptionContainer"]{color:#e9d5ff}
[data-testid="stChatMessageAvatarUser"],[data-testid="stChatMessageAvatarAssistant"]{background:rgba(255,255,255,.1)}

/* ---------- Streamer-Liste (linke Spalte) ---------- */
.stButton>button[kind="secondary"] p{font-size:.82rem}

/* ---------- Mobil ---------- */
@media (max-width:640px){
 .block-container,[data-testid="stMainBlockContainer"]{padding:4rem .7rem 5rem!important}
 .sd-head{padding:8px 10px}.sd-sub{display:none}
 button[data-baseweb="tab"]{padding:7px 11px}
}
</style>"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def header_html(subtitle="", status="CORE SYNCED"):
    sub = f'<div class="sd-sub">{html.escape(subtitle)}</div>' if subtitle else ""
    return (f'<div class="sd-head"><div><div class="sd-logo">⚡ STREAMDEX <small>OS</small></div>{sub}</div>'
            f'<div class="sd-status"><span class="sd-pulse"></span>{html.escape(status)}</div></div>')


def render_header(subtitle="", status="CORE SYNCED"):
    st.markdown(header_html(subtitle, status), unsafe_allow_html=True)
