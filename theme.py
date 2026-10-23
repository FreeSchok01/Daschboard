"""STREAMDEX OS Look: Cyber-Dark-Design (Lila/Cyan) für alle Seiten des Dashboards.

Nutzung: apply_theme() einmal pro Seite aufrufen, header_html(...) für die Kopfzeile.
Rein visuell, keine Funktion wird verändert.
"""
import html

import streamlit as st

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
:root{--bg:#070a18;--panel:rgba(13,19,38,.88);--primary:#8b5cf6;--glow:rgba(139,92,246,.36);--accent:#22d3ee;
--muted:#8e9bbd;--ok:#22c55e;--bad:#fb7185;--line:rgba(148,163,184,.16);--text:#eef2ff;
--sd-purple:#8b5cf6;--sd-cyan:#22d3ee;--sd-card:rgba(15,23,42,.72)}

html,body,[class*="css"],.stApp{font-family:'Plus Jakarta Sans',sans-serif}
.stApp{background-color:var(--bg);
 background-image:radial-gradient(ellipse at 6% 0%,rgba(139,92,246,.13) 0%,transparent 34%),
                  radial-gradient(ellipse at 95% 45%,rgba(34,211,238,.075) 0%,transparent 35%),
                  linear-gradient(135deg,#070a18 0%,#090e20 52%,#080d1c 100%);
 background-attachment:fixed;color:var(--text)}
header[data-testid="stHeader"]{background:rgba(7,10,24,.72);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}
[data-testid="stToolbar"]{right:1rem}
.block-container,[data-testid="stMainBlockContainer"]{padding-top:2.5rem!important;padding-bottom:3rem!important;max-width:1460px}
h1,h2,h3{font-weight:800;letter-spacing:-.025em;color:#f3f5ff}
h2,h3{font-size:1.15rem!important}
p,li{line-height:1.65}
[data-testid="stCaptionContainer"],.stCaption{color:var(--muted)}
hr{border-color:rgba(148,163,184,.15)!important}

/* ---------- Streamlit Seitenleiste ---------- */
section[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(9,13,29,.98),rgba(7,10,24,.98));border-right:1px solid var(--line)}
section[data-testid="stSidebar"]>div{padding-top:1.15rem}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3{letter-spacing:-.02em}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{font-size:.82rem;color:#a8b4d2}
section[data-testid="stSidebar"] button{border-radius:10px!important}

/* ---------- Kopfzeile ---------- */
.sd-head{display:flex;align-items:center;justify-content:space-between;gap:16px;
 background:linear-gradient(115deg,rgba(15,23,42,.94),rgba(12,18,37,.86));border:1px solid var(--line);
 border-radius:16px;padding:13px 18px;margin:0 0 18px;backdrop-filter:blur(20px);
 box-shadow:0 12px 34px rgba(0,0,0,.22),inset 0 1px 0 rgba(255,255,255,.035)}
.sd-logo{font-family:'JetBrains Mono',monospace;font-weight:800;font-size:1.05rem;display:flex;align-items:center;gap:8px;
 background:linear-gradient(105deg,#c084fc 0%,#a78bfa 45%,#67e8f9 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sd-logo small{font-size:.62rem;color:var(--accent);-webkit-text-fill-color:var(--accent);letter-spacing:1.3px}
.sd-sub{color:#8e9bbd;font-size:.75rem;font-family:'JetBrains Mono',monospace;margin-top:5px}
.sd-status{display:flex;align-items:center;gap:7px;font-size:.68rem;font-family:'JetBrains Mono',monospace;
 background:rgba(34,197,94,.075);border:1px solid rgba(34,197,94,.25);padding:6px 10px;border-radius:20px;color:#86efac;white-space:nowrap}
.sd-pulse{width:6px;height:6px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok);animation:sdp 1.5s infinite}
@keyframes sdp{0%{transform:scale(1);opacity:1}50%{transform:scale(1.5);opacity:.4}100%{transform:scale(1);opacity:1}}

/* ---------- Reiter / Navigation ---------- */
div[data-baseweb="tab-list"],div[role="tablist"]{gap:9px!important;overflow-x:auto;scrollbar-width:none;padding:5px 2px 12px;border:none!important}
div[data-baseweb="tab-list"]::-webkit-scrollbar,div[role="tablist"]::-webkit-scrollbar{display:none}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none!important;background:transparent!important;height:0!important}
button[data-baseweb="tab"],button[role="tab"]{background:rgba(20,28,49,.72)!important;border:1px solid rgba(148,163,184,.15)!important;
 border-radius:10px!important;padding:10px 14px!important;height:auto!important;white-space:nowrap;transition:all .18s ease;color:#9ba8c8!important}
button[role="tab"] p,button[role="tab"] span,button[role="tab"] div{font-size:.82rem;font-weight:700;color:inherit!important}
button[role="tab"][aria-selected="true"]{background:linear-gradient(105deg,#7c3aed,#5b49e8 60%,#087f9c)!important;
 border-color:rgba(196,181,253,.55)!important;box-shadow:0 6px 20px rgba(91,73,232,.22);color:#fff!important}
button[role="tab"]:hover{border-color:rgba(167,139,250,.65)!important;background:rgba(44,35,79,.86)!important}
div[role="tabpanel"] div[role="tablist"] button[role="tab"][aria-selected="true"]{background:rgba(139,92,246,.22)!important;box-shadow:none}

/* ---------- Tool-Leiste ---------- */
.st-key-os_nav div[role="radiogroup"]{gap:9px;flex-wrap:nowrap;overflow-x:auto;padding:3px 1px 8px}
.st-key-os_nav label{flex:1;justify-content:center;background:rgba(20,28,49,.72);border:1px solid var(--line);
 border-radius:12px;padding:11px 15px;cursor:pointer;transition:all .18s;margin:0;min-width:max-content}
.st-key-os_nav label>div:first-child{display:none}
.st-key-os_nav label p{font-weight:800;color:#9ba8c8;text-align:center;white-space:nowrap;font-size:.82rem}
.st-key-os_nav label:has(input:checked){background:linear-gradient(120deg,rgba(139,92,246,.38),rgba(34,211,238,.2));
 border-color:rgba(167,139,250,.7);box-shadow:0 0 18px rgba(139,92,246,.14)}
.st-key-os_nav label:has(input:checked) p{color:#fff}
.st-key-os_nav label:hover{border-color:rgba(167,139,250,.45)}

/* ---------- Karten / Container ---------- */
div[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(145deg,rgba(15,23,42,.86),rgba(11,17,34,.88));
 border:1px solid var(--line)!important;border-radius:15px;box-shadow:0 10px 28px rgba(0,0,0,.17),inset 0 1px 0 rgba(255,255,255,.025)}
div[data-testid="stMetric"]{background:linear-gradient(145deg,rgba(17,25,47,.92),rgba(11,17,34,.9));border:1px solid var(--line);
 border-radius:14px;padding:14px 15px;box-shadow:0 8px 22px rgba(0,0,0,.13)}
div[data-testid="stMetricLabel"] p{font-family:'JetBrains Mono',monospace;font-size:.69rem;text-transform:uppercase;letter-spacing:.45px;color:#8e9bbd}
div[data-testid="stMetricValue"]{font-weight:800;color:#f4f5ff}
div[data-testid="stMetricDelta"]{font-weight:700}
details[data-testid="stExpander"],div[data-testid="stExpander"] details{background:rgba(13,19,38,.78);border:1px solid var(--line);border-radius:12px}
div[data-testid="stExpander"] summary:hover{color:var(--accent)}
div[data-testid="stAlert"]{border-radius:12px;border:1px solid var(--line);background:rgba(15,23,42,.74)}
div[data-testid="stDataFrame"],div[data-testid="stDataEditor"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}
[data-testid="stTable"]{border-radius:10px;overflow:hidden}

/* ---------- Formulare / Buttons ---------- */
.stTextInput input,.stTextArea textarea,.stSelectbox div[data-baseweb="select"]>div,.stNumberInput input,
.stDateInput input,.stTimeInput input,div[data-testid="stChatInput"] textarea{
 background:rgba(7,11,24,.84)!important;border:1px solid rgba(148,163,184,.19)!important;border-radius:9px!important;color:#eef2ff!important}
.stTextInput input:focus,.stTextArea textarea:focus,.stNumberInput input:focus{border-color:var(--primary)!important;box-shadow:0 0 0 1px var(--primary)!important}
div[data-testid="stChatInput"]{background:rgba(7,11,24,.84);border:1px solid var(--line);border-radius:12px}
.stButton>button,.stLinkButton>a,.stFormSubmitButton>button{border-radius:9px;font-weight:750;border:1px solid rgba(148,163,184,.18);
 background:rgba(28,39,64,.85);color:#eef2ff;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}
.stButton>button:hover,.stLinkButton>a:hover,.stFormSubmitButton>button:hover{border-color:rgba(167,139,250,.7);color:#fff;box-shadow:0 5px 17px rgba(0,0,0,.18),0 0 14px rgba(139,92,246,.12);transform:translateY(-1px)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"],.stLinkButton>a[kind="primary"]{
 background:linear-gradient(105deg,#8b5cf6,#635bdf 58%,#087f9c);border-color:rgba(167,139,250,.75);color:#fff;box-shadow:0 7px 18px rgba(91,73,232,.2)}
.stButton>button:disabled{opacity:.42;box-shadow:none;transform:none}
button[kind="primary"],[data-testid="stFormSubmitButton"] button{font-weight:800}

/* ---------- Chat ---------- */
div[data-testid="stChatMessage"]{background:rgba(25,35,58,.74);border:1px solid rgba(148,163,184,.1);border-radius:12px;padding:11px 14px;max-width:91%}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]){flex-direction:row-reverse;margin-left:auto;
 background:linear-gradient(130deg,rgba(109,40,217,.95),rgba(91,33,182,.9));border:1px solid rgba(196,181,253,.18);color:#fff}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stCaptionContainer"]{color:#e9d5ff}
[data-testid="stChatMessageAvatarUser"],[data-testid="stChatMessageAvatarAssistant"]{background:rgba(255,255,255,.08);border-radius:9px}

/* ---------- Allgemeine Details ---------- */
.st-key-sd_profile_header [data-testid="stCaptionContainer"]{font-size:.76rem}
.stButton>button[kind="secondary"] p{font-size:.82rem}
a{color:#a5b4fc}
a:hover{color:#67e8f9}
::selection{background:rgba(139,92,246,.38);color:#fff}

/* ---------- Mobil ---------- */
@media(max-width:900px){
 .block-container,[data-testid="stMainBlockContainer"]{padding-top:1.5rem!important;padding-left:1.15rem!important;padding-right:1.15rem!important}
 .st-key-os_nav div[role="radiogroup"]{flex-wrap:wrap}
 .sd-head{padding:11px 13px}
}
@media(max-width:640px){
 .block-container,[data-testid="stMainBlockContainer"]{padding:1rem .7rem 4rem!important}
 .sd-head{padding:9px 10px;border-radius:12px;gap:8px}
 .sd-sub{display:none}
 .sd-logo{font-size:.92rem}
 .sd-status{font-size:.58rem;padding:5px 7px}
 button[data-baseweb="tab"]{padding:8px 11px!important}
 div[data-testid="stMetric"]{padding:11px}
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
