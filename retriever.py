"""
retriever.py — Hybrid retrieval engine for SHL product catalog.

Combines TF-IDF vector search with keyword matching and metadata filters
to find the most relevant SHL assessments for a given query.
"""
import json
import math
import re
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ── Constants ───────────────────────────────────────────────────────────────────

CATALOG_PATH = Path(__file__).parent / "catalog.json"

TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgment",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


# ── Catalog Loader ──────────────────────────────────────────────────────────────

def load_catalog() -> List[Dict]:
    """Load the scraped catalog from JSON."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog.json not found at {CATALOG_PATH}")
    with open(CATALOG_PATH) as f:
        data = json.load(f)
    # Ensure each product has required fields
    for p in data:
        p.setdefault("name", "")
        p.setdefault("description", "")
        p.setdefault("testTypes", [])
        p.setdefault("duration_minutes", None)
        p.setdefault("languages", [])
        p.setdefault("jobLevels", [])
        p.setdefault("remoteSupported", False)
        p.setdefault("adaptiveIRT", False)
        p.setdefault("url", "")
        p.setdefault("slug", "")
    return data


def build_search_text(product: Dict) -> str:
    """Build a rich searchable text string for a product."""
    parts = [
        product.get("name", ""),
        product.get("description", ""),
        " ".join(product.get("jobLevels", [])),
        " ".join(product.get("languages", [])),
    ]
    # Add test type labels
    for code in product.get("testTypes", []):
        if code in TYPE_LABELS:
            parts.append(TYPE_LABELS[code])
    # Add slug words (useful for keyword matching)
    slug = product.get("slug", "")
    parts.append(slug.replace("-", " "))
    return " ".join(parts).lower()


# ── Retriever Class ─────────────────────────────────────────────────────────────

class SHLRetriever:
    """Hybrid TF-IDF + keyword retriever for SHL product catalog."""

    def __init__(self, catalog: Optional[List[Dict]] = None):
        self.catalog = catalog or load_catalog()
        self._build_index()

    def _build_index(self):
        """Build TF-IDF index and keyword lookup structures."""
        self.search_texts = [build_search_text(p) for p in self.catalog]

        # TF-IDF vectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.search_texts)

        # Build keyword index for exact matching
        self.name_index = {}  # lowercase name → index
        self.slug_index = {}  # slug → index
        for i, p in enumerate(self.catalog):
            name_lower = p.get("name", "").lower().strip()
            if name_lower:
                self.name_index[name_lower] = i
            slug = p.get("slug", "").lower().strip()
            if slug:
                self.slug_index[slug] = i

    def search(
        self,
        query: str,
        top_k: int = 10,
        test_types: Optional[List[str]] = None,
        max_duration: Optional[int] = None,
        language: Optional[str] = None,
        remote_only: bool = False,
    ) -> List[Dict]:
        """
        Search the catalog using hybrid TF-IDF + keyword scoring.
        
        Args:
            query: Natural language search query
            top_k: Max results to return
            test_types: Filter by test type codes (A, B, C, etc.)
            max_duration: Filter by max duration in minutes
            language: Filter by language availability
            remote_only: Only return remote-testing-supported products
            
        Returns:
            List of product dicts sorted by relevance score
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        # ── TF-IDF Scoring ──
        query_vec = self.vectorizer.transform([query_lower])
        tfidf_scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # ── Keyword Boost ──
        keyword_scores = np.zeros(len(self.catalog))
        query_words = set(re.findall(r'\w+', query_lower))

        # Identify technology/domain keywords in the query
        tech_keywords = {
            "java", "python", "sql", "excel", "word", "angular", "react",
            "spring", "docker", "aws", "azure", "linux", "networking",
            "c#", "javascript", "typescript", "nodejs", "php", "ruby",
            "salesforce", "sap", "oracle", "accounting", "finance",
            "leadership", "personality", "cognitive", "numerical",
            "verbal", "mechanical", "safety", "customer", "sales",
            "hadoop", "kafka", "spark", "hive", "hbase", "django",
            "flask", "tensorflow", "kubernetes", "terraform", "jenkins",
            "git", "agile", "scrum", "devops", "blockchain", "cybersecurity",
            "powerbi", "tableau", "photoshop", "autocad", "excel",
            "hipaa", "medical", "nursing", "contact", "center",
        }
        query_tech = query_words & tech_keywords

        for i, text in enumerate(self.search_texts):
            boost = 0.0
            name = self.catalog[i].get("name", "").lower()
            slug = self.catalog[i].get("slug", "").lower()
            slug_words = set(slug.replace("-", " ").split())

            # Strong boost: technology keyword appears in the product slug
            for kw in query_tech:
                if kw in slug:  # substring match in slug
                    boost += 0.4
                elif kw in name:  # substring match in name
                    boost += 0.3

            # Exact name match boost
            if query_lower in name or name in query_lower:
                boost += 0.5

            # Word overlap with product name
            name_words = set(re.findall(r'\w+', name))
            overlap = len(query_words & name_words)
            if overlap > 0:
                boost += 0.15 * overlap / max(len(query_words), 1)

            # Penalize products that don't match any tech keyword from the query
            if query_tech and not any(kw in slug or kw in text for kw in query_tech):
                boost -= 0.1

            keyword_scores[i] = max(boost, 0.0)

        # ── Combine Scores ──
        # When tech keywords are present, weight keywords more heavily
        if query_tech:
            combined = 0.3 * tfidf_scores + 0.7 * keyword_scores
        else:
            combined = 0.6 * tfidf_scores + 0.4 * keyword_scores

        # ── Apply Filters ──
        for i in range(len(self.catalog)):
            p = self.catalog[i]

            # Test type filter
            if test_types:
                p_types = set(p.get("testTypes", []))
                if not p_types & set(test_types):
                    combined[i] = 0.0

            # Duration filter
            if max_duration and p.get("duration_minutes"):
                if p["duration_minutes"] > max_duration:
                    combined[i] *= 0.5  # Penalize but don't exclude

            # Language filter
            if language:
                p_langs = [l.lower() for l in p.get("languages", [])]
                if p_langs and not any(language.lower() in l for l in p_langs):
                    combined[i] *= 0.3

            # Remote filter
            if remote_only and not p.get("remoteSupported", False):
                combined[i] *= 0.5

        # ── Rank and Return ──
        top_indices = np.argsort(combined)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if combined[idx] <= 0.0:
                continue
            product = dict(self.catalog[idx])
            product["_score"] = float(combined[idx])
            results.append(product)

        return results

    def get_by_name(self, name: str) -> Optional[Dict]:
        """Look up a product by exact name."""
        idx = self.name_index.get(name.lower().strip())
        if idx is not None:
            return dict(self.catalog[idx])
        # Fuzzy match
        for n, i in self.name_index.items():
            if name.lower() in n or n in name.lower():
                return dict(self.catalog[i])
        return None

    def get_by_slug(self, slug: str) -> Optional[Dict]:
        """Look up a product by URL slug."""
        idx = self.slug_index.get(slug.lower().strip())
        if idx is not None:
            return dict(self.catalog[idx])
        return None

    def get_all_products(self) -> List[Dict]:
        """Return the full catalog."""
        return list(self.catalog)

    def format_product_context(self, products: List[Dict]) -> str:
        """Format a list of products as context text for the LLM."""
        lines = []
        for p in products:
            types_str = ", ".join(
                f"{c} ({TYPE_LABELS.get(c, c)})" for c in p.get("testTypes", [])
            )
            dur = p.get("duration_minutes")
            dur_str = f"{dur} minutes" if dur else "Variable"
            langs = p.get("languages", [])
            lang_str = f"{len(langs)} languages" if langs else "English"
            
            lines.append(
                f"- **{p['name']}** | Type: {types_str or 'N/A'} | Duration: {dur_str} | "
                f"Languages: {lang_str} | URL: {p.get('url', 'N/A')}"
            )
        return "\n".join(lines)
