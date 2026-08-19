"""Metadata-aware query routing for AtlasIQ V1.

Detects explicit document identifiers in the user query (e.g. Module 12,
Region 01, Framework 10) and matches them against chunk ``source`` /
``doc_id`` metadata so near-duplicate sibling documents can be disambiguated.

This does **not** replace hybrid scoring
(``combined = similarity + keyword_count * keyword_weight``).
It only extracts routing signals and applies a deterministic prioritization
/ soft boost on top of hybrid scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

# Soft boost added to hybrid combined_score when metadata matches.
# Large enough to outrank typical keyword variance, small enough to stay
# interpretable next to cosine similarity in [0, 1].
METADATA_MATCH_BOOST = 5.0

# Named-entity patterns: label + integer (optional zero-padding in query).
_ENTITY_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("module", re.compile(r"\bmodules?\s*0*(\d+)\b", re.IGNORECASE)),
    ("region", re.compile(r"\bregions?\s*0*(\d+)\b", re.IGNORECASE)),
    ("framework", re.compile(r"\bframeworks?\s*0*(\d+)\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class QueryEntity:
    """One explicit identifier extracted from a query."""

    kind: str  # module | region | framework
    value: str  # canonical zero-padded 2-digit string, e.g. "12", "01"

    @property
    def int_value(self) -> int:
        return int(self.value)


def normalize_entity_id(raw: str) -> str:
    """Normalize a numeric identifier to zero-padded 2 digits (corpus filenames)."""
    return f"{int(raw):02d}"


def extract_query_entities(query: str) -> List[QueryEntity]:
    """Extract Module / Region / Framework identifiers from ``query``.

    Deterministic: first unique (kind, value) in pattern order, left-to-right.
    Returns an empty list when no explicit identifiers are present.
    """
    if not query or not query.strip():
        return []

    found: List[QueryEntity] = []
    seen = set()
    for kind, pattern in _ENTITY_PATTERNS:
        for match in pattern.finditer(query):
            value = normalize_entity_id(match.group(1))
            key = (kind, value)
            if key in seen:
                continue
            seen.add(key)
            found.append(QueryEntity(kind=kind, value=value))
    return found


def entity_source_hints(entity: QueryEntity) -> List[str]:
    """Likely exact ``source`` paths for an entity (corpus naming convention)."""
    n = entity.value
    if entity.kind == "module":
        return [f"corpus/skus/product_tier_{n}.md"]
    if entity.kind == "region":
        return [f"corpus/legal/sla_agreement_region_{n}.md"]
    if entity.kind == "framework":
        return [f"corpus/policies/discount_matrix_policy_{n}.md"]
    return []


def source_matches_entity(source: str, doc_id: str, entity: QueryEntity) -> bool:
    """True if chunk metadata refers to the same sibling document as ``entity``."""
    blob = f"{source} {doc_id}".lower().replace("\\", "/")
    n = entity.value
    n_int = str(entity.int_value)
    if entity.kind == "module":
        return (
            f"product_tier_{n}" in blob
            or f"product_tier_{n_int}." in blob
            or f"/product_tier_{n_int}" in blob
        )
    if entity.kind == "region":
        return (
            f"region_{n}" in blob
            or f"region_{n_int}." in blob
            or f"/region_{n_int}" in blob
        )
    if entity.kind == "framework":
        return (
            f"policy_{n}" in blob
            or f"discount_matrix_policy_{n}" in blob
            or f"policy_{n_int}." in blob
        )
    return False


def any_entity_match(source: str, doc_id: str, entities: Sequence[QueryEntity]) -> bool:
    return any(source_matches_entity(source, doc_id, e) for e in entities)


def metadata_boost_for(
    source: str, doc_id: str, entities: Sequence[QueryEntity]
) -> float:
    """Return ``METADATA_MATCH_BOOST`` if metadata matches any entity, else 0."""
    if not entities:
        return 0.0
    return METADATA_MATCH_BOOST if any_entity_match(source, doc_id, entities) else 0.0


def ranking_score(combined_score: float, metadata_boost: float) -> float:
    """Final sort key: hybrid combined_score + metadata boost."""
    return float(combined_score) + float(metadata_boost)


def apply_metadata_routing(
    candidates: Sequence,
    entities: Sequence[QueryEntity],
    *,
    get_source=lambda c: c.source,
    get_doc_id=lambda c: c.doc_id,
    get_combined=lambda c: c.combined_score,
    rebuild=None,
) -> List:
    """Re-rank candidates with metadata boost; preserve hybrid combined_score.

    ``rebuild(candidate, metadata_boost, ranking_score)`` must return a new
    candidate object if the candidate type is immutable. If ``rebuild`` is
    None, candidates are sorted in place by ranking score only (no field updates).
    """
    if not candidates:
        return []
    if not entities:
        return list(candidates)

    scored = []
    for c in candidates:
        boost = metadata_boost_for(get_source(c), get_doc_id(c), entities)
        rank = ranking_score(get_combined(c), boost)
        scored.append((rank, boost, c))

    # Deterministic: ranking_score desc, then source, then chunk_id if present
    def sort_key(item):
        rank, boost, c = item
        chunk_id = getattr(c, "chunk_id", "") or ""
        source = get_source(c) or ""
        return (-rank, source, chunk_id)

    scored.sort(key=sort_key)

    if rebuild is None:
        return [c for _, _, c in scored]

    return [rebuild(c, boost, rank) for rank, boost, c in scored]
