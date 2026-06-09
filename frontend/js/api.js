const API = "https://ukfuel-ml.azurewebsites.net";
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes

// Dashboard tabs use short codes; DB/API uses actual fuel type names for some endpoints
const DB_FUEL_MAP = { B7: "B7_STANDARD", SDV: "HVO" };

export let usingCache = false;

async function get(path) {
  const key = "ukfuel:" + path;
  try {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error(`${res.status}`);
    const data = await res.json();
    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch {}
    return data;
  } catch (err) {
    // Fallback to localStorage cache
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const { ts, data } = JSON.parse(raw);
        if (Date.now() - ts < CACHE_TTL_MS * 48) { // keep cache 24 hours
          usingCache = true;
          return data;
        }
      }
    } catch {}
    throw err;
  }
}

export const api = {
  status:             ()             => get("/stats/status"),
  summary:            ()             => get("/stats/summary"),
  priceChange:        ()             => get("/stats/price-change"),
  priceTrend:         (days=30)      => get(`/stats/price-trend?days=${days}`),
  byCounty:           (ft="E10")     => get(`/stats/by-county?fuel_type=${DB_FUEL_MAP[ft]||ft}`),
  byBrand:            (ft="E10")     => get(`/stats/by-brand?fuel_type=${DB_FUEL_MAP[ft]||ft}`),
  byDow:              (ft="E10")     => get(`/stats/by-day-of-week?fuel_type=${DB_FUEL_MAP[ft]||ft}`),
  byMonth:            (ft="E10")     => get(`/stats/by-month?fuel_type=${DB_FUEL_MAP[ft]||ft}`),
  cheapestStations:   (ft="E10")     => get(`/stats/cheapest-stations?fuel_type=${DB_FUEL_MAP[ft]||ft}&limit=10`),
  motorwayCompare:    ()             => get("/stats/motorway-compare"),
  supermarketCompare: ()             => get("/stats/supermarket-compare"),
  distribution:       (ft="E10")     => get(`/stats/distribution?fuel_type=${DB_FUEL_MAP[ft]||ft}`),
  stationByCounty:    ()             => get("/stats/station-count-by-county"),
  forecast:           (ft="E10")     => get(`/forecast/${DB_FUEL_MAP[ft] || ft}`),
  anomalies:          (ft="")        => { const dbft = DB_FUEL_MAP[ft] || ft; return get(`/anomalies${dbft ? "?fuel_type="+dbft : ""}`); },
  predict:            (node,ft)      => get(`/predict?node_id=${encodeURIComponent(node)}&fuel_type=${ft}`),
  predictedCheapest:  (ft="E10")     => get(`/stats/predicted-cheapest?fuel_type=${ft}&limit=10`),
  stations:           ()             => get("/stations"),
  prices:             (ft="",lim=20) => get(`/prices?limit=${lim}${ft?"&fuel_type="+(DB_FUEL_MAP[ft]||ft):""}`),
};
