"""Hybrid search: BM25 (lexical) + embeddings (semantic), RRF fusion.

임베딩은 기본적으로 OpenAI Embeddings API를 쓴다. `WIKI_EMBED_PROVIDER=local`이면
fastembed로 로컬에서 돈다(네트워크 없음). 원격을 쓸 때 `sensitivity: confidential`
문서의 본문만 API로 보내지 않고 BM25로만 검색한다 (`WIKI_EMBED_SEND_SENSITIVE=1`로 해제).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import warnings
from pathlib import Path

import httpx
import numpy as np
from rank_bm25 import BM25Okapi

from .. import schema

_INCLUDE = ("00_Inbox", "01_Projects", "02_Areas", "03_Resources", "10_Claims", "30_Learning")
_RRF_K = 60
# fastembed의 multilingual e5는 large뿐이다 (small/base 미지원, 2026-08 확인)
_DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-large"
_DEFAULT_OPENAI_MODEL = "text-embedding-3-large"
_OPENAI_BASE_URL = "https://api.openai.com/v1"
_OPENAI_BATCH = 96            # 한 요청에 넣는 문서 수 (토큰 상한에 여유를 둔 보수적 값)
_OPENAI_TIMEOUT = 60.0
_OPENAI_RETRY_STATUS = (429, 500, 502, 503, 504)
_OPENAI_MAX_ATTEMPTS = 4
# e5는 문서/질의 접두사를 요구하고 OpenAI 모델은 요구하지 않는다
_E5_PREFIXES = ("passage: ", "query: ")
# 원격 API로 본문을 보내지 않는 민감도. 이 문서들은 BM25(로컬)로만 검색된다.
# work는 사용자 결정으로 전송 허용(2026-08-25). confidential은 설계 문서 §3.1이 회사 정책을
# 따르라고 해서 기본 차단으로 남긴다. 전부 보내려면 WIKI_EMBED_SEND_SENSITIVE=1.
_REMOTE_BLOCKED_SENSITIVITIES = ("confidential",)


def embed_provider() -> str:
    """`openai`(기본) 또는 `local`(fastembed, 오프라인)."""
    return (os.environ.get("WIKI_EMBED_PROVIDER") or "openai").strip().lower()


def embed_model_name() -> str:
    explicit = os.environ.get("WIKI_EMBED_MODEL")
    if explicit:
        return explicit
    return _DEFAULT_OPENAI_MODEL if embed_provider() == "openai" else _DEFAULT_LOCAL_MODEL


def embed_prefixes() -> tuple[str, str]:
    return ("", "") if embed_provider() == "openai" else _E5_PREFIXES


def remote_blocked_sensitivities() -> tuple[str, ...]:
    """원격 임베딩에서 제외할 민감도. 로컬 provider면 제외 대상이 없다."""
    if embed_provider() != "openai":
        return ()
    if (os.environ.get("WIKI_EMBED_SEND_SENSITIVE") or "").strip().lower() in ("1", "true", "yes"):
        return ()
    return _REMOTE_BLOCKED_SENSITIVITIES


def _embed_cache_dir() -> str:
    """Persistent cache for embedding weights/vectors: $WIKI_EMBED_CACHE > ~/.cache.

    fastembed defaults to the OS temp dir (e.g. /var/folders/.../T on macOS), which the
    OS may purge, forcing a multi-hundred-MB re-download. Pin it to a stable location.
    """
    override = os.environ.get("WIKI_EMBED_CACHE")
    return override or str(Path.home() / ".cache" / "wiki-toolkit" / "fastembed")


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
                     "path": str(p.relative_to(vault)),
                     "sensitivity": str(meta.get("sensitivity") or "")})
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
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{embed_provider()}-{embed_model_name()}")
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
    """prefixes는 (문서 접두사, 질의 접두사). 주입된 embed_fn에는 e5 기본값을 유지한다.

    skip_sensitivities에 걸린 문서는 embed_fn을 아예 타지 않고 0 벡터를 받는다.
    코사인 기여가 0이 되므로 BM25 신호만으로 순위에 들어온다 (검색에서 사라지지 않는다).
    """

    def __init__(self, docs: list[dict], embed_fn, vec_cache: VecCache | None = None,
                 prefixes: tuple[str, str] = _E5_PREFIXES,
                 skip_sensitivities: tuple[str, ...] = ()):
        self.docs = docs
        self._embed_fn = embed_fn
        self._query_prefix = prefixes[1]
        token_lists = [tokenize(d["text"]) for d in docs]
        # 전 문서가 빈 토큰이면 BM25Okapi가 ZeroDivisionError로 죽는다
        self._bm25 = BM25Okapi(token_lists) if any(token_lists) else None
        blocked = set(skip_sensitivities)
        sent = [i for i, d in enumerate(docs)
                if str(d.get("sensitivity") or "") not in blocked]
        vecs = _embed_texts([prefixes[0] + docs[i]["text"] for i in sent], embed_fn, vec_cache)
        self._doc_mat = None
        if vecs:
            dim = max(len(v) for v in vecs)
            mat = np.zeros((len(docs), dim), dtype=np.float32)
            for pos, i in enumerate(sent):
                v = vecs[pos]
                if len(v) == dim:
                    mat[i] = np.asarray(v, dtype=np.float32)
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
            qv = np.asarray(self._embed_fn([self._query_prefix + q])[0], dtype=np.float32)
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


def _local_embedder():
    """fastembed(ONNX) 로컬 임베딩. 첫 실행에서 가중치 2.1GB를 내려받는다."""
    with warnings.catch_warnings():
        # e5는 원래 mean pooling 모델이라 fastembed 0.8의 CLS->mean 전환 안내는 무해하다
        warnings.filterwarnings("ignore", message=".*mean pooling instead of CLS.*")
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name=embed_model_name(), cache_dir=_embed_cache_dir())

    def embed(texts):
        return [list(v) for v in model.embed(list(texts))]

    return embed


def _openai_client() -> httpx.Client:
    """테스트가 MockTransport로 갈아끼우는 지점."""
    base = (os.environ.get("WIKI_OPENAI_BASE_URL") or _OPENAI_BASE_URL).rstrip("/")
    return httpx.Client(base_url=base, timeout=_OPENAI_TIMEOUT)


def _openai_embed_batch(client: httpx.Client, key: str, model: str,
                        batch: list[str], dim: str | None) -> list[list[float]]:
    payload: dict = {"model": model, "input": batch}
    if dim:
        payload["dimensions"] = int(dim)
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(_OPENAI_MAX_ATTEMPTS):
        last = attempt == _OPENAI_MAX_ATTEMPTS - 1
        try:
            resp = client.post("/embeddings", json=payload, headers=headers)
        except httpx.HTTPError as e:
            if last:
                raise RuntimeError(
                    f"임베딩 API에 연결하지 못했다 ({type(e).__name__}: {e}). "
                    f"네트워크를 확인하거나 WIKI_EMBED_PROVIDER=local로 로컬 임베딩을 써라.") from e
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in _OPENAI_RETRY_STATUS and not last:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (401, 403):
            raise RuntimeError(
                f"임베딩 API가 키를 거부했다 (HTTP {resp.status_code}). OPENAI_API_KEY를 확인해라 "
                f"(.env 또는 셸 export). 로컬로 돌리려면 WIKI_EMBED_PROVIDER=local.")
        if resp.is_error:
            raise RuntimeError(
                f"임베딩 API가 HTTP {resp.status_code}를 돌려줬다: {resp.text[:300]}")
        rows = sorted(resp.json()["data"], key=lambda r: r["index"])
        if len(rows) != len(batch):
            raise RuntimeError(
                f"embedding API가 입력 {len(batch)}개에 벡터 {len(rows)}개를 돌려줬다")
        return [[float(x) for x in r["embedding"]] for r in rows]
    raise RuntimeError("embedding API 재시도 소진")  # 도달 불가: 마지막 시도는 raise/return


def _openai_embedder():
    """OpenAI Embeddings API. vault 본문이 이 경로로 외부에 나간다."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY가 없다. 키를 설정하거나 WIKI_EMBED_PROVIDER=local로 "
            "로컬 임베딩(fastembed)으로 돌려라.")
    model = embed_model_name()
    dim = os.environ.get("WIKI_EMBED_DIM")

    def embed(texts):
        items = [str(t) for t in texts]
        if not items:
            return []
        out: list[list[float]] = []
        with _openai_client() as client:
            for i in range(0, len(items), _OPENAI_BATCH):
                out.extend(_openai_embed_batch(client, key, model,
                                               items[i:i + _OPENAI_BATCH], dim))
        return out

    return embed


def _default_embedder():
    return _openai_embedder() if embed_provider() == "openai" else _local_embedder()


def _empty_embedder(texts):
    return [[] for _ in texts]


def build_index(vault: Path, embed_fn=None, vec_cache: VecCache | None = None) -> SearchIndex:
    docs = iter_docs(vault)
    prefixes, skip = _E5_PREFIXES, ()
    if embed_fn is None:
        # 빈 vault면 모델 로드도, API 키 요구도 하지 않는다
        if not docs:
            return SearchIndex([], _empty_embedder)
        embed_fn = _default_embedder()
        prefixes, skip = embed_prefixes(), remote_blocked_sensitivities()
        if vec_cache is None:
            vec_cache = _default_vec_cache()
    return SearchIndex(docs, embed_fn, vec_cache, prefixes=prefixes, skip_sensitivities=skip)


class IndexCache:
    """vault 지문이 바뀌면 자동으로 인덱스를 다시 만드는 세션 캐시 (서버/도구용)."""

    def __init__(self, vault: Path, embed_fn=None):
        self._vault = Path(vault)
        self._embed_fn = embed_fn
        self._injected = embed_fn is not None
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
        prefixes = _E5_PREFIXES if self._injected else embed_prefixes()
        skip = () if self._injected else remote_blocked_sensitivities()
        self._idx = SearchIndex(docs, self._embed_fn, self._vec_cache,
                                prefixes=prefixes, skip_sensitivities=skip)
        self._fp = fp
        return self._idx
