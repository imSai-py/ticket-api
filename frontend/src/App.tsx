import React, { useState } from "react";

export interface TriageResult {
  category: "Billing" | "Login" | "Shipping" | "Refunds" | "Technical" | "Account";
  priority: "urgent" | "high" | "normal" | "low";
  suggested_reply: string;
  article_ids: string[];
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
