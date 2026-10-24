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

/* ---------- Gemeinsames StreamDex-OS-Layout für Dashboard, Admin und Support ---------- */
/* Diese Regeln bilden die gleiche visuelle Sprache ab wie die öffentliche Landingpage. */
.block-container,[data-testid="stMainBlockContainer"]{
  width:100%!important;max-width:none!important;
  padding-left:clamp(1rem,2.35vw,2.5rem)!important;
  padding-right:clamp(1rem,2.35vw,2.5rem)!important;
  padding-bottom:2.5rem!important;
}
div[data-testid="stAppViewContainer"]>.main{background:transparent}
[data-testid="stMainBlockContainer"]>div{max-width:none}
.stApp{
  background-color:#070a18;
  background-image:
    radial-gradient(ellipse at 6% 0%,rgba(139,92,246,.12) 0%,transparent 33%),
    radial-gradient(ellipse at 94% 40%,rgba(34,211,238,.065) 0%,transparent 34%),
    linear-gradient(135deg,#070a18 0%,#090e20 52%,#080d1c 100%);
  background-attachment:fixed;
}
header[data-testid="stHeader"]{
  background:rgba(7,10,24,.76);backdrop-filter:blur(16px);
  border-bottom:1px solid rgba(148,163,184,.14);
}
h1{font-size:clamp(1.65rem,2.6vw,2.3rem);line-height:1.13}
h2{font-size:clamp(1.1rem,1.8vw,1.4rem)!important}
h3{font-size:1.04rem!important}
[data-testid="stVerticalBlockBorderWrapper"]{
  overflow:hidden;
}
div[data-testid="stHorizontalBlock"]{gap:clamp(.6rem,1.3vw,1.1rem)}
[data-testid="stMarkdownContainer"]>p{line-height:1.65}
[data-testid="stCaptionContainer"]{font-size:.77rem}

/* Tabs werden zu klaren, responsiven Navigationskarten. Dashboard-Navigation
   hat bereits eine eigene, spezifischere Variante in streamer_dashboard.py. */
div[data-baseweb="tab-list"],div[role="tablist"]{
  display:grid!important;
  grid-template-columns:repeat(auto-fit,minmax(145px,1fr))!important;
  gap:10px!important;
  width:100%!important;
  align-items:stretch!important;
  overflow:visible!important;
  padding:5px 0 16px!important;
  border:0!important;
  scrollbar-width:none;
}
div[data-baseweb="tab-list"]::-webkit-scrollbar,div[role="tablist"]::-webkit-scrollbar{display:none}
button[data-baseweb="tab"],button[role="tab"]{
  display:flex!important;align-items:center!important;justify-content:center!important;
  width:100%!important;min-width:0!important;min-height:48px!important;height:100%!important;
  white-space:normal!important;text-align:center!important;
  padding:11px 12px!important;border-radius:11px!important;
  border:1px solid rgba(48,61,103,.78)!important;
  background:linear-gradient(145deg,rgba(13,19,40,.9),rgba(9,14,29,.95))!important;
  color:#aeb9d8!important;box-shadow:0 6px 18px rgba(0,0,0,.12)!important;
  transition:transform .16s ease,border-color .16s ease,background .16s ease!important;
}
button[data-baseweb="tab"] p,button[role="tab"] p,button[role="tab"] span,button[role="tab"] div{
  white-space:normal!important;text-align:center!important;color:inherit!important;
  font-size:.78rem!important;font-weight:750!important;line-height:1.35!important;
}
button[data-baseweb="tab"]:hover,button[role="tab"]:hover{
  transform:translateY(-1px)!important;border-color:rgba(167,139,250,.7)!important;
  color:#fff!important;background:linear-gradient(145deg,rgba(38,29,71,.96),rgba(11,23,43,.98))!important;
}
button[role="tab"][aria-selected="true"]{
  color:#fff!important;border-color:rgba(196,181,253,.7)!important;
  background:linear-gradient(110deg,rgba(124,58,237,.95),rgba(79,70,229,.92) 62%,rgba(8,127,156,.86))!important;
  box-shadow:0 8px 23px rgba(91,73,232,.19),inset 0 1px 0 rgba(255,255,255,.08)!important;
}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none!important}

/* Admin-Toolradio und Abmelde-/Aktionsbuttons angleichen. */
.st-key-os_nav div[role="radiogroup"]{gap:10px!important;align-items:stretch}
.st-key-os_nav label{
  border:1px solid rgba(48,61,103,.78)!important;
  background:linear-gradient(145deg,rgba(13,19,40,.9),rgba(9,14,29,.95))!important;
  border-radius:11px!important;min-height:42px;padding:10px 12px!important;
}
.st-key-os_nav label:has(input:checked){
  background:linear-gradient(110deg,rgba(124,58,237,.65),rgba(8,127,156,.35))!important;
  border-color:rgba(196,181,253,.7)!important;
}
.stButton>button,.stLinkButton>a,.stFormSubmitButton>button{
  min-height:38px;border-radius:10px!important;
}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"],.stLinkButton>a[kind="primary"]{
  background:linear-gradient(105deg,#8b5cf6,#635bdf 58%,#087f9c)!important;
}
.stButton>button:focus-visible,.stLinkButton>a:focus-visible{
  outline:2px solid #22d3ee!important;outline-offset:2px!important;
}

/* Support-Chats und Listen bekommen denselben Kartenrhythmus. */
div[data-testid="stChatMessage"]{
  max-width:100%;border-radius:13px;padding:12px 14px;
  box-shadow:0 6px 18px rgba(0,0,0,.1);
}
div[data-testid="stChatInput"]{
  border-radius:13px!important;
}
div[data-testid="stAlert"]{
  border-radius:12px!important;
}
div[data-testid="stDataFrame"],div[data-testid="stDataEditor"],[data-testid="stTable"]{
  border:1px solid rgba(148,163,184,.15)!important;border-radius:12px!important;overflow:hidden;
}
div[data-testid="stExpander"] details{
  border-radius:12px!important;overflow:hidden;
}
.stTextInput input,.stTextArea textarea,.stNumberInput input,.stDateInput input,.stTimeInput input{
  min-height:40px;
}
.stTextArea textarea{min-height:90px}
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,rgba(9,13,29,.99),rgba(7,10,24,.98))!important;
  border-right:1px solid rgba(148,163,184,.14);
}
section[data-testid="stSidebar"] button{
  border-radius:10px!important;
}
a{color:#b7a1ff}
a:hover{color:#67e8f9}
@media(max-width:900px){
  .block-container,[data-testid="stMainBlockContainer"]{
    padding-left:1.15rem!important;padding-right:1.15rem!important;
  }
  div[data-baseweb="tab-list"],div[role="tablist"]{
    grid-template-columns:repeat(auto-fit,minmax(125px,1fr))!important;gap:8px!important;
  }
}
@media(max-width:640px){
  .block-container,[data-testid="stMainBlockContainer"]{
    padding:1rem .7rem 3rem!important;
  }
  div[data-baseweb="tab-list"],div[role="tablist"]{
    grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important;
  }
  button[data-baseweb="tab"],button[role="tab"]{
    min-height:44px!important;padding:9px 8px!important;border-radius:9px!important;
  }
}


/* Gemeinsame Navigation für alle angemeldeten StreamDex-OS-Bereiche */
.sd-os-nav-wrap{margin:0 0 18px}
.sd-os-nav-label{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 2px 8px;
 color:#93a1c4;font:700 .62rem 'JetBrains Mono',monospace;letter-spacing:.12em;text-transform:uppercase}
.sd-os-nav-label strong{color:#bda5ff;font-weight:700}
.sd-os-nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px}
.sd-os-nav a{display:flex;align-items:center;justify-content:center;gap:7px;min-height:42px;padding:9px 10px;
 border:1px solid rgba(48,61,103,.78);border-radius:11px;background:linear-gradient(145deg,rgba(13,19,40,.9),rgba(9,14,29,.95));
 color:#b9c4e2;text-decoration:none;text-align:center;font-size:.76rem;font-weight:750;line-height:1.3;
 transition:background .16s,border-color .16s,transform .16s;overflow-wrap:anywhere}
.sd-os-nav a:hover{border-color:rgba(167,139,250,.72);background:linear-gradient(145deg,rgba(38,29,71,.96),rgba(11,23,43,.98));color:#fff;transform:translateY(-1px)}
.sd-os-nav a.is-active{color:#fff;border-color:rgba(196,181,253,.76);
 background:linear-gradient(110deg,rgba(124,58,237,.78),rgba(79,70,229,.7) 62%,rgba(8,127,156,.66));
 box-shadow:0 6px 18px rgba(91,73,232,.16)}
.sd-os-nav a:focus-visible{outline:2px solid #22d3ee;outline-offset:2px}
.sd-empty-state{display:flex;align-items:flex-start;gap:14px;padding:18px 19px;margin:8px 0 14px;
 border:1px dashed rgba(139,92,246,.42);border-radius:14px;
 background:linear-gradient(135deg,rgba(139,92,246,.075),rgba(34,211,238,.035))}
.sd-empty-state-icon{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border-radius:12px;
 background:rgba(139,92,246,.15);border:1px solid rgba(139,92,246,.28);font-size:1.25rem}
.sd-empty-state-copy{min-width:0}
.sd-empty-state-copy strong{display:block;color:#f1f5ff;font-size:.94rem;margin:1px 0 5px}
.sd-empty-state-copy p{color:#aab7d5;font-size:.8rem;line-height:1.65;margin:0}
@media(max-width:640px){
 .sd-os-nav{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
 .sd-os-nav a{min-height:44px;padding:9px 7px;font-size:.72rem;border-radius:9px}
 .sd-os-nav-label{font-size:.58rem}
 .sd-empty-state{gap:10px;padding:14px}
 .sd-empty-state-icon{flex-basis:36px;width:36px;height:36px;font-size:1.1rem}
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


def render_os_navigation(current="dashboard"):
    """Renders shared, responsive quick navigation for signed-in StreamDex OS pages."""
    items = (
        ("dashboard", "⌂ Übersicht", "/?dashboard=1"),
        ("radar", "◈ Insight", "/?radar=1"),
        ("planner", "▦ Planner", "/?planner=1"),
        ("clips", "▶ Clips", "/?clips=1"),
        ("feedback", "✦ Feedback", "/?feedback=1"),
        ("community", "♧ Community", "/?community=1"),
        ("profile", "♙ Profil", "/?profile=1"),
        ("ideas", "🧩 Tools", "/?ideas=1"),
        ("tour", "✦ Rundgang", "/?tour=1"),
    )
    links = []
    for key, label, url in items:
        active = ' class="is-active" aria-current="page"' if key == current else ""
        links.append(f'<a href="{html.escape(url, quote=True)}"{active}>{html.escape(label)}</a>')
    st.markdown(
        '<div class="sd-os-nav-wrap">'
        '<div class="sd-os-nav-label"><span>STREAMDEX OS</span><strong>Schnellzugriff</strong></div>'
        '<nav class="sd-os-nav" aria-label="StreamDex Schnellnavigation">'
        + "".join(links) + '</nav></div>',
        unsafe_allow_html=True,
    )


def render_empty_state(title, description, icon="✦"):
    """Consistent, accessible empty state with a clear next-step explanation."""
    st.markdown(
        '<div class="sd-empty-state" role="status">'
        f'<div class="sd-empty-state-icon" aria-hidden="true">{html.escape(str(icon))}</div>'
        '<div class="sd-empty-state-copy">'
        f'<strong>{html.escape(str(title))}</strong>'
        f'<p>{html.escape(str(description))}</p>'
        '</div></div>',
        unsafe_allow_html=True,
    )
