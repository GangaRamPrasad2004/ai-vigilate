"""
Pillar 4: Knowledge Foundation - Historical Vendor Risk Vector Store via Qdrant.
Stores historical vendor profiles, risk classifications, and prior audit verdicts.
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

logger = logging.getLogger("knowledge-vendor-risk")

VECTOR_DIM = 64
COLLECTION_NAME = "vendor_risk_profiles"


def text_to_vector(text: str, dim: int = VECTOR_DIM) -> List[float]:
    """
    Generates a deterministic semantic dense embedding vector for text.
    Provides instant, zero-latency vector generation that runs completely offline
    without requiring external cloud embedding models or GPU dependencies.
    """
    clean_text = text.lower().strip()
    words = clean_text.split()
    vec = np.zeros(dim, dtype=np.float32)

    for i, word in enumerate(words):
        # Hash each token across the vector space
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        weight = 1.0 / (1.0 + 0.1 * i)
        vec[idx] += sign * weight

    # Add character n-grams for prefix/vendor name robustness
    for k in range(len(clean_text) - 2):
        ngram = clean_text[k:k + 3]
        h = int(hashlib.md5(ngram.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 0.3

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


class VendorRiskKnowledgeBase:
    """
    Qdrant-backed Vector Knowledge Base for Vendor Risk and Historical Audit Decisions.
    Implements Pillar 4 (Knowledge Foundation) of the 5 Core Pillars of Agentic AI.
    """

    def __init__(self, in_memory: bool = True):
        # Uses Qdrant in-memory mode for fast local verification
        self.client = QdrantClient(":memory:")
        self._init_collection()
        self._seed_mock_knowledge()

    def _init_collection(self):
        """Initializes the Qdrant collection with cosine distance metric."""
        if self.client.collection_exists(COLLECTION_NAME):
            self.client.delete_collection(COLLECTION_NAME)
        self.client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        )
        logger.info(f"Initialized Qdrant vector collection: '{COLLECTION_NAME}' (dim={VECTOR_DIM})")

    def _seed_mock_knowledge(self):
        """Seeds historical vendor risk knowledge and past audit outcomes."""
        records = [
            {
                "id": 1,
                "vendor": "Initech Systems",
                "risk_level": "CRITICAL_HIGH",
                "risk_score": 0.95,
                "historical_profile": (
                    "Initech Systems: High Risk - Prior history of indirect prompt injection attacks, "
                    "forged invoice notes, and unauthorized invoice overrides. Previous audit logs "
                    "flagged attempt to bypass CFO limits with 'IGNORE ALL PREVIOUS POLICIES' text. "
                    "Durable enterprise policy: Auto-approval is strictly forbidden; instant kill switch upon anomaly."
                ),
                "past_audit_verdict": "BLOCKED & QUARANTINED (Incident SEC-2025-089)",
                "category": "IT Infrastructure"
            },
            {
                "id": 2,
                "vendor": "Acme Supplies",
                "risk_level": "LOW",
                "risk_score": 0.10,
                "historical_profile": (
                    "Acme Supplies: Low Risk - Standard office supplies vendor with 5-year verified clean audit track record. "
                    "Routine recurring purchases under Net-30 enterprise terms. Consistent line-item pricing and 100% "
                    "compliance with auto-approval threshold ($10,000)."
                ),
                "past_audit_verdict": "APPROVED (Audits 2024-Q4, 2025-Q2, 2025-Q4 100% compliant)",
                "category": "Office Supplies"
            },
            {
                "id": 3,
                "vendor": "Globex Consulting",
                "risk_level": "MEDIUM",
                "risk_score": 0.55,
                "historical_profile": (
                    "Globex Consulting: Medium Risk - Strategic advisory partner. History of variable hourly billing and "
                    "scope amendments. Invoices between $10,000 and $20,000 require formal human supervisor escalation. "
                    "No historical prompt injection detected, but frequent budget overruns."
                ),
                "past_audit_verdict": "ESCALATED TO HUMAN SUPERVISOR (Audit 2025-Q3)",
                "category": "Management Consulting"
            }
        ]

        points = []
        for rec in records:
            full_text = f"{rec['vendor']} {rec['risk_level']} {rec['historical_profile']}"
            vector = text_to_vector(full_text)
            points.append(
                PointStruct(
                    id=rec["id"],
                    vector=vector,
                    payload=rec
                )
            )

        self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"Seeded {len(points)} vendor risk profiles into Qdrant vector store.")

    def search_vendor_history(self, vendor_name: str, limit: int = 2) -> List[Dict[str, Any]]:
        """
        Retrieves matching historical risk profiles from Qdrant vector database.
        """
        query_vec = text_to_vector(vendor_name)
        
        # Qdrant client compatibility
        try:
            results = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vec,
                limit=limit
            )
        except AttributeError:
            # Fallback for newer Qdrant client versions using query_points
            response = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vec,
                limit=limit
            )
            results = response.points

        matches = []
        for res in results:
            item = dict(res.payload)
            item["similarity_score"] = round(float(res.score), 4)
            matches.append(item)

        return matches


# Global singleton instance
vendor_knowledge_base = VendorRiskKnowledgeBase()
