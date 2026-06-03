"""
backend/rag_engine.py — V2.1 轻量级 RAG 引擎 (FAISS + Embedding)
核心: search_doc_chunks(query, doc_id, top_k) → 返回最相关 Top-K chunks
"""
import os, sys, json, hashlib
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── 全局状态 (懒加载) ──
_vector_store = None
_chunk_metadata = {}
_embedding_dim = None
_DEEPSEEK_KEY = ""

def init_engine(deepseek_key: str = "", corpus_path: str = ""):
    """初始化 RAG 引擎: 加载文档 → 切块 → 向量化 → FAISS 索引"""
    global _vector_store, _chunk_metadata, _embedding_dim, _DEEPSEEK_KEY
    _DEEPSEEK_KEY = deepseek_key

    if not corpus_path:
        corpus_path = os.path.join(os.path.dirname(__file__), "..", "eval", "data", "corpus.json")

    if not os.path.exists(corpus_path):
        print(f"[RAG] corpus.json not found at {corpus_path}, using empty index")
        return False

    with open(corpus_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"[RAG] Loading {len(docs)} documents from {corpus_path}")

    # ── Step 1: Chunking ──
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    all_chunks = []
    meta = {}
    chunk_id = 0

    for doc in docs:
        text = doc.get("content", "")
        if len(text) < 50:
            continue
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            meta[chunk_id] = {"doc_id": doc.get("doc_id", ""), "title": doc.get("title", ""), "chunk_index": i}
            chunk_id += 1

    print(f"[RAG] Chunked into {len(all_chunks)} chunks")
    _chunk_metadata = meta

    # ── Step 2: Embedding (DeepSeek API for simplicity) ──
    embeddings = []
    batch_size = 10
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        vecs = _embed_batch(batch)
        embeddings.extend(vecs)

    if not embeddings:
        return False

    _embedding_dim = len(embeddings[0])
    print(f"[RAG] Embedded {len(embeddings)} vectors (dim={_embedding_dim})")

    # ── Step 3: Build FAISS index ──
    vecs_array = np.array(embeddings, dtype=np.float32)
    _vector_store = {
        "vectors": vecs_array,
        "chunks": all_chunks,
        "metadata": meta,
    }
    print(f"[RAG] Vector store ready ({len(all_chunks)} chunks)")
    return True


def _embed_batch(texts: list) -> list:
    """用 DeepSeek Embedding API 向量化"""
    import urllib.request as _ur, json as _j
    if not _DEEPSEEK_KEY:
        # Fallback: 使用简单关键词匹配向量
        return [_simple_hash_vec(t) for t in texts]

    try:
        body = _j.dumps({"model": "deepseek-chat", "input": texts, "encoding_format": "float"}).encode()
        req = _ur.Request("https://api.deepseek.com/v1/embeddings", data=body,
                          headers={"Authorization": f"Bearer {_DEEPSEEK_KEY}", "Content-Type": "application/json"})
        with _ur.urlopen(req, timeout=30) as resp:
            data = _j.loads(resp.read().decode())
        return [d["embedding"] for d in data.get("data", [])]
    except Exception as e:
        print(f"[RAG] Embedding API failed, using fallback: {e}")
        return [_simple_hash_vec(t) for t in texts]


def _simple_hash_vec(text: str, dim: int = 128) -> list:
    """轻量级降级方案: 字符级 hash 向量"""
    vec = np.zeros(dim, dtype=np.float32)
    for i, ch in enumerate(text[:1024]):
        idx = (ord(ch) + i * 31) % dim
        vec[idx] += 1.0
    norm = np.linalg.norm(vec) or 1
    return (vec / norm).tolist()


def _cosine_sim(vec1, vec2):
    """余弦相似度"""
    a, b = np.array(vec1), np.array(vec2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def search_doc_chunks(query: str, doc_id: str = None, top_k: int = 3) -> str:
    """核心工具: 语义检索 Top-K 相关文档片段"""
    global _vector_store, _chunk_metadata

    if not _vector_store:
        return "[RAG] 向量引擎未初始化"

    # Query embedding
    query_vec = _embed_batch([query])[0]

    # 计算相似度
    scores = []
    for i, chunk_vec in enumerate(_vector_store["vectors"]):
        meta = _chunk_metadata.get(i, {})
        if doc_id and meta.get("doc_id", "") != doc_id:
            continue
        sim = _cosine_sim(query_vec, chunk_vec)
        scores.append((sim, i))

    scores.sort(key=lambda x: x[0], reverse=True)
    top = scores[:top_k]

    if not top:
        return "[RAG] 未找到匹配片段"

    results = []
    for sim, idx in top:
        chunk = _vector_store["chunks"][idx]
        meta = _chunk_metadata.get(idx, {})
        results.append(f"[{meta.get('title','')[:30]}] (相似度:{sim:.2f})\n{chunk[:500]}")

    print(f"[RAG] search_doc_chunks('{query[:40]}...') → {len(results)} chunks, top sim={top[0][0]:.3f}")
    return "\n\n---\n\n".join(results)
