"""Deployment readiness helpers for AtlasIQ V1 (no LLM calls)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from atlas.config import AtlasConfig, config as default_config


PREFERRED_EVAL_ARTIFACTS: Tuple[str, ...] = (
    "run_v1_clean_full.json",
    "run_phase8_challenge_clean_v3.json",
)


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    ok: bool
    severity: str  # blocker | warn | ok
    message: str


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def configured_app_password(
    *,
    secrets_password: Optional[str] = None,
) -> Optional[str]:
    """Return the gate password from env or Streamlit secrets (never log it)."""
    env_pw = (os.getenv("ATLASIQ_APP_PASSWORD") or "").strip()
    if env_pw:
        return env_pw
    if secrets_password is not None and str(secrets_password).strip():
        return str(secrets_password).strip()
    return None


def configured_app_username(
    *,
    secrets_username: Optional[str] = None,
) -> str:
    """Return the expected login username (env / secrets / default demo user)."""
    env_user = (os.getenv("ATLASIQ_APP_USERNAME") or "").strip()
    if env_user:
        return env_user
    if secrets_username is not None and str(secrets_username).strip():
        return str(secrets_username).strip()
    return "demo"


def credentials_match(
    provided_username: str,
    provided_password: str,
    *,
    expected_username: str,
    expected_password: Optional[str],
) -> bool:
    if not expected_password:
        return False
    user_ok = (provided_username or "").strip().lower() == (expected_username or "").strip().lower()
    return user_ok and (provided_password or "") == expected_password


def auth_required(*, password: Optional[str]) -> bool:
    """Public deploy should set ATLASIQ_REQUIRE_AUTH=1; password alone also enables gate."""
    if env_flag("ATLASIQ_REQUIRE_AUTH", default=False):
        return True
    return bool(password)


def passwords_match(provided: str, expected: Optional[str]) -> bool:
    if not expected:
        return False
    return (provided or "") == expected


def is_rate_limit_error(error: Optional[str]) -> bool:
    if not error:
        return False
    text = error.lower()
    return (
        "429" in text
        or "rate limit" in text
        or "tokens per day" in text
        or "tpd" in text
        or "too many requests" in text
    )


def friendly_pipeline_error(error: Optional[str]) -> Tuple[str, str]:
    """Return (kind, user-facing message). Never includes secrets."""
    if not error:
        return "none", ""
    if "GROQ_API_KEY" in error:
        return (
            "missing_key",
            "Generation is unavailable because GROQ_API_KEY is not configured "
            "on this host. Set it as an environment secret and restart.",
        )
    if "Embedding model is unavailable" in error:
        return (
            "embedding_unavailable",
            "Document search is unavailable because the embedding model could not load. "
            "Use the project virtualenv (`.venv/bin/streamlit run app.py`) and run "
            "`python scripts/warm_models.py` once to download/cache the model, then restart.",
        )
    if is_rate_limit_error(error):
        return (
            "unavailable",
            "This answer is temporarily unavailable. "
            "Try another sample question, or ask again shortly.",
        )
    return "pipeline_error", error


def assess_deployment_readiness(
    cfg: Optional[AtlasConfig] = None,
    *,
    chunk_count: Optional[int] = None,
    index_error: Optional[str] = None,
    secrets_password: Optional[str] = None,
) -> List[ReadinessItem]:
    cfg = cfg or default_config
    items: List[ReadinessItem] = []

    has_key = cfg.has_groq_api_key
    items.append(
        ReadinessItem(
            key="groq_api_key",
            ok=has_key,
            severity="ok" if has_key else "blocker",
            message=(
                "GROQ_API_KEY is configured (value never displayed)."
                if has_key
                else "GROQ_API_KEY is missing — grounded answers will fail."
            ),
        )
    )

    password = configured_app_password(secrets_password=secrets_password)
    require = env_flag("ATLASIQ_REQUIRE_AUTH", default=False)
    if require and not password:
        items.append(
            ReadinessItem(
                key="auth",
                ok=False,
                severity="blocker",
                message=(
                    "ATLASIQ_REQUIRE_AUTH is set but no ATLASIQ_APP_PASSWORD / "
                    "secrets password is configured."
                ),
            )
        )
    elif password:
        items.append(
            ReadinessItem(
                key="auth",
                ok=True,
                severity="ok",
                message="App password gate is configured.",
            )
        )
    else:
        items.append(
            ReadinessItem(
                key="auth",
                ok=False,
                severity="warn",
                message=(
                    "No app password set — OK for local use only. "
                    "Set ATLASIQ_APP_PASSWORD (and ATLASIQ_REQUIRE_AUTH=1) before a public URL."
                ),
            )
        )

    if index_error:
        items.append(
            ReadinessItem(
                key="index",
                ok=False,
                severity="blocker",
                message=f"Vector index unavailable: {index_error}",
            )
        )
    elif chunk_count is None:
        items.append(
            ReadinessItem(
                key="index",
                ok=False,
                severity="warn",
                message="Could not read index chunk count.",
            )
        )
    elif chunk_count <= 0:
        items.append(
            ReadinessItem(
                key="index",
                ok=False,
                severity="blocker",
                message="Index is empty — run scripts/index_corpus.py (or Settings → Index).",
            )
        )
    else:
        items.append(
            ReadinessItem(
                key="index",
                ok=True,
                severity="ok",
                message=f"Index ready ({chunk_count} chunks in {cfg.chroma.collection_name}).",
            )
        )

    eval_dir = cfg.paths.eval_results_dir
    missing = [
        name
        for name in PREFERRED_EVAL_ARTIFACTS
        if not (eval_dir / name).is_file()
    ]
    if missing:
        items.append(
            ReadinessItem(
                key="eval_artifacts",
                ok=False,
                severity="warn",
                message=(
                    "Preferred Evaluation artifacts missing on this host: "
                    + ", ".join(missing)
                ),
            )
        )
    else:
        items.append(
            ReadinessItem(
                key="eval_artifacts",
                ok=True,
                severity="ok",
                message="Preferred clean Evaluation artifacts are present.",
            )
        )

    corpus_ok = cfg.paths.corpus_dir.is_dir()
    items.append(
        ReadinessItem(
            key="corpus",
            ok=corpus_ok,
            severity="ok" if corpus_ok else "blocker",
            message=(
                f"Corpus directory present at {cfg.paths.corpus_dir}."
                if corpus_ok
                else f"Corpus directory missing: {cfg.paths.corpus_dir}"
            ),
        )
    )

    return items


def readiness_blockers(items: Sequence[ReadinessItem]) -> List[ReadinessItem]:
    return [i for i in items if i.severity == "blocker"]


def synthetic_corpus_disclaimer() -> str:
    return (
        "Demo corpus: AI Sales Assistant uses a synthetic 50-document Sales/CPQ knowledge base "
        "(SKU pricing, discount policy, regional SLAs). Figures are for product "
        "demonstration only — not a real customer’s commercial terms."
    )
