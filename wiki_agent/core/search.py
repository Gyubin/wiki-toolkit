"""Hybrid local search: BM25 (lexical) + local embeddings (semantic), RRF fusion."""
from __future__ import annotations

import math
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from .. import schema

_INCLUDE = ("00_Inbox", "01_Projects", "02_Areas", "03_Resources", "10_Claims", "30_Learning")
_RRF_K = 60


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def iter_docs(vault: Path) -> list[dict]:
    vault = Path(vault)
    docs: list[dict] = []
    for root in _INCLUDE:
        base = vault / root
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            try:
                meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            title = (meta.get("title") or meta.get("name") or meta.get("claim")
                     or meta.get("topic") or p.stem)
            ref = meta.get("id") or meta.get("name") or str(p.relative_to(vault))
            head = " ".join(str(meta.get(k, "")) for k in ("title", "name", "claim", "topic"))
            text = f"{head}\n{body}".strip()
            docs.append({"ref": str(ref), "title": str(title), "text": text,
                         "path": str(p.relative_to(vault))})
    return docs


def _cosine(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0


class SearchIndex:
    def __init__(self, docs: list[dict], embed_fn):
        self.docs = docs
        self._embed_fn = embed_fn
        self._bm25 = BM25Okapi([tokenize(d["text"]) for d in docs]) if docs else None
        self._doc_vecs = embed_fn([d["text"] for d in docs]) if docs else []

    def query(self, q: str, k: int = 8) -> list[dict]:
        if not self.docs or not q.strip():
            return []
        n = len(self.docs)
        bm = self._bm25.get_scores(tokenize(q))
        qvec = self._embed_fn([q])[0]
        cos = [_cosine(qvec, v) for v in self._doc_vecs]
        bm_rank = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: bm[i], reverse=True))}
        cos_rank = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: cos[i], reverse=True))}
        fused = sorted(
            ((1.0 / (_RRF_K + bm_rank[i]) + 1.0 / (_RRF_K + cos_rank[i]), i) for i in range(n)),
            reverse=True,
        )
        out = []
        for score, i in fused[:k]:
            d = self.docs[i]
            out.append({"ref": d["ref"], "title": d["title"],
                        "score": round(score, 6), "snippet": d["text"][:200]})
        return out


def _default_embedder():
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name="intfloat/multilingual-e5-large")

    def embed(texts):
        return [list(v) for v in model.embed(list(texts))]

    return embed


def build_index(vault: Path, embed_fn=None) -> SearchIndex:
    return SearchIndex(iter_docs(vault), embed_fn or _default_embedder())
