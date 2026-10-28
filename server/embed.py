"""임베딩 백엔드.

- model2vec: 정적(static) 다국어 임베딩. CPU에서 초고속, 한국어 지원.
- hashing : 외부 모델이 없을 때 쓰는 결정론적 폴백 (문자 n-gram signed hashing).
두 백엔드 모두 L2 정규화된 float32 벡터를 반환하므로 코사인 유사도 = 내적.
"""
from __future__ import annotations

import zlib
from typing import Sequence

import numpy as np

from . import config
from .kotext import index_terms


class Embedder:
    name: str = "base"
    dim: int = 0
    semantic: bool = False

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


def _l2(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return (mat / np.maximum(norms, 1e-9)).astype(np.float32)


class HashingEmbedder(Embedder):
    """문자 n-gram signed hashing -> 고정 차원 밀집 벡터.

    의미 임베딩은 아니지만 형태적 유사도를 안정적으로 잡고, 의존성이 0이다.
    """

    name = "hashing-ngram"
    semantic = False

    def __init__(self, dim: int | None = None):
        self.dim = int(dim or config.EMBED_DIM)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        m = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for term in index_terms(text or ""):
                h = zlib.crc32(term.encode("utf-8"))
                idx = h % self.dim
                sign = 1.0 if (h >> 15) & 1 else -1.0
                m[i, idx] += sign
        return _l2(m)


class Model2VecEmbedder(Embedder):
    name = "model2vec"
    semantic = True

    def __init__(self, model_name: str | None = None):
        from model2vec import StaticModel  # 지연 임포트

        self.model = StaticModel.from_pretrained(model_name or config.EMBED_MODEL)
        probe = self.model.encode(["테스트"], show_progress_bar=False)
        self.dim = int(probe.shape[1])

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(list(texts), show_progress_bar=False)
        return _l2(np.asarray(vecs, dtype=np.float32))


_CACHE: dict[str, Embedder] = {}


def get_embedder(backend: str | None = None) -> Embedder:
    backend = (backend or config.EMBED_BACKEND or "auto").lower()
    key = backend + ":" + config.EMBED_MODEL
    if key in _CACHE:
        return _CACHE[key]

    if backend in ("auto", "model2vec"):
        try:
            emb = Model2VecEmbedder()
            _CACHE[key] = emb
            return emb
        except Exception as exc:  # 모델 다운로드 실패 등
            if backend == "model2vec":
                raise
            print(f"[embed] model2vec 사용 불가({exc}); hashing 폴백으로 전환")

    emb = HashingEmbedder()
    _CACHE[key] = emb
    return emb
