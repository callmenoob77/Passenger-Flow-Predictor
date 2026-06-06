// Screen2.tsx
// Props:
//   flightNumber  — string, e.g.: "LH6769"
//   status        — "ON_TIME" | "FOG_RISK"  (from backend)
//   onActivate    — callback for "Activate Email Alerts"
//   onAlternatives — callback for "Check Alternatives To Your Flight"
import React from "react";
import logo from "../assets/Logo.png";
import imageRoute from "../assets/imagineBCN.png";
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
  padding: "0px",
},
  content: {
    flex: 1,
    padding: "40px 24px 32px",
    display: "flex",
    flexDirection: "column",
    gap: "32px",
  },
  flightTitle: {
    margin: 0,
    fontSize: "26px",
    fontWeight: 500,
    color: "#0A0F1E",
    fontFamily: "'Outfit', sans-serif",
  },
  routeImage: {
    width: "100%",
    // Replace with your Figma export
    // e.g.: import routeImg from './assets/route-ias-bcn.png'
    // and set: src={routeImg}
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  statusLabel: {
    fontSize: "22px",
    fontWeight: 500,
    color: "#0A0F1E",
    fontFamily: "'Outfit', sans-serif",
    margin: 0,
  },
  pill: {
    borderRadius: "999px",
    padding: "8px 20px",
    fontSize: "15px",
    fontWeight: 500,
    fontFamily: "'Outfit', sans-serif",
    background: "#CAD5E8",
  },
  pillOnTime: {
    color: "#6DD400",
  },
  pillFogRisk: {
    color: "#F5A623",
  },
  button: {
    width: "100%",
    padding: "18px",
    background: "transparent",
    borderRadius: "999px",
    fontSize: "16px",
    fontWeight: 600,
    fontFamily: "'Outfit', sans-serif",
    cursor: "pointer",
    color: "#6DD400",
    border: "2px solid #6DD400",
  },
  adBanner: {
  marginTop: "auto",
  background: "#174A5D",
  borderRadius: "16px",
  padding: "18px",
  color: "#FFFFFF",
},

adLabel: {
  fontSize: "12px",
  opacity: 0.8,
  marginBottom: "8px",
},

adTitle: {
  fontSize: "18px",
  fontWeight: 600,
  marginBottom: "6px",
},

adText: {
  fontSize: "14px",
  lineHeight: "1.5",
},
};

type Screen2Props = {
  flightNumber?: string;
  status?: string;
  onActivate: () => void;
  onAlternatives: () => void;
};

export default function Screen2({
  flightNumber = "LH6769",
  status = "ON_TIME",
  onActivate,
  onAlternatives,
}: Screen2Props)  {
  const isFogRisk = status === "FOG_RISK";

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
  <img
    src={logo}
    alt="Logo"
    style={{
      width: "100px",
      height: "auto",
    }}
  />
</div>

      {/* Content */}
      <div style={styles.content}>
        <p style={styles.flightTitle}>Your Flight: {flightNumber}</p>

      
        <img
          src={imageRoute}
          alt="Flight route IAS to BCN"
          style={styles.routeImage}
        />

        {/* Status pill */}
        <div style={styles.statusRow}>
          <p style={styles.statusLabel}>Status:</p>
          <span
            style={{
              ...styles.pill,
              ...(isFogRisk ? styles.pillFogRisk : styles.pillOnTime),
            }}
          >
            {isFogRisk ? "FOG RISK" : "ON TIME"}
          </span>
        </div>

        {/* Button — changes depending on status */}
       {isFogRisk && (
  <>
    <button style={styles.button} onClick={onAlternatives}>
      Check Alternatives To Your Flight
    </button>

    <div style={styles.adBanner}>
      <div style={styles.adLabel}>Partner Recommendation</div>

      <div style={styles.adTitle}>
        Need a backup travel plan?
      </div>

      <div style={styles.adText}>
        Book airport transfers, hotel accommodation,
        or alternative transportation options with
        exclusive disruption assistance rates.
      </div>
    </div>
  </>
)}

        {!isFogRisk && (
  <div
    style={{
      background: "#CAD5E8",
      borderRadius: "16px",
      padding: "16px",
    }}
  >
    <strong>Monitoring Active</strong>
    <p style={{ marginTop: "8px" }}>
      We will notify you automatically if weather conditions
      increase the risk of delays or cancellations.
    </p>
  </div>
)}
      </div>
    </div>
  );
}
