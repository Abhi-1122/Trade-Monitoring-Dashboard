// Latency chart: the one place plain JS talks to the DRF API directly
// instead of HTMX — a redraw-in-place chart doesn't map cleanly onto
// htmx's swap-a-DOM-fragment model, so Chart.js owns this section.

let latencyChart = null;

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

async function initLatencyChart() {
  const canvas = document.getElementById("latency-chart");
  if (!canvas || typeof Chart === "undefined") return;

  const data = await fetchLatencySeries();
  const latencyValues = data.points.map((p) => p.latency_ms);

  latencyChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: toLabels(data.points),
      datasets: [
        {
          label: "Ack latency (ms)",
          data: latencyValues,
          borderColor: "#58a6ff",
          backgroundColor: "rgba(88, 166, 255, 0.12)",
          tension: 0.25,
          pointRadius: 2,
          fill: true,
        },
        {
          label: `Threshold (${data.threshold_ms}ms)`,
          data: thresholdLine(latencyValues.length, data.threshold_ms),
          borderColor: "#f85149",
          borderDash: [6, 4],
          borderWidth: 1,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      scales: {
        x: { ticks: { color: "#7d8896" }, grid: { color: "#232a37" } },
        y: { ticks: { color: "#7d8896" }, grid: { color: "#232a37" }, beginAtZero: true },
      },
      plugins: {
        legend: { labels: { color: "#d7dde5" } },
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
