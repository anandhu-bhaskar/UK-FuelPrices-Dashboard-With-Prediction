import { api } from "./api.js";

// ── State ──────────────────────────────────────────────────────────────────
let activeFuel = "E10";
let map, markersLayer;

const FUEL_COLORS = { E5: "#3b82f6", E10: "#22c55e", B7: "#f97316", SDV: "#a855f7" };
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ── Chart registry (destroy before redraw) ─────────────────────────────────
const charts = {};
function mkChart(id, config) {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id);
  if (!ctx) return;
  charts[id] = new Chart(ctx, config);
  return charts[id];
}

const defaultFont = { family: "Inter, system-ui, sans-serif", size: 11 };
Chart.defaults.font = defaultFont;
Chart.defaults.color = "#94a3b8";
const gridColor = "rgba(51,65,85,0.6)";

// ── Helpers ────────────────────────────────────────────────────────────────
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

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function el(id) { return document.getElementById(id); }

// ── 1. National Average Cards ──────────────────────────────────────────────
async function renderSummaryCards() {
  try {
    const [summary, changes] = await Promise.all([api.summary(), api.priceChange()]);
    const changeMap = Object.fromEntries(changes.map(r => [r.fuel_type, r]));
    const cont = el("summary-cards");
    cont.innerHTML = summary.map(r => {
      const ch = changeMap[r.fuel_type] || {};
      const d7 = pct(ch.current_avg, ch.week_ago_avg);
      const color = FUEL_COLORS[r.fuel_type] || "#3b82f6";
      return `
        <div class="card stat-card">
          <div class="fuel-label" style="color:${color}">${r.fuel_type}</div>
          <div class="price-big" style="color:${color}">${r.avg_price}p</div>
          <div class="price-sub">avg today</div>
          <div style="margin-top:0.5rem">${badgeHtml(d7)} <span style="font-size:0.7rem;color:var(--muted)">vs 7d ago</span></div>
          <div style="margin-top:0.4rem;font-size:0.72rem;color:var(--muted)">
            ${r.station_count.toLocaleString()} stations
          </div>
        </div>`;
    }).join("");

    // last updated
    const latest = summary.reduce((a, b) => a.last_updated > b.last_updated ? a : b, summary[0]);
    el("last-updated").textContent = "Data: " + formatTime(latest.last_updated);
  } catch (e) { el("summary-cards").innerHTML = `<div class="error-msg">${e.message}</div>`; }
}

// ── 2. Summary Stats bar ───────────────────────────────────────────────────
async function renderSummaryStats() {
  try {
    const data = await api.summary();
    const totalStations = data.reduce((s, r) => s + parseInt(r.station_count), 0);
    const totalReadings = data.reduce((s, r) => s + parseInt(r.reading_count), 0);
    el("stats-bar").innerHTML = `
      <div class="stat-item"><div class="label">Fuel types</div><div class="value">${data.length}</div></div>
      <div class="stat-item"><div class="label">Stations today</div><div class="value">${totalStations.toLocaleString()}</div></div>
      <div class="stat-item"><div class="label">Readings today</div><div class="value">${totalReadings.toLocaleString()}</div></div>
    `;
  } catch {}
}

// ── 3. Fuel Type Price Comparison bar ─────────────────────────────────────
async function renderFuelComparison() {
  try {
    const data = await api.summary();
    mkChart("chart-fuel-compare", {
      type: "bar",
      data: {
        labels: data.map(r => r.fuel_type),
        datasets: [{
          data: data.map(r => r.avg_price),
          backgroundColor: data.map(r => FUEL_COLORS[r.fuel_type] || "#3b82f6"),
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: "y", plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } },
          y: { grid: { display: false } }
        }
      }
    });
  } catch {}
}

// ── 4. Price Change Cards (7d / 30d) ──────────────────────────────────────
async function renderPriceChangeCards() {
  try {
    const data = await api.priceChange();
    const cont = el("change-cards");
    cont.innerHTML = data.map(r => {
      const d7 = pct(r.current_avg, r.week_ago_avg);
      const d30 = pct(r.current_avg, r.month_ago_avg);
      const color = FUEL_COLORS[r.fuel_type] || "#3b82f6";
      return `
        <div class="card">
          <div class="card-title" style="color:${color}">${r.fuel_type} Price Change</div>
          <div style="display:flex;gap:1.5rem;align-items:center">
            <div>
              <div style="font-size:0.7rem;color:var(--muted)">vs 7 days</div>
              <div style="margin-top:0.2rem">${badgeHtml(d7)}</div>
            </div>
            <div>
              <div style="font-size:0.7rem;color:var(--muted)">vs 30 days</div>
              <div style="margin-top:0.2rem">${badgeHtml(d30)}</div>
            </div>
            <div style="margin-left:auto;text-align:right">
              <div style="font-size:0.7rem;color:var(--muted)">Now</div>
              <div style="font-size:1.3rem;font-weight:700;color:${color}">${r.current_avg}p</div>
            </div>
          </div>
        </div>`;
    }).join("");
  } catch (e) { el("change-cards").innerHTML = `<div class="error-msg">${e.message}</div>`; }
}

// ── 5. 30-Day Price Trend ──────────────────────────────────────────────────
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
      data: {
        labels: dates.map(d => new Date(d).toLocaleDateString("en-GB", { day:"numeric", month:"short" })),
        datasets: fuels.map(f => ({
          label: f, data: byFuel[f],
          borderColor: FUEL_COLORS[f] || "#3b82f6",
          backgroundColor: "transparent",
          borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true,
        }))
      },
      options: {
        plugins: { legend: { position: "top" } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { maxTicksLimit: 8 } },
          y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } }
        }
      }
    });
  } catch {}
}

// ── 6. Day of Week Patterns ────────────────────────────────────────────────
async function renderDayOfWeek() {
  try {
    const data = await api.byDow(activeFuel);
    mkChart("chart-dow", {
      type: "bar",
      data: {
        labels: data.map(r => DOW[r.day_of_week]),
        datasets: [{
          label: activeFuel,
          data: data.map(r => r.avg_price),
          backgroundColor: data.map((r, i) => {
            const min = Math.min(...data.map(x => x.avg_price));
            return r.avg_price === min ? FUEL_COLORS[activeFuel] || "#3b82f6" : "rgba(148,163,184,0.25)";
          }),
          borderRadius: 5,
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" }, suggestedMin: (d => Math.min(...d.map(r=>r.avg_price)) - 2)(data) }
        }
      }
    });
  } catch {}
}

// ── 7. Monthly Seasonality ─────────────────────────────────────────────────
async function renderMonthly() {
  try {
    const data = await api.byMonth(activeFuel);
    mkChart("chart-monthly", {
      type: "line",
      data: {
        labels: data.map(r => MONTHS[r.month - 1]),
        datasets: [{
          label: activeFuel,
          data: data.map(r => r.avg_price),
          borderColor: FUEL_COLORS[activeFuel] || "#3b82f6",
          backgroundColor: (FUEL_COLORS[activeFuel] || "#3b82f6") + "22",
          fill: true, borderWidth: 2, pointRadius: 4, tension: 0.3,
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } }
        }
      }
    });
  } catch {}
}

// ── 8. Price Distribution Histogram ───────────────────────────────────────
async function renderDistribution() {
  try {
    const data = await api.distribution(activeFuel);
    mkChart("chart-dist", {
      type: "bar",
      data: {
        labels: data.map(r => r.bucket + "p"),
        datasets: [{
          data: data.map(r => r.count),
          backgroundColor: FUEL_COLORS[activeFuel] + "99" || "#3b82f699",
          borderColor: FUEL_COLORS[activeFuel] || "#3b82f6",
          borderWidth: 1, borderRadius: 2,
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
          y: { grid: { color: gridColor }, title: { display: true, text: "Stations" } }
        }
      }
    });
  } catch {}
}

// ── 9. Interactive Station Map ─────────────────────────────────────────────
async function renderMap() {
  if (!map) {
    map = L.map("map").setView([54.5, -2.5], 6);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap © CARTO", maxZoom: 18
    }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
  }
  try {
    const prices = await api.prices(activeFuel, 500);
    markersLayer.clearLayers();
    if (!prices.length) return;
    const vals = prices.map(p => parseFloat(p.price_pence));
    const min = Math.min(...vals), max = Math.max(...vals);
    prices.forEach(p => {
      if (!p.latitude || !p.longitude) return;
      const t = (parseFloat(p.price_pence) - min) / (max - min || 1);
      const r = Math.round(t * 255), g = Math.round((1 - t) * 200);
      const color = `rgb(${r},${g},40)`;
      L.circleMarker([p.latitude, p.longitude], {
        radius: 5, fillColor: color, color: "#0f172a",
        weight: 1, fillOpacity: 0.85,
      }).bindPopup(`<b>${p.brand_name}</b><br>${p.city}, ${p.county}<br>
        <b style="color:${color}">${p.price_pence}p</b> ${p.fuel_type}<br>
        <small>${formatTime(p.recorded_at)}</small>`)
        .addTo(markersLayer);
    });
  } catch {}
}

// ── 10. Cheapest Counties Table ────────────────────────────────────────────
async function renderCheapestCounties() {
  try {
    const data = await api.byCounty(activeFuel);
    const top = data.slice(0, 10);
    const maxP = Math.max(...top.map(r => r.avg_price));
    el("table-cheapest-counties").innerHTML = `
      <table>
        <thead><tr><th class="rank">#</th><th>County</th><th>Avg Price</th><th>Stations</th></tr></thead>
        <tbody>${top.map((r, i) => `
          <tr>
            <td class="rank">${i + 1}</td>
            <td>${r.county}</td>
            <td>
              <div class="price-bar-wrap">
                <span>${r.avg_price}p</span>
                <div class="price-bar" style="width:${(r.avg_price/maxP*80).toFixed(0)}px"></div>
              </div>
            </td>
            <td style="color:var(--muted)">${r.station_count}</td>
          </tr>`).join("")}
        </tbody>
      </table>`;
  } catch {}
}

// ── 11. Station Count by County ────────────────────────────────────────────
async function renderStationByCounty() {
  try {
    const data = await api.stationByCounty();
    const top = data.slice(0, 15);
    mkChart("chart-station-county", {
      type: "bar",
      data: {
        labels: top.map(r => r.county),
        datasets: [{ data: top.map(r => r.station_count), backgroundColor: "#3b82f666", borderColor: "#3b82f6", borderWidth: 1, borderRadius: 4 }]
      },
      options: {
        indexAxis: "y", plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: gridColor } },
          y: { grid: { display: false }, ticks: { font: { size: 10 } } }
        }
      }
    });
  } catch {}
}

// ── 12. County Price Ranking ───────────────────────────────────────────────
async function renderCountyPriceRanking() {
  try {
    const data = await api.byCounty(activeFuel);
    const expensive = [...data].sort((a, b) => b.avg_price - a.avg_price).slice(0, 10);
    el("table-expensive-counties").innerHTML = `
      <table>
        <thead><tr><th class="rank">#</th><th>County</th><th>Avg Price</th></tr></thead>
        <tbody>${expensive.map((r, i) => `
          <tr>
            <td class="rank">${i + 1}</td>
            <td>${r.county}</td>
            <td style="color:var(--red);font-weight:600">${r.avg_price}p</td>
          </tr>`).join("")}
        </tbody>
      </table>`;
  } catch {}
}

// ── 13. Brand Average Price ────────────────────────────────────────────────
async function renderBrandPrice() {
  try {
    const data = await api.byBrand(activeFuel);
    const top = data.slice(0, 15);
    mkChart("chart-brand-price", {
      type: "bar",
      data: {
        labels: top.map(r => r.brand_name),
        datasets: [{
          label: "Avg price (p)",
          data: top.map(r => r.avg_price),
          backgroundColor: top.map((_, i) => `hsl(${210 + i * 8},70%,55%)`),
          borderRadius: 5,
        }]
      },
      options: {
        indexAxis: "y", plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } },
          y: { grid: { display: false }, ticks: { font: { size: 10 } } }
        }
      }
    });
  } catch {}
}

// ── 14. Brand Market Share Donut ───────────────────────────────────────────
async function renderBrandShare() {
  try {
    const data = await api.byBrand(activeFuel);
    const top = data.sort((a, b) => b.station_count - a.station_count).slice(0, 10);
    const others = data.slice(10).reduce((s, r) => s + r.station_count, 0);
    const labels = top.map(r => r.brand_name);
    const vals = top.map(r => r.station_count);
    if (others > 0) { labels.push("Others"); vals.push(others); }
    mkChart("chart-brand-share", {
      type: "doughnut",
      data: {
        labels,
        datasets: [{ data: vals, backgroundColor: labels.map((_, i) => `hsl(${i * 36},65%,55%)`), borderColor: "#1e293b", borderWidth: 2 }]
      },
      options: { plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } }, cutout: "65%" }
    });
  } catch {}
}

// ── 15. Motorway vs Regular ────────────────────────────────────────────────
async function renderMotorwayCompare() {
  try {
    const data = await api.motorwayCompare();
    const fuels = [...new Set(data.map(r => r.fuel_type))];
    const motorway = fuels.map(f => data.find(r => r.fuel_type === f && r.is_motorway === 1)?.avg_price ?? 0);
    const regular = fuels.map(f => data.find(r => r.fuel_type === f && r.is_motorway === 0)?.avg_price ?? 0);
    mkChart("chart-motorway", {
      type: "bar",
      data: {
        labels: fuels,
        datasets: [
          { label: "Motorway", data: motorway, backgroundColor: "#ef444466", borderColor: "#ef4444", borderWidth: 1, borderRadius: 4 },
          { label: "Regular",  data: regular,  backgroundColor: "#22c55e66", borderColor: "#22c55e", borderWidth: 1, borderRadius: 4 }
        ]
      },
      options: {
        plugins: { legend: { position: "top" } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } }
        }
      }
    });
  } catch {}
}

// ── 16. Supermarket vs Regular ─────────────────────────────────────────────
async function renderSupermarketCompare() {
  try {
    const data = await api.supermarketCompare();
    const fuels = [...new Set(data.map(r => r.fuel_type))];
    const supermarket = fuels.map(f => data.find(r => r.fuel_type === f && r.is_supermarket === 1)?.avg_price ?? 0);
    const regular = fuels.map(f => data.find(r => r.fuel_type === f && r.is_supermarket === 0)?.avg_price ?? 0);
    mkChart("chart-supermarket", {
      type: "bar",
      data: {
        labels: fuels,
        datasets: [
          { label: "Supermarket", data: supermarket, backgroundColor: "#3b82f666", borderColor: "#3b82f6", borderWidth: 1, borderRadius: 4 },
          { label: "Regular",     data: regular,     backgroundColor: "#a855f766", borderColor: "#a855f7", borderWidth: 1, borderRadius: 4 }
        ]
      },
      options: {
        plugins: { legend: { position: "top" } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } }
        }
      }
    });
  } catch {}
}

// ── 17. SNARIMAX Forecast ──────────────────────────────────────────────────
async function renderForecast() {
  const cont = el("forecast-content");
  try {
    const data = await api.forecast(activeFuel);
    mkChart("chart-forecast", {
      type: "line",
      data: {
        labels: data.map(r => new Date(r.date).toLocaleDateString("en-GB", { weekday:"short", day:"numeric", month:"short" })),
        datasets: [{
          label: `${activeFuel} forecast`,
          data: data.map(r => r.predicted_pence),
          borderColor: FUEL_COLORS[activeFuel] || "#3b82f6",
          backgroundColor: (FUEL_COLORS[activeFuel] || "#3b82f6") + "22",
          fill: true, borderWidth: 2.5, pointRadius: 5, tension: 0.3,
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: gridColor }, ticks: { callback: v => v + "p" } }
        }
      }
    });
    cont.style.display = "block";
    el("forecast-placeholder")?.remove();
  } catch {
    if (cont) cont.innerHTML = '<div class="loading">Forecast available after first model training (1st or 15th of the month)</div>';
  }
}

// ── 18. Anomaly Alerts ────────────────────────────────────────────────────
async function renderAnomalies() {
  const cont = el("anomaly-list");
  try {
    const data = await api.anomalies(activeFuel);
    if (!data.length) {
      cont.innerHTML = '<div class="loading" style="color:var(--green)">✓ No anomalies detected</div>';
      return;
    }
    cont.innerHTML = data.slice(0, 8).map(r => `
      <div class="anomaly-item">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <div class="a-station">${r.brand_name} — ${r.city}</div>
            <div class="a-meta">${r.county} · ${r.fuel_type}</div>
          </div>
          <div style="text-align:right">
            <div class="a-price">${parseFloat(r.price_pence).toFixed(1)}p</div>
            <div class="a-meta">range: ${r.lower_threshold?.toFixed(1)}–${r.upper_threshold?.toFixed(1)}p</div>
          </div>
        </div>
      </div>`).join("");
  } catch {
    cont.innerHTML = '<div class="loading">Anomaly data available after first model training</div>';
  }
}

// ── 19. XGBoost Price Predictor ────────────────────────────────────────────
async function initPredictor() {
  try {
    const stations = await api.stations();
    const sel = el("pred-station");
    stations.slice(0, 200).forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.node_id;
      opt.textContent = `${s.brand_name} — ${s.city}, ${s.county}`;
      sel.appendChild(opt);
    });
  } catch {}

  el("pred-btn")?.addEventListener("click", async () => {
    const node = el("pred-station").value;
    const ft = el("pred-fuel").value;
    const res = el("pred-result");
    res.innerHTML = '<div class="loading">Predicting…</div>';
    try {
      const data = await api.predict(node, ft);
      res.innerHTML = `
        <div class="predict-result">
          <div class="p-val">${data.predicted_pence}p</div>
          <div class="p-label">predicted price for ${ft}</div>
        </div>`;
    } catch {
      res.innerHTML = '<div class="loading">Prediction available after first model training</div>';
    }
  });
}

// ── 20. Recent Price Updates Feed ─────────────────────────────────────────
async function renderFeed() {
  try {
    const data = await api.prices(activeFuel, 20);
    el("price-feed").innerHTML = data.map(r => `
      <div class="feed-item">
        <div>
          <div class="feed-station">${r.brand_name}</div>
          <div class="feed-meta">${r.city}, ${r.county}</div>
        </div>
        <div style="text-align:right">
          <div class="feed-price">${parseFloat(r.price_pence).toFixed(1)}p</div>
          <div class="feed-meta">${formatTime(r.recorded_at)}</div>
        </div>
      </div>`).join("");
  } catch {}
}

// ── Fuel Tab Switching ─────────────────────────────────────────────────────
function refreshFuelDependents() {
  renderDayOfWeek();
  renderMonthly();
  renderDistribution();
  renderMap();
  renderCheapestCounties();
  renderCountyPriceRanking();
  renderBrandPrice();
  renderBrandShare();
  renderForecast();
  renderAnomalies();
  renderFeed();
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Fuel tab listeners
  document.querySelectorAll(".fuel-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".fuel-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFuel = btn.dataset.fuel;
      refreshFuelDependents();
    });
  });

  // Render all components
  await Promise.all([
    renderSummaryCards(),
    renderSummaryStats(),
    renderFuelComparison(),
    renderPriceChangeCards(),
    renderPriceTrend(),
    renderMotorwayCompare(),
    renderSupermarketCompare(),
    renderStationByCounty(),
  ]);

  refreshFuelDependents();
  initPredictor();
});
