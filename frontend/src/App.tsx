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

export interface BatchIngestRecord {
  ticket_id: string;
  created_at: string;
  status: string;
  priority: string;
  category: string;
  assigned_to: string;
  customer_email: string;
  labels: string;
  refund_amount: string;
}

export interface BatchIngestResult {
  status: string;
  processed_count: number;
  records: BatchIngestRecord[];
  escalated_count: number;
  escalations: Array<{
    ticket_id: string;
    recipient: string;
    subject: string;
    amount?: number;
    alert_type?: string;
  }>;
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

  // Batch Ingestion state
  const [batchFile, setBatchFile] = useState<File | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<BatchIngestResult | null>(null);

  // Support Agent Re-submission state
  const [resubmitTicketId, setResubmitTicketId] = useState("");
  const [resubmitContext, setResubmitContext] = useState("");
  const [resubmitAmount, setResubmitAmount] = useState("");
  const [resubmitAgent, setResubmitAgent] = useState("");
  const [resubmitLoading, setResubmitLoading] = useState(false);
  const [resubmitError, setResubmitError] = useState<string | null>(null);
  const [resubmitSuccess, setResubmitSuccess] = useState<string | null>(null);

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

  const handleLoadSampleBatch = () => {
    const sampleCsv = `ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount
TCK-5007,2026-10-05 13:05,in_progress,urgent,Refunds,riya,omar.ali@example.com,escalated,480.00
TCK-5084,2026-10-05 13:21,in_progress,normal,Login,riya,jo.marsh@example.com,,0.00
TCK-5041,2026-10-05 13:25,open,normal,Refunds,lia,max.obi@example.com,esc,80.00
TCK-5052,2026-10-05 13:55,open,normal,Refunds,sam,hana.ito@example.com,esc,250.00
TCK-5043,2026-10-05 14:02,resolved,normal,Technical,riya,ava.stone@example.com,,0.00`;
    const file = new File([sampleCsv], "helpdesk_export_sample.csv", {
      type: "text/csv",
    });
    setBatchFile(file);
    setBatchError(null);
  };

  const handleBatchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBatchError(null);
    setBatchResult(null);

    if (!batchFile) {
      setBatchError("Please select a CSV file or load a sample first.");
      return;
    }

    setBatchLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", batchFile);

      const response = await fetch(`${apiBaseUrl}/ops/ingest-batch`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errData = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(errData.detail || `HTTP error ${response.status}`);
      }

      const data: BatchIngestResult = await response.json();
      setBatchResult(data);
    } catch (err: unknown) {
      setBatchError(
        err instanceof Error ? err.message : "Failed to import batch CSV."
      );
    } finally {
      setBatchLoading(false);
    }
  };

  const handleResubmitSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resubmitTicketId.trim()) {
      setResubmitError("Ticket ID is required for re-submission.");
      return;
    }
    if (!resubmitContext.trim()) {
      setResubmitError("Supplemental context / operational justification is required.");
      return;
    }
    setResubmitLoading(true);
    setResubmitError(null);
    setResubmitSuccess(null);
    try {
      const payload: Record<string, unknown> = {
        ticket_id: resubmitTicketId.trim(),
        reason: resubmitContext.trim(),
        agent: resubmitAgent.trim() || "Support Agent",
      };
      if (resubmitAmount.trim()) {
        const parsed = parseFloat(resubmitAmount.replace(/[^0-9.]/g, ""));
        if (!isNaN(parsed)) {
          payload.amount = parsed;
        }
      }
      const response = await fetch(`${apiBaseUrl}/ops/sync-ticket`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        ticket?: { ticket_id?: string; status?: string };
      };
      if (!response.ok) {
        setResubmitError(data?.detail || "Re-submission failed.");
      } else {
        setResubmitSuccess(
          `Ticket ${resubmitTicketId} re-submitted successfully and returned to Pending queue for manager approval.`
        );
      }
    } catch (err: unknown) {
      setResubmitError(
        err instanceof Error ? err.message : "Failed to re-submit ticket."
      );
    } finally {
      setResubmitLoading(false);
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

      {/* Batch CSV Ingest Card */}
      <div className="card" style={{ border: "2px solid #059669", marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
          <div>
            <h2 style={{ margin: 0, color: "#065f46", fontSize: "1.25rem" }}>
              📁 Batch Helpdesk CSV Ingestion & Escalation Routing
            </h2>
            <p style={{ margin: "0.25rem 0 0 0", color: "#4b5563", fontSize: "0.9rem" }}>
              Bulk upload historical Helpdesk exports. Automatically normalizes 9 standard columns, resolves priority hierarchy, and triggers instant manager alerts.
            </p>
          </div>
          <button
            type="button"
            onClick={handleLoadSampleBatch}
            style={{
              background: "#d1fae5",
              color: "#065f46",
              border: "1px solid #a7f3d0",
              borderRadius: "6px",
              padding: "0.4rem 0.8rem",
              fontSize: "0.85rem",
              cursor: "pointer",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            📋 Load Sample Batch CSV
          </button>
        </div>

        <form onSubmit={handleBatchSubmit} noValidate>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", marginBottom: "1rem" }}>
            <input
              type="file"
              accept=".csv"
              aria-label="Upload CSV File"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setBatchFile(e.target.files[0]);
                  setBatchError(null);
                }
              }}
              style={{ padding: "0.5rem", border: "1px solid #d1d5db", borderRadius: "6px" }}
            />
            {batchFile && (
              <span style={{ fontSize: "0.9rem", color: "#047857", fontWeight: 600 }}>
                Selected: {batchFile.name} ({(batchFile.size / 1024).toFixed(1)} KB)
              </span>
            )}
            <button
              type="submit"
              disabled={batchLoading || !batchFile}
              aria-label="Upload & Ingest Batch CSV"
              style={{
                background: batchLoading || !batchFile ? "#9ca3af" : "#059669",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                padding: "0.55rem 1.25rem",
                fontWeight: 600,
                cursor: batchLoading || !batchFile ? "not-allowed" : "pointer",
              }}
            >
              {batchLoading ? "Processing Batch CSV..." : "🚀 Upload & Ingest Batch CSV"}
            </button>
          </div>
        </form>

        {batchError && (
          <div className="alert-error" role="alert" style={{ marginTop: "0.5rem" }}>
            <strong>Batch Ingestion Notice:</strong> {batchError}
          </div>
        )}

        {batchResult && (
          <div
            data-testid="batch-result-card"
            style={{
              marginTop: "1.25rem",
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              borderRadius: "8px",
              padding: "1rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
              <span style={{ fontWeight: 700, color: "#166534", fontSize: "1.05rem" }}>
                ✓ Successfully Ingested {batchResult.processed_count} Tickets to Spreadsheet
              </span>
              {batchResult.escalated_count > 0 && (
                <span style={{ background: "#dc2626", color: "#fff", padding: "0.25rem 0.75rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: 700 }}>
                  ⚠️ {batchResult.escalated_count} URGENT ESCALATIONS TRIGGERED
                </span>
              )}
            </div>

            {batchResult.escalations && batchResult.escalations.length > 0 && (
              <div style={{ marginBottom: "1rem", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "6px", padding: "0.75rem" }}>
                <strong style={{ color: "#991b1b", fontSize: "0.9rem" }}>Dispatched Escalation Alerts:</strong>
                <ul style={{ margin: "0.4rem 0 0 1.2rem", padding: 0, fontSize: "0.85rem", color: "#7f1d1d" }}>
                  {batchResult.escalations.map((esc, i) => (
                    <li key={i}>
                      <strong>{esc.ticket_id}</strong>: {esc.subject} → {esc.recipient}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", background: "#ffffff" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", textAlign: "left", borderBottom: "2px solid #e2e8f0" }}>
                    <th style={{ padding: "0.5rem" }}>Ticket ID</th>
                    <th style={{ padding: "0.5rem" }}>Priority</th>
                    <th style={{ padding: "0.5rem" }}>Category</th>
                    <th style={{ padding: "0.5rem" }}>Refund Amount</th>
                    <th style={{ padding: "0.5rem" }}>Customer</th>
                    <th style={{ padding: "0.5rem" }}>Agent</th>
                    <th style={{ padding: "0.5rem" }}>Labels</th>
                  </tr>
                </thead>
                <tbody>
                  {batchResult.records.slice(0, 10).map((r) => (
                    <tr key={r.ticket_id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "0.4rem 0.5rem", fontWeight: 600 }}>{r.ticket_id}</td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        <span className={`badge badge-priority-${r.priority.toLowerCase()}`}>
                          {r.priority.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{r.category}</td>
                      <td style={{ padding: "0.4rem 0.5rem", fontWeight: 600, color: parseFloat(r.refund_amount) > 0 ? "#b45309" : "#64748b" }}>
                        ${parseFloat(r.refund_amount || "0").toFixed(2)}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{r.customer_email || "Customer"}</td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{r.assigned_to || "Unassigned"}</td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{r.labels || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {batchResult.records.length > 10 && (
                <div style={{ textAlign: "center", fontSize: "0.8rem", color: "#64748b", marginTop: "0.5rem" }}>
                  Showing first 10 of {batchResult.records.length} records. All records persisted to <code>ops_tracking_sheet.csv</code>.
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Support Agent Re-submission Card */}
      <div className="card" style={{ border: "2px solid #0d9488", marginBottom: "2rem" }}>
        <h2 style={{ margin: "0 0 0.5rem 0", color: "#0f766e", fontSize: "1.25rem" }}>
          🔄 Support Agent Ticket Re-submission & Verification
        </h2>
        <p style={{ fontSize: "0.9rem", color: "#64748b", margin: "0 0 1rem 0" }}>
          Re-submit tickets flagged with "Need More Info" with supplemental customer details and verified operational justification. Moves the ticket back to Pending for the next manager approval digest.
        </p>

        <form onSubmit={handleResubmitSubmit} noValidate>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div className="form-group">
              <label htmlFor="resubmit-ticket-id">Ticket ID *</label>
              <input
                id="resubmit-ticket-id"
                type="text"
                aria-label="Ticket ID for Re-submission"
                placeholder="e.g. TCK-1001"
                value={resubmitTicketId}
                onChange={(e) => setResubmitTicketId(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="resubmit-agent">Support Agent *</label>
              <input
                id="resubmit-agent"
                type="text"
                aria-label="Agent Name"
                placeholder="e.g. Riya"
                value={resubmitAgent}
                onChange={(e) => setResubmitAgent(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="resubmit-amount">Refund Amount USD (Optional)</label>
            <input
              id="resubmit-amount"
              type="text"
              aria-label="Refund Amount"
              placeholder="e.g. 150.00"
              value={resubmitAmount}
              onChange={(e) => setResubmitAmount(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="resubmit-context">Supplemental Context & Operational Justification *</label>
            <textarea
              id="resubmit-context"
              aria-label="Supplemental Context"
              placeholder="Explain verified customer circumstances, merchant gateway transaction IDs, or billing audit details..."
              value={resubmitContext}
              onChange={(e) => setResubmitContext(e.target.value)}
            />
          </div>

          <button
            type="submit"
            disabled={resubmitLoading}
            aria-label="Re-submit Ticket"
            style={{ background: "#0d9488", color: "#fff", fontWeight: 600 }}
          >
            {resubmitLoading ? "Submitting Context..." : "Re-submit Ticket for Manager Review"}
          </button>
        </form>

        {resubmitError && (
          <div className="alert-error" role="alert" style={{ marginTop: "1rem" }}>
            <strong>Notice:</strong> {resubmitError}
          </div>
        )}

        {resubmitSuccess && (
          <div
            data-testid="resubmit-success"
            style={{
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              color: "#166534",
              padding: "1rem",
              borderRadius: "6px",
              marginTop: "1rem",
            }}
          >
            ✓ {resubmitSuccess}
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
