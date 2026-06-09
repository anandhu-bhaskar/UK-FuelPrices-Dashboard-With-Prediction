import { api, usingCache } from "./api.js";

// ── State ──────────────────────────────────────────────────────────────────
let activeFuel = "E10";
let map, markersLayer;

const FUEL_COLORS = {
  E10: "#2563eb", E5: "#0891b2",
  B7: "#7c3aed", B7_STANDARD: "#7c3aed", B7_PREMIUM: "#9333ea",
  SDV: "#059669", HVO: "#059669", B10: "#0d9488"
};
const FUEL_LABELS = {
  E10: "E10 (Petrol)", E5: "E5 (Super Petrol)",
  B7: "B7 (Diesel)", B7_STANDARD: "B7 (Diesel)", B7_PREMIUM: "B7 Premium (Diesel)",
  SDV: "SDV (Super Diesel)", HVO: "HVO (Super Diesel)", B10: "B10 (Biofuel)"
};
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const charts = {};
function mkChart(id, config) {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id);
  if (!ctx) return;
  charts[id] = new Chart(ctx, config);
}

Chart.defaults.font = { family: "Inter, system-ui, sans-serif", size: 11 };
Chart.defaults.color = "#64748b";
const gridColor = "rgba(226,232,240,1)";

function pct(a, b) {
  if (!a || !b) return null;
  return (((a - b) / b) * 100).toFixed(1);
}

function badgeHtml(val) {
  if (val === null) return '<span class="badge flat">—</span>';
  const n = parseFloat(val);
  const cls = n > 0 ? "up" : n < 0 ? "down" : "flat";
  const arrow = n > 0 ? "▲" : n < 0 ? "▼" : "—";
  return `<span class="badge ${cls}">${arrow} ${Math.abs(n)}%</span>`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day:"numeric", month:"short", year:"numeric" });
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", { day:"numeric", month:"short", year:"numeric", hour:"2-digit", minute:"2-digit" });
}

function el(id) { return document.getElementById(id); }

// ── Cache banner ────────────────────────────────────────────────────────────
function showCacheBanner() {
  if (!usingCache) return;
  const banner = document.createElement("div");
  banner.id = "cache-banner";
  banner.innerHTML = "⚠️ API unavailable — showing cached data. Dashboard may not reflect latest prices.";
  Object.assign(banner.style, {
    background: "#92400e", color: "#fef3c7", padding: "0.5rem 2rem",
    fontSize: "0.8rem", textAlign: "center",
  });
  document.body.insertBefore(banner, document.querySelector("main"));
}

// ── 1 + 2. National Avg Cards + Summary Stats ───────────────────────────────
async function renderSummaryCards() {
  try {
    const [summary, changes] = await Promise.all([api.summary(), api.priceChange()]);
    const changeMap = Object.fromEntries(changes.map(r => [r.fuel_type, r]));
    el("summary-cards").innerHTML = summary.map(r => {
      const ch = changeMap[r.fuel_type] || {};
      const d7 = pct(ch.current_avg, ch.week_ago_avg);
      const color = FUEL_COLORS[r.fuel_type] || "#3b82f6";
      return `
        <div class="card stat-card">
          <div class="fuel-label" style="color:${color}">${FUEL_LABELS[r.fuel_type] || r.fuel_type}</div>
          <div class="price-big" style="color:${color}">${r.avg_price}p</div>
          <div class="price-sub">avg today · ${parseInt(r.station_count).toLocaleString()} stations</div>
          <div style="margin-top:0.5rem">${badgeHtml(d7)} <span style="font-size:0.7rem;color:var(--muted)">vs 7d ago</span></div>
        </div>`;
    }).join("");
    const latest = summary.reduce((a, b) => a.last_updated > b.last_updated ? a : b, summary[0]);
    el("last-updated").textContent = "Data: " + fmtDate(latest.last_updated);
  } catch (e) { el("summary-cards").innerHTML = `<div class="error-msg">${e.message}</div>`; }
}

// ── 3. System Status Card ───────────────────────────────────────────────────
async function renderStatusCard() {
  try {
    const s = await api.status();
    const dot = (val) => val
      ? `<span style="color:var(--green)">●</span>`
      : `<span style="color:var(--muted)">○</span>`;
    el("status-card").innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
        <div>
          <div style="font-size:0.7rem;color:var(--muted);margin-bottom:0.2rem">${dot(s.last_data)} Price Data</div>
          <div style="font-size:0.82rem;font-weight:600">${fmtDate(s.last_data)}</div>
          <div style="font-size:0.7rem;color:var(--muted);margin-top:0.1rem">${parseInt(s.total_readings||0).toLocaleString()} readings · ${parseInt(s.total_stations||0).toLocaleString()} stations</div>
        </div>
        <div>
          <div style="font-size:0.7rem;color:var(--muted);margin-bottom:0.2rem">${dot(s.last_ingest)} Last Ingest</div>
          <div style="font-size:0.82rem;font-weight:600">${fmtDateTime(s.last_ingest)}</div>
        </div>
        <div>
          <div style="font-size:0.7rem;color:var(--muted);margin-bottom:0.2rem">${dot(s.last_forecast)} Forecasts</div>
          <div style="font-size:0.82rem;font-weight:600">${s.last_forecast ? fmtDate(s.last_forecast) : "Not yet trained"}</div>
        </div>
        <div>
          <div style="font-size:0.7rem;color:var(--muted);margin-bottom:0.2rem">${dot(s.last_anomaly_check)} Anomaly Check</div>
          <div style="font-size:0.82rem;font-weight:600">${s.last_anomaly_check ? fmtDate(s.last_anomaly_check) : "Not yet trained"}</div>
        </div>
        <div>
          <div style="font-size:0.7rem;color:var(--muted);margin-bottom:0.2rem">${dot(s.last_predictions)} Predictions</div>
          <div style="font-size:0.82rem;font-weight:600">${s.last_predictions ? fmtDate(s.last_predictions) : "Not yet trained"}</div>
        </div>
        <div>
          <div style="font-size:0.7rem;color:var(--muted);margin-bottom:0.2rem">Data Source</div>
          <div style="font-size:0.82rem;font-weight:600" id="source-indicator">Live ✓</div>
        </div>
      </div>`;
    setTimeout(() => {
      const src = el("source-indicator");
      if (src) {
        if (usingCache) { src.textContent = "Cached ⚠️"; src.style.color = "var(--yellow)"; }
        else { src.style.color = "var(--green)"; }
      }
    }, 1000);
  } catch { el("status-card").innerHTML = '<div class="error-msg">Status unavailable</div>'; }
}

// ── 4. Fuel Type Comparison ─────────────────────────────────────────────────
async function renderFuelComparison() {
  try {
    const data = await api.summary();
    mkChart("chart-fuel-compare", {
      type: "bar",
      data: {
        labels: data.map(r => r.fuel_type),
        datasets: [{ data: data.map(r => r.avg_price), backgroundColor: data.map(r => FUEL_COLORS[r.fuel_type] || "#2563eb"), borderRadius: 4 }]
      },
      options: { indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } }, y: { grid: { display: false } } } }
    });
  } catch {}
}

// ── 5. Price Change Cards ───────────────────────────────────────────────────
async function renderPriceChangeCards() {
  try {
    const data = await api.priceChange();
    el("change-cards").innerHTML = data.map(r => {
      const d7 = pct(r.current_avg, r.week_ago_avg);
      const d30 = pct(r.current_avg, r.month_ago_avg);
      const color = FUEL_COLORS[r.fuel_type] || "#3b82f6";
      return `
        <div class="card">
          <div class="card-title" style="color:${color}">${r.fuel_type} Price Change</div>
          <div style="display:flex;gap:1.5rem;align-items:center">
            <div><div style="font-size:0.7rem;color:var(--muted)">vs 7 days</div><div style="margin-top:0.2rem">${badgeHtml(d7)}</div></div>
            <div><div style="font-size:0.7rem;color:var(--muted)">vs 30 days</div><div style="margin-top:0.2rem">${badgeHtml(d30)}</div></div>
            <div style="margin-left:auto;text-align:right">
              <div style="font-size:0.7rem;color:var(--muted)">Now</div>
              <div style="font-size:1.3rem;font-weight:700;color:${color}">${r.current_avg}p</div>
            </div>
          </div>
        </div>`;
    }).join("");
  } catch (e) { el("change-cards").innerHTML = `<div class="error-msg">${e.message}</div>`; }
}

// ── 6. 30-Day Trend ─────────────────────────────────────────────────────────
async function renderPriceTrend() {
  try {
    const data = await api.priceTrend(30);
    const dates = [...new Set(data.map(r => r.date))].sort();
    const fuels = [...new Set(data.map(r => r.fuel_type))];
    const byFuel = {};
    fuels.forEach(f => {
      const map = Object.fromEntries(data.filter(r => r.fuel_type === f).map(r => [r.date, r.avg_price]));
      byFuel[f] = dates.map(d => map[d] ?? null);
    });
    mkChart("chart-trend", {
      type: "line",
      data: { labels: dates.map(d => new Date(d).toLocaleDateString("en-GB", { day:"numeric", month:"short" })),
        datasets: fuels.map(f => ({ label: FUEL_LABELS[f] || f, data: byFuel[f], borderColor: FUEL_COLORS[f] || "#2563eb",
          backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true })) },
      options: { plugins: { legend: { position: "top" } },
        scales: { x: { grid: { color: gridColor }, ticks: { maxTicksLimit: 8 } },
                  y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } } } }
    });
  } catch {}
}

// ── 7. Day of Week ──────────────────────────────────────────────────────────
async function renderDayOfWeek() {
  try {
    const data = await api.byDow(activeFuel);
    const min = Math.min(...data.map(x => x.avg_price));
    mkChart("chart-dow", {
      type: "bar",
      data: { labels: data.map(r => DOW[r.day_of_week]),
        datasets: [{ data: data.map(r => r.avg_price),
          backgroundColor: data.map(r => r.avg_price === min ? FUEL_COLORS[activeFuel] || "#2563eb" : "#e2e8f0"),
          borderRadius: 5 }] },
      options: { plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } },
                  y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" }, suggestedMin: min - 2 } } }
    });
  } catch {}
}

// ── 8. Monthly Seasonality ──────────────────────────────────────────────────
async function renderMonthly() {
  try {
    const data = await api.byMonth(activeFuel);
    const color = FUEL_COLORS[activeFuel] || "#2563eb";
    mkChart("chart-monthly", {
      type: "line",
      data: { labels: data.map(r => MONTHS[r.month - 1]),
        datasets: [{ label: activeFuel, data: data.map(r => r.avg_price),
          borderColor: color, backgroundColor: color + "22", fill: true, borderWidth: 2, pointRadius: 4, tension: 0.3 }] },
      options: { plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } } } }
    });
  } catch {}
}

// ── 9. Price Distribution ───────────────────────────────────────────────────
async function renderDistribution() {
  try {
    const data = await api.distribution(activeFuel);
    const color = FUEL_COLORS[activeFuel] || "#2563eb";
    mkChart("chart-dist", {
      type: "bar",
      data: { labels: data.map(r => r.bucket + "p"),
        datasets: [{ data: data.map(r => r.count), backgroundColor: color + "99",
          borderColor: color, borderWidth: 1, borderRadius: 2 }] },
      options: { plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
                  y: { grid: { color: gridColor }, title: { display: true, text: "Stations" } } } }
    });
  } catch {}
}

// ── 10. Map ─────────────────────────────────────────────────────────────────
async function renderMap() {
  if (!map) {
    map = L.map("map").setView([54.5, -2.5], 6);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      { attribution: "© OpenStreetMap © CARTO", maxZoom: 18 }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
  }
  try {
    const prices = await api.prices(activeFuel, 500);
    markersLayer.clearLayers();
    // Filter to UK bounding box only (excludes bad coordinates from DB)
    const uk = prices.filter(p =>
      p.latitude && p.longitude &&
      p.latitude >= 49.5 && p.latitude <= 60.8 &&
      p.longitude >= -8.0 && p.longitude <= 2.0
    );
    if (!uk.length) return;
    const vals = uk.map(p => parseFloat(p.price_pence));
    const min = Math.min(...vals), max = Math.max(...vals);
    uk.forEach(p => {
      const t = (parseFloat(p.price_pence) - min) / (max - min || 1);
      const r = Math.round(t * 220), g = Math.round((1 - t) * 160);
      const color = `rgb(${r},${g},50)`;
      L.circleMarker([p.latitude, p.longitude], { radius: 5, fillColor: color, color: "#ffffff", weight: 1, fillOpacity: 0.85 })
        .bindPopup(`<b>${p.brand_name}</b><br>${p.city}, ${p.county}<br><b style="color:${color}">${p.price_pence}p</b> ${p.fuel_type}<br><small>${fmtDate(p.recorded_at)}</small>`)
        .addTo(markersLayer);
    });
  } catch {}
}

// ── 11. Cheapest Counties ───────────────────────────────────────────────────
async function renderCheapestCounties() {
  try {
    const data = await api.byCounty(activeFuel);
    const top = data.slice(0, 10);
    const maxP = Math.max(...top.map(r => r.avg_price));
    el("table-cheapest-counties").innerHTML = `<table>
      <thead><tr><th class="rank">#</th><th>County</th><th>Avg</th><th>Stations</th></tr></thead>
      <tbody>${top.map((r, i) => `<tr>
        <td class="rank">${i+1}</td><td>${r.county}</td>
        <td><div class="price-bar-wrap"><span>${r.avg_price}p</span><div class="price-bar" style="width:${(r.avg_price/maxP*70).toFixed(0)}px"></div></div></td>
        <td style="color:var(--muted)">${r.station_count}</td>
      </tr>`).join("")}</tbody></table>`;
  } catch {}
}

// ── 12. Station Count by County ─────────────────────────────────────────────
async function renderStationByCounty() {
  try {
    const data = (await api.stationByCounty()).slice(0, 15);
    mkChart("chart-station-county", {
      type: "bar",
      data: { labels: data.map(r => r.county),
        datasets: [{ data: data.map(r => r.station_count), backgroundColor: "#0891b233", borderColor: "#0891b2", borderWidth: 1.5, borderRadius: 4 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { grid: { color: gridColor } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } } }
    });
  } catch {}
}

// ── 13. Most Expensive Counties ─────────────────────────────────────────────
async function renderCountyPriceRanking() {
  try {
    const data = [...await api.byCounty(activeFuel)].sort((a,b) => b.avg_price - a.avg_price).slice(0,10);
    el("table-expensive-counties").innerHTML = `<table>
      <thead><tr><th class="rank">#</th><th>County</th><th>Avg</th></tr></thead>
      <tbody>${data.map((r,i) => `<tr><td class="rank">${i+1}</td><td>${r.county}</td>
        <td style="color:var(--red);font-weight:600">${r.avg_price}p</td></tr>`).join("")}
      </tbody></table>`;
  } catch {}
}

// ── 14. Brand Price ─────────────────────────────────────────────────────────
async function renderBrandPrice() {
  try {
    const data = (await api.byBrand(activeFuel)).slice(0, 15);
    mkChart("chart-brand-price", {
      type: "bar",
      data: { labels: data.map(r => r.brand_name),
        datasets: [{ data: data.map(r => r.avg_price), backgroundColor: "#2563eb99", borderColor: "#2563eb", borderWidth: 1, borderRadius: 4 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { grid: { color: gridColor }, ticks: { callback: v => v+"p" } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } } }
    });
  } catch {}
}

// ── 15. Brand Market Share ──────────────────────────────────────────────────
async function renderBrandShare() {
  try {
    const all = (await api.byBrand(activeFuel)).sort((a,b) => b.station_count - a.station_count);
    const top = all.slice(0, 10);
    const others = all.slice(10).reduce((s,r) => s + r.station_count, 0);
    const labels = top.map(r => r.brand_name);
    const vals = top.map(r => r.station_count);
    if (others > 0) { labels.push("Others"); vals.push(others); }
    mkChart("chart-brand-share", {
      type: "doughnut",
      data: { labels, datasets: [{ data: vals, backgroundColor: ["#2563eb","#0891b2","#7c3aed","#059669","#d97706","#dc2626","#0d9488","#6366f1","#0369a1","#9333ea","#64748b"], borderColor: "#ffffff", borderWidth: 2 }] },
      options: { plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } }, cutout: "65%" }
    });
  } catch {}
}

// ── 16. Motorway vs Regular ─────────────────────────────────────────────────
async function renderMotorwayCompare() {
  try {
    const data = await api.motorwayCompare();
    const fuels = [...new Set(data.map(r => r.fuel_type))];
    mkChart("chart-motorway", {
      type: "bar",
      data: { labels: fuels, datasets: [
        { label: "Motorway", data: fuels.map(f => data.find(r => r.fuel_type===f && r.is_motorway===1)?.avg_price??0), backgroundColor: "#dc262633", borderColor: "#dc2626", borderWidth: 1.5, borderRadius: 4 },
        { label: "Regular",  data: fuels.map(f => data.find(r => r.fuel_type===f && r.is_motorway===0)?.avg_price??0), backgroundColor: "#2563eb33", borderColor: "#2563eb", borderWidth: 1.5, borderRadius: 4 }
      ]},
      options: { plugins: { legend: { position: "top" } },
        scales: { x: { grid: { display: false } }, y: { grid: { color: gridColor }, ticks: { callback: v => v+"p" } } } }
    });
  } catch {}
}

// ── 17. Supermarket vs Regular ──────────────────────────────────────────────
async function renderSupermarketCompare() {
  try {
    const data = await api.supermarketCompare();
    const fuels = [...new Set(data.map(r => r.fuel_type))];
    mkChart("chart-supermarket", {
      type: "bar",
      data: { labels: fuels, datasets: [
        { label: "Supermarket", data: fuels.map(f => data.find(r => r.fuel_type===f && r.is_supermarket===1)?.avg_price??0), backgroundColor: "#05996933", borderColor: "#059669", borderWidth: 1.5, borderRadius: 4 },
        { label: "Regular",    data: fuels.map(f => data.find(r => r.fuel_type===f && r.is_supermarket===0)?.avg_price??0), backgroundColor: "#2563eb33", borderColor: "#2563eb", borderWidth: 1.5, borderRadius: 4 }
      ]},
      options: { plugins: { legend: { position: "top" } },
        scales: { x: { grid: { display: false } }, y: { grid: { color: gridColor }, ticks: { callback: v => v+"p" } } } }
    });
  } catch {}
}

// ── 18. SNARIMAX Forecast ───────────────────────────────────────────────────
async function renderForecast() {
  try {
    const data = await api.forecast(activeFuel);
    const color = FUEL_COLORS[activeFuel] || "#2563eb";
    if (!data.length) throw new Error("no data");
    mkChart("chart-forecast", {
      type: "line",
      data: { labels: data.map(r => new Date(r.date).toLocaleDateString("en-GB", { weekday:"short", day:"numeric", month:"short" })),
        datasets: [{ label: activeFuel+" forecast", data: data.map(r => r.predicted_pence),
          borderColor: color, backgroundColor: color+"22", fill: true, borderWidth: 2.5, pointRadius: 5, tension: 0.3 }] },
      options: { plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { grid: { color: gridColor }, ticks: { callback: v => v+"p" } } } }
    });
    el("forecast-placeholder").style.display = "none";
  } catch {
    el("forecast-placeholder").textContent = "Forecast unavailable for this fuel type";
    el("forecast-placeholder").style.display = "block";
    el("chart-forecast").style.display = "none";
  }
}

// ── 19. Anomaly Alerts ──────────────────────────────────────────────────────
async function renderAnomalies() {
  try {
    const data = await api.anomalies(activeFuel);
    el("anomaly-list").innerHTML = !data.length
      ? '<div class="loading" style="color:var(--green)">✓ No anomalies detected</div>'
      : data.slice(0,8).map(r => `
          <div class="anomaly-item">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div><div class="a-station">${r.brand_name} — ${r.city}</div><div class="a-meta">${r.county} · ${FUEL_LABELS[r.fuel_type]||r.fuel_type}</div></div>
              <div style="text-align:right">
                <div class="a-price">${parseFloat(r.price_pence).toFixed(1)}p</div>
                <div class="a-meta">range: ${r.lower_threshold?.toFixed(1)}–${r.upper_threshold?.toFixed(1)}p</div>
              </div>
            </div>
          </div>`).join("");
  } catch {
    el("anomaly-list").innerHTML = '<div class="loading">Anomaly detection available after first training run</div>';
  }
}

// ── 20a. Predicted Cheapest Stations (XGBoost, pre-computed) ────────────────
async function renderPredictedCheapest() {
  try {
    const data = await api.predictedCheapest(activeFuel);
    el("predicted-cheapest").innerHTML = `<table>
      <thead><tr><th class="rank">#</th><th>Brand</th><th>City</th><th>County</th><th>Predicted</th></tr></thead>
      <tbody>${data.map((r,i) => `<tr>
        <td class="rank">${i+1}</td>
        <td style="font-weight:500">${r.brand_name}</td>
        <td>${r.city}</td>
        <td style="color:var(--muted)">${r.county}</td>
        <td style="color:var(--green);font-weight:700">${r.predicted_pence}p</td>
      </tr>`).join("")}
      </tbody></table>`;
  } catch {
    el("predicted-cheapest").innerHTML = '<div class="loading">Predictions available after first training run (1st or 15th)</div>';
  }
}

// ── 20b. Recent Price Feed ──────────────────────────────────────────────────
async function renderFeed() {
  try {
    const data = await api.prices(activeFuel, 20);
    el("price-feed").innerHTML = data.map(r => `
      <div class="feed-item">
        <div><div class="feed-station">${r.brand_name}</div><div class="feed-meta">${r.city}, ${r.county}</div></div>
        <div style="text-align:right">
          <div class="feed-price">${parseFloat(r.price_pence).toFixed(1)}p</div>
          <div class="feed-meta">${fmtDate(r.recorded_at)}</div>
        </div>
      </div>`).join("");
  } catch {}
}

// ── Refresh on fuel change ──────────────────────────────────────────────────
function refreshFuelDependents() {
  renderDayOfWeek(); renderMonthly(); renderDistribution();
  renderMap(); renderCheapestCounties(); renderCountyPriceRanking();
  renderBrandPrice(); renderBrandShare();
  renderForecast(); renderAnomalies();
  renderPredictedCheapest(); renderFeed();
}

// ── Init ────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".fuel-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".fuel-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFuel = btn.dataset.fuel;
      refreshFuelDependents();
    });
  });

  await Promise.all([
    renderSummaryCards(),
    renderStatusCard(),
    renderFuelComparison(),
    renderPriceChangeCards(),
    renderPriceTrend(),
    renderMotorwayCompare(),
    renderSupermarketCompare(),
    renderStationByCounty(),
  ]);

  refreshFuelDependents();
  setTimeout(showCacheBanner, 2000);
});
