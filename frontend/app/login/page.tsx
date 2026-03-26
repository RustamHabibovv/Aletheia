"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { ShieldAlertIcon } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    setLoading(false);
    if (result?.error) {
      setError("Invalid email address.");
    } else {
      router.push("/");
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--background)",
      }}
    >
      <div
        style={{
          width: 360,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 16,
          padding: 32,
        }}
      >
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 28 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <ShieldAlertIcon size={18} color="#fff" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>Aletheia</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>Misinformation Detection</div>
          </div>
        </div>

        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px" }}>
          Sign in
        </h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 24px" }}>
          Enter your email to get started.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              style={{
                width: "100%",
                padding: "9px 12px",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-primary)",
                fontSize: 14,
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              style={{
                width: "100%",
                padding: "9px 12px",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-primary)",
                fontSize: 14,
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          {error && (
            <p style={{ fontSize: 13, color: "#ef4444", margin: 0 }}>{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: "10px",
              background: loading ? "rgba(99,102,241,0.5)" : "linear-gradient(135deg, #6366f1, #8b5cf6)",
              border: "none",
              borderRadius: 8,
              color: "#fff",
              fontSize: 14,
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              marginTop: 4,
            }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
