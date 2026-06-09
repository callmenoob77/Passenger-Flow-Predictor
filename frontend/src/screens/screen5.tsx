// screen5.tsx — Refund & Credits Claim Screen
import React, { useState } from "react";
import logo from "../assets/Logo.png";
import { api } from "../lib/api";

const outfitFont = document.createElement("link");
outfitFont.rel = "stylesheet";
outfitFont.href = "https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap";
document.head.appendChild(outfitFont);

const styles: { [key: string]: React.CSSProperties } = {
  page: {
    width: "390px",
    minHeight: "844px",
    background: "#EDF2F4",
    display: "flex",
    flexDirection: "column",
    fontFamily: "'Outfit', sans-serif",
    margin: "0 auto",
  },
  header: {
    width: "100%",
    background: "#174A5D",
    padding: "20px 20px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    boxSizing: "border-box",
  },
  content: {
    flex: 1,
    padding: "40px 24px 32px",
    display: "flex",
    flexDirection: "column",
    gap: "20px",
  },
  back: {
    alignSelf: "flex-start",
    background: "transparent",
    border: "none",
    color: "#174A5D",
    fontSize: "15px",
    fontWeight: 500,
    cursor: "pointer",
    padding: 0,
    fontFamily: "'Outfit', sans-serif",
  },
  title: {
    margin: 0,
    fontSize: "24px",
    fontWeight: 600,
    color: "#0A0F1E",
  },
  subtitle: {
    margin: "4px 0 0",
    fontSize: "15px",
    color: "#5A6472",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    marginTop: "8px",
  },
  inputGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  label: {
    fontSize: "14px",
    fontWeight: 500,
    color: "#4A5568",
  },
  input: {
    width: "100%",
    padding: "14px 16px",
    borderRadius: "12px",
    border: "1px solid #CAD5E8",
    background: "#FFFFFF",
    fontSize: "15px",
    color: "#0A0F1E",
    outline: "none",
    fontFamily: "'Outfit', sans-serif",
    boxSizing: "border-box",
  },
  textarea: {
    width: "100%",
    padding: "14px 16px",
    borderRadius: "12px",
    border: "1px solid #CAD5E8",
    background: "#FFFFFF",
    fontSize: "15px",
    color: "#0A0F1E",
    outline: "none",
    fontFamily: "'Outfit', sans-serif",
    minHeight: "80px",
    resize: "vertical",
    boxSizing: "border-box",
  },
  typeSelector: {
    display: "flex",
    gap: "12px",
  },
  typeOption: {
    flex: 1,
    padding: "16px 12px",
    borderRadius: "12px",
    border: "2px solid #CAD5E8",
    background: "#FFFFFF",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    gap: "4px",
    transition: "all 0.2s ease",
  },
  typeOptionActive: {
    borderColor: "#174A5D",
    background: "#F0F4F8",
  },
  typeTitle: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#0A0F1E",
    margin: 0,
  },
  typeDesc: {
    fontSize: "11px",
    color: "#5A6472",
    margin: 0,
  },
  submitBtn: {
    marginTop: "12px",
    width: "100%",
    padding: "18px",
    background: "#174A5D",
    color: "#FFFFFF",
    border: "none",
    borderRadius: "999px",
    fontSize: "16px",
    fontWeight: 600,
    fontFamily: "'Outfit', sans-serif",
    cursor: "pointer",
  },
  error: {
    color: "#D62828",
    fontSize: "13px",
    margin: 0,
  },
  successCard: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: "32px 24px",
    textAlign: "center",
    boxShadow: "0 4px 20px rgba(10,15,30,0.08)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "20px",
    marginTop: "20px",
  },
  successBadge: {
    width: "64px",
    height: "64px",
    borderRadius: "50%",
    background: "#EDF7ED",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#6DD400",
  },
  successTitle: {
    fontSize: "22px",
    fontWeight: 600,
    color: "#0A0F1E",
    margin: 0,
  },
  successText: {
    fontSize: "15px",
    lineHeight: "1.6",
    color: "#4A5568",
    margin: 0,
  },
};

type Screen5Props = {
  flightNumber: string;
  email?: string;
  onBack: () => void;
  onHome: () => void;
};

export default function Screen5({
  flightNumber,
  email: initialEmail = "",
  onBack,
  onHome,
}: Screen5Props) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState(initialEmail);
  const [phone, setPhone] = useState("");
  const [pnr, setPnr] = useState("");
  const [refundType, setRefundType] = useState("payment_method"); // "payment_method" | "airline_credit"
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    if (!fullName.trim()) return setFormError("Full Name is required.");
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setFormError("Please enter a valid email address.");
    if (!phone.trim()) return setFormError("Phone Number is required.");
    if (pnr.trim().length !== 6 || !/^[a-zA-Z0-9]+$/.test(pnr)) return setFormError("Booking Reference (PNR) must be a 6-character alphanumeric code.");

    setLoading(true);

    try {
      const res = await fetch(api("/refund"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          flight_number: flightNumber,
          full_name: fullName,
          email: email,
          phone: phone,
          pnr: pnr.toUpperCase(),
          refund_type: refundType,
          notes: notes,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        let errMsg = "Failed to submit request.";
        try {
          const errJson = JSON.parse(errText);
          errMsg = errJson.detail || errMsg;
        } catch {
          errMsg = errText || errMsg;
        }
        throw new Error(errMsg);
      }

      setSubmitted(true);
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div style={styles.page}>
        <div style={styles.header}>
          <img src={logo} alt="Logo" style={{ width: "100px", height: "auto" }} />
          <svg
            width="32"
            height="32"
            viewBox="0 0 24 24"
            fill="none"
            style={{ cursor: "pointer", opacity: 0.8, transition: "opacity 0.2s" }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.8")}
          >
            <rect x="3" y="5" width="18" height="2" rx="1" fill="#EDF2F4" />
            <rect x="3" y="11" width="18" height="2" rx="1" fill="#EDF2F4" />
            <rect x="3" y="17" width="18" height="2" rx="1" fill="#EDF2F4" />
          </svg>
        </div>

        <div style={styles.content}>
          <div style={styles.successCard}>
            <div style={styles.successBadge}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h2 style={styles.successTitle}>Claim Submitted!</h2>
            <p style={styles.successText}>
              Your claim for <strong>{refundType === "payment_method" ? "Original Refund" : "110% Airline Credits"}</strong> has been successfully registered under PNR <strong>{pnr.toUpperCase()}</strong>.
            </p>
            <p style={{ ...styles.successText, fontSize: "13px", opacity: 0.8 }}>
              A confirmation summary has been sent to <strong>{email.toLowerCase()}</strong>. Please allow 3-5 business days for processing.
            </p>
            <button style={styles.submitBtn} onClick={onHome}>
              Return to Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <img src={logo} alt="Logo" style={{ width: "100px", height: "auto" }} />
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          style={{ cursor: "pointer", opacity: 0.8, transition: "opacity 0.2s" }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.8")}
        >
          <rect x="3" y="5" width="18" height="2" rx="1" fill="#EDF2F4" />
          <rect x="3" y="11" width="18" height="2" rx="1" fill="#EDF2F4" />
          <rect x="3" y="17" width="18" height="2" rx="1" fill="#EDF2F4" />
        </svg>
      </div>


      {/* Content */}
      <div style={styles.content}>
        <button style={styles.back} onClick={onBack}>
          ← Cancel and Go Back
        </button>

        <div>
          <h1 style={styles.title}>Claim Refund / Voucher</h1>
          <p style={styles.subtitle}>Flight: {flightNumber} · Cancelled due to Fog</p>
        </div>

        <form style={styles.form} onSubmit={handleSubmit}>
          {/* Full Name */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Full Passenger Name</label>
            <input
              type="text"
              placeholder="e.g. John Doe"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              style={styles.input}
              required
            />
          </div>

          {/* Email */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Email Address</label>
            <input
              type="email"
              placeholder="e.g. john@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
              required
            />
          </div>

          {/* Phone */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Phone Number</label>
            <input
              type="tel"
              placeholder="e.g. +40 722 123 456"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              style={styles.input}
              required
            />
          </div>

          {/* Booking Ref (PNR) */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Booking Reference (PNR)</label>
            <input
              type="text"
              maxLength={6}
              placeholder="e.g. AB12CD"
              value={pnr}
              onChange={(e) => setPnr(e.target.value)}
              style={{ ...styles.input, textTransform: "uppercase" }}
              required
            />
          </div>

          {/* Claim Type Selection */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Compensation Choice</label>
            <div style={styles.typeSelector}>
              <div
                style={{
                  ...styles.typeOption,
                  ...(refundType === "payment_method" ? styles.typeOptionActive : {}),
                }}
                onClick={() => setRefundType("payment_method")}
              >
                <p style={styles.typeTitle}>Original Refund</p>
                <p style={styles.typeDesc}>100% Value Back</p>
              </div>

              <div
                style={{
                  ...styles.typeOption,
                  ...(refundType === "airline_credits" ? styles.typeOptionActive : {}),
                }}
                onClick={() => setRefundType("airline_credits")}
              >
                <p style={styles.typeTitle}>Airline Credits</p>
                <p style={{ ...styles.typeDesc, color: "#6DD400", fontWeight: "bold" }}>110% Value Voucher</p>
              </div>
            </div>
          </div>

          {/* Optional Notes */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Additional Notes (Optional)</label>
            <textarea
              placeholder="E.g. requesting original card payment refund..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              style={styles.textarea}
            />
          </div>

          {formError && <p style={styles.error}>⚠️ {formError}</p>}

          <button type="submit" style={styles.submitBtn} disabled={loading}>
            {loading ? "Submitting Request..." : "Submit Claim Request"}
          </button>
        </form>
      </div>
    </div>
  );
}
