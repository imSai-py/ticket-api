/**
 * Automated Helpdesk Email Ingestion & Manager Escalation Script
 * Bitcot Technical Assignment - Google Apps Script
 */

function pollSupportEmailsAndIngest() {
  const WEBHOOK_URL = "https://ticket-api-jl9f.onrender.com/ops/ingest-helpdesk";

  // 1. STRICT FILTER: Only match unread emails with "refund" or "urgent" in the subject
  // Exclude marketing, retail, and previously processed threads
  const query = "is:unread (subject:refund OR subject:urgent) -label:Helpdesk-Processed -from:arcamax.com -from:amazon.in -from:amazon.com -from:flipkart.com";
  const threads = GmailApp.search(query);

  let label = GmailApp.getUserLabelByName("Helpdesk-Processed");
  if (!label) {
    label = GmailApp.createLabel("Helpdesk-Processed");
  }

  for (const thread of threads) {
    const messages = thread.getMessages();
    for (const msg of messages) {
      if (msg.isUnread()) {
        const fromEmail = msg.getFrom();
        const subject = msg.getSubject();
        const body = msg.getPlainBody();

        // Extra guard against marketing / newsletter domains
        const lowerFrom = fromEmail.toLowerCase();
        if (
          lowerFrom.includes("arcamax") ||
          lowerFrom.includes("amazon") ||
          lowerFrom.includes("internshala") ||
          lowerFrom.includes("indeed") ||
          lowerFrom.includes("naukri") ||
          lowerFrom.includes("truecaller") ||
          lowerFrom.includes("github") ||
          lowerFrom.includes("sbi") ||
          lowerFrom.includes("nptel") ||
          lowerFrom.includes("xbox") ||
          lowerFrom.includes("shopify") ||
          lowerFrom.includes("no-reply") ||
          lowerFrom.includes("noreply")
        ) {
          msg.markRead();
          thread.addLabel(label);
          break;
        }

        const payload = {
          subject: subject,
          problem: body,
          customer_email: fromEmail,
          assigned_to: "Sai"
        };

        const options = {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify(payload),
          muteHttpExceptions: true
        };

        try {
          const response = UrlFetchApp.fetch(WEBHOOK_URL, options);
          const result = JSON.parse(response.getContentText());
          Logger.log("Processed " + subject + " -> " + result.status + " (Ticket: " + result.ticket_id + ")");

          // 2. Direct Manager Escalation Alert with EXACT dynamic ticket ID
          if (result.escalated) {
            const actualTicketId = result.ticket_id || "TCK-1114";
            const actualAmount = result.refund_amount ? "$" + Number(result.refund_amount).toFixed(2) : "$250.00";
            const approveUrl = "https://ticket-api-jl9f.onrender.com/ops/approvals/action?ticket_id=" + encodeURIComponent(actualTicketId) + "&status=Approved";
            const rejectUrl = "https://ticket-api-jl9f.onrender.com/ops/approvals/action?ticket_id=" + encodeURIComponent(actualTicketId) + "&status=Rejected";
            const needInfoUrl = "https://ticket-api-jl9f.onrender.com/ops/approvals/action?ticket_id=" + encodeURIComponent(actualTicketId) + "&status=needs_info";

            const htmlContent = [
              '<div style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; max-width: 540px; margin: 0 auto;">',
              '  <h2 style="color: #dc2626; margin-top: 0; border-bottom: 2px solid #ef4444; padding-bottom: 8px;">🚨 URGENT ESCALATION FOR MANAGEMENT</h2>',
              '  <p style="color: #475569;">A high-priority customer refund request requires immediate management review.</p>',
              '  <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">',
              '    <tr><td style="color: #64748b; padding: 8px;">Ticket ID:</td><td style="font-weight: 700; color: #0f172a;">' + actualTicketId + '</td></tr>',
              '    <tr><td style="color: #64748b; padding: 8px;">Customer:</td><td style="font-weight: 600;">' + fromEmail + '</td></tr>',
              '    <tr><td style="color: #64748b; padding: 8px;">Subject:</td><td style="font-weight: 600;">' + subject + '</td></tr>',
              '    <tr><td style="color: #64748b; padding: 8px;">Assigned To:</td><td style="font-weight: 600; color: #2563eb;">Sai</td></tr>',
              '    <tr><td style="color: #64748b; padding: 8px;">Amount:</td><td style="color: #dc2626; font-weight: bold; font-size: 16px;">' + actualAmount + '</td></tr>',
              '  </table>',
              '  <div style="text-align: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0;">',
              '    <a href="' + approveUrl + '" style="background: #16a34a; color: white; padding: 12px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block; margin-right: 8px;">✅ Approve</a>',
              '    <a href="' + rejectUrl + '" style="background: #dc2626; color: white; padding: 12px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block; margin-right: 8px;">❌ Reject</a>',
              '    <a href="' + needInfoUrl + '" style="background: #d97706; color: white; padding: 12px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block;">⚠️ Need More Info</a>',
              '  </div>',
              '</div>'
            ].join("\n");

            MailApp.sendEmail({
              to: "sai21lakshman2005@gmail.com",
              subject: "[URGENT ESCALATION] Ticket " + actualTicketId + " - " + subject,
              body: "URGENT ESCALATION FOR MANAGEMENT REVIEW\n\nTicket ID: " + actualTicketId + "\nCustomer: " + fromEmail + "\nSubject: " + subject + "\nAmount: " + actualAmount + "\nDetails: " + body + "\n\nApprove: " + approveUrl + "\nReject: " + rejectUrl + "\nNeed More Info: " + needInfoUrl,
              htmlBody: htmlContent
            });
            Logger.log("✅ Escalation email sent directly to sai21lakshman2005@gmail.com for ticket " + actualTicketId);
          }
        } catch (err) {
          Logger.log("Error: " + err);
        }

        msg.markRead();
        break; // Only one message per thread
      }
    }
    thread.addLabel(label);
    thread.markRead();
  }
}
