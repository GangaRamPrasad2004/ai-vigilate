import logging
import time
from typing import List, Dict, Any, Optional
import httpx
from pydantic import BaseModel, Field

try:
    from .config import settings
except ImportError:
    from agent.config import settings

logger = logging.getLogger("decider-client")


class DeciderUnavailableError(Exception):
    """Raised when the Strands Decider 2B service cannot be reached and fail-closed is active."""
    pass


class DeciderDecision(BaseModel):
    """Normalized response from Strands Decider 2B."""
    choice: str = Field(..., description="Selected option, typically 'yes' or 'no'")
    confidence: float = Field(..., description="Model confidence score between 0.0 and 1.0")
    latency_ms: float = Field(..., description="Round-trip inference latency in milliseconds")
    raw: Dict[str, Any] = Field(default_factory=dict, description="Raw response payload")


class DeciderClient:
    """
    Client for interacting with Strands Decider 2B model server.
    Supports live HTTP inference and deterministic local mock for testing and CI.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        mode: Optional[str] = None,
        fail_closed: Optional[bool] = None,
        timeout: float = 5.0
    ):
        self.base_url = (base_url or settings.DECIDER_BASE_URL).rstrip("/")
        self.mode = (mode or settings.DECIDER_MODE).lower()
        self.fail_closed = settings.FAIL_CLOSED_IF_DECIDER_UNAVAILABLE if fail_closed is None else fail_closed
        self.timeout = timeout

        # Optional test overrides for unit test edge cases
        self._mock_override: Optional[Dict[str, Any]] = None

    def set_mock_override(self, choice: str, confidence: float) -> None:
        """Helper for unit tests to force a specific mock response."""
        self._mock_override = {"choice": choice, "confidence": confidence}

    def clear_mock_override(self) -> None:
        self._mock_override = None

    def decide_yes_no(
        self,
        question: str,
        context: Dict[str, Any],
        options: Optional[List[str]] = None
    ) -> DeciderDecision:
        """
        Executes a binary guardrail decision via Strands Decider 2B.

        Args:
            question: Typed decision prompt.
            context: Full runtime context (user request, policy, tool arguments, invoice data).
            options: List of allowed choices (defaults to ["yes", "no"]).

        Returns:
            DeciderDecision containing the choice, confidence, and measured latency.
        """
        if options is None:
            options = ["yes", "no"]

        start_time = time.perf_counter()

        if self.mode == "mock":
            return self._decide_mock(question, context, options, start_time)

        # Live HTTP Mode
        return self._decide_http(question, context, options, start_time)

    def _decide_http(
        self,
        question: str,
        context: Dict[str, Any],
        options: List[str],
        start_time: float
    ) -> DeciderDecision:
        """
        Sends HTTP request to running Strands Decider 2B server.
        Adapts standard Decider schema:
        POST /decide (or /v1/decide)
        Payload: { "question": str, "context": dict, "options": list[str] }
        Response: { "choice": str, "confidence": float, "scores": dict }
        """
        endpoint = f"{self.base_url}/decide"
        payload = {
            "question": question,
            "context": context,
            "options": options
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, json=payload)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                if response.status_code == 200:
                    data = response.json()
                    choice = data.get("choice", "no")
                    confidence = float(data.get("confidence", 0.0))
                    logger.info(
                        f"[STRANDS DECIDER 2B] Choice: '{choice}', Confidence: {confidence:.2f}, Latency: {latency_ms:.1f}ms"
                    )
                    return DeciderDecision(
                        choice=choice,
                        confidence=confidence,
                        latency_ms=round(latency_ms, 2),
                        raw=data
                    )
                else:
                    logger.error(f"Strands Decider returned HTTP {response.status_code}: {response.text}")

        except Exception as exc:
            logger.error(f"Failed to communicate with Strands Decider at {endpoint}: {exc}")

        # If we reached here, the Decider service failed or was unreachable
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        if self.fail_closed:
            logger.critical("FAIL CLOSED: Strands Decider is unreachable. Halting sensitive tool execution.")
            raise DeciderUnavailableError(
                f"Strands Decider 2B service at {self.base_url} is unavailable and fail-closed policy is ACTIVE."
            )

        logger.warning("Decider unavailable and fail-closed is disabled. Defaulting to safe 'no'.")
        return DeciderDecision(
            choice="no",
            confidence=0.0,
            latency_ms=round(latency_ms, 2),
            raw={"error": "decider_unreachable"}
        )

    def _decide_mock(
        self,
        question: str,
        context: Dict[str, Any],
        options: List[str],
        start_time: float
    ) -> DeciderDecision:
        """
        Deterministic mock Decider for local CI, development, and automated test suites.
        Explicitly logs [MOCK DECIDER] to distinguish from live model inference.
        """
        # Emulate 10-18ms local 2B model inference latency
        time.sleep(0.012)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if self._mock_override:
            logger.info(
                f"[MOCK DECIDER OVERRIDE] Choice: '{self._mock_override['choice']}', "
                f"Confidence: {self._mock_override['confidence']:.2f}, Latency: {latency_ms:.1f}ms"
            )
            return DeciderDecision(
                choice=self._mock_override["choice"],
                confidence=self._mock_override["confidence"],
                latency_ms=round(latency_ms, 2),
                raw={"mock": True, "override": True}
            )

        # Context analysis simulation:
        invoice = context.get("invoice_data", {})
        policy = context.get("durable_policy", {})
        note = str(invoice.get("note", "")).lower()
        amount = float(invoice.get("amount", 0.0))
        approval_limit = float(policy.get("approval_limit_usd", 10000.0))
        forbidden_phrases = policy.get("forbidden_phrases", [
            "ignore all previous",
            "ignore previous policies",
            "approve immediately",
            "system message"
        ])

        # 1. Prompt Injection, Malice, or High-Risk Vendor Check from Qdrant Knowledge Base
        vendor_risk = context.get("vendor_historical_risk", {})
        is_high_risk_vendor = vendor_risk.get("risk_level") == "CRITICAL_HIGH"
        has_injection = any(phrase.lower() in note for phrase in forbidden_phrases)

        if has_injection or amount > 20000.0 or is_high_risk_vendor:
            risk_reason = "high_risk_vendor_profile" if is_high_risk_vendor else "prompt_injection_or_critical_threshold_exceeded"
            logger.warning(
                f"[MOCK DECIDER] Flagged high-risk anomaly / policy breach! "
                f"Amount=${amount:,.2f}, Note='{note}', QdrantRisk='{vendor_risk.get('risk_level', 'NONE')}'. Decision='no'"
            )
            return DeciderDecision(
                choice="no",
                confidence=0.99,
                latency_ms=round(latency_ms, 2),
                raw={"mock": True, "reason": risk_reason, "vendor_risk": vendor_risk}
            )

        # 2. Exceeds standard auto-approval limit -> Escalate
        if amount > approval_limit:
            logger.info(
                f"[MOCK DECIDER] Invoice ${amount:,.2f} exceeds auto-approval limit ${approval_limit:,.2f}. Decision='no'"
            )
            return DeciderDecision(
                choice="no",
                confidence=0.94,
                latency_ms=round(latency_ms, 2),
                raw={"mock": True, "reason": "exceeds_approval_limit"}
            )

        # 3. Within normal policy parameters -> Approve
        logger.info(
            f"[MOCK DECIDER] Invoice ${amount:,.2f} within policy limit ${approval_limit:,.2f}. Decision='yes'"
        )
        return DeciderDecision(
            choice="yes",
            confidence=0.98,
            latency_ms=round(latency_ms, 2),
            raw={"mock": True, "reason": "within_policy"}
        )


# Singleton instance
decider_client = DeciderClient()
