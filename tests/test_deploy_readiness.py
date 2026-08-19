"""Deployment readiness helpers — no LLM / network required."""

from __future__ import annotations

import os

from atlas.deploy_readiness import (
    auth_required,
    configured_app_password,
    friendly_pipeline_error,
    is_rate_limit_error,
    passwords_match,
    readiness_blockers,
    assess_deployment_readiness,
    synthetic_corpus_disclaimer,
)


def test_rate_limit_classification():
    assert is_rate_limit_error("Error 429 rate_limit")
    assert is_rate_limit_error("tokens per day exceeded")
    kind, msg = friendly_pipeline_error("HTTP 429 Too Many Requests")
    assert kind == "unavailable"
    assert "temporarily unavailable" in msg.lower()


def test_missing_key_message():
    kind, msg = friendly_pipeline_error("GROQ_API_KEY is not set; cannot call")
    assert kind == "missing_key"
    assert "GROQ_API_KEY" in msg


def test_password_gate_helpers(monkeypatch):
    monkeypatch.delenv("ATLASIQ_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ATLASIQ_REQUIRE_AUTH", raising=False)
    assert configured_app_password() is None
    assert auth_required(password=None) is False
    assert auth_required(password="secret") is True
    monkeypatch.setenv("ATLASIQ_REQUIRE_AUTH", "1")
    assert auth_required(password=None) is True
    assert passwords_match("secret", "secret")
    assert not passwords_match("nope", "secret")


def test_readiness_reports_auth_warn_without_password(monkeypatch):
    monkeypatch.delenv("ATLASIQ_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ATLASIQ_REQUIRE_AUTH", raising=False)
    items = assess_deployment_readiness(chunk_count=100, index_error=None)
    auth = next(i for i in items if i.key == "auth")
    assert auth.severity == "warn"
    assert not readiness_blockers([auth])


def test_readiness_blocker_when_auth_required_without_password(monkeypatch):
    monkeypatch.setenv("ATLASIQ_REQUIRE_AUTH", "1")
    monkeypatch.delenv("ATLASIQ_APP_PASSWORD", raising=False)
    items = assess_deployment_readiness(chunk_count=100, secrets_password=None)
    assert any(i.key == "auth" and i.severity == "blocker" for i in items)
    assert readiness_blockers(items)


def test_disclaimer_mentions_synthetic():
    text = synthetic_corpus_disclaimer()
    assert "synthetic" in text.lower()
