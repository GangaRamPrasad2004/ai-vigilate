"""
Pillar 4: Knowledge Foundation - RAG Tool Integration.
Provides the agent and the DeciderGuardrail with historical vendor intelligence retrieved from Qdrant.
"""

import json
import logging
from typing import Dict, Any, Optional

try:
    from .vendor_risk import vendor_knowledge_base
except ImportError:
    from knowledge.vendor_risk import vendor_knowledge_base

logger = logging.getLogger("knowledge-rag-tools")


def query_vendor_history(vendor_name: str) -> str:
    """
    Strands Agent Tool: query_vendor_history
    Queries the Qdrant vector knowledge foundation to retrieve historical risk classifications,
    prior audit decisions, and known prompt injection flags for a specific vendor.

    Args:
        vendor_name: Company or vendor name (e.g. 'Initech Systems', 'Acme Supplies').

    Returns:
        JSON string containing matching historical profiles, risk rating, and audit notes.
    """
    logger.info(f"[KNOWLEDGE RAG] Searching Qdrant vector store for vendor: '{vendor_name}'")
    matches = vendor_knowledge_base.search_vendor_history(vendor_name, limit=2)

    if not matches:
        return json.dumps({
            "vendor": vendor_name,
            "status": "not_found",
            "message": f"No prior historical risk records found for '{vendor_name}'. Treating as unverified vendor."
        })

    primary = matches[0]
    result = {
        "vendor": primary.get("vendor"),
        "risk_level": primary.get("risk_level"),
        "risk_score": primary.get("risk_score"),
        "historical_profile": primary.get("historical_profile"),
        "past_audit_verdict": primary.get("past_audit_verdict"),
        "similarity_score": primary.get("similarity_score"),
        "all_matches": matches
    }
    return json.dumps(result, indent=2)


def enrich_context_with_vendor_history(context: Dict[str, Any], vendor_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Enriches the Decider 2B Guardrail context with RAG intelligence from Qdrant.
    Gives Strands Decider 2B ground-truth audit memory before rendering allow/block/kill decisions.
    """
    v_name = vendor_name or context.get("invoice_data", {}).get("vendor")
    if not v_name:
        return context

    raw_history = query_vendor_history(v_name)
    try:
        parsed_history = json.loads(raw_history)
        context["vendor_historical_risk"] = {
            "vendor": parsed_history.get("vendor"),
            "risk_level": parsed_history.get("risk_level"),
            "summary": parsed_history.get("historical_profile"),
            "past_verdict": parsed_history.get("past_audit_verdict")
        }
    except Exception as exc:
        logger.warning(f"Failed to parse vendor history JSON: {exc}")
        context["vendor_historical_risk"] = {"error": "retrieval_failed"}

    return context
