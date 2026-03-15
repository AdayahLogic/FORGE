import Link from "next/link";

export default function PrivacyPage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        backgroundColor: "black",
        color: "white",
        fontFamily: "sans-serif",
        padding: "40px 20px",
      }}
    >
      <div style={{ maxWidth: "800px", margin: "0 auto", lineHeight: 1.7 }}>
        <h1>Privacy Policy</h1>

        <p>
          This is a placeholder MVP privacy policy for NegotiateAI.
        </p>

        <h2>1. Private Inputs</h2>
        <p>
          User-submitted messages may contain sensitive information and should be
          treated as private data.
        </p>

        <h2>2. Anonymous Usage</h2>
        <p>
          Anonymous usage should not persist raw conversation text. If a user is
          not logged in, conversation content should not be stored.
        </p>

        <h2>3. Logged-In Users</h2>
        <p>
          Logged-in users may optionally save analysis history. Saved data should
          be limited to needed analysis records, timestamps, and basic metadata.
        </p>

        <h2>4. What We Do Not Store</h2>
        <p>
          The system should not store API keys, sensitive system prompts, or raw
          anonymous conversation logs.
        </p>

        <h2>5. Data Deletion Requests</h2>
        <p>
          Users may request deletion of saved account data and saved analysis
          history when those features are enabled.
        </p>

        <h2>6. Future Updates</h2>
        <p>
          This privacy policy will be expanded as authentication, history, and
          storage features are added.
        </p>

        <p style={{ marginTop: "30px" }}>
          <Link href="/" style={{ color: "#7dd3fc" }}>
            Back to home
          </Link>
        </p>
      </div>
    </main>
  );
}