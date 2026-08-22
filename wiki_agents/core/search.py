"""Hybrid local search: BM25 (lexical) + local embeddings (semantic), RRF fusion."""
from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .. import schema

_INCLUDE = ("00_Inbox", "01_Projects", "02_Areas", "03_Resources", "10_Claims", "30_Learning")
_RRF_K = 60
# fastembed의 multilingual e5는 large뿐이다 (small/base 미지원, 2026-08 확인)
_DEFAULT_EMBED_MODEL = "intfloat/multilingual-e5-large"


def embed_model_name() -> str:
    return os.environ.get("WIKI_EMBED_MODEL", _DEFAULT_EMBED_MODEL)


def _embed_cache_dir() -> str:
    """Persistent cache for embedding weights/vectors: $WIKI_EMBED_CACHE > ~/.cache.

    fastembed defaults to the OS temp dir (e.g. /var/folders/.../T on macOS), which the
    OS may purge, forcing a multi-hundred-MB re-download. Pin it to a stable location.
    """
    override = os.environ.get("WIKI_EMBED_CACHE")
    return override or str(Path.home() / ".cache" / "wiki-agents" / "fastembed")


def tokenize(text: str) -> list[str]:
    """ASCII 단어는 그대로, 한글 연속열은 unigram + 2-gram (BM25용).

    unigram이 없으면 한 글자 질의("밥")가 문서의 "밥솥"("밥솥" bigram만 생성)과
    구조적으로 매치 불가능해진다. 흔한 글자는 idf가 낮아 노이즈는 제한된다.
    """
    toks: list[str] = []
    for m in re.finditer(r"[a-z0-9]+|[가-힣]+", text.lower()):
        t = m.group(0)
        if "가" <= t[0] <= "힣" and len(t) > 1:
            toks.extend(t)
            toks.extend(t[i:i + 2] for i in range(len(t) - 1))
        else:
            toks.append(t)
    return toks


def _md_files(vault: Path) -> list[Path]:
    vault = Path(vault)
    files = sorted(vault.glob("*.md"))  # 루트의 설계 문서 등은 비재귀로 포함
    for root in _INCLUDE:
        base = vault / root
        if base.exists():
            files.extend(sorted(base.rglob("*.md")))
    return files


def iter_docs(vault: Path) -> list[dict]:
    vault = Path(vault)
    docs: list[dict] = []
    for p in _md_files(vault):
        try:
            meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 - skip unreadable vault files; indexing is best-effort
            continue
        title = (meta.get("title") or meta.get("name") or meta.get("claim")
                 or meta.get("topic") or p.stem)
        ref = meta.get("id") or meta.get("name") or str(p.relative_to(vault))
        head = " ".join(str(meta.get(k, "")) for k in ("title", "name", "claim", "topic"))
        text = f"{head}\n{body}".strip()
        docs.append({"ref": str(ref), "title": str(title), "text": text,
                     "path": str(p.relative_to(vault))})
    return docs


def vault_fingerprint(vault: Path) -> int:
    """md 파일 목록 + mtime + 크기의 해시. 바뀌면 인덱스를 다시 만들어야 한다."""
    items = []
    for p in _md_files(vault):
        try:
            st = p.stat()
        except OSError:  # 깨진 심링크, glob과 stat 사이의 삭제 race
            continue
        items.append((str(p), st.st_mtime_ns, st.st_size))
    return hash(tuple(items))


class VecCache:
    """텍스트 해시 -> 임베딩 벡터 디스크 캐시. 바뀐 문서만 재임베딩하게 한다."""

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        # 오염된 항목(벡터가 아닌 값)은 로드에서 걸러 자가 복구한다
        self._data = {
            k: v for k, v in data.items()
            if isinstance(v, list) and v and all(isinstance(x, int | float) for x in v)
        }
        self._dirty = False

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        return self._data.get(self._key(text))

    def put(self, text: str, vec) -> None:
        self._data[self._key(text)] = [float(x) for x in vec]
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data), encoding="utf-8")
        tmp.replace(self.path)  # 원자적 교체: 저장 중 종료돼도 기존 캐시가 살아남는다
        self._dirty = False


def _default_vec_cache() -> VecCache:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", embed_model_name())
    return VecCache(Path(_embed_cache_dir()) / f"vecs-{safe}.json")


def _embed_texts(texts: list[str], embed_fn, vec_cache: VecCache | None) -> list[list[float]]:
    if not texts:
        return []
    if vec_cache is None:
        return [list(v) for v in embed_fn(texts)]
    missing = list(dict.fromkeys(t for t in texts if vec_cache.get(t) is None))
    if missing:
        for t, v in zip(missing, embed_fn(missing), strict=True):
            vec_cache.put(t, v)
        vec_cache.save()
    result = [vec_cache.get(t) for t in texts]
    # 모델이 바뀌는 등으로 캐시 차원이 섞이면 전체 재임베딩으로 자가 복구
    if len({len(v) for v in result}) > 1:
        fresh = [list(map(float, v)) for v in embed_fn(texts)]
        for t, v in zip(texts, fresh, strict=True):
            vec_cache.put(t, v)
        vec_cache.save()
        return fresh
    return result  # type: ignore[return-value]


def _competition_ranks(scores) -> list[int]:
    """동점은 같은 순위 (competition ranking: 순위 = 자기보다 큰 점수 개수).

    안정 정렬 기반 순위는 동점(특히 전부 0)일 때 파일 순회 순서를 순위로 둔갑시켜
    RRF 융합에서 실제 신호를 뒤집는다 (실측으로 확인된 결함).
    """
    s = [float(x) for x in scores]
    uniq = sorted(set(s), reverse=True)
    counts: dict[float, int] = {}
    for x in s:
        counts[x] = counts.get(x, 0) + 1
    start: dict[float, int] = {}
    c = 0
    for u in uniq:
        start[u] = c
        c += counts[u]
    return [start[x] for x in s]


class SearchIndex:
    def __init__(self, docs: list[dict], embed_fn, vec_cache: VecCache | None = None):
        self.docs = docs
        self._embed_fn = embed_fn
        token_lists = [tokenize(d["text"]) for d in docs]
        # 전 문서가 빈 토큰이면 BM25Okapi가 ZeroDivisionError로 죽는다
        self._bm25 = BM25Okapi(token_lists) if any(token_lists) else None
        # e5 계열은 문서에 passage:, 질의에 query: 접두사를 요구한다
        vecs = _embed_texts(["passage: " + d["text"] for d in docs], embed_fn, vec_cache)
        self._doc_mat = None
        if vecs:
            mat = np.asarray(vecs, dtype=np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            self._doc_mat = mat / norms

    def query(self, q: str, k: int = 8) -> list[dict]:
        if not self.docs or not q.strip():
            return []
        n = len(self.docs)
        bm = self._bm25.get_scores(tokenize(q)) if self._bm25 is not None \
            else np.zeros(n, dtype=np.float32)
        if self._doc_mat is not None:
            qv = np.asarray(self._embed_fn(["query: " + q])[0], dtype=np.float32)
            qn = float(np.linalg.norm(qv))
            cos = self._doc_mat @ (qv / qn if qn else qv)
        else:
            cos = np.zeros(n, dtype=np.float32)
        bm_rank = _competition_ranks(bm)
        cos_rank = _competition_ranks(cos)
        fused = sorted(
            ((1.0 / (_RRF_K + bm_rank[i]) + 1.0 / (_RRF_K + cos_rank[i]), i) for i in range(n)),
            key=lambda t: (-t[0], t[1]),  # 완전 동점만 안정적으로 파일 순
        )
        out = []
        for score, i in fused[:k]:
            d = self.docs[i]
            out.append({"ref": d["ref"], "title": d["title"],
                        "score": round(score, 6), "snippet": d["text"][:200]})
        return out


def _default_embedder():
    with warnings.catch_warnings():
        # e5는 원래 mean pooling 모델이라 fastembed 0.8의 CLS->mean 전환 안내는 무해하다
        warnings.filterwarnings("ignore", message=".*mean pooling instead of CLS.*")
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name=embed_model_name(), cache_dir=_embed_cache_dir())

    def embed(texts):
        return [list(v) for v in model.embed(list(texts))]

    return embed


def _empty_embedder(texts):
    return [[] for _ in texts]


def build_index(vault: Path, embed_fn=None, vec_cache: VecCache | None = None) -> SearchIndex:
    docs = iter_docs(vault)
    if embed_fn is None:
        if not docs:  # 빈 vault에 2.2GB 임베딩 모델을 로드할 이유가 없다
            return SearchIndex([], _empty_embedder)
        embed_fn = _default_embedder()
        if vec_cache is None:
            vec_cache = _default_vec_cache()
    return SearchIndex(docs, embed_fn, vec_cache)


class IndexCache:
    """vault 지문이 바뀌면 자동으로 인덱스를 다시 만드는 세션 캐시 (서버/도구용)."""

    def __init__(self, vault: Path, embed_fn=None):
        self._vault = Path(vault)
        self._embed_fn = embed_fn
        self._vec_cache = _default_vec_cache() if embed_fn is None else None
        self._fp: int | None = None
        self._idx: SearchIndex | None = None

    def get(self, force: bool = False) -> SearchIndex:
        fp = vault_fingerprint(self._vault)
        if not force and self._idx is not None and fp == self._fp:
            return self._idx
        docs = iter_docs(self._vault)
        if not docs and self._embed_fn is None:
            self._idx = SearchIndex([], _empty_embedder)
            self._fp = fp
            return self._idx
        if self._embed_fn is None:
            self._embed_fn = _default_embedder()
        self._idx = SearchIndex(docs, self._embed_fn, self._vec_cache)
        self._fp = fp
        return self._idx
