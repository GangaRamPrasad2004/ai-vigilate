from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Invoice(BaseModel):
    id: str = Field(..., description="Unique invoice identifier (e.g., INV-101)")
    vendor: str = Field(..., description="Vendor company name")
    amount: float = Field(..., description="Invoice total amount in USD")
    status: str = Field("pending", description="Invoice status: pending, approved, escalated")
    note: str = Field("", description="Invoice description, metadata, or notes")


class ActionRequest(BaseModel):
    actor: str = Field(..., description="Actor identity performing the action, e.g. agent or user")
    session_id: str = Field(..., description="Unique agent runtime session identifier")
    reason: str = Field(..., description="Justification or rationale for this action")


class SessionStateResponse(BaseModel):
    session_id: str
    active: bool
    created_at: str
    processed_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
