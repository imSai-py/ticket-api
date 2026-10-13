"""Knowledge Base article retrieval module using pure-Python BM25 scoring."""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it", "it's", "its",
    "itself", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "she", "should", "shouldn't", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "were", "weren't", "what",
    "when", "where", "which", "while", "who", "whom", "why", "with", "won't", "would", "wouldn't",
    "you", "your", "yours", "yourself", "yourselves",
}


@dataclass
class KBArticle:
    """Represents a knowledge base article."""

    article_id: str
    title: str
    content: str
    path: Path


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alpha-numeric words excluding stop words."""
    tokens = re.findall(r"\b[a-zA-Z0-9_\-]+\b", text.lower())
    return [t for t in tokens if len(t) > 1 and t not in STOP_WORDS]


class KBRetriever:
    """Pure-Python BM25 knowledge base retriever."""

    def __init__(self, kb_dir: Optional[Path] = None, k1: float = 1.5, b: float = 0.75):
        if kb_dir is None:
            self.kb_dir = Path(__file__).resolve().parent.parent / "kb"
        else:
            self.kb_dir = Path(kb_dir).resolve()

        self.k1 = k1
        self.b = b
        self.articles: List[KBArticle] = []
        self.doc_tokens: List[List[str]] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.idf: Dict[str, float] = {}

        self._load_and_index()

    def _load_and_index(self) -> None:
        """Load markdown articles from kb_dir and compute BM25 index parameters."""
        if not self.kb_dir.exists():
            return

        articles = []
        for file_path in sorted(self.kb_dir.glob("*.md")):
            content = file_path.read_text(encoding="utf-8")
            match = re.search(r"^(?:#\s*)?(KB-\d+)(?::\s*([^\n\r]+))?", content)
            if match:
                article_id = match.group(1).strip()
                title = match.group(2).strip() if match.group(2) else file_path.stem
            else:
                article_id = file_path.stem.split("-")[0]
                title = file_path.stem

            articles.append(
                KBArticle(
                    article_id=article_id,
                    title=title,
                    content=content,
                    path=file_path,
                )
            )

        self.articles = articles
        num_docs = len(self.articles)
        if num_docs == 0:
            return

        # Boost title tokens by appending them twice
        self.doc_tokens = []
        total_len = 0
        df: Dict[str, int] = {}

        for art in self.articles:
            tokens = tokenize(art.content) + tokenize(art.title) * 2
            self.doc_tokens.append(tokens)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            unique_terms = set(tokens)
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1

        self.avg_doc_len = total_len / num_docs

        for term, doc_count in df.items():
            self.idf[term] = math.log(((num_docs - doc_count + 0.5) / (doc_count + 0.5)) + 1.0)

    def retrieve(
        self,
        subject: str,
        text: str,
        top_k: int = 2,
        min_score: float = 0.5,
    ) -> List[KBArticle]:
        """Score articles against ticket subject and body and return top matches."""
        query_text = f"{subject} {text}"
        query_tokens = tokenize(query_text)
        if not query_tokens or not self.articles:
            return []

        scores: List[float] = []
        for idx, doc_tokens in enumerate(self.doc_tokens):
            score = 0.0
            doc_len = self.doc_lengths[idx]
            token_counts: Dict[str, int] = {}
            for t in doc_tokens:
                token_counts[t] = token_counts.get(t, 0) + 1

            for q_term in query_tokens:
                if q_term not in self.idf:
                    continue
                tf = token_counts.get(q_term, 0)
                if tf == 0:
                    continue
                idf = self.idf[q_term]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))
                score += idf * (numerator / denominator)

            scores.append(score)

        ranked = sorted(
            [(self.articles[i], scores[i]) for i in range(len(self.articles)) if scores[i] >= min_score],
            key=lambda x: x[1],
            reverse=True,
        )

        return [article for article, _ in ranked[:top_k]]

    @staticmethod
    def format_articles_for_prompt(articles: Optional[List[KBArticle]]) -> str:
        """Format retrieved articles into a clean context string for LLM prompts."""
        if not articles:
            return "No relevant knowledge base articles were found."

        parts = []
        for art in articles:
            parts.append(f"--- Article {art.article_id}: {art.title} ---\n{art.content.strip()}")
        return "\n\n".join(parts)


def format_articles_for_prompt(articles: Optional[List[KBArticle]]) -> str:
    return KBRetriever.format_articles_for_prompt(articles)
