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

  it("renders live tracking sheet table and download for Excel button with custom filename", async () => {
    const mockTickets = [
      {
        ticket_id: "TCK-5090",
        created_at: "16/10/2026",
        status: "open",
        priority: "urgent",
        category: "Refunds",
        assigned_to: "riya",
        customer_email: "sailakshman212005@gmail.com",
        labels: "escalated",
        refund_amount: "250.00",
      },
    ];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockTickets,
    } as Response);

    render(<App />);

    expect(screen.getByTestId("tracking-sheet-table")).toBeInTheDocument();
    const downloadBtn = screen.getByTestId("download-excel-btn");
    expect(downloadBtn).toBeInTheDocument();
    expect(downloadBtn).toHaveTextContent("Download for Excel");
    expect(downloadBtn).toHaveAttribute(
      "download",
      "Help Desk Tracking Sheet.csv"
    );
    expect(downloadBtn).toHaveAttribute(
      "href",
      expect.stringContaining("/ops/export-tracking-sheet")
    );

    await waitFor(() => {
      expect(screen.getByText("TCK-5090")).toBeInTheDocument();
    });
    expect(screen.getByText("sailakshman212005@gmail.com")).toBeInTheDocument();
    expect(screen.getByText("$250.00")).toBeInTheDocument();
  });

  it("renders clear sheet button and handles clearing tracking records", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    const clearBtn = screen.getByTestId("clear-sheet-btn");
    expect(clearBtn).toBeInTheDocument();
    expect(clearBtn).toHaveTextContent("Clear Sheet");

    await waitFor(() => {
      expect(clearBtn).not.toBeDisabled();
    });

    fireEvent.click(clearBtn);

    expect(confirmSpy).toHaveBeenCalled();
  });

  it("renders auto-extract fields button in live helpdesk card", () => {
    render(<App />);
    expect(
      screen.getByRole("button", { name: /auto-extract fields/i })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/customer name/i)).toBeInTheDocument();
  });

  it("calls /triage/extract and populates customer fields with auto-populated badges", async () => {
    const mockExtraction = {
      customer_name: "Marcus Brody",
      customer_email: "marcus@example.com",
      agent: "Sai",
      subject: "Password Reset and Account Access Issue",
      operational_reason: "Account authentication lockout",
      category: "Login",
      priority: "normal",
      suggested_reply: "Please follow these password reset steps.",
      article_ids: ["KB-001"],
      refund_amount: 0.0,
      auto_populated_fields: ["customer_name", "customer_email", "subject", "agent", "operational_reason"],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockExtraction,
    } as Response);

    render(<App />);

    fireEvent.change(screen.getByLabelText(/problem/i), {
      target: {
        value: "My name is Marcus Brody. I cannot log in at marcus@example.com.",
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /auto-extract fields/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/customer name/i)).toHaveValue("Marcus Brody");
    });

    expect(screen.getByLabelText(/customer email/i)).toHaveValue("marcus@example.com");
    expect(screen.getByLabelText(/query subject/i)).toHaveValue(
      "Password Reset and Account Access Issue"
    );
    expect(screen.getByLabelText(/assigned agent/i)).toHaveValue("Sai");
    expect(screen.getAllByText(/auto-populated/i).length).toBeGreaterThan(0);
  });
});



