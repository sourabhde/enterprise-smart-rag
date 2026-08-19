"""Corpus ingestion for AtlasIQ V1.

Reads ``corpus/**/*.md``, applies proven semantic chunking, and returns
structured chunk records. Does not write to Chroma or load Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from atlas.chunking import semantic_chunk_text
from atlas.config import REPO_ROOT, config
from atlas.embeddings import get_embedding_model


@dataclass(frozen=True)
class ChunkRecord:
    """One semantic chunk prepared for indexing (T5) or retrieval."""

    chunk_id: str
    doc_id: str
    text: str
    source: str
    domain: str
    chunk_index: int


@dataclass
class IngestResult:
    """Outcome of a full corpus ingest run."""

    chunks: List[ChunkRecord] = field(default_factory=list)
    documents: List[str] = field(default_factory=list)
    zero_chunk_documents: List[str] = field(default_factory=list)
    domain_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


def _repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def domain_from_source(source: str) -> str:
    """Derive domain from ``corpus/<domain>/...`` path segments."""
    parts = Path(source).as_posix().split("/")
    if len(parts) >= 2 and parts[0] == "corpus":
        return parts[1]
    raise ValueError(f"Cannot derive domain from source path: {source!r}")


def doc_id_from_source(source: str) -> str:
    """Deterministic document id: repository-relative path without ``.md``."""
    return Path(source).with_suffix("").as_posix()


def discover_markdown_files(corpus_dir: Optional[Path] = None) -> List[Path]:
    """Return sorted paths to all ``*.md`` files under the corpus directory."""
    root = Path(corpus_dir) if corpus_dir is not None else config.paths.corpus_dir
    return sorted(root.rglob("*.md"))


def ingest_document(
    path: Path,
    *,
    model: Optional[Any] = None,
    repo_root: Optional[Path] = None,
) -> List[ChunkRecord]:
    """Read one markdown file and return semantic chunk records.

    Empty or whitespace-only chunk texts are dropped. An empty document yields
    an empty list (caller may record it as a zero-chunk document).
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    path = Path(path)
    source = _repo_relative(path, root)
    domain = domain_from_source(source)
    doc_id = doc_id_from_source(source)

    text = path.read_text(encoding="utf-8")
    if model is None:
        model = get_embedding_model()
    if model is None:
        raise RuntimeError("Embedding model is unavailable; cannot chunk.")

    raw_chunks = semantic_chunk_text(text, model)
    records: List[ChunkRecord] = []
    for chunk_index, chunk_text in enumerate(raw_chunks):
        cleaned = chunk_text.strip()
        if not cleaned:
            continue
        # Re-number only non-empty chunks so indexes are contiguous from 0
        idx = len(records)
        records.append(
            ChunkRecord(
                chunk_id=f"{doc_id}:{idx}",
                doc_id=doc_id,
                text=cleaned,
                source=source,
                domain=domain,
                chunk_index=idx,
            )
        )
    return records


def ingest_corpus(
    corpus_dir: Optional[Path] = None,
    *,
    model: Optional[Any] = None,
    repo_root: Optional[Path] = None,
) -> IngestResult:
    """Ingest all markdown files under ``corpus/`` into chunk records."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    files = discover_markdown_files(corpus_dir)
    if model is None:
        model = get_embedding_model()
    if model is None:
        raise RuntimeError("Embedding model is unavailable; cannot ingest corpus.")

    result = IngestResult()
    for path in files:
        source = _repo_relative(path, root)
        result.documents.append(source)
        records = ingest_document(path, model=model, repo_root=root)
        if not records:
            result.zero_chunk_documents.append(source)
            continue
        result.chunks.extend(records)
        domain = records[0].domain
        result.domain_counts[domain] = result.domain_counts.get(domain, 0) + len(records)

    return result
