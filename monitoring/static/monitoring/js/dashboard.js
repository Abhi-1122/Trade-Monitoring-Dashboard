// Latency chart: the one place plain JS talks to the DRF API directly
// instead of HTMX — a redraw-in-place chart doesn't map cleanly onto
// htmx's swap-a-DOM-fragment model, so Chart.js owns this section.

let latencyChart = null;

const ACCENT = "#2dd7b5";
const RED = "#fb5a7e";
const TEXT_DIM = "#8991a8";
const GRID = "rgba(255, 255, 255, 0.06)";

async function fetchLatencySeries() {
  const res = await fetch("/api/latency-series/?limit=50");
  return res.json();
}

function thresholdLine(length, value) {
  return new Array(length).fill(value);
}

function toLabels(points) {
  return points.map((p) => new Date(p.created_at).toLocaleTimeString());
}

function accentGradient(ctx) {
  const gradient = ctx.createLinearGradient(0, 0, 0, 260);
  gradient.addColorStop(0, "rgba(45, 215, 181, 0.35)");
  gradient.addColorStop(1, "rgba(45, 215, 181, 0)");
  return gradient;
}

async function initLatencyChart() {
  const canvas = document.getElementById("latency-chart");
  if (!canvas || typeof Chart === "undefined") return;

  const data = await fetchLatencySeries();
  const latencyValues = data.points.map((p) => p.latency_ms);
  const ctx = canvas.getContext("2d");

  latencyChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: toLabels(data.points),
      datasets: [
        {
          label: "Ack latency (ms)",
          data: latencyValues,
          borderColor: ACCENT,
          backgroundColor: accentGradient(ctx),
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: ACCENT,
          borderWidth: 2,
          fill: true,
        },
        {
          label: `Threshold (${data.threshold_ms}ms)`,
          data: thresholdLine(latencyValues.length, data.threshold_ms),
          borderColor: RED,
          borderDash: [6, 5],
          borderWidth: 1,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      interaction: { intersect: false, mode: "index" },
      scales: {
        x: {
          ticks: { color: TEXT_DIM, font: { family: "'JetBrains Mono', monospace", size: 10 } },
          grid: { color: GRID, drawTicks: false },
          border: { color: GRID },
        },
        y: {
          ticks: { color: TEXT_DIM, font: { family: "'JetBrains Mono', monospace", size: 10 } },
          grid: { color: GRID, drawTicks: false },
          border: { display: false },
          beginAtZero: true,
        },
      },
      plugins: {
        legend: {
          labels: {
            color: "#edf0f8",
            font: { family: "'Inter', sans-serif", size: 12 },
            usePointStyle: true,
            pointStyle: "circle",
            boxWidth: 8,
          },
        },
        tooltip: {
          backgroundColor: "#12141f",
          borderColor: "rgba(255,255,255,0.1)",
          borderWidth: 1,
          titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
          bodyFont: { family: "'JetBrains Mono', monospace", size: 12 },
          padding: 10,
          cornerRadius: 8,
        },
      },
    },
  });
}

async function refreshLatencyChart() {
  if (!latencyChart) return;
  const data = await fetchLatencySeries();
  const latencyValues = data.points.map((p) => p.latency_ms);
  latencyChart.data.labels = toLabels(data.points);
  latencyChart.data.datasets[0].data = latencyValues;
  latencyChart.data.datasets[1].data = thresholdLine(latencyValues.length, data.threshold_ms);
  latencyChart.update();
}

document.addEventListener("DOMContentLoaded", () => {
  initLatencyChart();
  setInterval(refreshLatencyChart, 10000);
});
