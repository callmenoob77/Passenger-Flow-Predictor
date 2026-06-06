// Screen2.tsx
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
    gap: "24px",
  },
  flightTitle: {
    margin: 0,
    fontSize: "26px",
    fontWeight: 500,
    color: "#0A0F1E",
    fontFamily: "'Outfit', sans-serif",
  },
  imageWrapper: {
    position: "relative",
    width: "100%",
  },
  routeImage: {
    width: "100%",
    height: "auto",
    display: "block",
  },
  originOverlay: {
    position: "absolute",
    left: "2px",
    bottom: "13px",
    background: "#EDF2F4",
    padding: "4px 8px",
    fontSize: "22px",
    fontWeight: "bold",
    color: "#174A5D",
    textAlign: "center",
    minWidth: "65px",
    borderRadius: "4px",
  },
  destOverlay: {
    position: "absolute",
    right: "2px",
    bottom: "13px",
    background: "#EDF2F4",
    padding: "4px 8px",
    fontSize: "22px",
    fontWeight: "bold",
    color: "#174A5D",
    textAlign: "center",
    minWidth: "65px",
    borderRadius: "4px",
  },
  infoCard: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: "20px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.05)",
  },
  infoRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottom: "1px solid #EDF2F4",
    paddingBottom: "8px",
  },
  infoLabel: {
    fontSize: "14px",
    color: "#718096",
  },
  infoValue: {
    fontSize: "15px",
    fontWeight: 600,
    color: "#0A0F1E",
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
  originCity?: string;
  originIcao?: string;
  destCity?: string;
  destIcao?: string;
  scheduledDeparture?: string;
  status?: string;
  onActivate: () => void;
  onAlternatives: () => void;
};

const formatDeparture = (isoStr?: string) => {
  if (!isoStr) return "N/A";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch (e) {
    return isoStr;
  }
};

export default function Screen2({
  flightNumber = "LH6769",
  originCity = "Iasi",
  originIcao = "LRIA",
  destCity = "Milano",
  destIcao = "MXP",
  scheduledDeparture,
  status = "ON_TIME",
  onActivate,
  onAlternatives,
}: Screen2Props) {
  const isFogRisk = status === "FOG_RISK";

  // Use the 3-letter IATA code if ICAO is LRIA (since image displays IAS)
  const displayOrigin = originIcao === "LRIA" ? "IAS" : originIcao;
  const displayDest = destIcao === "MXP" ? "MXP" : destIcao; // MXP is already 3-letter

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

        {/* Original Route Illustration with Dynamic Overlays */}
        <div style={styles.imageWrapper}>
          <img
            src={imageRoute}
            alt={`Flight route ${displayOrigin} to ${displayDest}`}
            style={styles.routeImage}
          />
          {/* Dynamic Origin Overlay */}
          <div style={styles.originOverlay}>
            {displayOrigin}
          </div>
          {/* Dynamic Destination Overlay */}
          <div style={styles.destOverlay}>
            {displayDest}
          </div>
        </div>

        {/* Info Card */}
        <div style={styles.infoCard}>
          <div style={styles.infoRow}>
            <span style={styles.infoLabel}>Destination Place</span>
            <span style={styles.infoValue}>{destCity} ({destIcao})</span>
          </div>
          <div style={{ ...styles.infoRow, borderBottom: "none", paddingBottom: 0 }}>
            <span style={styles.infoLabel}>Scheduled Departure</span>
            <span style={styles.infoValue}>{formatDeparture(scheduledDeparture)}</span>
          </div>
        </div>

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
              <div style={styles.adTitle}>Need a backup travel plan?</div>
              <div style={styles.adText}>
                Book airport transfers, hotel accommodation, or alternative
                transportation options with exclusive disruption assistance rates.
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
              We will notify you automatically if weather conditions increase the
              risk of delays or cancellations.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
