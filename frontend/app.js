// ======== CONFIG ========

const WS_URL = "ws://127.0.0.1:8000/ws/prices";
const TRACKED_SYMBOLS = ["AAPL", "TSLA", "NVDA", "MSFT"];

// ======== STATE ========

let latestPrices = {};
let chart = null;
let chartSymbol = "AAPL";
let chartHistory = [];
let useMock = true;

// ======== DOM REFS ========

const wsStatusPill = document.getElementById("ws-status-pill");
const stocksTableBody = document.getElementById("stocks-table-body");
const recentAlertsContainer = document.getElementById("recent-alerts");
const chartSymbolLabel = document.getElementById("chart-symbol-label");

// ======== Helpers ========

function setWsStatus(state, text) {
  wsStatusPill.classList.remove("connected", "error");
  if (state === "connected") wsStatusPill.classList.add("connected");
  if (state === "error") wsStatusPill.classList.add("error");
  wsStatusPill.querySelector(".status-text").textContent = text;
}

function formatTime(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

// ======== Stocks table ========

function renderStocksTable() {
  stocksTableBody.innerHTML = "";

  TRACKED_SYMBOLS.forEach((symbol) => {
    const data = latestPrices[symbol];
    if (!data) return;

    const tr = document.createElement("tr");

    const changeClass = data.change >= 0 ? "price-up" : "price-down";
    const sign = data.change >= 0 ? "+" : "";

    // Highlight selected row
    if (symbol === chartSymbol) {
      tr.classList.add("row-selected");
    }

    tr.innerHTML = `
      <td>${symbol}</td>
      <td>${data.price.toFixed(2)}</td>
      <td class="${changeClass}">${sign}${data.change.toFixed(2)}</td>
      <td class="${changeClass}">${sign}${data.percentChange.toFixed(2)}%</td>
      <td>${formatTime(data.ts)}</td>
    `;

    // Click row → change chart symbol
    tr.addEventListener("click", () => {
      chartSymbol = symbol;
      chartHistory = [];
      chartSymbolLabel.textContent = symbol;
      renderStocksTable();
      updateChart(chartSymbol);
    });

    stocksTableBody.appendChild(tr);
  });
}

// ======== Recent Alerts ========

function addRecentAlert(symbol, direction, price) {
  const div = document.createElement("div");
  div.className = "alert-item";

  div.innerHTML = `
    <span class="alert-text">${symbol} moved ${direction} to ${price.toFixed(2)}</span>
    <span class="alert-meta">${formatTime()}</span>
  `;

  recentAlertsContainer.prepend(div);

  while (recentAlertsContainer.children.length > 6) {
    recentAlertsContainer.removeChild(recentAlertsContainer.lastChild);
  }
}

// ======== Chart ========

function initChart() {
  try {
    if (typeof Chart === "undefined") return;
    const ctx = document.getElementById("price-chart").getContext("2d");

    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Price",
            data: [],
            tension: 0.25,
            pointRadius: 2
          }
        ]
      },
      options: {
        responsive: true,
        scales: {
          x: {
            ticks: { color: "#9ca3af" },
            grid: { display: false }
          },
          y: {
            ticks: { color: "#9ca3af" },
            grid: { color: "rgba(55,65,81,0.3)" }
          }
        },
        plugins: { legend: { display: false } }
      }
    });
  } catch (err) {
    console.error("Chart init failed:", err);
  }
}

function updateChart(symbol) {
  if (!chart) return;

  const data = latestPrices[symbol];
  if (!data) return;

  chartHistory.push({ ts: data.ts, price: data.price });
  if (chartHistory.length > 10) chartHistory.shift();

  chart.data.labels = chartHistory.map((p) => formatTime(p.ts));
  chart.data.datasets[0].data = chartHistory.map((p) => p.price);
  chart.update();
}

// ======== WebSocket handling ========

function connectWebSocket() {
  const socket = new WebSocket(WS_URL);

  socket.addEventListener("open", () => {
    useMock = false;
    setWsStatus("connected", "Live data: connected");
  });

  socket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type !== "price_update") return;

    msg.data.forEach((item) => {
      const prev = latestPrices[item.symbol];
      latestPrices[item.symbol] = item;

      if (prev && Math.abs(item.price - prev.price) > 1) {
        const direction = item.price > prev.price ? "up" : "down";
        addRecentAlert(item.symbol, direction, item.price);
      }
    });

    renderStocksTable();
    updateChart(chartSymbol);
  });

  socket.addEventListener("close", () => {
    if (!useMock) startMockFeed();
  });

  socket.addEventListener("error", () => {
    if (!useMock) startMockFeed();
  });
}

// ======== Mock feed ========

function startMockFeed() {
  useMock = true;
  setWsStatus("error", "Mock feed active (no backend yet)");

  if (Object.keys(latestPrices).length === 0) {
    const now = new Date().toISOString();
    TRACKED_SYMBOLS.forEach((sym, idx) => {
      latestPrices[sym] = {
        symbol: sym,
        price: 100 + idx * 50,
        change: 0,
        percentChange: 0,
        ts: now
      };
    });

    renderStocksTable();
    updateChart(chartSymbol);
  }

  setInterval(() => {
    const now = new Date().toISOString();
    TRACKED_SYMBOLS.forEach((sym) => {
      const prev = latestPrices[sym];
      const delta = (Math.random() - 0.5) * 4;
      const newPrice = Math.max(1, prev.price + delta);
      const change = newPrice - prev.price;
      const percentChange = (change / prev.price) * 100;

      latestPrices[sym] = {
        symbol: sym,
        price: newPrice,
        change,
        percentChange,
        ts: now
      };

      if (Math.abs(change) > 1) {
        const direction = newPrice > prev.price ? "up" : "down";
        addRecentAlert(sym, direction, newPrice);
      }
    });

    renderStocksTable();
    updateChart(chartSymbol);
  }, 2500);
}

// ======== Init ========

document.addEventListener("DOMContentLoaded", () => {
  initChart();
  chartSymbolLabel.textContent = chartSymbol;

  try {
    connectWebSocket();
    setTimeout(() => {
      if (useMock) startMockFeed();
    }, 2000);
  } catch {
    startMockFeed();
  }

  // Sidebar scroll
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelectorAll(".nav-item").forEach((i) => i.classList.remove("active"));
      item.classList.add("active");

      const targetId = item.getAttribute("data-target");
      if (targetId === "top") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        const section = document.getElementById(targetId);
        if (section) section.scrollIntoView({ behavior: "smooth" });
      }
    });
  });
});
