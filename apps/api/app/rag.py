import hashlib
import math
import os
import re
from collections import Counter

from fastapi import HTTPException
from openai import OpenAI

from . import storage
from .authz import can_read_manual
from .config import settings
from .schemas import EvaluationResult, Manual, SourceChunk, User


class OpenAIKeyMissing(RuntimeError):
    pass


def require_openai_client() -> OpenAI:
    if not settings.openai_api_key:
        raise OpenAIKeyMissing("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key)


def chunk_text(text: str, size: int = 260, overlap: int = 60) -> list[str]:
    """Chunking: 長い文書を検索しやすい小さな単位に分割する。

    LLMは長い社内マニュアルを一度に正確に扱いにくい。そこで文章をchunkに分け、
    質問に関係するchunkだけを検索して回答に渡す。overlapは前後の文脈を少し重ねる設定。
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        chunks.append(normalized[start : start + size])
        if start + size >= len(normalized):
            break
        start += max(1, size - overlap)
    return chunks


def demo_embedding(text: str, dimensions: int = 64) -> list[float]:
    """テスト用の決定的なEmbedding。

    本番のEmbeddingはOpenAI APIを使う。この関数はAPIキーなしでも権限制御や評価ロジックを
    テストできるようにするための代替で、通常の回答生成APIでは使わない。
    """
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = digest[0] % dimensions
        sign = 1 if digest[1] % 2 == 0 else -1
        vector[index] += sign * (1 + len(token) / 10)
    return normalize(vector)


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = require_openai_client()
    response = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def ingest_manual(manual: Manual, use_demo_embeddings: bool = False) -> int:
    chunks = chunk_text(manual.body)
    if use_demo_embeddings:
        embeddings = [demo_embedding(text) for text in chunks]
    else:
        embeddings = embed_texts(chunks)
    return storage.replace_chunks(manual, zip(chunks, embeddings))


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ンー]+", text.lower())


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(size))


def keyword_score(query: str, text: str, title: str, tags: list[str]) -> float:
    q = Counter(tokenize(query))
    haystack = Counter(tokenize(" ".join([text, title, " ".join(tags)])))
    if not q:
        return 0.0
    matches = sum(min(count, haystack[token]) for token, count in q.items())
    return matches / sum(q.values())


def search(user: User, query: str, top_k: int = 5, use_demo_embeddings: bool = False) -> tuple[list[SourceChunk], int]:
    """Hybrid Search: ベクトル検索とキーワード検索を組み合わせる。

    ベクトル検索は「意味が近い」文書に強く、キーワード検索は店舗名や固有名詞に強い。
    社内検索では両方が必要なので、vector_scoreとkeyword_scoreを足して候補を作る。
    """
    chunks = storage.list_chunks()
    if use_demo_embeddings:
        query_embedding = demo_embedding(query)
    else:
        query_embedding = embed_texts([query])[0]

    scored = []
    filtered_out = 0
    for chunk in chunks:
        manual = storage.get_manual(chunk["manual_id"])
        if not can_read_manual(user, manual):
            filtered_out += 1
            continue
        vector = cosine(query_embedding, chunk["embedding"])
        keyword = keyword_score(query, chunk["text"], chunk["manual_title"], chunk["tags"])
        hybrid = 0.72 * vector + 0.28 * keyword
        scored.append((chunk, vector, keyword, hybrid))

    scored.sort(key=lambda item: item[3], reverse=True)
    candidates = scored[: max(top_k * 3, top_k)]
    reranked = rerank(query, candidates)[:top_k]
    return [
        SourceChunk(
            chunk_id=chunk["id"],
            manual_id=chunk["manual_id"],
            manual_title=chunk["manual_title"],
            manual_version=chunk["manual_version"],
            text=chunk["text"],
            vector_score=round(vector, 4),
            keyword_score=round(keyword, 4),
            hybrid_score=round(hybrid, 4),
            rerank_score=round(rerank_score, 4),
        )
        for chunk, vector, keyword, hybrid, rerank_score in reranked
    ], filtered_out


def rerank(query: str, candidates: list[tuple[dict, float, float, float]]) -> list[tuple[dict, float, float, float, float]]:
    """Rerank: 最初の検索候補を質問に近い順へ並び替える。

    MVPでは軽量なスコア合成で実装する。将来は専用Rerankモデルに差し替えられる。
    RAGではRerank後の上位chunkだけをLLMに渡すことで、根拠の質を上げる。
    """
    query_terms = set(tokenize(query))
    reranked = []
    for chunk, vector, keyword, hybrid in candidates:
        text_terms = set(tokenize(chunk["text"]))
        coverage = len(query_terms & text_terms) / max(1, len(query_terms))
        rerank_score = 0.62 * hybrid + 0.38 * coverage
        reranked.append((chunk, vector, keyword, hybrid, rerank_score))
    reranked.sort(key=lambda item: item[4], reverse=True)
    return reranked


def generate_answer(query: str, sources: list[SourceChunk]) -> str:
    client = require_openai_client()
    context = "\n\n".join(
        f"[{idx + 1}] {source.manual_title} v{source.manual_version}: {source.text}"
        for idx, source in enumerate(sources)
    )
    response = client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {
                "role": "system",
                "content": "あなたはネイル会社の社内マニュアル検索AIです。根拠にない内容は推測せず、参照番号付きで日本語で簡潔に回答してください。",
            },
            {"role": "user", "content": f"質問: {query}\n\n根拠候補:\n{context}"},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def answer(user: User, query: str, top_k: int = 5) -> tuple[str, list[SourceChunk], int, str]:
    sources, filtered_out = search(user, query, top_k=top_k)
    if not sources:
        text = "参照可能なマニュアルから回答できる根拠が見つかりませんでした。"
    else:
        text = generate_answer(query, sources)
    audit_id = storage.create_audit_log(
        user.id,
        query,
        text,
        [source.model_dump() for source in sources],
        filtered_out,
    )
    return text, sources, filtered_out, audit_id


def run_evaluation(top_k: int = 5) -> list[EvaluationResult]:
    """Evaluation: Golden Datasetで検索品質を測る。

    Recallは「本来見つけるべき文書を拾えた割合」。
    Precisionは「取ってきた文書のうち正解だった割合」。
    権限漏洩チェックは、ユーザーが読めない文書が検索結果に混ざっていないかを見る。
    """
    results: list[EvaluationResult] = []
    for item in storage.list_golden_questions():
        user = storage.get_user(item["user_id"])
        sources, _ = search(user, item["query"], top_k=top_k, use_demo_embeddings=not bool(settings.openai_api_key))
        expected = set(item["expected_manual_ids"])
        retrieved = [source.manual_id for source in sources]
        retrieved_set = set(retrieved)
        readable_expected = {
            manual_id for manual_id in expected if can_read_manual(user, storage.get_manual(manual_id))
        }
        recall = len(readable_expected & retrieved_set) / max(1, len(readable_expected))
        precision = len(readable_expected & retrieved_set) / max(1, len(retrieved_set))
        leaked = [
            manual_id for manual_id in retrieved_set if not can_read_manual(user, storage.get_manual(manual_id))
        ]
        results.append(
            EvaluationResult(
                user_id=user.id,
                query=item["query"],
                expected_manual_ids=list(readable_expected),
                retrieved_manual_ids=retrieved,
                recall=round(recall, 4),
                precision=round(precision, 4),
                top_k_hit=bool(readable_expected & retrieved_set),
                leaked_manual_ids=leaked,
            )
        )
    return results


def api_error_for_openai_missing(exc: OpenAIKeyMissing) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "detail": str(exc),
            "hint": "apps/api/.env に OPENAI_API_KEY を手動設定してAPIを再起動してください。",
        },
    )

