import { useState } from "react";
import Home from "./screens/home";
import Screen2 from "./screens/screen2";
import CancelledScreen from "./screens/screen3";
import AlternativesScreen from "./screens/screen4";
import RefundScreen from "./screens/screen5";

// In dev: empty string → Vite proxy rewrites /api/* to backend.
// In prod: set VITE_API_BASE=https://your-backend.onrender.com (no trailing slash).
const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const api = (path: string) =>
  API_BASE ? `${API_BASE}${path}` : `/api${path}`;

function App() {
  const [screen, setScreen] = useState(1);
  const [flightData, setFlightData] = useState<any>(null);
  const [rerouteData, setRerouteData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchAlternatives = async (flight: any) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(api("/reroute"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(flight),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setRerouteData(data);
      setScreen(4);
    } catch (e: any) {
      setError("Error fetching alternatives: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {screen === 1 && (
        <Home
          onSubmit={async (data: any) => {
            setError("");
            setLoading(true);
            try {
              const code = data.flightNumber.trim().toUpperCase().replace(/\s+/, "-");
              
              // 1. Register passenger notification subscription
              const subRes = await fetch(api("/subscribe"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  email: data.email,
                  flight_number: data.flightNumber,
                }),
              });
              if (!subRes.ok) {
                const errText = await subRes.text();
                let errMsg = "Failed to register notifications.";
                try {
                  const errJson = JSON.parse(errText);
                  errMsg = errJson.detail || errMsg;
                } catch {
                  errMsg = errText || errMsg;
                }
                throw new Error(errMsg);
              }

              // 2. Fetch flight status
              const res = await fetch(api(`/flight/${encodeURIComponent(code)}`));
              if (!res.ok) throw new Error("Flight not found in the demo database.");
              const route = await res.json();
              setFlightData({ ...data, ...route });
              setScreen(2);
            } catch (e: any) {
              setError(e.message);
            } finally {
              setLoading(false);
            }
          }}
        />
      )}

      {loading && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.3)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999 }}>
          <div style={{ background: "#fff", borderRadius: 16, padding: "24px 40px", fontFamily: "'Outfit', sans-serif", fontSize: 18 }}>Loading...</div>
        </div>
      )}

      {error && (
        <div style={{ position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", background: "#F04E23", color: "#fff", padding: "12px 24px", borderRadius: 999, fontFamily: "'Outfit', sans-serif", fontSize: 14, zIndex: 999 }}>
          {error}
        </div>
      )}

      {screen === 2 && flightData && (
        <Screen2
          flightNumber={flightData.flightNumber}
          originCity={flightData.origin_city}
          originIcao={flightData.origin_icao}
          destCity={flightData.dest_city}
          destIcao={flightData.dest_icao}
          scheduledDeparture={flightData.scheduled_departure}
          status={flightData.status || "ON_TIME"}
          onActivate={() => console.log("Alerts activated")}
          onAlternatives={() => setScreen(3)}
        />
      )}

      {screen === 3 && flightData && (
        <CancelledScreen
          flightNumber={flightData.flightNumber}
          onRefund={() => setScreen(5)}
          onRerouting={() => fetchAlternatives(flightData)}
        />
      )}

      {screen === 4 && rerouteData && (
        <AlternativesScreen
          flightNumber={flightData?.flightNumber}
          data={rerouteData}
          onBack={() => setScreen(3)}
        />
      )}

      {screen === 5 && flightData && (
        <RefundScreen
          flightNumber={flightData.flightNumber}
          email={flightData.email}
          onBack={() => setScreen(3)}
          onHome={() => setScreen(1)}
        />
      )}
    </>
  );
}

export default App;
