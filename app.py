"""AI Sales Assistant — enterprise Sales & CPQ deal assistant (Streamlit UI)."""

from __future__ import annotations

import html
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

from atlas.config import config
from atlas.deploy_readiness import (
    auth_required,
    configured_app_password,
    configured_app_username,
    credentials_match,
    friendly_pipeline_error,
    synthetic_corpus_disclaimer,
)
from atlas.embeddings import embedding_load_error, get_embedding_model
from atlas.ingest import discover_markdown_files
from atlas.pipeline import PipelineResult, answer_query
from atlas.store import collection_count, index_corpus
from atlas.ui_eval import list_candidate_runs, order_runs_for_display, run_authority

PRODUCT_NAME = "AI Sales Assistant"
PRODUCT_ROLE = "Enterprise Sales & CPQ Assistant"
PRODUCT_HERO = (
    "Research customers. Price products. Build deals. Navigate discount policy. Close with confidence — "
    "every answer is grounded in your company's policy documents for maximum accuracy and correctness."
)
PRODUCT_AUDIENCE = "For Sales · RevOps · Deal Desk · CPQ"

st.set_page_config(
    page_title=f"{PRODUCT_NAME} — Sales & CPQ",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

if "turns" not in st.session_state:
    st.session_state.turns: List[Dict[str, Any]] = []
if "last_result" not in st.session_state:
    st.session_state.last_result: Optional[Dict[str, Any]] = None
if "last_question" not in st.session_state:
    st.session_state.last_question: Optional[str] = None
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "ask"
if "nav_open" not in st.session_state:
    st.session_state.nav_open = {"ask": True, "evidence": False}
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "ui_mode" not in st.session_state:
    st.session_state.ui_mode = "Grounded"
if "ui_rerank" not in st.session_state:
    st.session_state.ui_rerank = bool(config.rerank.enabled)
if "ui_threshold" not in st.session_state:
    st.session_state.ui_threshold = float(config.retrieval.similarity_threshold)
if "draft_question" not in st.session_state:
    st.session_state.draft_question = ""

# Pipeline mode keys stay Grounded/Auto/General; UI shows sales-oriented labels.
MODE_OPTIONS = ["Grounded", "Auto", "General"]
MODE_LABELS = {
    "Grounded": "Use Sales Policy Documents (Strict)",
    "Auto": "Use Sales Policy Documents (Preferably)",
    "General": "General Knowledge",
}
MODE_OVERVIEW_HELP = (
    "Controls whether the assistant must answer from governed sales policy documents. "
    "Use Strict for pricing, discounts, and terms that must be auditable."
)
MODE_DETAIL = {
    "Grounded": (
        "Answers only from indexed sales policy documents. If evidence is weak or missing, "
        "the assistant refuses rather than guessing — required for accurate commercial numbers."
    ),
    "Auto": (
        "Uses sales policy documents when match strength is good; may fall back to general knowledge. "
        "Not recommended for exact list price, discount caps, or SLA figures."
    ),
    "General": (
        "Does not require document evidence. Fine for orientation questions; "
        "do not treat as approved commercial guidance."
    ),
}

ABSTENTION_KIND_LABELS = {
    "customer_specific": "Named-account / negotiated terms",
    "unsupported_topic": "Not in catalog / out of scope",
    "underspecified": "Needs a specific SKU or framework",
    "entity_miss": "Unknown product or policy id",
    "no_evidence": "No matching documents",
    "score_gate": "Match too weak to confirm",
}

SAMPLE_QUESTIONS = [
    {
        "id": "grounded",
        "type": "Pricing",
        "label": "Module 12 pricing",
        "question": "What is the annual base subscription for Module 12, and how many seats are included?",
    },
    {
        "id": "policy",
        "type": "Discount policy",
        "label": "Framework 10 discount",
        "question": "What is the maximum AE discount for Framework 10?",
    },
    {
        "id": "unsupported",
        "type": "Out of catalog",
        "label": "Unknown product",
        "question": "What is the price for Framework 99?",
    },
    {
        "id": "customer",
        "type": "Named account",
        "label": "Customer deal",
        "question": "What negotiated price did Acme receive?",
    },
    {
        "id": "ambiguous",
        "type": "Needs SKU",
        "label": "Ambiguous ask",
        "question": "What is the maximum AE discount?",
    },
    {
        "id": "module6_extra_seat_cost",
        "type": "Pricing",
        "label": "Module 6 seats add-on",
        "question": "What is the per-seat annual cost for additional users on Module 6 beyond the included seats?",
    },
    {
        "id": "framework10_approve_15pct",
        "type": "Discount policy",
        "label": "Framework 10 15% approval",
        "question": "Who can approve a 15% discount under Framework 10?",
    },
    {
        "id": "region10_monthly_uptime",
        "type": "SLA",
        "label": "Region 10 uptime",
        "question": "What monthly uptime guarantee applies to production workloads in Region 10?",
    },
    {
        "id": "module12_tcv_reduction",
        "type": "Commercial terms",
        "label": "Module 12 multi-year",
        "question": "What TCV reduction applies to a 36-month commitment on Module 12?",
    },
    {
        "id": "framework2_ae_discount",
        "type": "Discount policy",
        "label": "Framework 2 discount",
        "question": "What is the maximum AE discount for Framework 2?",
    },
]

REFINE_LABEL = "Prefer stronger document matches"
REFINE_HELP = (
    "Spend a little longer choosing which policy/SKU passages best match the question. "
    "Useful on close calls between similar frameworks; slightly slower."
)

# Nav labels are sales-oriented; routes/keys unchanged.
NAV_SECTIONS: List[Tuple[str, str, str, List[Tuple[str, str]]]] = [
    ("ask", "Ask", "ask", [("ask:settings", "Answer policy")]),
    (
        "evidence",
        "Evidence",
        "evidence",
        [("evidence:signals", "Match strength")],
    ),
    ("quality", "Quality", "quality", []),
    ("system", "Sales Policy", "system", []),
]

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@500;600&display=swap');
html, body, [class*="css"] { font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, sans-serif; }
.stApp { background: #f0f2f5; color: #1a1d26; }
section[data-testid="stSidebar"] { background: #0f172a; border-right: 1px solid #1e293b; }
section[data-testid="stSidebar"] .atl-brand,
section[data-testid="stSidebar"] .atl-brand-role,
section[data-testid="stSidebar"] .atl-brand-sub,
section[data-testid="stSidebar"] [data-testid="stMarkdown"] p,
section[data-testid="stSidebar"] label p { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] .atl-brand-role { color: #5eead4 !important; }
section[data-testid="stSidebar"] .stCaption { color: #94a3b8 !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] > button,
section[data-testid="stSidebar"] button[kind="secondary"],
section[data-testid="stSidebar"] button[data-testid="baseButton-secondary"] {
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  color: #e2e8f0 !important;
  text-align: left !important;
  justify-content: flex-start !important;
  font-weight: 600;
  padding: 0.35rem 0.25rem !important;
  box-shadow: none !important;
  border-radius: 4px !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
section[data-testid="stSidebar"] button[kind="secondary"]:hover,
section[data-testid="stSidebar"] button[data-testid="baseButton-secondary"]:hover {
  background: #1e293b !important;
  background-color: #1e293b !important;
  color: #f8fafc !important;
  border: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button > div,
section[data-testid="stSidebar"] div[data-testid="stButton"] > button p,
section[data-testid="stSidebar"] div[data-testid="stButton"] > button span {
  justify-content: flex-start !important;
  text-align: left !important;
  width: 100%;
}
section[data-testid="stSidebar"] [data-baseweb="select"] *,
section[data-testid="stSidebar"] [data-baseweb="select"] input { color: #0f172a !important; }
/* Streamlit sidebar collapse / expand controls — force visible in demos */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
button[data-testid="stBaseButton-headerNoPadding"],
button[kind="headerNoPadding"],
header[data-testid="stHeader"] button {
  visibility: visible !important;
  opacity: 1 !important;
  display: inline-flex !important;
  color: #334155 !important;
  z-index: 999 !important;
}
button[data-testid="stBaseButton-headerNoPadding"] {
  background-color: #e2e8f0 !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 4px !important;
  min-width: 2.1rem !important;
  min-height: 2.1rem !important;
}
.block-container {
  /* Must clear Streamlit’s top header — 1rem caused page titles to clip on every screen */
  padding-top: 5.5rem !important;
  padding-bottom: 3rem !important;
  max-width: 760px;
}
.atl-brand { font-family: "IBM Plex Serif", Georgia, serif; font-weight: 600; font-size: 1.4rem;
  color: #f8fafc; margin: 0 0 0.15rem 0; }
.atl-brand-role { font-size: 0.78rem; font-weight: 600; color: #5eead4; letter-spacing: 0.02em;
  margin: 0 0 0.35rem 0; line-height: 1.3; }
.atl-brand-sub { font-size: 0.72rem; color: #94a3b8; line-height: 1.4; margin-bottom: 1rem; }
.atl-page-title { font-family: "IBM Plex Serif", Georgia, serif; font-size: 1.65rem; font-weight: 600;
  color: #0f172a; margin: 0 0 0.25rem 0; }
.atl-page-sub { color: #475569; font-size: 0.95rem; margin-bottom: 1rem; line-height: 1.45; }
.atl-audience { font-size: 0.78rem; color: #64748b; margin: 0.35rem 0 0.75rem 0; line-height: 1.4; }
.atl-panel {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0.35rem 0 0.15rem 0;
  margin-bottom: 0;
}
.atl-panel-latest {
  border-bottom: none;
}
.atl-panel-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.07em;
  text-transform: uppercase; color: #64748b; margin: 0 0 0.75rem 0; }
.atl-answer { font-size: 1.05rem; line-height: 1.65; color: #0f172a; }
.atl-q-text { font-size: 0.98rem; color: #334155; margin-bottom: 0.65rem; line-height: 1.45;
  font-weight: 500; }
.atl-abstain { border-left: 2px solid #b45309; background: transparent; padding: 0.35rem 0 0.35rem 0.75rem;
  color: #78350f; font-size: 0.95rem; line-height: 1.55; }
.atl-soft { border-left: 2px solid #64748b; background: transparent; padding: 0.35rem 0 0.35rem 0.75rem;
  color: #334155; font-size: 0.95rem; line-height: 1.55; }
.atl-error { border-left: 2px solid #b91c1c; background: transparent; padding: 0.35rem 0 0.35rem 0.75rem;
  color: #7f1d1d; font-size: 0.95rem; }
.atl-grounded { border-left: 2px solid #0f766e; background: transparent; padding: 0.2rem 0 0.35rem 0.75rem;
  color: #115e59; font-size: 0.82rem; margin-bottom: 0.55rem; }
.atl-meta { display: flex; flex-wrap: wrap; gap: 0.55rem 1rem; margin-top: 0.65rem;
  padding-top: 0.55rem; border-top: 1px solid #e2e8f0; font-size: 0.8rem; color: #475569; }
.atl-cite { font-family: ui-monospace, Menlo, monospace; font-size: 0.8rem; background: transparent;
  border: none; padding: 0; margin-right: 0.45rem; color: #0f766e; }
.atl-chip { display: inline-block; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.03em;
  text-transform: uppercase; border: 1px solid #cbd5e1; color: #334155; padding: 0.15rem 0.55rem;
  border-radius: 999px; background: #f8fafc; white-space: nowrap; }
.atl-empty { color: #64748b; font-size: 0.92rem; }
.atl-step { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  color: #94a3b8; margin: 0 0 0.3rem 0; }
.atl-disclaimer { color: #9a3412; font-size: 0.75rem; line-height: 1.4; margin-top: 0.5rem; }
.atl-footer { margin-top: 1.25rem; padding-top: 0.75rem; border-top: 1px solid #e2e8f0;
  color: #64748b; font-size: 0.78rem; }
.atl-chunk { font-size: 0.88rem; line-height: 1.5; color: #334155; white-space: pre-wrap;
  word-break: break-word; max-height: 220px; overflow: auto; background: transparent;
  border: none; border-top: 1px solid #e2e8f0; border-radius: 0; padding: 0.75rem 0 0 0; margin-top: 0.35rem; }
.atl-mgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem; margin: 0.5rem 0 1rem 0; }
.atl-mcard { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.9rem 1rem;
  min-height: 6.2rem; }
.atl-mval { font-size: 1.45rem; font-weight: 700; color: #0f172a; line-height: 1.15; }
.atl-mlabel { font-size: 0.78rem; font-weight: 600; color: #334155; margin-top: 0.35rem; }
.atl-mhint { font-size: 0.72rem; color: #64748b; margin-top: 0.25rem; line-height: 1.35; }
.atl-info { color: #94a3b8; font-weight: 500; font-size: 0.72rem; }
.atl-faq-type {
  font-style: italic; color: #0f766e; text-align: right; font-size: 0.82rem;
  padding-top: 0.6rem; white-space: nowrap;
}
.atl-composer {
  background: transparent;
  border: none;
  padding: 0;
  margin: 0;
}
.atl-composer div[data-testid="stSelectbox"] label p { font-size: 0.78rem !important; color: #64748b !important; }
/* Ask composer — dock to viewport bottom at CONTENT height (not full-screen stretch) */
body.atl-ask-active section.stMain div[data-testid="stForm"],
body.atl-ask-active section[data-testid="stMain"] div[data-testid="stForm"],
body.atl-ask-active section.main div[data-testid="stForm"] {
  position: fixed !important;
  bottom: 0 !important;
  top: auto !important;
  height: auto !important;
  min-height: 0 !important;
  max-height: 42vh !important;
  z-index: 999 !important;
  background: #f0f2f5 !important;
  border-top: 1px solid #cbd5e1 !important;
  box-shadow: 0 -8px 24px rgba(15, 23, 42, 0.08) !important;
  padding: 0.65rem 1rem 0.85rem !important;
  margin: 0 !important;
  overflow: visible !important;
  flex: none !important;
  align-self: auto !important;
}
body.atl-ask-active section.stMain div[data-testid="stForm"] > div,
body.atl-ask-active section[data-testid="stMain"] div[data-testid="stForm"] > div {
  height: auto !important;
  min-height: 0 !important;
  flex: none !important;
}
.atl-chat-hero {
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  text-align: center;
  padding: 0.5rem 1rem 6rem;
}
.atl-chat-hero h1 {
  font-family: "IBM Plex Serif", Georgia, serif; font-size: 1.75rem; font-weight: 600;
  color: #0f172a; margin: 0 0 0.45rem 0;
}
.atl-chat-hero p { color: #64748b; font-size: 0.95rem; margin: 0; max-width: 36rem; line-height: 1.5; }
.atl-chat-hero .atl-audience { color: #64748b; margin-top: 0.85rem; }
.atl-turn-rule { border: none; border-top: 1px solid #e2e8f0; margin: 0.35rem 0 0.85rem 0; }
body.atl-ask-active section.stMain .block-container,
body.atl-ask-active section[data-testid="stMain"] .block-container,
body.atl-ask-active section.main .block-container {
  padding-top: 5.5rem !important;
  padding-bottom: 15rem !important;
  max-width: 760px;
}
body.atl-ask-active .atl-footer { display: none !important; }
.atl-ask-title {
  font-family: "IBM Plex Serif", Georgia, serif;
  font-size: 1.15rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0 0 0.75rem 0;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
  background: #134e4a !important;
  color: #ccfbf1 !important;
  border: 1px solid #2dd4bf !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers (needed before auth UI)
# ---------------------------------------------------------------------------

def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _secrets_password() -> Optional[str]:
    try:
        return st.secrets.get("password")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None


def _secrets_username() -> Optional[str]:
    try:
        return st.secrets.get("username")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None


_app_password = configured_app_password(secrets_password=_secrets_password())
_app_username = configured_app_username(secrets_username=_secrets_username())
# Local review fallback — replace before any public URL.
_demo_auth = not _app_password and not auth_required(password=None)
if _demo_auth:
    _app_username = "demo"
    _app_password = "demo"
_need_auth = bool(_app_password) or auth_required(password=_app_password)

if _need_auth:
    if not _app_password:
        st.error("Login is enabled but no password is configured (ATLASIQ_APP_PASSWORD).")
        st.stop()
    if not st.session_state.authenticated:
        st.markdown(f'<p class="atl-page-title">{_esc(PRODUCT_NAME)}</p>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="atl-page-sub" style="margin-top:-0.25rem;"><strong>{_esc(PRODUCT_ROLE)}</strong></p>',
            unsafe_allow_html=True,
        )
        st.caption(PRODUCT_HERO)
        if _demo_auth:
            st.warning(
                "Demo login for local review only: username `demo`, password `demo`. "
                "Set ATLASIQ_APP_USERNAME / ATLASIQ_APP_PASSWORD before publishing."
            )
        with st.form("auth_form"):
            user = st.text_input("Username", value="", autocomplete="username")
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            if st.form_submit_button("Sign in", type="primary"):
                if credentials_match(
                    user,
                    pw,
                    expected_username=_app_username,
                    expected_password=_app_password,
                ):
                    st.session_state.authenticated = True
                    st.rerun()
                st.error("Incorrect username or password.")
        st.stop()
else:
    st.session_state.authenticated = True


@st.cache_resource(show_spinner="Loading document search model…")
def _warm_embedding_model() -> bool:
    """Load MiniLM once per process so retrieval works on first question."""
    get_embedding_model.cache_clear()
    return get_embedding_model() is not None


_embedding_ready = _warm_embedding_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_ms(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.0f} ms"
    except (TypeError, ValueError):
        return "—"


def metric_cards(items: List[Tuple[str, str, str]]) -> None:
    """Product metric cards. Third field is hint + hover tooltip."""
    cells = [
        f'<div class="atl-mcard" title="{_esc(h)}"><div class="atl-mval">{_esc(v)}</div>'
        f'<div class="atl-mlabel">{_esc(l)} <span class="atl-info">ⓘ</span></div>'
        f'<div class="atl-mhint">{_esc(h)}</div></div>'
        for l, v, h in items
    ]
    st.markdown(f'<div class="atl-mgrid">{"".join(cells)}</div>', unsafe_allow_html=True)


def metrics_with_info(items: List[Tuple[str, str, str]]) -> None:
    """Alias — Quality uses the same card grid with ⓘ hints."""
    metric_cards(items)


def render_evidence_table(chunks: List[Dict[str, Any]]) -> None:
    """Source audit table: which documents were found vs cited in the answer."""
    rows = [
        {
            "#": ch.get("rank"),
            "Document": ch.get("source") or "",
            "Area": ch.get("domain") or "",
            "Match": round(float(ch.get("combined_score") or 0.0), 4),
            "Found": "Yes" if ch.get("accessed") else "No",
            "Cited in answer": "Yes" if ch.get("used") else "No",
        }
        for ch in chunks
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _turn_label(question: str, index: int) -> str:
    q = (question or "").strip()
    if len(q) <= 88:
        return f"#{index + 1} · {q}"
    return f"#{index + 1} · {q[:85]}…"


def render_turn_evidence(question: str, payload: Dict[str, Any], *, expanded: bool) -> None:
    with st.expander(_turn_label(question, payload.get("_turn_index", 0)), expanded=expanded):
        st.markdown(_trust_banner(payload), unsafe_allow_html=True)
        chunks = payload.get("chunks") or []
        if not chunks:
            st.caption("No document passages retained for this response.")
            return
        st.markdown("##### Documents found vs cited")
        render_evidence_table(chunks)
        st.markdown("##### Passage text")
        for ch in chunks:
            used_flag = "Cited in answer" if ch.get("used") else "Found only"
            with st.expander(
                f"#{ch['rank']}  {ch['source']} · {used_flag}",
                expanded=bool(ch.get("used")),
            ):
                st.caption(
                    f"Match {ch['combined_score']:.4f} · area={ch.get('domain') or '—'}"
                )
                st.markdown(
                    f'<div class="atl-chunk">{_esc(ch.get("text") or "")}</div>',
                    unsafe_allow_html=True,
                )


def render_turn_signals(question: str, payload: Dict[str, Any], *, expanded: bool) -> None:
    with st.expander(_turn_label(question, payload.get("_turn_index", 0)), expanded=expanded):
        score = payload.get("max_combined_score")
        thr = payload.get("similarity_threshold")
        metrics_with_info(
            [
                (
                    "Best match",
                    f"{score:.3f}" if score is not None else "—",
                    "Strongest document match for this question.",
                ),
                (
                    "Refuse below",
                    f"{thr}" if thr is not None else "—",
                    "Minimum match strength required before the assistant will confirm an answer.",
                ),
                (
                    "Citations",
                    str(len(payload.get("citations") or [])),
                    "Citation markers in the answer text.",
                ),
                (
                    "Passages",
                    str(len(payload.get("chunks") or [])),
                    "Document passages retained for audit (see Evidence).",
                ),
            ]
        )


def pipeline_to_payload(result: PipelineResult) -> Dict[str, Any]:
    return {
        "answer": result.answer,
        "abstained": result.abstained,
        "abstention_reason": result.abstention_reason,
        "abstention_kind": result.abstention_kind,
        "citations": list(result.citations),
        "mode": result.mode,
        "prompt_version": result.prompt_version,
        "model_id": result.model_id,
        "prompt_name": result.prompt_name,
        "generation_called": result.generation_called,
        "error": result.error,
        "max_combined_score": result.max_combined_score,
        "similarity_threshold": result.similarity_threshold,
        "timings": result.timings.as_dict(),
        "from_cache": bool(result.cache_hit),
        "cache_age_seconds": result.cache_age_seconds,
        "chunks": [
            {
                "rank": i + 1,
                "chunk_id": c.chunk_id,
                "source": c.source,
                "domain": c.domain,
                "doc_id": c.doc_id,
                "similarity_score": c.similarity_score,
                "combined_score": c.combined_score,
                "accessed": c.accessed,
                "used": c.used,
                "text": c.text,
            }
            for i, c in enumerate(result.chunks)
        ],
    }


def get_index_stats() -> Dict[str, Any]:
    stats: Dict[str, Any] = {"chunk_count": None, "doc_count": None, "error": None}
    try:
        stats["chunk_count"] = collection_count()
    except Exception as exc:  # noqa: BLE001
        stats["error"] = str(exc)
    try:
        stats["doc_count"] = len(discover_markdown_files())
    except Exception:
        stats["doc_count"] = None
    return stats


def load_preferred_eval() -> Tuple[Optional[Path], Optional[dict], str]:
    runs = order_runs_for_display(list_candidate_runs(config.paths.eval_results_dir))
    if not runs:
        return None, None, "none"
    path = runs[0]
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return path, None, "unreadable"
    _, status = run_authority(report)
    return path, report, status


def _mode_label(raw_mode: Any) -> str:
    key = str(raw_mode or "").strip().lower()
    if key == "grounded":
        return MODE_LABELS["Grounded"]
    if key == "auto":
        return MODE_LABELS["Auto"]
    if key == "general":
        return MODE_LABELS["General"]
    return str(raw_mode or "—")


def _trust_banner(payload: Dict[str, Any]) -> str:
    if payload.get("error"):
        kind, _ = friendly_pipeline_error(payload.get("error"))
        if kind == "unavailable":
            return (
                '<div class="atl-grounded" style="border-left-color:#64748b;color:#334155;">'
                "<strong>Temporarily unavailable</strong> — retry shortly or try another question."
                "</div>"
            )
        return (
            '<div class="atl-grounded" style="border-left-color:#b91c1c;color:#7f1d1d;">'
            "<strong>Could not complete this request</strong>"
            "</div>"
        )
    if payload.get("abstained"):
        kind = payload.get("abstention_kind") or ""
        kind_label = ABSTENTION_KIND_LABELS.get(str(kind), "")
        suffix = f" · {_esc(kind_label)}" if kind_label else ""
        return (
            '<div class="atl-grounded" style="border-left-color:#b45309;color:#78350f;">'
            f"<strong>Not confirmed from approved documents</strong>{suffix}"
            "</div>"
        )
    cached = " · served from cache" if payload.get("from_cache") else ""
    return (
        '<div class="atl-grounded">'
        f"<strong>Verified against Sales &amp; CPQ documents</strong>{cached}"
        "</div>"
    )


def render_answer_panel(question: str, payload: Dict[str, Any], *, latest: bool = False) -> None:
    """Deal-desk turn: trust state → answer → question → audit cues."""
    cls = "atl-panel atl-panel-latest" if latest else "atl-panel"
    st.markdown(f'<div class="{cls}" id="{"atl-latest-turn" if latest else ""}">', unsafe_allow_html=True)
    st.markdown(_trust_banner(payload), unsafe_allow_html=True)

    if payload.get("error"):
        kind, friendly = friendly_pipeline_error(payload.get("error"))
        css = "atl-soft" if kind == "unavailable" else "atl-error"
        st.markdown(f'<div class="{css}">{_esc(friendly)}</div>', unsafe_allow_html=True)
        st.markdown('<p class="atl-step">You asked</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="atl-q-text">{_esc(question)}</div>', unsafe_allow_html=True)
    elif payload.get("abstained"):
        st.markdown('<p class="atl-step">You asked</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="atl-q-text">{_esc(question)}</div>', unsafe_allow_html=True)
        st.markdown('<p class="atl-step">Why the assistant will not confirm</p>', unsafe_allow_html=True)
        reason = (
            payload.get("abstention_reason")
            or "Insufficient matching evidence in approved Sales & CPQ documents."
        )
        st.markdown(f'<div class="atl-abstain">{_esc(reason)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="atl-step">Answer</p>', unsafe_allow_html=True)
        answer = (payload.get("answer") or "").replace("**", "")
        st.markdown(f'<div class="atl-answer">{_esc(answer)}</div>', unsafe_allow_html=True)
        st.markdown('<p class="atl-step">You asked</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="atl-q-text">{_esc(question)}</div>', unsafe_allow_html=True)

    cites = payload.get("citations") or []
    if cites and not payload.get("error") and not payload.get("abstained"):
        st.markdown('<p class="atl-step">Document citations</p>', unsafe_allow_html=True)
        st.markdown(
            " ".join(f'<span class="atl-cite">[{_esc(c)}]</span>' for c in cites),
            unsafe_allow_html=True,
        )
        st.caption("Open Evidence to audit which policy or SKU passages support this answer.")

    timings = payload.get("timings") or {}
    st.markdown(
        f"""
        <div class="atl-meta">
          <span><strong>Response</strong> {timings.get('total_ms', 0):.0f} ms</span>
          <span><strong>Policy</strong> {_esc(_mode_label(payload.get("mode")))}</span>
          <span><strong>Freshness</strong> {"cache" if payload.get("from_cache") else "live"}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    if not latest:
        st.markdown('<hr class="atl-turn-rule" />', unsafe_allow_html=True)


def run_question(ask_text: str) -> None:
    mode_key = st.session_state.ui_mode.lower()
    threshold = float(st.session_state.ui_threshold)
    rerank = bool(st.session_state.ui_rerank)
    run_cfg = replace(
        config,
        retrieval=replace(config.retrieval, similarity_threshold=threshold),
        rerank=replace(config.rerank, enabled=rerank),
    )
    with st.spinner("Checking approved documents…"):
        result = answer_query(
            ask_text,
            mode=mode_key,
            cfg=run_cfg,
            rerank_enabled=rerank,
            use_cache=True,
        )
    payload = pipeline_to_payload(result)
    st.session_state.turns.append({"question": ask_text, "result": payload})
    st.session_state.last_result = payload
    st.session_state.last_question = ask_text


def goto(page: str) -> None:
    st.session_state.nav_page = page
    section = page.split(":")[0]
    # Open only the destination section; close all others (e.g. leave Ask → Ask collapses)
    for k in st.session_state.nav_open:
        st.session_state.nav_open[k] = k == section
    st.rerun()


def nav_toggle(section: str) -> None:
    st.session_state.nav_open[section] = not st.session_state.nav_open.get(section, False)


# ---------------------------------------------------------------------------
# Left navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f'<p class="atl-brand">{_esc(PRODUCT_NAME)}</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="atl-brand-role">{_esc(PRODUCT_ROLE)}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="atl-brand-sub">{_esc(PRODUCT_HERO)}</p>',
        unsafe_allow_html=True,
    )

    for key, title, default_page, children in NAV_SECTIONS:
        parent_active = st.session_state.nav_page == default_page
        if children:
            open_ = bool(st.session_state.nav_open.get(key, False))
            tri = "▼" if open_ else "▶"
            btn_type = "primary" if parent_active else "secondary"
            if st.button(
                f"{tri}   {title}",
                key=f"nav_{key}",
                use_container_width=True,
                type=btn_type,
            ):
                if parent_active:
                    nav_toggle(key)
                    st.rerun()
                else:
                    goto(default_page)
            if open_:
                for sub_page, sub_title in children:
                    if st.button(
                        f"  {sub_title}",
                        key=f"sub_{sub_page}",
                        use_container_width=True,
                        type="primary" if st.session_state.nav_page == sub_page else "secondary",
                    ):
                        goto(sub_page)
        else:
            if st.button(
                title,
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if parent_active else "secondary",
            ):
                goto(default_page)

    stats = get_index_stats()
    st.markdown("---")
    if not stats["error"]:
        st.caption(
            f"{stats['doc_count'] or '—'} documents indexed · {stats['chunk_count'] or '—'} passages"
        )
    if not _embedding_ready:
        st.caption("Document search model not loaded — run warm_models.py")
    if config.has_groq_api_key:
        st.caption("Ready for Sales, RevOps, Deal Desk &amp; CPQ")
    else:
        st.caption("API key missing — answers unavailable")

page = st.session_state.nav_page
if page != "ask":
    components.html(
        """
        <script>
        (function() {
          const doc = window.parent.document;
          doc.body.classList.remove('atl-ask-active');
          doc.querySelectorAll('.atl-ask-active').forEach((el) => el.classList.remove('atl-ask-active'));
        })();
        </script>
        """,
        height=0,
    )

# ---------------------------------------------------------------------------
# ASK — deal-desk Q&A
# ---------------------------------------------------------------------------

if page == "ask":
    if not _embedding_ready:
        err_detail = embedding_load_error() or "unknown load failure"
        st.error(
            "Document search is unavailable — the embedding model did not load. "
            "Stop this app and restart with the project virtualenv:\n\n"
            "`.venv/bin/streamlit run app.py`\n\n"
            "Then run once: `python scripts/warm_models.py`"
        )
        st.caption(f"Load error: {err_detail}")

    turns = st.session_state.turns
    faq_by_id = {s["id"]: s for s in SAMPLE_QUESTIONS}
    faq_ids = ["__none__"] + [s["id"] for s in SAMPLE_QUESTIONS]

    def _faq_label(fid: str) -> str:
        if fid == "__none__":
            return "Try a sample deal question…"
        return faq_by_id[fid]["question"]

    # Always keep the product name at the top of Ask so the thread can scroll
    # from brand → older answers → latest answer above the fixed composer.
    st.markdown(
        f'<p class="atl-ask-title">{_esc(PRODUCT_NAME)}</p>',
        unsafe_allow_html=True,
    )
    if not turns:
        st.markdown(
            f'<div class="atl-chat-hero">'
            f'<p style="font-weight:600;color:#0f766e;margin:0 0 0.65rem 0;">'
            f"{_esc(PRODUCT_ROLE)}</p>"
            f"<p>{_esc(PRODUCT_HERO)}</p>"
            f'<p class="atl-audience">{_esc(PRODUCT_AUDIENCE)}</p>'
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        last_i = len(turns) - 1
        for i, turn in enumerate(turns):
            render_answer_panel(
                turn["question"],
                turn["result"],
                latest=(i == last_i),
            )

    scroll_after_answer = bool(st.session_state.pop("_scroll_ask", False))

    if st.session_state.pop("faq_pick_reset", False):
        st.session_state.faq_pick = "__none__"
    if "faq_pick" not in st.session_state:
        st.session_state.faq_pick = "__none__"

    with st.form("ask_form", clear_on_submit=True):
        faq_col, type_col = st.columns([0.80, 0.20])
        with faq_col:
            picked = st.selectbox(
                "Sample deal questions",
                faq_ids,
                format_func=_faq_label,
                label_visibility="collapsed",
                key="faq_pick",
                help="Full sample questions. The italic label on the right is the commercial question type.",
            )
        with type_col:
            if picked != "__none__":
                st.markdown(
                    f'<p class="atl-faq-type">{_esc(faq_by_id[picked]["type"])}</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<p class="atl-faq-type" style="opacity:0.35;">type</p>',
                    unsafe_allow_html=True,
                )
        question = st.text_area(
            "Question",
            value="",
            height=90,
            placeholder="Ask about list price, discount authority, seats, entitlements, or quote terms…",
            label_visibility="collapsed",
        )
        mode_col, send_col = st.columns([0.62, 0.38])
        with mode_col:
            form_mode = st.selectbox(
                "Answer policy",
                MODE_OPTIONS,
                index=MODE_OPTIONS.index(st.session_state.ui_mode)
                if st.session_state.ui_mode in MODE_OPTIONS
                else 0,
                format_func=lambda m: MODE_LABELS.get(m, m),
                help=MODE_OVERVIEW_HELP,
                label_visibility="collapsed",
            )
        with send_col:
            submitted = st.form_submit_button("Ask", type="primary", use_container_width=True)

    # Align Ask bar to the main content column (not the full section under the sidebar).
    # Only auto-scroll after a new answer — never lock the user from scrolling to the top.
    components.html(
        f"""
        <script>
        (function() {{
          const w = window.parent;
          const doc = w.document;
          const SHOULD_SCROLL = {str(scroll_after_answer).lower()};
          const activate = () => {{
            doc.body.classList.add('atl-ask-active');
            const main = doc.querySelector('section.stMain, section[data-testid="stMain"], section.main');
            if (main) main.classList.add('atl-ask-active');
          }};
          const findForm = () => doc.querySelector(
            'section.stMain div[data-testid="stForm"], section[data-testid="stMain"] div[data-testid="stForm"], section.main div[data-testid="stForm"]'
          );
          const findColumn = () => doc.querySelector(
            'section.stMain div.stMainBlockContainer, section.stMain div.block-container, section[data-testid="stMain"] div.block-container'
          );
          const scrollParent = (el) => {{
            let p = el ? el.parentElement : null;
            while (p && p !== doc.body) {{
              const style = w.getComputedStyle(p);
              if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && p.scrollHeight > p.clientHeight + 4) {{
                return p;
              }}
              p = p.parentElement;
            }}
            return doc.scrollingElement || doc.documentElement;
          }};
          const pin = () => {{
            activate();
            const col = findColumn();
            const form = findForm();
            if (!col || !form) return;
            const rect = col.getBoundingClientRect();
            const left = Math.round(rect.left);
            const width = Math.round(rect.width);
            form.style.setProperty('position', 'fixed', 'important');
            form.style.setProperty('bottom', '0px', 'important');
            form.style.setProperty('top', 'auto', 'important');
            form.style.setProperty('left', left + 'px', 'important');
            form.style.setProperty('width', width + 'px', 'important');
            form.style.setProperty('right', 'auto', 'important');
            form.style.setProperty('height', 'auto', 'important');
            form.style.setProperty('min-height', '0', 'important');
            form.style.setProperty('max-height', '40vh', 'important');
            form.style.setProperty('z-index', '999', 'important');
            form.style.setProperty('background', '#f0f2f5', 'important');
            form.style.setProperty('margin', '0', 'important');
            form.style.setProperty('flex', 'none', 'important');
            form.style.removeProperty('inset');
          }};
          const scrollLatest = () => {{
            if (!SHOULD_SCROLL) return;
            const anchor = doc.getElementById('atl-latest-turn');
            const form = findForm();
            if (!anchor) return;
            const scroller = scrollParent(anchor);
            const formH = form ? form.getBoundingClientRect().height : 220;
            const anchorTop = anchor.getBoundingClientRect().top;
            const scrollerTop = scroller === doc.scrollingElement || scroller === doc.documentElement
              ? 0
              : scroller.getBoundingClientRect().top;
            const delta = anchorTop - scrollerTop - 24;
            const next = Math.max(0, scroller.scrollTop + delta);
            // Keep latest answer visible above the fixed Ask bar; do not force block:start
            // which clips the top of the thread under the header.
            const maxScroll = Math.max(0, scroller.scrollHeight - scroller.clientHeight - formH);
            scroller.scrollTo({{ top: Math.min(next, maxScroll), behavior: 'smooth' }});
          }};
          pin();
          w.addEventListener('resize', pin);
          setTimeout(pin, 50);
          setTimeout(pin, 250);
          if (SHOULD_SCROLL) {{
            setTimeout(scrollLatest, 180);
            setTimeout(scrollLatest, 400);
          }}
        }})();
        </script>
        """,
        height=0,
    )

    if submitted:
        st.session_state.ui_mode = form_mode
        if picked != "__none__":
            run_question(faq_by_id[picked]["question"])
            st.session_state.faq_pick_reset = True
            st.session_state._scroll_ask = True
            st.rerun()
        elif question.strip():
            run_question(question.strip())
            st.session_state._scroll_ask = True
            st.rerun()

elif page == "ask:settings":
    st.markdown('<p class="atl-page-title">Answer policy</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="atl-page-sub">How strictly {PRODUCT_NAME} must stick to governed sales '
        "policy documents on the next question.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("##### Document grounding")
    st.markdown(
        f'<p class="atl-mode-help">{_esc(MODE_OVERVIEW_HELP)}</p>',
        unsafe_allow_html=True,
    )
    mode_cols = st.columns(len(MODE_OPTIONS))
    for col, m in zip(mode_cols, MODE_OPTIONS):
        with col:
            if st.button(
                MODE_LABELS[m],
                key=f"settings_mode_{m}",
                use_container_width=True,
                type="primary" if st.session_state.ui_mode == m else "secondary",
                help=MODE_DETAIL[m],
            ):
                st.session_state.ui_mode = m
                st.rerun()
    st.caption(MODE_DETAIL[st.session_state.ui_mode])

    st.markdown("##### When to refuse")
    st.session_state.ui_threshold = st.slider(
        "Minimum match strength to answer",
        0.0,
        2.0,
        float(st.session_state.ui_threshold),
        0.05,
        help="If the best document match is below this, the assistant will not confirm a commercial answer.",
    )

    st.markdown("##### Match quality")
    st.session_state.ui_rerank = st.toggle(
        REFINE_LABEL,
        value=bool(st.session_state.ui_rerank),
        help=REFINE_HELP,
    )
    st.caption(REFINE_HELP)

# ---------------------------------------------------------------------------
# EVIDENCE — source audit for the latest answer
# ---------------------------------------------------------------------------

elif page == "evidence":
    st.markdown('<p class="atl-page-title">Evidence</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="atl-page-sub">Session audit trail — which Sales &amp; CPQ documents '
        "were found and cited for each question you asked.</p>",
        unsafe_allow_html=True,
    )
    turns = st.session_state.turns
    if not turns:
        st.info("Ask a question first, then return here to audit sources.")
    else:
        st.caption(f"{len(turns)} question(s) in this session")
        for i, turn in enumerate(reversed(turns)):
            payload = dict(turn["result"])
            payload["_turn_index"] = len(turns) - 1 - i
            render_turn_evidence(
                turn["question"],
                payload,
                expanded=(i == 0),
            )

elif page == "evidence:signals":
    st.markdown('<p class="atl-page-title">Match strength</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="atl-page-sub">How strongly documents matched each question in this session — '
        "not the product-wide Quality benchmark.</p>",
        unsafe_allow_html=True,
    )
    turns = st.session_state.turns
    if not turns:
        st.info("Ask a question first.")
    else:
        st.caption(f"{len(turns)} question(s) in this session")
        for i, turn in enumerate(reversed(turns)):
            payload = dict(turn["result"])
            payload["_turn_index"] = len(turns) - 1 - i
            render_turn_signals(
                turn["question"],
                payload,
                expanded=(i == 0),
            )

# ---------------------------------------------------------------------------
# QUALITY — frozen release benchmark (not live usage)
# ---------------------------------------------------------------------------

elif page == "quality":
    st.markdown('<p class="atl-page-title">Quality</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="atl-page-sub"><strong>These scores do not change as sellers ask questions.</strong> '
        "They are a frozen pre-release check on a fixed Sales &amp; CPQ test set — "
        "proof that this build retrieves, answers, and refuses correctly. "
        "Each card’s hint explains the metric.</p>",
        unsafe_allow_html=True,
    )
    path, report, status = load_preferred_eval()
    if not report:
        st.warning("No release-quality report found for this build.")
    else:
        agg = report.get("aggregate") or {}
        conf = agg.get("confusion") or {}
        lat = agg.get("latency_ms") or {}
        st.caption(
            f"Benchmark: `{path.name if path else '—'}` · {report.get('case_count')} labeled questions"
            + (" · clean run" if status == "CLEAN" else f" · {status}")
        )
        st.markdown("##### Finding the right document")
        metrics_with_info(
            [
                (
                    "Recall@3",
                    _fmt_pct(agg.get("recall_at_3")),
                    "Was the right document among the top 3 matches?",
                ),
                (
                    "Recall@1",
                    _fmt_pct(agg.get("recall_at_1")),
                    "Was the right document the top match?",
                ),
                (
                    "Answer overlap",
                    _fmt_pct(agg.get("answer_token_f1_mean")),
                    "How closely answers match the expected commercial wording.",
                ),
                (
                    "Citation integrity",
                    _fmt_pct(agg.get("citation_accuracy_mean")),
                    "Whether citations point at retrieved document evidence.",
                ),
            ]
        )
        st.markdown("##### Knowing when not to answer")
        metrics_with_info(
            [
                (
                    "Refuse precision",
                    _fmt_pct(agg.get("abstention_precision")),
                    "Of questions we refused, how many should have been refused.",
                ),
                (
                    "Refuse recall",
                    _fmt_pct(agg.get("abstention_recall")),
                    "Of questions that should be refused, how many we caught.",
                ),
                (
                    "Unsafe answers",
                    _fmt_pct(agg.get("false_positive_answer_rate")),
                    "Answered when we should have refused — commercial risk.",
                ),
                (
                    "Over-refusal",
                    _fmt_pct(agg.get("false_abstention_rate")),
                    "Refused when we should have answered.",
                ),
            ]
        )
        st.markdown("##### Response time on the test set")
        metrics_with_info(
            [
                (
                    "Median total",
                    _fmt_ms(lat.get("total_p50")),
                    "Median end-to-end time on the golden set.",
                ),
                (
                    "Median generate",
                    _fmt_ms(lat.get("generate_p50")),
                    "Median time spent writing the answer.",
                ),
                (
                    "p95 total",
                    _fmt_ms(lat.get("total_p95")),
                    "Slow-tail end-to-end time.",
                ),
                (
                    "Errors",
                    str(int(conf.get("ERROR") or 0)),
                    "Infrastructure failures in the benchmark run.",
                ),
            ]
        )

# ---------------------------------------------------------------------------
# CORPUS — indexed knowledge base
# ---------------------------------------------------------------------------

elif page == "system":
    st.markdown('<p class="atl-page-title">Sales Policy</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="atl-page-sub">Governed business knowledge {PRODUCT_NAME} uses to price deals, '
        "apply discount policy, and validate commercial terms.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="atl-disclaimer">{_esc(synthetic_corpus_disclaimer())}</p>',
        unsafe_allow_html=True,
    )
    stats = get_index_stats()
    st.markdown("##### Index")
    metric_cards(
        [
            (
                "Documents",
                str(stats["doc_count"] if stats["doc_count"] is not None else "—"),
                "Pricing, policy, entitlements, and commercial rules",
            ),
            (
                "Passages",
                str(stats["chunk_count"] if stats["chunk_count"] is not None else "—"),
                "Searchable units in the index",
            ),
            ("Collection", config.chroma.collection_name, "Vector index name"),
        ]
    )
    st.caption(f"Embeddings: `{config.embedding.model_id}` · Chat: `{config.generation.model_id}`")
    st.markdown("##### Answer cache")
    ttl = int(config.cache.ttl_seconds)
    ttl_label = "off (no expiry)" if ttl == 0 else f"{ttl // 60} min" if ttl >= 60 else f"{ttl}s"
    st.caption(
        f"{'Enabled' if config.cache.enabled else 'Disabled'} · refresh after {ttl_label} · "
        f"max {config.cache.max_entries} entries. "
        "Repeating the same question within the window reuses the last confirmed answer; "
        "re-syncing Sales Policy clears the cache so numbers cannot go stale."
    )
    if st.button("Re-sync Sales Policy", type="primary"):
        with st.spinner("Updating Sales Policy index…"):
            try:
                upserted, final_count = index_corpus()
                st.success(
                    f"Indexed {upserted} passages · collection {final_count} · answer cache cleared"
                )
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

if page != "ask":
    st.markdown(
        f'<div class="atl-footer">{_esc(PRODUCT_NAME)} · evidence-backed pricing, policy, and quotes</div>',
        unsafe_allow_html=True,
    )
