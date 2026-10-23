"""
Standalone Reusable Pattern: Guardrail Before Tool Call
Compatible with Strands Agents, Decider 2B, and standard Python agent frameworks.
"""

import functools
import json
import logging
import time
from typing import Callable, Dict, Any, Optional, List
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("reusable-decider-guardrail")


class DeciderDecision(BaseModel):
    choice: str = Field(..., description="'yes' or 'no'")
    confidence: float = Field(..., ge=0.0, le=1.0)
    latency_ms: float = Field(...)
    raw: Dict[str, Any] = Field(default_factory=dict)


class DeciderGuardrail:
    """
    Reusable Guardrail class wrapping Strands Decider 2B.
    Evaluates proposed tool execution against durable enterprise policy and user intent.
    """

    DEFAULT_QUESTION = (
        "Given the user's original request, durable policy, and proposed tool call, "
        "should the agent execute this tool call?"
    )

    def __init__(
        self,
        decider_base_url: str = "http://localhost:8001",
        confidence_threshold: float = 0.65,
        timeout: float = 3.0,
        mode: str = "http"
    ):
        self.decider_base_url = decider_base_url.rstrip("/")
        self.confidence_threshold = confidence_threshold
        self.timeout = timeout
        self.mode = mode.lower()

    def decide(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        durable_policy: Dict[str, Any],
        user_request: str,
        resource_context: Optional[Dict[str, Any]] = None,
        session_id: str = "default-session"
    ) -> Dict[str, Any]:
        """
        Executes the Guardrail decision check via Strands Decider 2B.
        """
        context = {
            "user_request": user_request,
            "tool_name": tool_name,
            "tool_arguments": tool_arguments,
            "durable_policy": durable_policy,
            "resource_context": resource_context or {},
            "session_id": session_id
        }

        start = time.perf_counter()

        if self.mode == "mock":
            # Deterministic simulation for tests
            latency_ms = (time.perf_counter() - start) * 1000.0
            return {
                "allowed": True,
                "action": "allow",
                "choice": "yes",
                "confidence": 0.98,
                "latency_ms": latency_ms
            }

        url = f"{self.decider_base_url}/decide"
        payload = {
            "question": self.DEFAULT_QUESTION,
            "context": context,
            "options": ["yes", "no"]
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                latency_ms = (time.perf_counter() - start) * 1000.0
                if resp.status_code == 200:
                    data = resp.json()
                    choice = data.get("choice", "no").lower()
                    conf = float(data.get("confidence", 0.0))

                    if choice == "yes" and conf >= self.confidence_threshold:
                        return {
                            "allowed": True,
                            "action": "allow",
                            "choice": choice,
                            "confidence": conf,
                            "latency_ms": latency_ms
                        }
                    elif conf < self.confidence_threshold:
                        return {
                            "allowed": False,
                            "action": "escalate",
                            "choice": choice,
                            "confidence": conf,
                            "latency_ms": latency_ms,
                            "reason": "Confidence below threshold; routing to human."
                        }
                    else:
                        return {
                            "allowed": False,
                            "action": "block",
                            "choice": choice,
                            "confidence": conf,
                            "latency_ms": latency_ms,
                            "reason": "Action blocked by Decider 2B policy check."
                        }
        except Exception as exc:
            logger.error(f"Decider connection error: {exc}")

        # Fail closed
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {
            "allowed": False,
            "action": "block",
            "choice": "no",
            "confidence": 0.0,
            "latency_ms": latency_ms,
            "reason": "Fail-closed: Strands Decider service unavailable."
        }


def with_decider_guardrail(tool_name: Optional[str] = None, guardrail: Optional[DeciderGuardrail] = None):
    """
    Decorator for wrapping functions with Decider 2B pre-invocation verification.
    """
    guard = guardrail or DeciderGuardrail()

    def decorator(func: Callable):
        t_name = tool_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            context = kwargs.pop("__guardrail_context__", {})
            policy = context.get("durable_policy", {})
            user_req = context.get("user_request", "Default tool invocation")
            res_context = context.get("resource_context", {})
            sess_id = context.get("session_id", "default")

            verdict = guard.decide(
                tool_name=t_name,
                tool_arguments=kwargs,
                durable_policy=policy,
                user_request=user_req,
                resource_context=res_context,
                session_id=sess_id
            )

            if not verdict["allowed"]:
                return json.dumps({
                    "status": "blocked",
                    "action": verdict.get("action", "block"),
                    "reason": verdict.get("reason", "Blocked by Decider Guardrail")
                })

            return func(*args, **kwargs)

        return wrapper

    return decorator
