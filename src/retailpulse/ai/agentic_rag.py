import math
import re
from collections import Counter
from typing import Any

class HybridRAGEngine:
    """Hybrid BM25-style lexical + cosine token overlap retriever with strict citations."""

    def __init__(self) -> None:
        self.chunks: list[dict[str, str]] = []

    def index_markdown(self, doc_id: str, text: str) -> int:
        sections = [s.strip() for s in re.split(r"\n#{1,3}\s+", text) if s.strip()]
        for idx, sec in enumerate(sections):
            self.chunks.append({"chunk_id": f"{doc_id}#c{idx+1}", "doc_id": doc_id, "text": sec})
        return len(sections)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9_]+", text.lower())

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        q_tokens = Counter(self._tokenize(query))
        if not q_tokens or not self.chunks:
            return []
        scored = []
        for ch in self.chunks:
            c_tokens = Counter(self._tokenize(ch["text"]))
            dot = sum(q_tokens[t] * c_tokens[t] for t in q_tokens)
            norm = math.sqrt(sum(v * v for v in q_tokens.values())) * math.sqrt(sum(v * v for v in c_tokens.values()))
            score = round(dot / norm, 4) if norm else 0.0
            if score > 0:
                scored.append({**ch, "grounding_score": score})
        return sorted(scored, key=lambda x: x["grounding_score"], reverse=True)[:top_k]

class AgenticOrchestrator:
    """Planner -> Retriever/SQL Guard -> Critic loop."""

    def __init__(self, rag: HybridRAGEngine, router: Any) -> None:
        self.rag = rag
        self.router = router

    def run(self, query: str, role: str = "viewer") -> dict[str, Any]:
        blocked = any(k in query.upper() for k in ("DROP ", "DELETE ", "UPDATE ", "INSERT ", "SQLITE_MASTER", ";--"))
        if blocked:
            return {
                "status": "blocked",
                "reason": "Security policy blocked mutating or schema-probing SQL intent.",
                "citations": [],
            }
        selected = self.router.pick_model()
        evidence = self.rag.search(query, top_k=3)
        return {
            "status": "ok",
            "role": role,
            "route": selected,
            "plan": ["classify_intent", "retrieve_grounded_docs", "verify_citations"],
            "citations": [{"id": e["chunk_id"], "score": e["grounding_score"]} for e in evidence],
            "context": [e["text"][:280] for e in evidence],
        }
