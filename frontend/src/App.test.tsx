import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";

describe("App Triage Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders core operations forms and ensures legacy form is removed", () => {
    render(<App />);
    expect(screen.getByLabelText(/query subject/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/customer email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/problem/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ingest & sync to spreadsheet/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /upload & ingest batch csv/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /re-submit ticket/i })
    ).toBeInTheDocument();

    // Verify duplicate legacy form is completely removed
    expect(
      screen.queryByRole("button", { name: /review ticket with ai/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /triage ticket/i })
    ).not.toBeInTheDocument();
  });

  it("shows validation message when submitting empty query form", async () => {
    render(<App />);
    fireEvent.click(
      screen.getByRole("button", { name: /ingest & sync to spreadsheet/i })
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /please provide a query subject or problem description/i
    );
  });

  it("loads sample helpdesk query when clicking sample button", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /load sample query/i }));

    expect(screen.getByLabelText(/query subject/i)).toHaveValue(
      "Charged twice for annual plan"
    );
    expect(screen.getByLabelText(/customer email/i)).toHaveValue(
      "omar.ali@example.com"
    );
  });

  it("submits helpdesk query and renders synced spreadsheet confirmation card", async () => {
    const mockIngestResult = {
      status: "success",
      ticket_id: "TCK-5007",
      category: "Refunds",
      priority: "urgent",
      refund_amount: 480.0,
      customer_name: "Omar Ali",
      assigned_to: "Riya",
      suggested_reply: "We have initiated a refund of $480.00 for invoice #INV-8821.",
      record: {
        ticket_id: "TCK-5007",
        customer_name: "Omar Ali",
        category: "Refunds",
        priority: "urgent",
        amount: "480.00",
        reason: "Duplicate charge refund",
        agent: "Riya",
        status: "open",
        escalated: "True",
        created_at: "2026-10-15 14:00:00",
      },
      escalated: true,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockIngestResult,
    } as Response);

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /load sample query/i }));
    fireEvent.click(screen.getByRole("button", { name: /ingest & sync to spreadsheet/i }));

    await waitFor(() => {
      expect(screen.getByTestId("ingest-result-card")).toBeInTheDocument();
    });

    expect(screen.getByTestId("ingest-result-card")).toHaveTextContent("Synced to Spreadsheet (TCK-5007)");
    expect(screen.getByTestId("ingest-result-card")).toHaveTextContent("Refund Amount: $480.00 USD");
    expect(screen.getByTestId("ingest-result-card")).toHaveTextContent("URGENT ESCALATION ALERT");
  });

  it("loads sample batch CSV and displays selected file name", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /load sample batch csv/i }));

    expect(screen.getByText(/selected: helpdesk_export_sample\.csv/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload & ingest batch csv/i })).not.toBeDisabled();
  });

  it("submits batch CSV and renders batch summary with escalation alerts", async () => {
    const mockBatchResult = {
      status: "success",
      processed_count: 5,
      records: [
        {
          ticket_id: "TCK-5007",
          created_at: "2026-10-05 13:05",
          status: "in_progress",
          priority: "urgent",
          category: "Refunds",
          assigned_to: "riya",
          customer_email: "omar.ali@example.com",
          labels: "escalated",
          refund_amount: "480.00",
        },
        {
          ticket_id: "TCK-5084",
          created_at: "2026-10-05 13:21",
          status: "in_progress",
          priority: "normal",
          category: "Login",
          assigned_to: "riya",
          customer_email: "jo.marsh@example.com",
          labels: "",
          refund_amount: "0.00",
        },
      ],
      escalated_count: 1,
      escalations: [
        {
          ticket_id: "TCK-5007",
          recipient: "manager@company.com",
          subject: "[URGENT ESCALATION] Ticket TCK-5007 - omar.ali@example.com",
          amount: 480.0,
        },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBatchResult,
    } as Response);

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /load sample batch csv/i }));
    fireEvent.click(screen.getByRole("button", { name: /upload & ingest batch csv/i }));

    await waitFor(() => {
      expect(screen.getByTestId("batch-result-card")).toBeInTheDocument();
    });

    expect(screen.getByTestId("batch-result-card")).toHaveTextContent("Successfully Ingested 5 Tickets to Spreadsheet");
    expect(screen.getByTestId("batch-result-card")).toHaveTextContent("1 URGENT ESCALATIONS TRIGGERED");
    expect(screen.getByTestId("batch-result-card")).toHaveTextContent("TCK-5007");
    expect(screen.getByTestId("batch-result-card")).toHaveTextContent("$480.00");
  });

  it("re-submits updated ticket with supplemental context and displays confirmation", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ticket: { ticket_id: "TCK-1001", status: "Pending" },
      }),
    } as Response);

    render(<App />);

    fireEvent.change(screen.getByLabelText(/ticket id for re-submission/i), {
      target: { value: "TCK-1001" },
    });
    fireEvent.change(screen.getByLabelText(/supplemental context/i), {
      target: { value: "Verified double billing transaction ID #TX99821." },
    });

    fireEvent.click(screen.getByRole("button", { name: /re-submit ticket/i }));

    await waitFor(() => {
      expect(screen.getByTestId("resubmit-success")).toBeInTheDocument();
    });

    expect(screen.getByTestId("resubmit-success")).toHaveTextContent(
      "Ticket TCK-1001 re-submitted successfully"
    );
  });
});

