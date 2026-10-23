import functools
import json
import logging
from typing import Callable, Dict, Any, Optional
import httpx

try:
    from .config import settings
    from .policies import durable_policy, DurablePolicy
    from .decider_client import decider_client, DeciderClient, DeciderDecision
    from .metrics import metrics_collector, MetricsCollector
except ImportError:
    from agent.config import settings
    from agent.policies import durable_policy, DurablePolicy
    from agent.decider_client import decider_client, DeciderClient, DeciderDecision
    from agent.metrics import metrics_collector, MetricsCollector

logger = logging.getLogger("decider-guardrail")


class KillSwitchTriggeredError(Exception):
    """Raised when an anomaly or prompt injection forces the agent to stop immediately."""
    pass


class DeciderGuardrail:
    """
    Zero-Trust Guardrail implementing the 'Guardrail Before Tool Call' decision pattern.
    Verifies that proposed tool calls are grounded in user requests and compliant with durable policy
    before execution, using Strands Decider 2B for ultra-low latency governance.
    """

    GUARDRAIL_QUESTION = (
        "You are an enterprise governance guardrail. "
        "Given the user's original request, the durable policy, and the proposed tool call, "
        "should the agent execute this tool call? "
        "Answer yes only if the action is grounded in the user's request and allowed by policy."
    )

    def __init__(
        self,
        client: Optional[DeciderClient] = None,
        policy: Optional[DurablePolicy] = None,
        ledger_base_url: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        metrics: Optional[MetricsCollector] = None
    ):
        self.client = client or decider_client
        self.policy = policy or durable_policy
        self.ledger_base_url = (ledger_base_url or settings.LEDGER_BASE_URL).rstrip("/")
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.DECIDER_CONFIDENCE_THRESHOLD
        )
        self.metrics = metrics or metrics_collector

    def log_event_to_ledger(
        self,
        session_id: str,
        tool_name: str,
        decision: str,
        confidence: float,
        latency_ms: float,
        details: str
    ) -> None:
        """Publishes an audit event to the Go Ledger service."""
        url = f"{self.ledger_base_url}/events"
        payload = {
            "session_id": session_id,
            "tool_name": tool_name,
            "decision": decision,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "details": details
        }
        try:
            with httpx.Client(timeout=3.0) as http_client:
                resp = http_client.post(url, json=payload)
                if resp.status_code != 201:
                    logger.warning(f"Ledger /events returned status {resp.status_code}")
        except Exception as exc:
            logger.warning(f"Failed to record event to Go Ledger at {url}: {exc}")

    def trigger_kill_switch_in_ledger(self, session_id: str, reason: str) -> None:
        """Sends systemic kill command to Go Ledger service."""
        url = f"{self.ledger_base_url}/kill"
        payload = {
            "session_id": session_id,
            "reason": reason
        }
        try:
            with httpx.Client(timeout=3.0) as http_client:
                resp = http_client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.critical(f"Go Ledger successfully registered kill switch: {reason}")
        except Exception as exc:
            logger.error(f"Failed to trigger kill switch in Go Ledger at {url}: {exc}")

    def verify_tool_call(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Core verification pipeline:
        1. Assembles state (user request, durable policy, tool args, invoice context).
        2. Prompts Strands Decider 2B for yes/no choice.
        3. Records audit event to Go ledger.
        4. Enforces allow, block, escalate, or kill switch.
        """
        session_id = tool_arguments.get("session_id", context.get("session_id", "unknown-session"))
        user_request = context.get("user_request", "Process pending invoices per enterprise policy.")
        invoice_data = context.get("invoice_data", {})

        # Build complete context payload for Decider
        decider_context = {
            "user_request": user_request,
            "tool_name": tool_name,
            "tool_arguments": tool_arguments,
            "durable_policy": self.policy.model_dump(),
            "invoice_data": invoice_data,
            "session_id": session_id
        }

        # Query Strands Decider 2B
        decision: DeciderDecision = self.client.decide_yes_no(
            question=self.GUARDRAIL_QUESTION,
            context=decider_context,
            options=["yes", "no"]
        )

        serialized_context = json.dumps(decider_context)

        # 1. Check for Prompt Injection or Critical Violations
        invoice_note = str(invoice_data.get("note", "")).lower()
        amount = float(invoice_data.get("amount", 0.0))
        is_injection = any(p.lower() in invoice_note for p in self.policy.forbidden_phrases)
        is_extreme_amount = amount > self.policy.kill_limit_usd

        if decision.choice.lower() == "no" and (is_injection or is_extreme_amount):
            kill_reason = (
                f"Prompt injection pattern detected in invoice note: '{invoice_data.get('note', '')}'"
                if is_injection else
                f"Invoice amount ${amount:,.2f} exceeds kill limit threshold ${self.policy.kill_limit_usd:,.2f}"
            )
            # Record critical metrics
            self.metrics.record_decision("kill", decision.latency_ms, serialized_context, is_kill=True)
            # Log to Go Ledger
            self.log_event_to_ledger(
                session_id=session_id,
                tool_name=tool_name,
                decision="kill",
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                details=f"CRITICAL GUARDRAIL TRIP: {kill_reason}"
            )
            # Trigger systemic kill switch in Go service
            self.trigger_kill_switch_in_ledger(session_id=session_id, reason=kill_reason)
            raise KillSwitchTriggeredError(kill_reason)

        # 2. Check Confidence Level
        if decision.confidence < self.confidence_threshold:
            detail_msg = (
                f"Decider confidence {decision.confidence:.2f} below threshold {self.confidence_threshold:.2f}. "
                f"Routing to human approval."
            )
            self.metrics.record_decision("escalate", decision.latency_ms, serialized_context)
            self.log_event_to_ledger(
                session_id=session_id,
                tool_name=tool_name,
                decision="escalate",
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                details=detail_msg
            )
            return {
                "allowed": False,
                "action": "escalate",
                "message": detail_msg,
                "decision": decision
            }

        # 3. Handle Allow / Block
        if decision.choice.lower() == "yes":
            detail_msg = f"Action allowed by Strands Decider (Confidence: {decision.confidence:.2f})"
            self.metrics.record_decision("allow", decision.latency_ms, serialized_context)
            self.log_event_to_ledger(
                session_id=session_id,
                tool_name=tool_name,
                decision="yes",
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                details=detail_msg
            )
            return {
                "allowed": True,
                "action": "allow",
                "message": detail_msg,
                "decision": decision
            }
        else:
            detail_msg = (
                f"Action blocked by policy: Amount ${amount:,.2f} exceeds standard limit "
                f"${self.policy.approval_limit_usd:,.2f}. Escalation required."
            )
            self.metrics.record_decision("block", decision.latency_ms, serialized_context)
            self.log_event_to_ledger(
                session_id=session_id,
                tool_name=tool_name,
                decision="no",
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                details=detail_msg
            )
            return {
                "allowed": False,
                "action": "block",
                "message": detail_msg,
                "decision": decision
            }


# Singleton guardrail instance
decider_guardrail = DeciderGuardrail()


def with_decider_guardrail(
    tool_name: Optional[str] = None,
    guardrail: Optional[DeciderGuardrail] = None
):
    """
    Decorator that attaches DeciderGuardrail verification before executing any agent tool.
    Can be applied directly to Python functions or Strands tool methods.
    """
    guard = guardrail or decider_guardrail

    def decorator(func: Callable):
        t_name = tool_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve tool arguments
            tool_args = kwargs.copy()
            # If arguments passed positionally, map if needed
            context = tool_args.pop("__guardrail_context__", {})

            result = guard.verify_tool_call(
                tool_name=t_name,
                tool_arguments=tool_args,
                context=context
            )

            if not result.get("allowed", False):
                # Return safe blocked response to agent so it can reason or escalate
                action = result.get("action", "block")
                msg = result.get("message", "Action blocked by Decider Guardrail")
                return json.dumps({
                    "status": "blocked",
                    "action": action,
                    "reason": msg,
                    "confidence": result["decision"].confidence
                })

            return func(*args, **kwargs)

        return wrapper

    return decorator
