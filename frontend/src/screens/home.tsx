import React, { useState } from "react";
import logo from "../assets/Logo.png";

const outfitFont = document.createElement("link");
outfitFont.rel = "stylesheet";
outfitFont.href = "https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700&display=swap";
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
padding: "0px 0px 0px",
},
content: {
flex: 1,
padding: "40px 24px 32px",
display: "flex",
flexDirection: "column",
gap: "20px",
},
title: {
margin: "0 0 8px",
fontSize: "28px",
fontWeight: 500,
color: "#0A0F1E",
lineHeight: 1.2,
fontFamily: "'Outfit', sans-serif",
},
inputGroup: {
display: "flex",
flexDirection: "column",
gap: "12px",
},
inputWrapper: {
display: "flex",
alignItems: "center",
background: "#CAD5E8",
borderRadius: "16px",
padding: "18px 20px",
},
input: {
border: "none",
background: "transparent",
fontSize: "15px",
color: "#6B7A99",
outline: "none",
width: "100%",
fontFamily: "'Outfit', sans-serif",
},
sendRow: {
display: "flex",
justifyContent: "flex-end",
},
sendButton: {
background: "#CAD5E8",
color: "#4A5568",
border: "none",
borderRadius: "20px",
padding: "8px 20px",
fontSize: "14px",
fontFamily: "'Outfit', sans-serif",
cursor: "pointer",
},
banner: {
marginTop: "24px",
background: "#174A5D",
borderRadius: "16px",
padding: "20px",
display: "flex",
alignItems: "center",
gap: "16px",
},
bannerText: {
margin: 0,
fontSize: "14px",
color: "#FFFFFF",
lineHeight: 1.6,
fontFamily: "'Outfit', sans-serif",
},
};

export default function Home({ onSubmit }: { onSubmit?: (data: any) => void }) {
const [flightNumber, setFlightNumber] = useState("");
const [email, setEmail] = useState("");
const [loading, setLoading] = useState(false);
const [flightError, setFlightError] = useState("");
const [emailError, setEmailError] = useState("");
const [success, setSuccess] = useState(false);

const handleSend = () => {
  setFlightError("");
  setEmailError("");

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  // 2 letters + space + 1 to 4 digits
  const flightRegex = /^[A-Z]{2}\s\d{1,4}$/;

  let hasError = false;

  if (!flightRegex.test(flightNumber.trim().toUpperCase())) {
    setFlightError(
      "Flight number must be in format LL X to LL XXXX (e.g. RO 1, RO 1234)"
    );
    hasError = true;
  }

  if (!emailRegex.test(email.trim())) {
    setEmailError("Please enter a valid email address.");
    hasError = true;
  }

  if (hasError) return;

  setLoading(true);

  setTimeout(() => {
    setLoading(false);
    setSuccess(true);

    if (onSubmit) {
      onSubmit({
        flightNumber,
        email,
      });
    }
  }, 1000);
};

return (
<div style={styles.page}>
{/* Header with logo */}
<div style={styles.header}>
<img src={logo} alt="Logo" style={{ width: "100px", height: "auto" }} />

</div>

{/* Content */}
<div style={styles.content}>
<h1 style={styles.title}>Check Your Flight Status!</h1>

<div style={styles.inputGroup}>
<div style={styles.inputWrapper}>
  <input
    type="text"
    placeholder="Your Flight Number..."
    value={flightNumber}
    onChange={(e) => {
  setFlightNumber(e.target.value.toUpperCase());
  setSuccess(false);
}}
    style={styles.input}
  />
</div>

{flightError && (
  <p
    style={{
      color: "#D62828",
      fontSize: "13px",
      margin: "4px 0 0 4px",
    }}
  >
    {flightError}
  </p>
)}

<div style={{ ...styles.inputWrapper, padding: "14px 20px" }}>
 <input
  type="email"
  placeholder="Your Email Address..."
  value={email}
  onChange={(e) => {
    setEmail(e.target.value);
    setSuccess(false);
  }}
  style={styles.input}
/>
</div>

{emailError && (
  <p
    style={{
      color: "#D62828",
      fontSize: "13px",
      margin: "4px 0 0 4px",
    }}
  >
    {emailError}
  </p>
)}

<div style={styles.sendRow}>
<button
  onClick={handleSend}
  style={{
    ...styles.sendButton,
    background: success ? "#6DD400" : "#CAD5E8",
    color: success ? "#FFFFFF" : "#4A5568",
  }}
>
{loading ? "Sending..." : success ? "Sent!" : "Send"}</button>
</div>

{/* Banner */}
<div style={styles.banner}>
<svg width="40" height="40" viewBox="0 0 36 36" fill="none"  style={{ flexShrink: 0
 }}>
<path d="M18 4 L32 30 H4 Z" fill="none" stroke="#B0B0B0" strokeWidth="2"/>
<text x="18" y="26" textAnchor="middle" fontSize="14" fill="#6DD400" fontWeight="bold">!</text>
</svg>
<p style={styles.bannerText}>
Iasi Airport is frequently affected by fog. Please submit your email address to receive notifications in real time.
</p>
</div>
</div>
</div>
</div>)};
