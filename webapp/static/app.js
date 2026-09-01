// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  currentTicker: null,
  originTabId: "tab-watchlist",   // which tab to return to when "Back" is clicked
  period: "6M",
  timeframe: "day",
  bbWindow: null,
  rsiPeriod: null,
  macdPreset: "standard",
  volumeLookback: null,
  visibleIndicators: {
    bollinger: true, rsi: true, macd: true, volume: true,
    trendline: true, smaCrossover: true, atr: true,
    stratLines: true,
    frvpPriorDay: false, frvpPrior3d: false, frvpPriorWeek: false,
  },
  charts: {},          // live lightweight-charts instances, keyed by "<prefix><pane>" (e.g. "price", "a-price")
  lastChartData: null, // most recently fetched chart payload for the single company view, for instant re-renders on toggle
  controlsBuilt: false,
  compareControlsBuilt: false,
  companies: [],        // full S&P 500 {symbol, name} list, for search
  compare: { tickerA: null, tickerB: null },
  compareData: { a: null, b: null }, // most recent chart payload per side, for instant re-renders on toggle
  lastPortfolioHoldings: null, // cached for a clean re-render when the Portfolio tab becomes visible
  frvpRedraw: {},        // per-prefix "redraw the FRVP overlay" closures, replayed on window resize
};

const CHART_PANES = ["price", "rsi", "macd", "volume", "atr"];

const MAIN_CONTROL_IDS = {
  timeframeControls: "timeframe-controls",
  periodControls: "period-controls",
  indicatorToggles: "indicator-toggles",
  indicatorSettings: "indicator-settings",
};
const COMPARE_CONTROL_IDS = {
  timeframeControls: "compare-timeframe-controls",
  periodControls: "compare-period-controls",
  indicatorToggles: "compare-indicator-toggles",
  indicatorSettings: "compare-indicator-settings",
};

const TIMEFRAME_LABELS = { month: "Month", week: "Week", day: "Day", "30min": "30-Min" };

const INDICATOR_LABELS = {
  bollinger: "Bollinger", rsi: "RSI", macd: "MACD", volume: "Volume",
  trendline: "Trendline", smaCrossover: "SMA 50/200", atr: "ATR",
  stratLines: "Support/Resistance",
  frvpPriorDay: "POC: Prior Day", frvpPrior3d: "POC: Prior 3D", frvpPriorWeek: "POC: Prior Week",
};

const INDICATOR_INFO = {
  bollinger: "Bands plotted 2 standard deviations above and below a rolling average price. Price touching the lower band can signal oversold conditions (a potential buy); touching the upper band can signal overbought conditions (a potential sell). In a strong trend, price can \"walk the band\" for a while without actually reversing.",
  rsi: "Relative Strength Index measures the speed and size of recent price changes on a 0-100 scale. Traditionally, below 30 is considered oversold and above 70 is considered overbought.",
  macd: "Moving Average Convergence/Divergence compares a fast and a slow moving average of price. When the MACD line is above its signal line (positive histogram), it suggests bullish momentum; below suggests bearish momentum.",
  volume: "Compares today's trading volume to its recent average. Unusually high volume during a price move suggests more conviction behind that move; unusually low volume suggests less.",
  trendline: "A straight best-fit line through prices over the period you're currently viewing, showing the overall direction (up, down, or sideways) at a glance. Refits automatically when you change the period.",
  smaCrossover: "Plots the 50-day and 200-day simple moving averages. When the 50-day crosses above the 200-day (a \"Golden Cross\"), it's a classic bullish trend-following signal; crossing below (a \"Death Cross\") is bearish.",
  atr: "Average True Range measures typical daily price movement (volatility) over the last 14 days, in dollars. It doesn't predict direction -- it's mainly used to size stop-losses or price targets relative to a stock's normal noise.",
  stratLines: "Support/resistance rays connecting swing highs or lows on the bars you're currently viewing, without any bar crossing the line -- the algorithmic version of manually drawing trend lines. A break of one is a potential trend reversal; a bounce off one is a potential trend continuation.",
  frvpPriorDay: "Fixed Range Volume Profile for the prior completed trading day: a horizontal histogram of how much volume traded at each price level, with a line at the Point of Control (POC) -- the single price level with the most volume, where a price revisit often causes a reaction.",
  frvpPrior3d: "Same as the Prior Day profile, but built from the prior 3 completed trading days.",
  frvpPriorWeek: "Same as the Prior Day profile, but built from the prior 5 completed trading days (about a week).",
};

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    document.getElementById("company-view").classList.add("hidden");
    document.body.classList.toggle("compare-active", btn.dataset.tab === "compare");

    if (btn.dataset.tab === "compare") {
      ensureCompareViewBuilt();
      if (state.compare.tickerA && state.compare.tickerB) refreshCompareView();
    }

    // The portfolio chart is measured from its container's actual rendered
    // width, which is 0 while its tab is display:none -- re-render (no
    // refetch needed) now that the container is actually visible and laid out.
    if (btn.dataset.tab === "portfolio" && state.lastPortfolioHoldings) {
      renderPortfolioChart(state.lastPortfolioHoldings);
    }

    if (btn.dataset.tab === "guide") loadGuide();
  });
});

// Fetched once per page load and cached -- the guide only changes when a
// new feature is added, not during normal use, so there's no need to
// refetch every time the tab is clicked.
async function loadGuide() {
  if (state.guideLoaded) return;
  const el = document.getElementById("guide-content");
  try {
    const res = await fetch("/api/guide");
    const data = await res.json();
    el.innerHTML = data.html;
    el.classList.remove("muted");
    state.guideLoaded = true;
  } catch (err) {
    el.textContent = "Failed to load the trading guide.";
    console.error(err);
  }
}

document.getElementById("back-btn").addEventListener("click", () => {
  document.getElementById("company-view").classList.add("hidden");
  document.getElementById(state.originTabId).classList.add("active");

  const originTabName = state.originTabId.replace("tab-", "");
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === originTabName);
  });
});

// ---------------------------------------------------------------------------
// Company search / autocomplete (reused by Watchlist search and Compare pickers)
// ---------------------------------------------------------------------------
async function loadCompanies() {
  try {
    const res = await fetch("/api/companies");
    state.companies = await res.json();
  } catch (err) {
    console.error("Failed to load company list for search:", err);
  }
}

function attachTickerSearch(inputEl, resultsEl, onSelect) {
  inputEl.addEventListener("input", () => {
    const q = inputEl.value.trim().toLowerCase();
    if (!q) {
      resultsEl.classList.add("hidden");
      resultsEl.innerHTML = "";
      return;
    }

    const matches = state.companies.filter(c =>
      c.symbol.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
    ).slice(0, 8);

    if (matches.length === 0) {
      resultsEl.innerHTML = `<div class="search-no-results">No matches</div>`;
    } else {
      resultsEl.innerHTML = matches.map(c => `
        <div class="search-result-item" data-symbol="${c.symbol}">
          <span class="search-result-name">${c.name}</span>
          <span class="search-result-symbol">${c.symbol}</span>
        </div>
      `).join("");
      resultsEl.querySelectorAll(".search-result-item").forEach(item => {
        item.addEventListener("click", () => {
          onSelect(item.dataset.symbol);
          inputEl.value = "";
          resultsEl.classList.add("hidden");
          resultsEl.innerHTML = "";
        });
      });
    }
    resultsEl.classList.remove("hidden");
  });
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".search-wrap")) {
    document.querySelectorAll(".search-results").forEach(r => r.classList.add("hidden"));
  }
  if (!e.target.closest(".indicator-info-wrap")) {
    document.querySelectorAll(".info-popover").forEach(p => p.remove());
  }
});

attachTickerSearch(
  document.getElementById("ticker-search-input"),
  document.getElementById("ticker-search-results"),
  (symbol) => addTickerToWatchlist(symbol)
);

async function addTickerToWatchlist(ticker) {
  await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  loadWatchlist();
}

// ---------------------------------------------------------------------------
// Watchlist
// ---------------------------------------------------------------------------
async function loadWatchlist() {
  const res = await fetch("/api/watchlist");
  const data = await res.json();
  const container = document.getElementById("watchlist-list");
  container.innerHTML = "";

  if (data.quotes.length === 0) {
    container.innerHTML = `<p class="muted">Search for a company above to start tracking it.</p>`;
    return;
  }

  data.quotes.forEach(q => {
    const row = document.createElement("div");
    row.className = "ticker-row";
    const changeClass = (q.change ?? 0) >= 0 ? "change-up" : "change-down";
    const changeSign = (q.change ?? 0) >= 0 ? "+" : "";
    row.innerHTML = `
      <div>
        <span class="ticker-symbol">${q.ticker}</span>
        <span class="ticker-name">${q.name || ""}</span>
      </div>
      <div class="ticker-right">
        <span>${q.price != null ? "$" + q.price.toFixed(2) : "N/A"}</span>
        <span class="${changeClass}">${q.change != null ? changeSign + q.change.toFixed(2) + " (" + changeSign + (q.change_percent ?? 0).toFixed(2) + "%)" : ""}</span>
        <button class="remove-btn" data-ticker="${q.ticker}" title="Remove">&times;</button>
      </div>
    `;
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("remove-btn")) return;
      openCompany(q.ticker, "tab-watchlist");
    });
    row.querySelector(".remove-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/watchlist/${q.ticker}`, { method: "DELETE" });
      loadWatchlist();
    });
    container.appendChild(row);
  });
}

// ---------------------------------------------------------------------------
// Movers
// ---------------------------------------------------------------------------
function recommendationBadgeClass(rec) {
  if (rec === "BUY") return "badge-buy";
  if (rec === "SELL") return "badge-sell";
  return "badge-hold";
}

function checkGlyph(passes) {
  return passes ? "✓" : "—"; // checkmark / em-dash
}

async function loadMovers() {
  const res = await fetch("/api/movers");
  const data = await res.json();

  document.getElementById("movers-updated").textContent = data.updated_at
    ? `Updated ${new Date(data.updated_at).toLocaleString()}` +
      (data.last_full_scan_date ? ` · last full analysis ${data.last_full_scan_date}` : "")
    : "";

  // Determined entirely by SPY's own prior closes -- knowable the moment
  // the PREVIOUS trading day closes, not something that develops during
  // the day itself. Shown up front since it decides whether trend-line
  // signals are trusted at all today (see regime gate in strategy_engine.py).
  const regimeEl = document.getElementById("movers-regime");
  const regime = data.market_regime || "unknown";
  const regimeText = regime === "bullish"
    ? "Bullish -- no validated edge, trend-line signals are NOT trusted today"
    : regime === "unknown"
      ? "Unknown (no scan yet)"
      : `${regime.charAt(0).toUpperCase()}${regime.slice(1)} -- trend-line signals are trusted today`;
  regimeEl.textContent = `Market regime (SPY): ${regimeText}`;
  regimeEl.className = `regime-banner regime-${regime}`;

  document.getElementById("movers-summary").textContent = data.summary || "No data yet.";

  const tbody = document.getElementById("movers-table-body");
  tbody.innerHTML = "";

  if (!data.companies || data.companies.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 9;
    td.className = "muted";
    td.textContent = "Nothing currently passes the trend-line or volume-profile methods.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    loadDigest();
    return;
  }

  data.companies.forEach(c => {
    const tr = document.createElement("tr");
    tr.className = "movers-row";

    const nameTd = document.createElement("td");
    const earningsBadge = c.earnings_soon
      ? `<span class="badge-earnings" title="Earnings report within 7 days">E</span>`
      : "";
    nameTd.innerHTML = `<span class="ticker-symbol">${c.ticker}</span>${earningsBadge} <span class="ticker-name">${c.name || ""}</span>`;
    tr.appendChild(nameTd);

    const recTd = document.createElement("td");
    const forming = c.trend_line_check?.forming_signal;
    const watchingBadge = forming
      ? ` <span class="badge-watching" title="Price is testing this line RIGHT NOW, intraday -- not confirmed until today's close. Not a recommendation.">Watching</span>`
      : "";
    recTd.innerHTML = `<span class="badge ${recommendationBadgeClass(c.recommendation)}">${c.recommendation}</span>${watchingBadge}`;
    tr.appendChild(recTd);

    const trendTd = document.createElement("td");
    trendTd.textContent = checkGlyph(c.trend_line_check?.passes);
    trendTd.className = c.trend_line_check?.passes ? "change-up" : "muted";
    tr.appendChild(trendTd);

    const pocTd = document.createElement("td");
    pocTd.textContent = checkGlyph(c.poc_check?.approaching);
    pocTd.className = c.poc_check?.approaching ? "change-up" : "muted";
    tr.appendChild(pocTd);

    const priceTd = document.createElement("td");
    priceTd.textContent = c.price != null ? `$${c.price.toFixed(2)}` : "N/A";
    tr.appendChild(priceTd);

    const plan = c.trade_plan;
    [["entry", plan?.entry], ["stop", plan?.stop], ["target", plan?.target]].forEach(([, v]) => {
      const td = document.createElement("td");
      td.textContent = v != null ? `$${v.toFixed(2)}` : "—";
      tr.appendChild(td);
    });
    const qtyTd = document.createElement("td");
    qtyTd.textContent = plan?.qty != null ? plan.qty : "—";
    tr.appendChild(qtyTd);

    tr.addEventListener("click", () => openCompany(c.ticker, "tab-movers"));
    tbody.appendChild(tr);
  });

  loadDigest();
}

async function loadDigest() {
  const res = await fetch("/api/digest");
  const data = await res.json();
  const box = document.getElementById("digest-box");

  const earningsCount = Object.keys(data.earnings || {}).length;
  const macroCount = (data.macro_news || []).length;

  if (earningsCount === 0 && macroCount === 0) {
    box.innerHTML = "";
    return;
  }

  let html = "<h4>This morning's digest</h4>";
  if (earningsCount > 0) {
    html += "<div><strong>Earnings soon:</strong> " +
      Object.entries(data.earnings).map(([t, d]) => `${t} (${d})`).join(", ") + "</div>";
  }
  if (macroCount > 0) {
    html += "<div style='margin-top:8px'><strong>Macro headlines:</strong></div>";
    data.macro_news.forEach(n => {
      html += `<div class="news-item">${n.headline} <span class="news-source">(${n.source})</span></div>`;
    });
  }
  box.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Company detail view (single-company: Watchlist/Movers)
// ---------------------------------------------------------------------------
async function openCompany(ticker, fromTabId) {
  state.currentTicker = ticker;
  state.originTabId = fromTabId || document.querySelector(".tab-panel.active")?.id || "tab-watchlist";

  // This was the actual bug: previously only company-view was shown, but the
  // tab list underneath was never hidden, so both rendered stacked on the
  // same page instead of company-view replacing the list.
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.getElementById("company-view").classList.remove("hidden");
  document.getElementById("company-error").classList.add("hidden");

  await refreshCompanyView();
}

const FRVP_WINDOW_KEYS = {
  frvpPriorDay: "prior_day", frvpPrior3d: "prior_3d", frvpPriorWeek: "prior_week",
};

function buildCompanyParams() {
  const params = new URLSearchParams({ period: state.period, macd_preset: state.macdPreset, timeframe: state.timeframe });
  if (state.bbWindow) params.set("bb_window", state.bbWindow);
  if (state.rsiPeriod) params.set("rsi_period", state.rsiPeriod);
  if (state.volumeLookback) params.set("volume_lookback", state.volumeLookback);

  const activeFrvp = Object.entries(FRVP_WINDOW_KEYS)
    .filter(([stateKey]) => state.visibleIndicators[stateKey])
    .map(([, apiKey]) => apiKey);
  if (activeFrvp.length) params.set("frvp_windows", activeFrvp.join(","));

  return params;
}

async function refreshCompanyView() {
  if (!state.currentTicker) return;
  const errorBox = document.getElementById("company-error");
  errorBox.classList.add("hidden");

  try {
    const params = buildCompanyParams();
    const res = await fetch(`/api/company/${state.currentTicker}?${params.toString()}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Server returned status ${res.status}`);
    }
    const data = await res.json();

    // Sync settings to whatever the backend actually used, so dropdowns
    // reflect real defaults on first load without hardcoding them here.
    if (state.bbWindow == null) state.bbWindow = data.chart.bollinger.window;
    if (state.rsiPeriod == null) state.rsiPeriod = data.chart.rsi.period;
    if (state.volumeLookback == null) state.volumeLookback = data.chart.volume_avg.window;
    state.lastChartData = data.chart;

    if (!state.controlsBuilt) {
      buildControlsInto(MAIN_CONTROL_IDS, data.settings, handleMainControlChange);
      state.controlsBuilt = true;
    }
    syncAllControlsActiveState();
    renderInfoPanel(data.info, data.news, state.currentTicker, data.chart);
    renderStrategyBox(data.strategy);
    renderOutlook(data.outlook);
    renderSummary(data.summary_lines);
    renderCharts(data.chart);
  } catch (err) {
    console.error("Failed to load company data:", err);
    errorBox.textContent = `Couldn't load data for ${state.currentTicker}: ${err.message}`;
    errorBox.classList.remove("hidden");
  }
}

// --- Controls: built ONCE per view (ticker-agnostic UI chrome), just re-synced after that.
// (Rebuilding this DOM on every refresh was the bug behind period/setting buttons
// silently going dead -- the safer approach is to build the elements a single
// time and only update their active/selected state afterward.) ---
function buildControlsInto(ids, settings, onChange) {
  const timeframeBox = document.getElementById(ids.timeframeControls);
  timeframeBox.innerHTML = "";
  (settings.timeframe_options || []).forEach(tf => {
    const btn = document.createElement("button");
    btn.textContent = TIMEFRAME_LABELS[tf] || tf;
    btn.dataset.timeframe = tf;
    btn.addEventListener("click", () => onChange({ timeframe: tf }));
    timeframeBox.appendChild(btn);
  });

  const periodBox = document.getElementById(ids.periodControls);
  periodBox.innerHTML = "";
  settings.period_options.forEach(p => {
    const btn = document.createElement("button");
    btn.textContent = p;
    btn.dataset.period = p;
    btn.addEventListener("click", () => onChange({ period: p }));
    periodBox.appendChild(btn);
  });

  const toggleBox = document.getElementById(ids.indicatorToggles);
  toggleBox.innerHTML = "";
  Object.keys(state.visibleIndicators).forEach(key => {
    const wrap = document.createElement("div");
    wrap.className = "indicator-info-wrap";

    const btn = document.createElement("button");
    btn.textContent = INDICATOR_LABELS[key] || key;
    btn.dataset.indicator = key;
    btn.addEventListener("click", () => onChange({ toggle: key }));

    const infoBtn = document.createElement("button");
    infoBtn.type = "button";
    infoBtn.className = "info-btn";
    infoBtn.textContent = "i";
    infoBtn.setAttribute("aria-label", `What is ${INDICATOR_LABELS[key] || key}?`);
    attachInfoPopover(infoBtn, key);

    wrap.appendChild(btn);
    wrap.appendChild(infoBtn);
    toggleBox.appendChild(wrap);
  });

  const settingsBox = document.getElementById(ids.indicatorSettings);
  settingsBox.innerHTML = `
    <label>Bollinger window
      <select class="bb-window-select">
        ${settings.bb_window_options.map(w => `<option value="${w}">${w}d</option>`).join("")}
      </select>
    </label>
    <label>RSI period
      <select class="rsi-period-select">
        ${settings.rsi_period_options.map(p => `<option value="${p}">${p}d</option>`).join("")}
      </select>
    </label>
    <label>MACD preset
      <select class="macd-preset-select">
        ${settings.macd_presets.map(p => `<option value="${p}">${p}</option>`).join("")}
      </select>
    </label>
    <label>Volume avg
      <select class="volume-lookback-select">
        ${settings.volume_lookback_options.map(w => `<option value="${w}">${w}d</option>`).join("")}
      </select>
    </label>
  `;
  settingsBox.querySelector(".bb-window-select").addEventListener("change", e => onChange({ bbWindow: parseInt(e.target.value) }));
  settingsBox.querySelector(".rsi-period-select").addEventListener("change", e => onChange({ rsiPeriod: parseInt(e.target.value) }));
  settingsBox.querySelector(".macd-preset-select").addEventListener("change", e => onChange({ macdPreset: e.target.value }));
  settingsBox.querySelector(".volume-lookback-select").addEventListener("change", e => onChange({ volumeLookback: parseInt(e.target.value) }));
}

function updateControlsActiveState(ids) {
  document.querySelectorAll(`#${ids.timeframeControls} button`).forEach(btn => {
    btn.classList.toggle("active", btn.dataset.timeframe === state.timeframe);
  });
  // The display-period buttons (1M/3M/.../5Y) only apply to the Day
  // timeframe -- Month/Week/30-Min use their own fixed display depth
  // (see chart_data.py), so gray the period group out otherwise rather
  // than leaving stale, inapplicable buttons active.
  document.getElementById(ids.periodControls).classList.toggle("disabled-group", state.timeframe !== "day");
  document.querySelectorAll(`#${ids.periodControls} button`).forEach(btn => {
    btn.classList.toggle("active", btn.dataset.period === state.period);
  });
  document.querySelectorAll(`#${ids.indicatorToggles} button[data-indicator]`).forEach(btn => {
    btn.classList.toggle("active", state.visibleIndicators[btn.dataset.indicator]);
  });
  const box = document.getElementById(ids.indicatorSettings);
  const bbSel = box.querySelector(".bb-window-select");
  if (bbSel && state.bbWindow != null) bbSel.value = state.bbWindow;
  const rsiSel = box.querySelector(".rsi-period-select");
  if (rsiSel && state.rsiPeriod != null) rsiSel.value = state.rsiPeriod;
  const macdSel = box.querySelector(".macd-preset-select");
  if (macdSel) macdSel.value = state.macdPreset;
  const volSel = box.querySelector(".volume-lookback-select");
  if (volSel && state.volumeLookback != null) volSel.value = state.volumeLookback;
}

// Settings (period/bbWindow/rsiPeriod/macdPreset/volumeLookback/visibleIndicators)
// are shared across the single-company view AND the Compare tab -- if either
// control bar has been built, keep it in sync with the shared state.
function syncAllControlsActiveState() {
  if (state.controlsBuilt) updateControlsActiveState(MAIN_CONTROL_IDS);
  if (state.compareControlsBuilt) updateControlsActiveState(COMPARE_CONTROL_IDS);
}

function makeControlChangeHandler(refreshFn, getRenderTargets) {
  return function (change) {
    if (change.toggle) {
      state.visibleIndicators[change.toggle] = !state.visibleIndicators[change.toggle];
      syncAllControlsActiveState();
      if (change.toggle in FRVP_WINDOW_KEYS) {
        // FRVP bins are only computed server-side when requested -- a plain
        // client-side re-render (like the other toggles use) wouldn't have
        // the data the first time a window is switched on.
        refreshFn();
      } else {
        getRenderTargets().forEach(([chart, prefix]) => { if (chart) renderCharts(chart, prefix); });
      }
      return;
    }
    if (change.period) state.period = change.period;
    if (change.timeframe) state.timeframe = change.timeframe;
    if (change.bbWindow !== undefined) state.bbWindow = change.bbWindow;
    if (change.rsiPeriod !== undefined) state.rsiPeriod = change.rsiPeriod;
    if (change.macdPreset !== undefined) state.macdPreset = change.macdPreset;
    if (change.volumeLookback !== undefined) state.volumeLookback = change.volumeLookback;
    syncAllControlsActiveState();
    refreshFn();
  };
}

const handleMainControlChange = makeControlChangeHandler(
  refreshCompanyView,
  () => [[state.lastChartData, ""]]
);
const handleCompareControlChange = makeControlChangeHandler(
  refreshCompareView,
  () => [[state.compareData.a, "a-"], [state.compareData.b, "b-"]]
);

// ---------------------------------------------------------------------------
// Info popovers (what does this indicator mean?)
// ---------------------------------------------------------------------------
function attachInfoPopover(button, key) {
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    const already = button.parentElement.querySelector(".info-popover");
    document.querySelectorAll(".info-popover").forEach(p => p.remove());
    if (already) return; // clicking the same info button again just closes it
    const pop = document.createElement("div");
    pop.className = "info-popover";
    pop.textContent = INDICATOR_INFO[key] || "No description available.";
    button.parentElement.appendChild(pop);
  });
}

// ---------------------------------------------------------------------------
// Info panel / outlook / summary rendering (shared by single view + Compare)
// ---------------------------------------------------------------------------
function computePotentialToMean(chart, info) {
  const meanArr = chart?.bollinger?.mean;
  const mean = meanArr && meanArr.length ? meanArr[meanArr.length - 1] : null;
  if (mean == null) return null;

  const closeArr = chart?.close;
  const refPrice = (info?.price != null) ? info.price : (closeArr && closeArr.length ? closeArr[closeArr.length - 1] : null);
  if (refPrice == null) return null;

  return {
    pct: (mean - refPrice) / refPrice * 100,
    window: chart.bollinger.window,
  };
}

function renderInfoPanel(info, news, ticker, chart, prefix = "") {
  document.getElementById(`${prefix}company-header`).textContent = `${info.name || ticker} (${ticker})`;

  const change = info.change ?? 0;
  const changeClass = change >= 0 ? "change-up" : "change-down";
  const sign = change >= 0 ? "+" : "";
  document.getElementById(`${prefix}company-quote`).innerHTML = `
    <span class="price">${info.price != null ? "$" + info.price.toFixed(2) : "N/A"}</span>
    <span class="change ${changeClass}">${info.change != null ? sign + info.change.toFixed(2) + " (" + sign + (info.change_percent ?? 0).toFixed(2) + "%)" : ""}</span>
  `;

  // Distinct from the "today's change" figure above -- this answers "how far
  // back to the Bollinger average is price right now", the same measure the
  // Movers tab sorts by, so the two numbers are never confused for each other.
  const potentialBox = document.getElementById(`${prefix}company-potential`);
  const potential = computePotentialToMean(chart, info);
  if (potential) {
    const pctClass = potential.pct >= 0 ? "change-up" : "change-down";
    const pctSign = potential.pct >= 0 ? "+" : "";
    potentialBox.innerHTML = `
      <div class="potential-label">Potential move to the ${potential.window}-day average</div>
      <div class="potential-value ${pctClass}">${pctSign}${potential.pct.toFixed(2)}%</div>
      <div class="potential-caption">Distance back to the rolling average -- not today's price change above, and not a price target or guarantee.</div>
    `;
  } else {
    potentialBox.innerHTML = "";
  }

  document.getElementById(`${prefix}company-profile`).innerHTML = `
    <div><strong>Industry:</strong> ${info.industry || "N/A"}</div>
    <div><strong>Exchange:</strong> ${info.exchange || "N/A"}</div>
    <div><strong>Market cap:</strong> ${info.market_cap_millions ? "$" + Math.round(info.market_cap_millions).toLocaleString() + "M" : "N/A"}</div>
    <div><strong>P/E (TTM):</strong> ${info.pe_ttm != null ? info.pe_ttm.toFixed(1) : "N/A"}</div>
    <div><strong>Dividend yield:</strong> ${info.dividend_yield_pct != null ? info.dividend_yield_pct.toFixed(2) + "%" : "N/A"}</div>
    <div><strong>52wk range:</strong> ${info.week_52_low != null && info.week_52_high != null ? "$" + info.week_52_low.toFixed(2) + " - $" + info.week_52_high.toFixed(2) : "N/A"}</div>
  `;

  const earningsHtml = (info.recent_earnings || []).map(e =>
    `<div>${e.period}: EPS ${e.eps_actual ?? "N/A"} vs est. ${e.eps_estimate ?? "N/A"}${e.surprise_percent != null ? ` (${e.surprise_percent > 0 ? "+" : ""}${e.surprise_percent.toFixed(1)}%)` : ""}</div>`
  ).join("");
  document.getElementById(`${prefix}company-earnings`).innerHTML = `<strong>Recent earnings</strong>${earningsHtml || "<div>No data</div>"}`;

  renderNewsList(news, prefix);

  document.getElementById(`${prefix}company-about`).innerHTML =
    `<strong>About</strong><div>${info.description || "Description not available."}</div>`;
}

// News: precomputed items carry a "bullet" (extractive short summary) and,
// when has_indepth is true, an "indepth" list of sentences shown in a popup
// on click. Tickers without precomputed summaries just get the plain
// headline with no click affordance, same as before this feature existed.
// Built with real DOM nodes + textContent (not innerHTML string interpolation)
// since headlines/summaries originate from third-party news sources.
function renderNewsList(news, prefix) {
  const container = document.getElementById(`${prefix}company-news`);
  container.innerHTML = "";

  const title = document.createElement("strong");
  title.textContent = "Recent news";
  container.appendChild(title);

  if (!news || news.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "No recent news";
    container.appendChild(empty);
    return;
  }

  news.forEach(n => {
    const item = document.createElement("div");
    item.className = "news-item";

    const textWrap = document.createElement("span");
    textWrap.className = "news-item-text";

    const textSpan = document.createElement("span");
    textSpan.textContent = n.bullet || n.headline;
    textWrap.appendChild(textSpan);

    const sourceSpan = document.createElement("span");
    sourceSpan.className = "muted";
    sourceSpan.textContent = ` (${n.source})`;
    textWrap.appendChild(sourceSpan);

    item.appendChild(textWrap);

    // A dedicated button, not just a clickable row -- same idea as the
    // indicator "i" buttons: an explicit, always-visible affordance rather
    // than something you only discover by hovering.
    if (n.has_indepth) {
      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.className = "news-view-btn";
      viewBtn.textContent = "›"; // ›
      viewBtn.setAttribute("aria-label", `Read more: ${n.headline}`);
      viewBtn.addEventListener("click", () => openNewsModal(n));
      item.appendChild(viewBtn);
    }

    container.appendChild(item);
  });
}

function openNewsModal(newsItem) {
  document.getElementById("news-modal-headline").textContent = newsItem.headline || "";
  document.getElementById("news-modal-source").textContent = newsItem.source || "";

  const body = document.getElementById("news-modal-body");
  body.innerHTML = "";
  (newsItem.indepth || []).forEach(sentence => {
    const p = document.createElement("p");
    p.textContent = sentence;
    body.appendChild(p);
  });

  const linkWrap = document.getElementById("news-modal-link-wrap");
  linkWrap.innerHTML = "";
  if (newsItem.url) {
    const link = document.createElement("a");
    link.href = newsItem.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Read the full article";
    linkWrap.appendChild(link);
  }

  document.getElementById("news-modal-overlay").classList.remove("hidden");
}

function closeNewsModal() {
  document.getElementById("news-modal-overlay").classList.add("hidden");
}

document.getElementById("news-modal-close").addEventListener("click", closeNewsModal);
document.getElementById("news-modal-overlay").addEventListener("click", (e) => {
  if (e.target.id === "news-modal-overlay") closeNewsModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeNewsModal();
});

// The trend-line + volume-profile strategy engine's read for this ticker --
// same data that drives the Movers tab, shown here in full (touches,
// higher-timeframe bias, POC windows, trade plan) rather than the table's
// compact checkmarks. Most watchlist tickers won't have this yet (only
// tickers a full scan or a manual Refresh has actually analyzed do).
function renderStrategyBox(strategy, prefix = "") {
  const box = document.getElementById(`${prefix}company-strategy`);
  if (!strategy) {
    box.innerHTML = `<div class="strategy-empty muted">No strategy analysis yet for this ticker -- click Refresh to run the trend-line + volume-profile check now.</div>`;
    return;
  }

  const leanClass = strategy.recommendation === "BUY" ? "change-up" : strategy.recommendation === "SELL" ? "change-down" : "";
  const trend = strategy.trend_line_check || {};
  const poc = strategy.poc_check || {};
  const plan = strategy.trade_plan;

  let html = `<div class="strategy-lean ${leanClass}">${strategy.recommendation}${
    strategy.earnings_soon ? ` <span class="badge-earnings" title="Earnings report within 7 days">E</span>` : ""
  }${
    trend.forming_signal ? ` <span class="badge-watching" title="Price is testing this line RIGHT NOW, intraday -- not confirmed until today's close. Not a recommendation.">Watching</span>` : ""
  }</div>`;
  html += `<div class="strategy-row"><strong>Trend-line:</strong> ${
    trend.passes ? `${trend.breakout_or_bounce === "breakout" ? "Breakout" : "Bounce"} (${trend.signal})` : "No signal"
  }</div>`;
  if (trend.forming_signal) {
    html += `<div class="strategy-row"><span class="badge-watching">Watching</span> <span class="muted">Price is currently testing a line intraday (${trend.forming_signal}) -- unconfirmed until today's close, not a recommendation. Check back after close or tomorrow.</span></div>`;
  }
  html += `<div class="strategy-row"><strong>Higher-timeframe bias:</strong> ${strategy.higher_tf_bias || "neutral"}</div>`;

  const regimeNote = trend.market_bias === "bullish"
    ? `<span class="muted">(no validated edge in a bullish market -- signals not trusted right now)</span>`
    : `<span class="muted">(trend-line signals trusted)</span>`;
  html += `<div class="strategy-row"><strong>Market regime (SPY):</strong> ${trend.market_bias || "neutral"} ${regimeNote}</div>`;

  const pocLines = Object.entries(poc.windows || {})
    .filter(([, w]) => w.approaching)
    .map(([key, w]) => `${key.replace(/_/g, " ")}: POC $${w.poc_price.toFixed(2)} (${w.distance_pct.toFixed(2)}% away)`);
  html += `<div class="strategy-row"><strong>Near POC:</strong> ${
    pocLines.length ? pocLines.join("; ") : "Not currently approaching a tracked POC level"
  } <span class="muted">(informational -- doesn't drive the recommendation)</span></div>`;

  if (plan) {
    html += `
      <div class="trade-plan-grid">
        <div><span class="muted">Entry</span><br>$${plan.entry.toFixed(2)}</div>
        <div><span class="muted">Stop</span><br>$${plan.stop.toFixed(2)}</div>
        <div><span class="muted">Target</span><br>$${plan.target.toFixed(2)}</div>
        <div><span class="muted">Qty</span><br>${plan.qty}</div>
      </div>
      <div class="strategy-disclaimer muted">Not financial advice -- sized to a $${plan.risk_dollars.toFixed(0)} risk at a ${plan.reward_risk}:1 reward:risk ratio.${
        plan.atr != null ? ` Stop derived using an ATR (14-day) of $${plan.atr.toFixed(2)}.` : ""
      }</div>
    `;
  }

  if (strategy.last_full_analysis_at) {
    html += `<div class="strategy-timestamp muted">Last full analysis: ${new Date(strategy.last_full_analysis_at).toLocaleString()}</div>`;
  }

  box.innerHTML = html;
}

function wireRefreshButton(btnId, prefix, getTicker) {
  const btn = document.getElementById(btnId);
  btn.addEventListener("click", async () => {
    const ticker = getTicker();
    if (!ticker) return;
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Refreshing…";
    try {
      const res = await fetch(`/api/company/${ticker}/refresh`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Server returned status ${res.status}`);
      }
      const result = await res.json();
      renderStrategyBox(result, prefix);
    } catch (err) {
      console.error("Strategy refresh failed:", err);
      document.getElementById(`${prefix}company-strategy`).innerHTML =
        `<div class="strategy-empty muted">Refresh failed: ${err.message}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}

function renderOutlook(outlook, prefix = "") {
  const box = document.getElementById(`${prefix}company-outlook`);
  if (!outlook) {
    box.innerHTML = "";
    return;
  }
  const leanClass = outlook.lean === "BUY" ? "change-up" : outlook.lean === "SELL" ? "change-down" : "";
  box.innerHTML = `
    <div class="outlook-lean ${leanClass}">${outlook.lean}</div>
    <div class="outlook-text">${outlook.text}</div>
  `;
}

function renderSummary(lines, prefix = "") {
  const ul = document.getElementById(`${prefix}summary-lines`);
  ul.innerHTML = "";
  (lines || []).forEach(line => {
    const li = document.createElement("li");
    li.textContent = line;
    ul.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// Charts (lightweight-charts)
// ---------------------------------------------------------------------------
function disposeCharts(prefix = "") {
  CHART_PANES.forEach(name => {
    const key = prefix + name;
    if (state.charts[key]) {
      try { state.charts[key].remove(); } catch (e) { /* container already gone -- fine */ }
      delete state.charts[key];
    }
  });
}

function makeChart(containerId) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  // autoSize keeps the chart's canvas correctly matched to its container via
  // a ResizeObserver -- without this, charts sized themselves once at
  // creation time and could end up too wide, spilling into the sidebar.
  return LightweightCharts.createChart(container, {
    autoSize: true,
    layout: { background: { color: "#ffffff" }, textColor: "#333" },
    grid: { vertLines: { color: "#f0f0f0" }, horzLines: { color: "#f0f0f0" } },
    timeScale: { borderColor: "#ddd" },
    rightPriceScale: { borderColor: "#ddd" },
  });
}

function toSeries(dates, values) {
  const out = [];
  for (let i = 0; i < dates.length; i++) {
    if (values[i] != null) out.push({ time: dates[i], value: values[i] });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Fixed Range Volume Profile overlay -- a horizontal volume-at-price
// histogram drawn as an absolutely-positioned SVG layered over the price
// chart (lightweight-charts v4 has no native sideways-histogram series type;
// every built-in series is time-indexed on the x-axis). Bar length is
// proportional to volume at that price bin; a solid line marks the Point of
// Control. One or more windows can be shown at once, each in its own color.
// ---------------------------------------------------------------------------
const FRVP_WINDOWS_META = [
  { key: "prior_day", stateKey: "frvpPriorDay", color: "#2f6fb3" },
  { key: "prior_3d", stateKey: "frvpPrior3d", color: "#c98a2c" },
  { key: "prior_week", stateKey: "frvpPriorWeek", color: "#7a4fbf" },
];

function renderFrvpOverlay(chart, container, candleSeries) {
  const old = container.querySelector(".frvp-overlay");
  if (old) old.remove();

  const active = FRVP_WINDOWS_META.filter(w => state.visibleIndicators[w.stateKey]);
  if (active.length === 0) return;

  if (!chart.frvp) {
    console.warn("FRVP overlay: no toggle is active on the backend's response yet (chart.frvp is empty) -- " +
                  "this can happen for one redraw right after switching timeframe/toggling. Will retry.");
    return;
  }

  // getBoundingClientRect (not clientWidth/clientHeight) so this still works
  // correctly even with sub-pixel layout or border-box sizing quirks.
  const rect = container.getBoundingClientRect();
  const width = Math.round(rect.width);
  const height = Math.round(rect.height);
  if (!width || !height) return;

  const svg = svgEl("svg", {
    class: "frvp-overlay", width, height,
    viewBox: `0 0 ${width} ${height}`,
  });
  const maxBarWidthPx = Math.max(30, width * 0.28);
  let drewAnything = false;

  active.forEach(meta => {
    const profile = chart.frvp[meta.key];
    if (!profile || !profile.bins || profile.bins.length === 0) return;

    const maxVol = Math.max(0, ...profile.bins.map(b => b.volume || 0));
    if (maxVol <= 0) return;

    const g = svgEl("g", { class: "frvp-window" });

    profile.bins.forEach(bin => {
      // priceToCoordinate can legitimately return null for one redraw if
      // it's called before the chart has finished its first layout pass --
      // guard per-call rather than letting it throw and abort the whole
      // overlay (or, worse, the rest of renderCharts).
      let yHigh, yLow;
      try {
        yHigh = candleSeries.priceToCoordinate(bin.price_high);
        yLow = candleSeries.priceToCoordinate(bin.price_low);
      } catch (e) { return; }
      if (yHigh == null || yLow == null) return;

      const top = Math.min(yHigh, yLow);
      const barHeight = Math.max(1, Math.abs(yLow - yHigh));
      const barW = ((bin.volume || 0) / maxVol) * maxBarWidthPx;
      if (!(barW > 0)) return;
      g.appendChild(svgEl("rect", {
        x: (width - barW).toFixed(1), y: top.toFixed(1),
        width: barW.toFixed(1), height: barHeight.toFixed(1),
        fill: meta.color, opacity: 0.35,
      }));
      drewAnything = true;
    });

    try {
      const pocY = candleSeries.priceToCoordinate(profile.poc_price);
      if (pocY != null) {
        g.appendChild(svgEl("line", {
          x1: 0, x2: width, y1: pocY.toFixed(1), y2: pocY.toFixed(1),
          stroke: meta.color, "stroke-width": 2,
        }));
        drewAnything = true;
      }
    } catch (e) { /* chart not laid out yet -- next redraw retries */ }

    svg.appendChild(g);
  });

  container.appendChild(svg);
  if (!drewAnything) {
    console.warn("FRVP overlay: toggle is on and data was returned, but nothing could be drawn " +
                  "(chart likely hasn't finished laying out yet) -- retrying next frame.");
    requestAnimationFrame(() => renderFrvpOverlay(chart, container, candleSeries));
  }
}

// Redrawn on render + window resize (not on live pan/zoom -- a known v1
// limitation, since that would need a per-frame redraw loop).
let frvpResizeScheduled = false;
window.addEventListener("resize", () => {
  if (frvpResizeScheduled) return;
  frvpResizeScheduled = true;
  requestAnimationFrame(() => {
    frvpResizeScheduled = false;
    Object.values(state.frvpRedraw).forEach(fn => fn());
  });
});

function renderCharts(chart, prefix = "") {
  document.getElementById(`${prefix}price-chart`).classList.remove("hidden");
  document.getElementById(`${prefix}rsi-chart`).classList.toggle("hidden", !state.visibleIndicators.rsi);
  document.getElementById(`${prefix}macd-chart`).classList.toggle("hidden", !state.visibleIndicators.macd);
  document.getElementById(`${prefix}volume-chart`).classList.toggle("hidden", !state.visibleIndicators.volume);
  document.getElementById(`${prefix}atr-chart`).classList.toggle("hidden", !state.visibleIndicators.atr);

  disposeCharts(prefix);  // clean up any previous chart instances before creating new ones

  // --- Price chart: candlesticks + optional Bollinger/Trendline/SMA overlays ---
  const priceChart = makeChart(`${prefix}price-chart`);
  const candleSeries = priceChart.addCandlestickSeries({
    upColor: "#1c7c3f", downColor: "#b3261e", borderVisible: false,
    wickUpColor: "#1c7c3f", wickDownColor: "#b3261e",
  });
  const candles = [];
  for (let i = 0; i < chart.dates.length; i++) {
    if (chart.open[i] == null) continue;
    candles.push({
      time: chart.dates[i], open: chart.open[i], high: chart.high[i],
      low: chart.low[i], close: chart.close[i],
    });
  }
  candleSeries.setData(candles);

  if (state.visibleIndicators.bollinger) {
    const upperSeries = priceChart.addLineSeries({ color: "#8a7fd6", lineWidth: 1 });
    const lowerSeries = priceChart.addLineSeries({ color: "#8a7fd6", lineWidth: 1 });
    const meanSeries = priceChart.addLineSeries({ color: "#c9c2f0", lineWidth: 1, lineStyle: 2 });
    upperSeries.setData(toSeries(chart.dates, chart.bollinger.upper));
    lowerSeries.setData(toSeries(chart.dates, chart.bollinger.lower));
    meanSeries.setData(toSeries(chart.dates, chart.bollinger.mean));
  }

  if (state.visibleIndicators.trendline && chart.trendline) {
    const trendSeries = priceChart.addLineSeries({ color: "#c98a2c", lineWidth: 2 });
    trendSeries.setData(toSeries(chart.dates, chart.trendline.values));
  }

  if (state.visibleIndicators.smaCrossover && chart.sma_crossover) {
    const fastSeries = priceChart.addLineSeries({ color: "#2f6fb3", lineWidth: 1.5 });
    const slowSeries = priceChart.addLineSeries({ color: "#b3552f", lineWidth: 1.5 });
    fastSeries.setData(toSeries(chart.dates, chart.sma_crossover.fast));
    slowSeries.setData(toSeries(chart.dates, chart.sma_crossover.slow));
  }

  // Swing-hull support/resistance lines for whichever timeframe is
  // currently displayed -- the algorithmic version of manually drawing
  // trend lines (see trendline_engine.py). Green = support (upward), red =
  // resistance (downward), per the videos' own convention -- but a
  // brighter, thicker shade than the candles' green/red so the line reads
  // as a distinct overlay rather than blending into the candle bodies.
  if (state.visibleIndicators.stratLines && chart.strategy_trend_lines) {
    if (chart.strategy_trend_lines.upward) {
      const upSeries = priceChart.addLineSeries({ color: "#00b368", lineWidth: 3, lineStyle: 0 });
      upSeries.setData(toSeries(chart.dates, chart.strategy_trend_lines.upward));
    }
    if (chart.strategy_trend_lines.downward) {
      const downSeries = priceChart.addLineSeries({ color: "#ff3b30", lineWidth: 3, lineStyle: 0 });
      downSeries.setData(toSeries(chart.dates, chart.strategy_trend_lines.downward));
    }
  }

  priceChart.timeScale().fitContent();
  state.charts[`${prefix}price`] = priceChart;

  const priceContainer = document.getElementById(`${prefix}price-chart`);
  const doFrvpRedraw = () => renderFrvpOverlay(chart, priceContainer, candleSeries);
  state.frvpRedraw[prefix] = doFrvpRedraw;
  // Double rAF: wait a full paint cycle so the freshly-created chart (and,
  // for autoSize, its ResizeObserver-driven layout) has actually settled
  // before querying priceToCoordinate -- calling it synchronously right
  // after setData() is the classic lightweight-charts gotcha where it can
  // still return null for a chart that hasn't laid out yet.
  requestAnimationFrame(() => requestAnimationFrame(doFrvpRedraw));

  // --- RSI ---
  if (state.visibleIndicators.rsi) {
    const rsiChart = makeChart(`${prefix}rsi-chart`);
    const rsiSeries = rsiChart.addLineSeries({ color: "#0b3d2e", lineWidth: 1.5 });
    rsiSeries.setData(toSeries(chart.dates, chart.rsi.values));
    const oversoldSeries = rsiChart.addLineSeries({ color: "#b3261e", lineWidth: 1, lineStyle: 2 });
    const overboughtSeries = rsiChart.addLineSeries({ color: "#b3261e", lineWidth: 1, lineStyle: 2 });
    oversoldSeries.setData(chart.dates.map(d => ({ time: d, value: chart.rsi.oversold })));
    overboughtSeries.setData(chart.dates.map(d => ({ time: d, value: chart.rsi.overbought })));
    rsiChart.timeScale().fitContent();
    state.charts[`${prefix}rsi`] = rsiChart;
  }

  // --- MACD ---
  if (state.visibleIndicators.macd) {
    const macdChart = makeChart(`${prefix}macd-chart`);
    const histSeries = macdChart.addHistogramSeries({ color: "#a9d6b8" });
    histSeries.setData(chart.dates.map((d, i) => ({
      time: d, value: chart.macd.histogram[i] ?? 0,
      color: (chart.macd.histogram[i] ?? 0) >= 0 ? "#1c7c3f" : "#b3261e",
    })).filter((_, i) => chart.macd.histogram[i] != null));
    const macdLine = macdChart.addLineSeries({ color: "#0b3d2e", lineWidth: 1 });
    const signalLine = macdChart.addLineSeries({ color: "#c98a2c", lineWidth: 1 });
    macdLine.setData(toSeries(chart.dates, chart.macd.macd));
    signalLine.setData(toSeries(chart.dates, chart.macd.signal));
    macdChart.timeScale().fitContent();
    state.charts[`${prefix}macd`] = macdChart;
  }

  // --- Volume ---
  if (state.visibleIndicators.volume) {
    const volChart = makeChart(`${prefix}volume-chart`);
    const volSeries = volChart.addHistogramSeries({ color: "#c7c7c7" });
    volSeries.setData(toSeries(chart.dates, chart.volume));
    const avgSeries = volChart.addLineSeries({ color: "#c98a2c", lineWidth: 1 });
    avgSeries.setData(toSeries(chart.dates, chart.volume_avg.values));
    volChart.timeScale().fitContent();
    state.charts[`${prefix}volume`] = volChart;
  }

  // --- ATR ---
  if (state.visibleIndicators.atr && chart.atr) {
    const atrChart = makeChart(`${prefix}atr-chart`);
    const atrSeries = atrChart.addLineSeries({ color: "#7a4fbf", lineWidth: 1.5 });
    atrSeries.setData(toSeries(chart.dates, chart.atr.values));
    atrChart.timeScale().fitContent();
    state.charts[`${prefix}atr`] = atrChart;
  }
}

// ---------------------------------------------------------------------------
// Compare tab
// ---------------------------------------------------------------------------
let compareViewBuilt = false;

function companyPaneShellHTML(prefix, label) {
  return `
    <div class="compare-pane">
      <h3 class="compare-pane-title">${label}</h3>
      <div class="search-wrap compare-picker">
        <input type="text" id="${prefix}ticker-search-input" placeholder="Search a company" autocomplete="off">
        <div id="${prefix}ticker-search-results" class="search-results hidden"></div>
      </div>
      <div id="${prefix}company-error" class="error-box hidden"></div>
      <div class="company-layout">
        <div class="chart-column">
          <div id="${prefix}price-chart" class="chart-box price-chart"></div>
          <div id="${prefix}rsi-chart" class="chart-box small-chart"></div>
          <div id="${prefix}macd-chart" class="chart-box small-chart"></div>
          <div id="${prefix}volume-chart" class="chart-box small-chart"></div>
          <div id="${prefix}atr-chart" class="chart-box small-chart"></div>
        </div>
        <aside class="info-column">
          <div id="${prefix}company-header"></div>
          <button type="button" id="${prefix}refresh-strategy-btn" class="refresh-btn">&#8635; Refresh analysis</button>
          <div id="${prefix}company-quote"></div>
          <div id="${prefix}company-strategy" class="strategy-box"></div>
          <div id="${prefix}company-potential" class="potential-box"></div>
          <div id="${prefix}company-outlook" class="outlook-box"></div>
          <div id="${prefix}company-profile"></div>
          <div id="${prefix}company-earnings"></div>
          <div id="${prefix}company-news"></div>
          <div id="${prefix}company-about"></div>
        </aside>
      </div>
      <div class="summary-panel">
        <h3>What the indicators are telling you</h3>
        <ul id="${prefix}summary-lines"></ul>
      </div>
    </div>
  `;
}

function ensureCompareViewBuilt() {
  if (compareViewBuilt) return;
  compareViewBuilt = true;

  document.getElementById("compare-layout").innerHTML =
    companyPaneShellHTML("a-", "Company A") + companyPaneShellHTML("b-", "Company B");

  attachTickerSearch(
    document.getElementById("a-ticker-search-input"),
    document.getElementById("a-ticker-search-results"),
    (symbol) => { state.compare.tickerA = symbol; updateComparePlaceholder(); refreshCompareView(); }
  );
  attachTickerSearch(
    document.getElementById("b-ticker-search-input"),
    document.getElementById("b-ticker-search-results"),
    (symbol) => { state.compare.tickerB = symbol; updateComparePlaceholder(); refreshCompareView(); }
  );

  wireRefreshButton("a-refresh-strategy-btn", "a-", () => state.compare.tickerA);
  wireRefreshButton("b-refresh-strategy-btn", "b-", () => state.compare.tickerB);
}

function updateComparePlaceholder() {
  const ready = !!(state.compare.tickerA && state.compare.tickerB);
  document.getElementById("compare-placeholder").classList.toggle("hidden", ready);
}

async function refreshCompareView() {
  const { tickerA, tickerB } = state.compare;
  if (!tickerA || !tickerB) return;

  const params = buildCompanyParams();
  const fetchOne = (ticker) => fetch(`/api/company/${ticker}?${params.toString()}`).then(async (r) => {
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error || `Server returned status ${r.status}`);
    }
    return r.json();
  });

  const [a, b] = await Promise.allSettled([fetchOne(tickerA), fetchOne(tickerB)]);

  const firstOk = a.status === "fulfilled" ? a.value : (b.status === "fulfilled" ? b.value : null);
  if (firstOk) {
    if (state.bbWindow == null) state.bbWindow = firstOk.chart.bollinger.window;
    if (state.rsiPeriod == null) state.rsiPeriod = firstOk.chart.rsi.period;
    if (state.volumeLookback == null) state.volumeLookback = firstOk.chart.volume_avg.window;
    if (!state.compareControlsBuilt) {
      buildControlsInto(COMPARE_CONTROL_IDS, firstOk.settings, handleCompareControlChange);
      state.compareControlsBuilt = true;
    }
    syncAllControlsActiveState();
  }

  renderComparePane("a-", tickerA, a, "a");
  renderComparePane("b-", tickerB, b, "b");
}

function renderComparePane(prefix, ticker, result, sideKey) {
  const errorBox = document.getElementById(`${prefix}company-error`);
  if (result.status !== "fulfilled") {
    errorBox.textContent = `Couldn't load data for ${ticker}: ${result.reason?.message || "unknown error"}`;
    errorBox.classList.remove("hidden");
    return;
  }
  errorBox.classList.add("hidden");
  const data = result.value;
  state.compareData[sideKey] = data.chart;

  renderInfoPanel(data.info, data.news, ticker, data.chart, prefix);
  renderStrategyBox(data.strategy, prefix);
  renderOutlook(data.outlook, prefix);
  renderSummary(data.summary_lines, prefix);
  renderCharts(data.chart, prefix);
}

// ---------------------------------------------------------------------------
// Portfolio
// ---------------------------------------------------------------------------
const PORTFOLIO_PERIODS = [
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
  { key: "year", label: "Year" },
  { key: "since_baseline", label: "Since start" },
];
const GAIN_COLOR = "#1c7c3f";
const LOSS_COLOR = "#b3261e";
const NO_DATA_COLOR = "#d0d0d0";

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  if (attrs) {
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  }
  return el;
}

function formatPct(v) {
  if (v == null) return "No data";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function niceAxisMax(absMax) {
  if (absMax <= 10) return Math.max(2, Math.ceil(absMax / 2) * 2);
  if (absMax <= 50) return Math.ceil(absMax / 10) * 10;
  if (absMax <= 100) return Math.ceil(absMax / 20) * 20;
  return Math.ceil(absMax / 50) * 50;
}

async function loadPortfolio() {
  try {
    const res = await fetch("/api/portfolio");
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    document.getElementById("portfolio-updated").textContent = data.updated_at
      ? `Updated ${new Date(data.updated_at).toLocaleString()}`
      : "";
    const holdingsList = data.holdings || [];
    document.getElementById("portfolio-total").textContent = holdingsList.length === 0
      ? "No holdings configured."
      : `Total value: $${data.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    state.lastPortfolioHoldings = data.holdings || [];
    renderPortfolioChart(state.lastPortfolioHoldings);
    renderPortfolioTable(state.lastPortfolioHoldings);
  } catch (err) {
    console.error("Failed to load portfolio:", err);
    document.getElementById("portfolio-total").textContent = "Couldn't load portfolio data.";
  }
}

function renderPortfolioTable(holdings) {
  const tbody = document.getElementById("portfolio-table-body");
  tbody.innerHTML = "";

  holdings.forEach(h => {
    const tr = document.createElement("tr");

    const tickerTd = document.createElement("td");
    tickerTd.className = "portfolio-ticker";
    tickerTd.textContent = h.ticker;
    tr.appendChild(tickerTd);

    const sharesTd = document.createElement("td");
    sharesTd.textContent = h.shares;
    tr.appendChild(sharesTd);

    const priceTd = document.createElement("td");
    priceTd.textContent = h.price != null ? `$${h.price.toFixed(2)}` : "N/A";
    tr.appendChild(priceTd);

    const valueTd = document.createElement("td");
    valueTd.textContent = h.value != null ? `$${h.value.toFixed(2)}` : "N/A";
    tr.appendChild(valueTd);

    PORTFOLIO_PERIODS.forEach(p => {
      const td = document.createElement("td");
      const v = h.gains ? h.gains[p.key] : null;
      td.textContent = formatPct(v);
      if (v != null) td.classList.add(v >= 0 ? "change-up" : "change-down");
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
}

function showPortfolioTooltip(holding, x, y) {
  const tooltip = document.getElementById("portfolio-tooltip");
  tooltip.innerHTML = "";

  const title = document.createElement("div");
  title.className = "chart-tooltip-title";
  title.textContent = holding.ticker;
  tooltip.appendChild(title);

  PORTFOLIO_PERIODS.forEach(p => {
    const row = document.createElement("div");
    row.className = "chart-tooltip-row";

    const label = document.createElement("span");
    label.className = "chart-tooltip-label";
    label.textContent = p.label;

    const value = document.createElement("span");
    const v = holding.gains ? holding.gains[p.key] : null;
    value.className = "chart-tooltip-value" + (v != null ? (v >= 0 ? " change-up" : " change-down") : "");
    value.textContent = formatPct(v);

    row.appendChild(label);
    row.appendChild(value);
    tooltip.appendChild(row);
  });

  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
  tooltip.classList.remove("hidden");
}

function hidePortfolioTooltip() {
  document.getElementById("portfolio-tooltip").classList.add("hidden");
}

function renderPortfolioChart(holdings) {
  const container = document.getElementById("portfolio-chart");
  container.innerHTML = "";

  const validHoldings = holdings.filter(h => h.price != null);
  if (validHoldings.length === 0) {
    container.innerHTML = `<p class="muted">No price data available right now.</p>`;
    return;
  }

  const width = container.clientWidth || 900;
  const marginLeft = 52, marginRight = 12, marginTop = 12, marginBottom = 34;
  const plotWidth = Math.max(200, width - marginLeft - marginRight);
  const plotHeight = 260;
  const totalHeight = marginTop + plotHeight + marginBottom;

  const clusterCount = validHoldings.length;
  const clusterWidth = plotWidth / clusterCount;
  const periodCount = PORTFOLIO_PERIODS.length;
  const barGap = 2;
  const clusterSidePad = clusterWidth * 0.1;
  const barsAreaWidth = clusterWidth - clusterSidePad * 2;
  const barWidth = Math.max(3, Math.min(20, (barsAreaWidth - barGap * (periodCount - 1)) / periodCount));
  const barsStartX = clusterSidePad + (barsAreaWidth - (barWidth * periodCount + barGap * (periodCount - 1))) / 2;

  let allVals = [];
  validHoldings.forEach(h => PORTFOLIO_PERIODS.forEach(p => {
    const v = h.gains ? h.gains[p.key] : null;
    if (v != null) allVals.push(v);
  }));
  const maxUp = Math.max(0, ...allVals);
  const maxDown = Math.abs(Math.min(0, ...allVals));
  const axisMax = niceAxisMax(Math.max(maxUp, maxDown, 1) * 1.15);
  const yScale = v => plotHeight / 2 - (v / axisMax) * (plotHeight / 2);

  const svg = svgEl("svg", {
    width: "100%", height: totalHeight,
    viewBox: `0 0 ${width} ${totalHeight}`,
    role: "img",
    "aria-label": "Percent gain by holding, across day, week, month, year, and since-tracking-started periods",
  });

  const plotG = svgEl("g", { transform: `translate(${marginLeft}, ${marginTop})` });
  svg.appendChild(plotG);

  const gridSteps = [-axisMax, -axisMax / 2, 0, axisMax / 2, axisMax];
  gridSteps.forEach(gv => {
    const y = yScale(gv);
    const isZero = gv === 0;
    plotG.appendChild(svgEl("line", {
      x1: 0, x2: plotWidth, y1: y.toFixed(2), y2: y.toFixed(2),
      stroke: isZero ? "#bbb" : "#eee",
      "stroke-width": 1,
    }));
    const label = svgEl("text", {
      x: -8, y: (y + 4).toFixed(2), "text-anchor": "end",
      "font-size": 11, fill: "#666",
    });
    label.textContent = `${gv > 0 ? "+" : ""}${gv}%`;
    plotG.appendChild(label);
  });

  validHoldings.forEach((h, i) => {
    const clusterX = i * clusterWidth;
    const clusterG = svgEl("g", { transform: `translate(${clusterX.toFixed(2)}, 0)`, tabindex: "0", role: "button" });
    clusterG.setAttribute(
      "aria-label",
      `${h.ticker}: day ${formatPct(h.gains.day)}, week ${formatPct(h.gains.week)}, ` +
      `month ${formatPct(h.gains.month)}, year ${formatPct(h.gains.year)}, since start ${formatPct(h.gains.since_baseline)}`
    );
    clusterG.classList.add("portfolio-cluster");

    const hoverRect = svgEl("rect", {
      x: 0, y: -4, width: clusterWidth.toFixed(2), height: (plotHeight + 8).toFixed(2),
      fill: "transparent",
    });
    hoverRect.classList.add("portfolio-cluster-hover");
    clusterG.appendChild(hoverRect);

    PORTFOLIO_PERIODS.forEach((p, pi) => {
      const v = h.gains ? h.gains[p.key] : null;
      const bx = barsStartX + pi * (barWidth + barGap);
      let rect;
      if (v == null) {
        rect = svgEl("rect", {
          x: bx.toFixed(2), y: (plotHeight / 2 - 1).toFixed(2), width: barWidth.toFixed(2), height: 2,
          fill: NO_DATA_COLOR, rx: 1,
        });
      } else {
        const y0 = yScale(0), y1 = yScale(v);
        const top = Math.min(y0, y1);
        const barHeight = Math.max(1.5, Math.abs(y1 - y0));
        rect = svgEl("rect", {
          x: bx.toFixed(2), y: top.toFixed(2), width: barWidth.toFixed(2), height: barHeight.toFixed(2),
          fill: v >= 0 ? GAIN_COLOR : LOSS_COLOR, rx: 2,
        });
      }
      clusterG.appendChild(rect);
    });

    const label = svgEl("text", {
      x: (clusterWidth / 2).toFixed(2), y: (plotHeight + 20).toFixed(2), "text-anchor": "middle",
      "font-size": 12, "font-weight": 600, fill: "#333",
    });
    label.textContent = h.ticker;
    clusterG.appendChild(label);

    const showTip = () => {
      const rawX = clusterX + clusterWidth / 2 + marginLeft;
      const x = Math.max(70, Math.min(rawX, width - 70));
      showPortfolioTooltip(h, x, marginTop + 6);
      clusterG.classList.add("portfolio-cluster-active");
    };
    const hideTip = () => {
      hidePortfolioTooltip();
      clusterG.classList.remove("portfolio-cluster-active");
    };
    clusterG.addEventListener("mouseenter", showTip);
    clusterG.addEventListener("mouseleave", hideTip);
    clusterG.addEventListener("focus", showTip);
    clusterG.addEventListener("blur", hideTip);

    plotG.appendChild(clusterG);
  });

  container.appendChild(svg);
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
wireRefreshButton("refresh-strategy-btn", "", () => state.currentTicker);

loadCompanies();
loadWatchlist();
loadMovers();
loadPortfolio();
