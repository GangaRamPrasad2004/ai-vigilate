package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestKillSwitchFlow(t *testing.T) {
	// Reset state first
	globalLedger.ResetKill()

	// 1. Initial State should be killed=false
	reqGet := httptest.NewRequest(http.MethodGet, "/kill", nil)
	rrGet := httptest.NewRecorder()
	handleKill(rrGet, reqGet)

	if rrGet.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d", rrGet.Code)
	}
	var state KillState
	if err := json.NewDecoder(rrGet.Body).Decode(&state); err != nil {
		t.Fatalf("Failed to decode kill state: %v", err)
	}
	if state.Killed {
		t.Errorf("Expected killed=false initially, got true")
	}

	// 2. POST /kill to activate kill switch
	killPayload := []byte(`{"reason":"Prompt injection detected","session_id":"sess-123"}`)
	reqPost := httptest.NewRequest(http.MethodPost, "/kill", bytes.NewBuffer(killPayload))
	rrPost := httptest.NewRecorder()
	handleKill(rrPost, reqPost)

	if rrPost.Code != http.StatusOK {
		t.Fatalf("Expected 200 on POST /kill, got %d", rrPost.Code)
	}
	var postState KillState
	if err := json.NewDecoder(rrPost.Body).Decode(&postState); err != nil {
		t.Fatalf("Failed to decode: %v", err)
	}
	if !postState.Killed {
		t.Errorf("Expected postState.Killed=true, got false")
	}
	if postState.Reason != "Prompt injection detected" {
		t.Errorf("Expected reason 'Prompt injection detected', got %s", postState.Reason)
	}

	// 3. GET /kill should now return killed=true
	reqVerify := httptest.NewRequest(http.MethodGet, "/kill", nil)
	rrVerify := httptest.NewRecorder()
	handleKill(rrVerify, reqVerify)

	var verifyState KillState
	_ = json.NewDecoder(rrVerify.Body).Decode(&verifyState)
	if !verifyState.Killed {
		t.Errorf("Expected verifyState.Killed=true, got false")
	}

	// 4. POST /reset resets kill switch
	reqReset := httptest.NewRequest(http.MethodPost, "/reset", nil)
	rrReset := httptest.NewRecorder()
	handleReset(rrReset, reqReset)

	if rrReset.Code != http.StatusOK {
		t.Fatalf("Expected 200 on reset, got %d", rrReset.Code)
	}
	var resetState KillState
	_ = json.NewDecoder(rrReset.Body).Decode(&resetState)
	if resetState.Killed {
		t.Errorf("Expected resetState.Killed=false after reset, got true")
	}
}

func TestAuditEvents(t *testing.T) {
	// Add an event via POST /events
	eventPayload := []byte(`{
		"session_id": "test-session-1",
		"tool_name": "approve_invoice",
		"decision": "yes",
		"confidence": 0.98,
		"latency_ms": 14.5,
		"details": "Invoice INV-101 approved within threshold"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/events", bytes.NewBuffer(eventPayload))
	rr := httptest.NewRecorder()
	handleEvents(rr, req)

	if rr.Code != http.StatusCreated {
		t.Fatalf("Expected status 201 Created, got %d", rr.Code)
	}

	// Query events via GET /events?session_id=test-session-1
	reqGet := httptest.NewRequest(http.MethodGet, "/events?session_id=test-session-1", nil)
	rrGet := httptest.NewRecorder()
	handleEvents(rrGet, reqGet)

	if rrGet.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", rrGet.Code)
	}
	var events []AuditEvent
	if err := json.NewDecoder(rrGet.Body).Decode(&events); err != nil {
		t.Fatalf("Failed to decode events: %v", err)
	}
	if len(events) == 0 {
		t.Errorf("Expected at least 1 event, got 0")
	}
	if events[0].ToolName != "approve_invoice" {
		t.Errorf("Expected tool_name 'approve_invoice', got %s", events[0].ToolName)
	}
}
