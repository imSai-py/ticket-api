import React, { useState } from "react";

export interface TriageResult {
  category: "Billing" | "Login" | "Shipping" | "Refunds" | "Technical" | "Account";
  priority: "urgent" | "high" | "normal" | "low";
  suggested_reply: string;
  article_ids: string[];
}

export interface HelpdeskIngestResult {
  status: string;
  ticket_id: string;
  category: string;
  priority: string;
  refund_amount: number;
  customer_name: string;
  assigned_to: string;
  suggested_reply: string;
  record: {
    ticket_id: string;
    customer_name: string;
    category: string;
    priority: string;
    amount: string;
    reason: string;
    agent: string;
    status: string;
    escalated: string;
    created_at: string;
  };
  escalated: boolean;
}

interface ValidationErrorDetail {
  msg?: string;
  type?: string;
  loc?: (string | number)[];
}

interface CustomImportMetaEnv {
  VITE_API_BASE_URL?: string;
}

export function App() {
  const [ticketId, setTicketId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [agentName, setAgentName] = useState("");
  const [reason, setReason] = useState("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TriageResult | null>(null);

  // Ingestion state
  const [ingestTicketId, setIngestTicketId] = useState("");
  const [ingestSubject, setIngestSubject] = useState("");
  const [ingestProblem, setIngestProblem] = useState("");
  const [ingestCustomerEmail, setIngestCustomerEmail] = useState("");
  const [ingestCustomerName, setIngestCustomerName] = useState("");
  const [ingestAgent, setIngestAgent] = useState("");
  const [ingestLabels, setIngestLabels] = useState("");
  const [ingestRefundAmount, setIngestRefundAmount] = useState("");
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [ingestResult, setIngestResult] = useState<HelpdeskIngestResult | null>(null);

  const env = (import.meta as unknown as { env?: CustomImportMetaEnv }).env;
  const defaultBaseUrl =
    typeof window !== "undefined" && window.location.port === "5173"
      ? "http://localhost:8000"
      : "";
  const apiBaseUrl =
    env?.VITE_API_BASE_URL !== undefined && env.VITE_API_BASE_URL !== ""
      ? env.VITE_API_BASE_URL
      : defaultBaseUrl;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (!customerName.trim()) {
      setError("Customer Name is required.");
      return;
    }

    if (!subject.trim() && !text.trim()) {
      setError("Please provide a subject or body text for the ticket.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticket_id: ticketId.trim(),
          customer_name: customerName.trim(),
          agent: agentName.trim(),
          reason: reason.trim(),
          subject: subject.trim(),
          text: text.trim(),
        }),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as {
          detail?: string | ValidationErrorDetail[];
        };
        const detail = errorData.detail;
        const message = Array.isArray(detail)
          ? detail
              .map((d: ValidationErrorDetail) => d.msg || "Invalid input")
              .join(", ")
          : typeof detail === "string"
          ? detail
          : `HTTP error ${response.status}`;
        throw new Error(message);
      }

      const data: TriageResult = await response.json();
      setResult(data);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : "Failed to triage ticket. Please check connection.";
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadSample = () => {
    setIngestTicketId("TCK-5007");
    setIngestSubject("Charged twice for annual plan");
    setIngestProblem(
      "I noticed two charges of $480.00 on my credit card statement for order #INV-8821. Please issue a refund immediately."
    );
    setIngestCustomerEmail("omar.ali@example.com");
    setIngestCustomerName("");
    setIngestAgent("Riya");
    setIngestLabels("escalated");
    setIngestRefundAmount("");
    setIngestError(null);
  };

  const handleIngestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIngestError(null);
    setIngestResult(null);

    if (!ingestSubject.trim() && !ingestProblem.trim()) {
      setIngestError("Please provide a query subject or problem description.");
      return;
    }

    setIngestLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/ops/ingest-helpdesk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticket_id: ingestTicketId.trim(),
          subject: ingestSubject.trim(),
          problem: ingestProblem.trim(),
          customer_email: ingestCustomerEmail.trim(),
          customer_name: ingestCustomerName.trim() || undefined,
          assigned_to: ingestAgent.trim(),
          labels: ingestLabels.trim(),
          refund_amount: ingestRefundAmount.trim()
            ? parseFloat(ingestRefundAmount)
            : undefined,
        }),
      });

      if (!response.ok) {
        const errData = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(errData.detail || `HTTP error ${response.status}`);
      }

      const data: HelpdeskIngestResult = await response.json();
      setIngestResult(data);
    } catch (err: unknown) {
      setIngestError(
        err instanceof Error ? err.message : "Failed to ingest helpdesk query."
      );
    } finally {
      setIngestLoading(false);
    }
  };

  return (
    <div className="container">
      <nav
        style={{
          background: "#f1f5f9",
          padding: "0.6rem 1rem",
          borderRadius: "8px",
          marginBottom: "1.5rem",
          display: "flex",
          gap: "1rem",
          alignItems: "center",
          fontSize: "0.95rem",
        }}
      >
        <strong>Support Hub:</strong>
        <a href="/triage-ui/" style={{ color: "#2563eb", fontWeight: 700, textDecoration: "none" }}>
          🤖 AI Ticket Assistant
        </a>
        <span>|</span>
        <a href={apiBaseUrl ? `${apiBaseUrl}/` : "/"} style={{ color: "#475569", fontWeight: 600, textDecoration: "none" }}>
          📊 Ticket Dashboard
        </a>
        <span>|</span>
        <a href={apiBaseUrl ? `${apiBaseUrl}/docs` : "/docs"} target="_blank" rel="noreferrer" style={{ color: "#475569", textDecoration: "none" }}>
          📖 API Documentation
        </a>
      </nav>
      <h1>AI Support Ticket Assistant</h1>
      <p>Review customer support tickets with automated category detection, urgency levels, and recommended customer replies.</p>

      {/* Live Helpdesk Ingest Card */}
      <div className="card" style={{ border: "2px solid #2563eb", marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
          <h2 style={{ margin: 0, color: "#1e3a8a", fontSize: "1.25rem" }}>
            ⚡ Live Helpdesk Query Ingest (Auto-Sync to Spreadsheet)
          </h2>
          <button
            type="button"
            onClick={handleLoadSample}
            style={{
              background: "#e0e7ff",
              color: "#3730a3",
              border: "1px solid #c7d2fe",
              padding: "0.3rem 0.75rem",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "0.85rem",
              fontWeight: 600,
            }}
          >
            📋 Load Sample Query ($480 Refund)
          </button>
        </div>
        <p style={{ fontSize: "0.9rem", color: "#64748b", margin: "0 0 1rem 0" }}>
          Paste a query from any helpdesk. AI extracts category, priority, and refund amounts, then automatically updates the 8-column tracking spreadsheet.
        </p>

        <form onSubmit={handleIngestSubmit} noValidate>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div className="form-group">
              <label htmlFor="ingest-subject">Query Subject</label>
              <input
                id="ingest-subject"
                type="text"
                placeholder="e.g. Charged twice on annual renewal"
                value={ingestSubject}
                onChange={(e) => setIngestSubject(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="ingest-email">Customer Email</label>
              <input
                id="ingest-email"
                type="email"
                placeholder="e.g. omar.ali@example.com"
                value={ingestCustomerEmail}
                onChange={(e) => setIngestCustomerEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="ingest-problem">Query Problem / Description</label>
            <textarea
              id="ingest-problem"
              rows={3}
              placeholder="Paste raw customer query text here (e.g. 'I was billed $480.00 twice on invoice #9021...')"
              value={ingestProblem}
              onChange={(e) => setIngestProblem(e.target.value)}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
            <div className="form-group">
              <label htmlFor="ingest-agent">Assigned Agent</label>
              <input
                id="ingest-agent"
                type="text"
                placeholder="e.g. Riya"
                value={ingestAgent}
                onChange={(e) => setIngestAgent(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="ingest-labels">Tags / Labels</label>
              <input
                id="ingest-labels"
                type="text"
                placeholder="e.g. escalated, vip"
                value={ingestLabels}
                onChange={(e) => setIngestLabels(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="ingest-tid">Ticket ID (Optional)</label>
              <input
                id="ingest-tid"
                type="text"
                placeholder="Auto-assigned if empty"
                value={ingestTicketId}
                onChange={(e) => setIngestTicketId(e.target.value)}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={ingestLoading}
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              padding: "0.6rem 1.25rem",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: 700,
              fontSize: "0.95rem",
            }}
          >
            {ingestLoading ? "Analyzing & Writing to Spreadsheet..." : "⚡ Ingest & Sync to Spreadsheet"}
          </button>
        </form>

        {ingestError && (
          <div className="alert-error" role="alert" style={{ marginTop: "1rem" }}>
            <strong>Notice:</strong> {ingestError}
          </div>
        )}

        {ingestResult && (
          <div
            data-testid="ingest-result-card"
            style={{
              marginTop: "1.25rem",
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              borderRadius: "8px",
              padding: "1rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <span style={{ fontWeight: 700, color: "#166534", fontSize: "1rem" }}>
                ✓ Synced to Spreadsheet ({ingestResult.ticket_id})
              </span>
              {ingestResult.escalated && (
                <span style={{ background: "#dc2626", color: "#fff", padding: "0.2rem 0.6rem", borderRadius: "4px", fontSize: "0.8rem", fontWeight: 700 }}>
                  ⚠️ URGENT ESCALATION ALERT
                </span>
              )}
            </div>

            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
              <span className="badge badge-category">Category: {ingestResult.category}</span>
              <span className={`badge badge-priority-${ingestResult.priority}`}>
                Priority: {ingestResult.priority.toUpperCase()}
              </span>
              <span style={{ background: "#fef3c7", color: "#92400e", padding: "0.2rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: 600 }}>
                Refund Amount: ${ingestResult.refund_amount.toFixed(2)} USD
              </span>
              <span style={{ background: "#e2e8f0", color: "#334155", padding: "0.2rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem" }}>
                Customer: {ingestResult.customer_name}
              </span>
              <span style={{ background: "#e2e8f0", color: "#334155", padding: "0.2rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem" }}>
                Agent: {ingestResult.assigned_to}
              </span>
            </div>

            <div style={{ fontSize: "0.9rem", color: "#1e293b", background: "#ffffff", padding: "0.75rem", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <strong>AI Suggested Reply:</strong>
              <p style={{ margin: "0.4rem 0 0 0", color: "#475569" }}>{ingestResult.suggested_reply}</p>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <form onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="customer">Customer Name <span style={{ color: "#dc2626" }}>*</span></label>
            <input
              id="customer"
              type="text"
              aria-label="Customer Name"
              placeholder="e.g. Acme Corp or Jane Doe"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="ticket-id">Ticket ID</label>
            <input
              id="ticket-id"
              type="text"
              aria-label="Ticket ID"
              placeholder="e.g. TCK-1020"
              value={ticketId}
              onChange={(e) => setTicketId(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="agent">Support Agent</label>
            <input
              id="agent"
              type="text"
              aria-label="Support Agent"
              placeholder="e.g. Alex Morgan"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="reason">Approval / Ticket Reason (Optional)</label>
            <input
              id="reason"
              type="text"
              aria-label="Approval / Ticket Reason"
              placeholder="e.g. Duplicate charge refund (auto-extracted if empty)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="subject">Ticket Subject</label>
            <input
              id="subject"
              type="text"
              aria-label="Ticket Subject"
              placeholder="e.g. Cannot log in"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="text">Ticket Body</label>
            <textarea
              id="text"
              aria-label="Ticket Body"
              placeholder="Paste customer message here..."
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          <button type="submit" disabled={loading} aria-label="Triage Ticket">
            {loading ? "Analyzing Ticket Details..." : "Review Ticket with AI"}
          </button>
        </form>

        {loading && (
          <div className="loading-spinner" role="status">
            Reading ticket details and finding the best recommended solution...
          </div>
        )}
      </div>

      {error && (
        <div className="alert-error" role="alert">
          <strong>Notice:</strong> {error}
        </div>
      )}

      {result && (
        <div className="card" data-testid="triage-result">
          <h2>Recommended Response & Ticket Summary</h2>
          <div style={{ marginBottom: "1rem" }}>
            <span className="badge badge-category" data-testid="result-category">
              Category: {result.category}
            </span>
            <span className={`badge badge-priority-${result.priority}`} data-testid="result-priority">
              Priority: {result.priority.toUpperCase()}
            </span>
          </div>

          <div>
            <h3>Recommended Customer Reply:</h3>
            <blockquote
              data-testid="result-reply"
              style={{
                background: "#f1f5f9",
                padding: "1rem",
                borderRadius: "6px",
                borderLeft: "4px solid #2563eb",
                margin: "0 0 1rem 0",
                whiteSpace: "pre-wrap",
              }}
            >
              {result.suggested_reply}
            </blockquote>
          </div>

          <div>
            <h3>Referenced Help Guides & Solutions:</h3>
            {result.article_ids && result.article_ids.length > 0 ? (
              <ul data-testid="result-sources">
                {result.article_ids.map((id) => (
                  <li key={id}>
                    <strong>{id}</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p data-testid="no-sources">No specific help guide referenced (flagged for manual team review).</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
