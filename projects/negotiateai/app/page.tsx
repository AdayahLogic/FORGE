"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type AnalyzeResponse = {
  tone: string;
  strategy: string;
  responses: string[];
};

const DISCLAIMER_TEXT =
  "This tool provides communication suggestions for informational purposes only and does not constitute legal, financial, or professional advice.";

export default function Home() {
  const [message, setMessage] = useState("");
  const [tone, setTone] = useState("");
  const [strategy, setStrategy] = useState("");
  const [responses, setResponses] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(false);
  const [checkedDisclaimer, setCheckedDisclaimer] = useState(false);

  useEffect(() => {
    const savedValue = localStorage.getItem("negotiateai_disclaimer_accepted");
    setDisclaimerAccepted(savedValue === "true");
    setCheckedDisclaimer(true);
  }, []);

  function acceptDisclaimer() {
    localStorage.setItem("negotiateai_disclaimer_accepted", "true");
    setDisclaimerAccepted(true);
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
  }

  async function handleAnalyze() {
    if (!disclaimerAccepted) {
      return;
    }

    if (message.trim() === "") {
      setTone("N/A");
      setStrategy("Please paste a message first.");
      setResponses([]);
      return;
    }

    setTone("");
    setStrategy("");
    setResponses([]);
    setLoading(true);

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
      });

      const data: AnalyzeResponse = await response.json();

      setTone(data.tone);
      setStrategy(data.strategy);
      setResponses(data.responses);
    } catch (error) {
      setTone("Error");
      setStrategy("Something went wrong while analyzing the message.");
      setResponses([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        fontFamily: "sans-serif",
        gap: "20px",
        padding: "20px",
        backgroundColor: "black",
        color: "white",
        position: "relative",
      }}
    >
      {!checkedDisclaimer ? null : !disclaimerAccepted ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(0, 0, 0, 0.85)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            padding: "20px",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              width: "600px",
              maxWidth: "100%",
              backgroundColor: "#111",
              border: "1px solid #333",
              borderRadius: "12px",
              padding: "24px",
            }}
          >
            <h2 style={{ marginTop: 0 }}>Before you use NegotiateAI</h2>

            <p style={{ lineHeight: 1.6 }}>{DISCLAIMER_TEXT}</p>

            <p style={{ lineHeight: 1.6, color: "#cfcfcf" }}>
              You are responsible for what you send, say, or decide to do.
            </p>

            <div
              style={{
                display: "flex",
                gap: "12px",
                flexWrap: "wrap",
                marginTop: "16px",
              }}
            >
              <Link href="/terms" style={{ color: "#7dd3fc" }}>
                Terms
              </Link>

              <Link href="/privacy" style={{ color: "#7dd3fc" }}>
                Privacy
              </Link>
            </div>

            <button
              onClick={acceptDisclaimer}
              style={{
                marginTop: "20px",
                padding: "10px 16px",
                borderRadius: "8px",
                cursor: "pointer",
                fontSize: "16px",
              }}
            >
              I Understand
            </button>
          </div>
        </div>
      ) : null}

      <h1 style={{ fontSize: "48px", margin: 0 }}>IDEAL</h1>

      <p style={{ margin: 0 }}>Your AI Negotiation & Communication Copilot</p>

      <textarea
        placeholder="Paste a message you want help responding to..."
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        style={{
          width: "500px",
          maxWidth: "90%",
          height: "140px",
          padding: "12px",
          fontSize: "16px",
          borderRadius: "8px",
        }}
      />

      <button
        onClick={handleAnalyze}
        disabled={loading || !disclaimerAccepted}
        style={{
          padding: "10px 20px",
          fontSize: "16px",
          cursor: loading || !disclaimerAccepted ? "not-allowed" : "pointer",
          borderRadius: "8px",
          opacity: loading || !disclaimerAccepted ? 0.7 : 1,
        }}
      >
        {loading ? "Analyzing..." : "Analyze Message"}
      </button>

      {(tone || strategy || responses.length > 0) && (
        <div
          style={{
            width: "500px",
            maxWidth: "90%",
            backgroundColor: "#111",
            padding: "16px",
            borderRadius: "8px",
            border: "1px solid #333",
          }}
        >
          <p>
            <strong>Tone:</strong> {tone}
          </p>

          <p>
            <strong>Strategy:</strong> {strategy}
          </p>

          {responses.length > 0 && (
            <div>
              <strong>Response Options:</strong>

              <div style={{ marginTop: "10px", display: "grid", gap: "10px" }}>
                {responses.map((item, index) => (
                  <div
                    key={index}
                    style={{
                      padding: "12px",
                      borderRadius: "8px",
                      backgroundColor: "#1a1a1a",
                      border: "1px solid #333",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "8px",
                        gap: "10px",
                      }}
                    >
                      <p style={{ margin: 0, fontWeight: "bold" }}>
                        Option {index + 1}
                      </p>

                      <button
                        onClick={() => copyToClipboard(item)}
                        style={{
                          padding: "6px 10px",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: "14px",
                        }}
                      >
                        Copy
                      </button>
                    </div>

                    <p style={{ margin: 0 }}>{item}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div
            style={{
              marginTop: "16px",
              paddingTop: "12px",
              borderTop: "1px solid #333",
              fontSize: "13px",
              lineHeight: 1.5,
              color: "#cfcfcf",
            }}
          >
            <strong>Disclaimer:</strong> {DISCLAIMER_TEXT}
          </div>

          <div
            style={{
              marginTop: "10px",
              display: "flex",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <Link href="/terms" style={{ color: "#7dd3fc" }}>
              Terms
            </Link>

            <Link href="/privacy" style={{ color: "#7dd3fc" }}>
              Privacy
            </Link>
          </div>
        </div>
      )}
    </main>
  );
}