package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"
)

// AuditEvent represents a logged governance action or Decider decision.
type AuditEvent struct {
	SessionID  string    `json:"session_id"`
	ToolName   string    `json:"tool_name"`
	Decision   string    `json:"decision"`
	Confidence float64   `json:"confidence"`
	LatencyMS  float64   `json:"latency_ms"`
	Details    string    `json:"details"`
	Timestamp  time.Time `json:"timestamp"`
}

// KillState represents the systemic kill switch status.
type KillState struct {
	Killed    bool   `json:"killed"`
	Reason    string `json:"reason"`
	SessionID string `json:"session_id"`
	Timestamp string `json:"timestamp"`
}

// Ledger holds in-memory state with mutex synchronization.
type Ledger struct {
	mu     sync.RWMutex
	events []AuditEvent
	kill   KillState
}

func NewLedger() *Ledger {
	return &Ledger{
		events: make([]AuditEvent, 0),
		kill: KillState{
			Killed:    false,
			Reason:    "",
			SessionID: "",
			Timestamp: "",
		},
	}
}

var globalLedger = NewLedger()

func (l *Ledger) AddEvent(e AuditEvent) AuditEvent {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e.Timestamp.IsZero() {
		e.Timestamp = time.Now().UTC()
	}
	l.events = append(l.events, e)
	return e
}

func (l *Ledger) GetEvents(sessionID string) []AuditEvent {
	l.mu.RLock()
	defer l.mu.RUnlock()
	if sessionID == "" {
		out := make([]AuditEvent, len(l.events))
		copy(out, l.events)
		return out
	}
	var filtered []AuditEvent
	for _, e := range l.events {
		if e.SessionID == sessionID {
			filtered = append(filtered, e)
		}
	}
	return filtered
}

func (l *Ledger) SetKill(reason, sessionID string) KillState {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.kill = KillState{
		Killed:    true,
		Reason:    reason,
		SessionID: sessionID,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	}
	return l.kill
}

func (l *Ledger) ResetKill() KillState {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.kill = KillState{
		Killed:    false,
		Reason:    "",
		SessionID: "",
		Timestamp: "",
	}
	return l.kill
}

func (l *Ledger) GetKill() KillState {
	l.mu.RLock()
	defer l.mu.RUnlock()
	return l.kill
}

// HTTP Handlers

func handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func handleEvents(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	switch r.Method {
	case http.MethodGet:
		sessionID := r.URL.Query().Get("session_id")
		events := globalLedger.GetEvents(sessionID)
		_ = json.NewEncoder(w).Encode(events)
	case http.MethodPost:
		var raw struct {
			SessionID  string  `json:"session_id"`
			ToolName   string  `json:"tool_name"`
			Decision   string  `json:"decision"`
			Confidence float64 `json:"confidence"`
			LatencyMS  float64 `json:"latency_ms"`
			Details    string  `json:"details"`
			Timestamp  string  `json:"timestamp"`
		}
		if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
			http.Error(w, fmt.Sprintf(`{"error":"invalid_json","message":%q}`, err.Error()), http.StatusBadRequest)
			return
		}
		var ts time.Time
		if raw.Timestamp != "" {
			var err error
			ts, err = time.Parse(time.RFC3339, raw.Timestamp)
			if err != nil {
				ts = time.Now().UTC()
			}
		} else {
			ts = time.Now().UTC()
		}

		event := AuditEvent{
			SessionID:  raw.SessionID,
			ToolName:   raw.ToolName,
			Decision:   raw.Decision,
			Confidence: raw.Confidence,
			LatencyMS:  raw.LatencyMS,
			Details:    raw.Details,
			Timestamp:  ts,
		}
		saved := globalLedger.AddEvent(event)
		log.Printf("[LEDGER EVENT] Tool=%s Decision=%s Conf=%.2f Latency=%.1fms Session=%s Details=%s",
			saved.ToolName, saved.Decision, saved.Confidence, saved.LatencyMS, saved.SessionID, saved.Details)
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(saved)
	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func handleKill(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	switch r.Method {
	case http.MethodGet:
		state := globalLedger.GetKill()
		_ = json.NewEncoder(w).Encode(state)
	case http.MethodPost:
		var req struct {
			Reason    string `json:"reason"`
			SessionID string `json:"session_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, fmt.Sprintf(`{"error":"invalid_json","message":%q}`, err.Error()), http.StatusBadRequest)
			return
		}
		state := globalLedger.SetKill(req.Reason, req.SessionID)
		log.Printf("!!! [KILL SWITCH TRIGGERED] Reason: %s (Session: %s) !!!", req.Reason, req.SessionID)
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(state)
	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func handleReset(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	state := globalLedger.ResetKill()
	log.Println("[LEDGER] Kill switch has been disarmed/reset.")
	_ = json.NewEncoder(w).Encode(state)
}

func handleDashboard(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	killState := globalLedger.GetKill()
	events := globalLedger.GetEvents("")

	badgeColor := "#10b981"
	badgeText := "DISARMED (NORMAL)"
	if killState.Killed {
		badgeColor = "#ef4444"
		badgeText = "ACTIVATED (SYSTEM BLOCKED)"
	}

	eventRows := ""
	for i := len(events) - 1; i >= 0; i-- {
		ev := events[i]
		decColor := "#10b981"
		if ev.Decision == "no" || ev.Decision == "block" || ev.Decision == "kill" {
			decColor = "#ef4444"
		} else if ev.Decision == "escalate" {
			decColor = "#f59e0b"
		}
		eventRows += fmt.Sprintf(`
		<tr style="border-bottom: 1px solid #e5e7eb;">
			<td style="padding: 10px; font-family: monospace; font-size: 0.85em;">%s</td>
			<td style="padding: 10px; font-family: monospace; font-size: 0.85em;">%s</td>
			<td style="padding: 10px; font-weight: 600;">%s</td>
			<td style="padding: 10px;"><span style="background: %s; color: white; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; text-transform: uppercase;">%s</span></td>
			<td style="padding: 10px;">%.2f</td>
			<td style="padding: 10px;">%.1f ms</td>
			<td style="padding: 10px; font-size: 0.85em; color: #4b5563;">%s</td>
		</tr>`,
			ev.Timestamp.Format("15:04:05"), ev.SessionID, ev.ToolName, decColor, ev.Decision, ev.Confidence, ev.LatencyMS, ev.Details)
	}

	html := fmt.Sprintf(`<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Strands Sentinel - Go Audit Ledger</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f3f4f6; margin: 0; padding: 30px; }
        .container { max-width: 1100px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); padding: 24px; }
        h1 { margin-top: 0; color: #111827; }
        .status-box { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }
        table { width: 100%%; border-collapse: collapse; text-align: left; }
        th { background: #f9fafb; padding: 10px; border-bottom: 2px solid #e5e7eb; color: #4b5563; font-size: 0.8em; text-transform: uppercase; }
        .badge { background: %s; color: white; padding: 6px 14px; border-radius: 9999px; font-weight: bold; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Strands Sentinel - Immutable Audit Ledger</h1>
        <div class="status-box">
            <div>
                <strong>Global Kill-Switch Status:</strong>
                <span class="badge">%s</span>
                %s
            </div>
            <div>
                <a href="/events" style="color: #2563eb; text-decoration: none; font-size: 0.9em;">Raw JSON Events &rarr;</a>
            </div>
        </div>
        <h3>Decider 2B Guardrail Decisions &amp; Tool Invocations (%d Recorded)</h3>
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Session ID</th>
                    <th>Tool</th>
                    <th>Decision</th>
                    <th>Confidence</th>
                    <th>Latency</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
                %s
            </tbody>
        </table>
    </div>
</body>
</html>`,
		badgeColor, badgeText,
		func() string {
			if killState.Killed {
				return fmt.Sprintf("<div style='margin-top: 6px; color: #dc2626; font-size: 0.9em;'><strong>Trigger Reason:</strong> %s (at %s)</div>", killState.Reason, killState.Timestamp)
			}
			return ""
		}(),
		len(events), eventRows)

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(html))
}

func main() {
	portStr := os.Getenv("LEDGER_PORT")
	port := 8081
	if portStr != "" {
		if p, err := strconv.Atoi(portStr); err == nil {
			port = p
		}
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", handleDashboard)
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/events", handleEvents)
	mux.HandleFunc("/kill", handleKill)
	mux.HandleFunc("/reset", handleReset)

	addr := fmt.Sprintf("0.0.0.0:%d", port)
	log.Printf("Starting Strands Sentinel Go Ledger on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
