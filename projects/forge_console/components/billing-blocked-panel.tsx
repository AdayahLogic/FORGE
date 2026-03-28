"use client";

import { useEffect, useState } from "react";

type BlockRecord = {
  blocked?: boolean;
  reason?: string;
  blocked_at?: string;
  unblock_reason?: string;
  unblocked_at?: string;
};

type BlockedCustomersResponse = {
  status?: string;
  message?: string;
  payload?: Record<string, BlockRecord>;
};

export function BillingBlockedPanel() {
  const [records, setRecords] = useState<Record<string, BlockRecord> | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const load = async () => {
    try {
      const response = await fetch("/api/forge/billing/blocked-customers", {
        method: "GET",
        cache: "no-store",
      });
      const data = (await response.json()) as BlockedCustomersResponse;
      const payload = data.payload && typeof data.payload === "object" ? data.payload : {};
      setRecords(payload);
      setErrorMessage("");
    } catch (error) {
      setRecords({});
      setErrorMessage(error instanceof Error ? error.message : "Unable to load blocked customers.");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (records === null) {
    return null;
  }

  const blockedEntries = Object.entries(records).filter(([, value]) => Boolean(value?.blocked));

  if (blockedEntries.length === 0) {
    return (
      <section className="panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Billing</div>
            <h3>Customer Block Status</h3>
          </div>
          <span className="chip success">All Clear</span>
        </div>
        {errorMessage ? <div className="audit-item muted">{errorMessage}</div> : null}
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="section-title">
        <div>
          <div className="eyebrow">Billing</div>
          <h3>Customer Block Status</h3>
        </div>
        <span className="chip danger">{blockedEntries.length} Blocked</span>
      </div>
      <div className="control-actions">
        {blockedEntries.map(([customerId, record]) => (
          <div className="audit-item" key={customerId}>
            <strong>{customerId}</strong> - {record.reason || "unknown"} at {record.blocked_at || "-"}
          </div>
        ))}
      </div>
      {errorMessage ? <div className="audit-item muted">{errorMessage}</div> : null}
    </section>
  );
}
