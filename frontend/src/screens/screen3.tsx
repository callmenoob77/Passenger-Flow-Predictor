import React from "react";
import logo from "../assets/Logo.png";

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

  logo: {
    width: "100px",
    height: "auto",
  },

  content: {
    padding: "60px 40px",
    display: "flex",
    flexDirection: "column",
  },

  topRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "70px",
  },

  flightTitle: {
    margin: 0,
    fontSize: "20px",
    fontWeight: 500,
    color: "#000",
  },

  cancelledPill: {
    background: "#C8D0E8",
    borderRadius: "999px",
    padding: "12px 20px",
    color: "#F04E23",
    fontSize: "16px",
    fontWeight: 700,
  },

  text: {
    fontSize: "18px",
    lineHeight: "1.5",
    color: "#000",
    marginBottom: "40px",
  },

  button: {
    width: "100%",
    background: "#174A5D",
    color: "#FFFFFF",
    border: "none",
    borderRadius: "28px",
    padding: "22px",
    fontSize: "16px",
    fontWeight: 400,
    cursor: "pointer",
    marginBottom: "24px",
    fontFamily: "'Outfit', sans-serif",
  },
};

type Screen3Props = {
  flightNumber?: string;
  onRefund: () => void;
  onRerouting: () => void;
};

export default function Screen3({
  flightNumber = "LH6769",
  onRefund,
  onRerouting,
}: Screen3Props) {
  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <img src={logo} alt="Logo" style={styles.logo} />
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
        <div style={styles.topRow}>
          <h1 style={styles.flightTitle}>
            Your Flight: {flightNumber}
          </h1>

          <div style={styles.cancelledPill}>
            Cancelled
          </div>
        </div>

        <p style={styles.text}>
          Due to extreme fog disruption, we regret to inform you that
          your flight has been cancelled.
        </p>

        <p style={styles.text}>
          As per EU Regulation 261/2004 (EU261) you have the
          following options:
        </p>

        <button
          style={styles.button}
          onClick={onRefund}
        >
          1. Request Refund / Airline Credits
        </button>

        <button
          style={styles.button}
          onClick={onRerouting}
        >
          2. View Available Rerouting Options
        </button>
      </div>
    </div>
  );
}