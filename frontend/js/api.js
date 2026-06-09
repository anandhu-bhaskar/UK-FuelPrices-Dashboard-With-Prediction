const API = "https://ukfuel-ml.azurewebsites.net";

async function get(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const api = {
  summary:            ()             => get("/stats/summary"),
  priceChange:        ()             => get("/stats/price-change"),
  priceTrend:         (days=30)      => get(`/stats/price-trend?days=${days}`),
  byCounty:           (ft="E10")     => get(`/stats/by-county?fuel_type=${ft}`),
  byBrand:            (ft="E10")     => get(`/stats/by-brand?fuel_type=${ft}`),
  byDow:              (ft="E10")     => get(`/stats/by-day-of-week?fuel_type=${ft}`),
  byMonth:            (ft="E10")     => get(`/stats/by-month?fuel_type=${ft}`),
  cheapestStations:   (ft="E10")     => get(`/stats/cheapest-stations?fuel_type=${ft}&limit=10`),
  motorwayCompare:    ()             => get("/stats/motorway-compare"),
  supermarketCompare: ()             => get("/stats/supermarket-compare"),
  distribution:       (ft="E10")     => get(`/stats/distribution?fuel_type=${ft}`),
  stationByCounty:    ()             => get("/stats/station-count-by-county"),
  fuelTypes:          ()             => get("/stats/fuel-types"),
  forecast:           (ft="E10")     => get(`/forecast/${ft}`),
  anomalies:          (ft="")        => get(`/anomalies${ft ? "?fuel_type="+ft : ""}`),
  predict:            (node,ft)      => get(`/predict?node_id=${encodeURIComponent(node)}&fuel_type=${ft}`),
  stations:           ()             => get("/stations"),
  prices:             (ft="",lim=20) => get(`/prices?limit=${lim}${ft?"&fuel_type="+ft:""}`),
};
