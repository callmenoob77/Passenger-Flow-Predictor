// screen4.tsx — Alternatives Screen
import React from "react";
import logo from "../assets/Logo.png";

interface Option {
  mode: "flight" | "bus" | "train" | "carpool";
  provider: string;
  depart?: string;
  arrive?: string;
  duration_h?: number;
  price_eur?: number;
  transfers: number;
  deep_link?: string;
  score: number;
}

interface CancelledFlight {
  origin?: string;
  dest?: string;
  scheduled_departure?: string;
}

interface RerouteData {
  cancelled_flight: CancelledFlight;
  options: Option[];
}

interface Screen4Props {
  flightNumber?: string;
  data?: RerouteData;
  onBack?: () => void;
}

const EXAMPLE_DATA: RerouteData = {
  cancelled_flight: {
    origin: "Iasi",
    dest: "Milan",
    scheduled_departure: "2026-06-10T07:00:00",
  },
  options: [
    { mode: "flight", provider: "Wizz Air (from Suceava)", depart: "2026-06-10T10:25:00", arrive: "2026-06-10T12:55:00", duration_h: 2.5, price_eur: 146, transfers: 1, deep_link: "https://www.google.com/travel/flights", score: 14.7 },
    { mode: "flight", provider: "Wizz Air (from Suceava)", depart: "2026-06-10T13:25:00", arrive: "2026-06-10T15:43:00", duration_h: 2.3, price_eur: 121, transfers: 1, deep_link: "https://www.google.com/travel/flights", score: 16.3 },
    { mode: "flight", provider: "Wizz Air",                depart: "2026-06-10T19:00:00", arrive: "2026-06-10T21:30:00", duration_h: 2.5, price_eur: 55,  transfers: 0, deep_link: "https://www.google.com/travel/flights", score: 17.2 },
    { mode: "flight", provider: "Wizz Air (from Chisinau)", depart: "2026-06-10T09:35:00", arrive: "2026-06-10T12:23:00", duration_h: 2.8, price_eur: 208, transfers: 1, deep_link: "https://www.google.com/travel/flights", score: 17.3 },
    { mode: "flight", provider: "Ryanair (from Bucharest)", depart: "2026-06-10T19:20:00", arrive: "2026-06-10T21:50:00", duration_h: 2.5, price_eur: 26,  transfers: 1, deep_link: "https://www.google.com/travel/flights", score: 17.6 },
  ],
};

const fmtTime = (iso?: string) =>
  iso ? new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "—";

const fmtDur = (h?: number) => {
  if (h == null) return "";
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return mm ? `${hh}h ${mm}m` : `${hh}h`;
};

const fmtPrice = (usd?: number) => (usd == null ? "—" : `~€${Math.round(usd * 0.92)}`);

interface ModeConfig {
  label: string;
  accent: string;
}

const MODE: Record<string, ModeConfig> = {
  flight: { label: "FLIGHT",  accent: "#174A5D" },
  bus:    { label: "BUS",     accent: "#F5A623" },
  train:  { label: "TRAIN",   accent: "#6DD400" },
  carpool:{ label: "CARPOOL", accent: "#174A5D" },
};

const styles: Record<string, React.CSSProperties> = {
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
    fontFamily: "'Outfit', sans-serif",
  },
  routeLine: {
    margin: "4px 0 0",
    fontSize: "16px",
    fontWeight: 400,
    color: "#5A6472",
    fontFamily: "'Outfit', sans-serif",
  },
  fogNote: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    background: "#CAD5E8",
    borderRadius: "16px",
    padding: "12px 16px",
    fontSize: "14px",
    color: "#174A5D",
    fontWeight: 500,
  },
  list: { display: "flex", flexDirection: "column", gap: "14px" },
  card: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: "16px 18px",
    boxShadow: "0 2px 10px rgba(10,15,30,0.06)",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  badge: {
    borderRadius: "999px",
    padding: "4px 12px",
    fontSize: "12px",
    fontWeight: 600,
    letterSpacing: "0.4px",
    background: "#CAD5E8",
  },
  price: { fontSize: "20px", fontWeight: 700, color: "#0A0F1E" },
  provider: { fontSize: "16px", fontWeight: 500, color: "#0A0F1E" },
  timeRow: { display: "flex", alignItems: "center", gap: "10px", fontSize: "20px", fontWeight: 600, color: "#0A0F1E" },
  arrow: { color: "#9AA4B2", fontSize: "18px" },
  meta: { fontSize: "13px", color: "#5A6472", fontWeight: 400 },
  bookBtn: {
    marginTop: "4px",
    width: "100%",
    padding: "12px",
    background: "transparent",
    borderRadius: "999px",
    fontSize: "15px",
    fontWeight: 600,
    fontFamily: "'Outfit', sans-serif",
    cursor: "pointer",
    color: "#6DD400",
    border: "2px solid #6DD400",
  },
  empty: { fontSize: "15px", color: "#5A6472", textAlign: "center", marginTop: "40px" },
};

function OptionCard({ opt }: { opt: Option }) {
  const m = MODE[opt.mode] || MODE.flight;
  const transferLabel =
    opt.transfers === 0
      ? "Direct, from your city"
      : `${opt.transfers} transfer${opt.transfers > 1 ? "s" : ""} · ground travel needed`;
  return (
    <div style={styles.card}>
      <div style={styles.cardTop}>
        <span style={{ ...styles.badge, color: m.accent }}>{m.label}</span>
        <span style={styles.price}>{fmtPrice(opt.price_eur)}</span>
      </div>

      <div style={styles.provider}>{opt.provider}</div>

      <div style={styles.timeRow}>
        <span>{fmtTime(opt.depart)}</span>
        <span style={styles.arrow}>→</span>
        <span>{fmtTime(opt.arrive)}</span>
        <span style={{ ...styles.meta, marginLeft: "6px" }}>· {fmtDur(opt.duration_h)}</span>
      </div>

      <div style={styles.meta}>{transferLabel}</div>

      <a href={opt.deep_link || "#"} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
        <button style={styles.bookBtn}>Book →</button>
      </a>
    </div>
  );
}

export default function Screen4({
  flightNumber = "LH6769",
  data = EXAMPLE_DATA,
  onBack,
}: Screen4Props) {
  const cf = data?.cancelled_flight || {};
  const options = data?.options || [];

  return (
    <div style={styles.page}>
      {/* Header — same as all other screens */}
      <div style={styles.header}>
        <img src={logo} alt="Logo" style={{ width: "100px", height: "auto" }} />
      </div>

      {/* Content */}
      <div style={styles.content}>
        {onBack && (
          <button style={styles.back} onClick={onBack}>
            ← Back
          </button>
        )}

        <div>
          <h1 style={styles.title}>Alternatives for your flight</h1>
          <p style={styles.routeLine}>
            {flightNumber} · {cf.origin} → {cf.dest}
          </p>
        </div>

        <div style={styles.fogNote}>
          ⚠️ Your flight is at risk of fog. Here are the best alternatives to get you there on time.
        </div>

        <div style={styles.list}>
          {options.length === 0 ? (
            <p style={styles.empty}>No alternatives found right now.</p>
          ) : (
            options.map((opt, i) => <OptionCard key={i} opt={opt} />)
          )}
        </div>
      </div>
    </div>
  );
}
