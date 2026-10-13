import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";

describe("App Triage Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders form inputs and submission button", () => {
    render(<App />);
    expect(screen.getByLabelText(/ticket subject/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/ticket body/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /triage ticket/i })).toBeInTheDocument();
  });

  it("submits ticket and displays triage result", async () => {
    const mockTriageResult = {
      category: "Login",
      priority: "high",
      suggested_reply: "Please use 'Forgot password' to reset your access. Email arrives within 10 minutes.",
      article_ids: ["KB-001"],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockTriageResult,
    } as Response);

    render(<App />);

    fireEvent.change(screen.getByLabelText(/ticket subject/i), {
      target: { value: "Cannot log in" },
    });
    fireEvent.change(screen.getByLabelText(/ticket body/i), {
      target: { value: "Reset password email never arrives" },
    });

    fireEvent.click(screen.getByRole("button", { name: /triage ticket/i }));

    await waitFor(() => {
      expect(screen.getByTestId("triage-result")).toBeInTheDocument();
    });

    expect(screen.getByTestId("result-category")).toHaveTextContent("Login");
    expect(screen.getByTestId("result-priority")).toHaveTextContent("HIGH");
    expect(screen.getByTestId("result-reply")).toHaveTextContent("Please use 'Forgot password'");
    expect(screen.getByTestId("result-sources")).toHaveTextContent("KB-001");
  });

  it("displays error state when submission fails", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "Invalid ticket input" }),
    } as Response);

    render(<App />);

    fireEvent.change(screen.getByLabelText(/ticket subject/i), {
      target: { value: "Test Subject" },
    });
    fireEvent.change(screen.getByLabelText(/ticket body/i), {
      target: { value: "Test Body" },
    });

    fireEvent.click(screen.getByRole("button", { name: /triage ticket/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Invalid ticket input");
  });

  it("shows local validation message when submitting completely empty form", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /triage ticket/i }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/please provide a subject or body text/i);
  });
});
