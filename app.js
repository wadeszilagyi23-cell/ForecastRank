const LATEST_URL = "data/latest.json";
const HISTORY_URL = "data/history.json";

const state = {
  latest: null,
  history: [],
  selectedDate: null,
  period: "7"
};

const elements = {
  notice: document.getElementById("notice"),
  resultContextLabel: document.getElementById("result-context-label"),
  locationName: document.getElementById("location-name"),
  verificationDate: document.getElementById("verification-date"),
  dateSelect: document.getElementById("date-select"),
  latestButton: document.getElementById("latest-button"),
  demoBadge: document.getElementById("demo-badge"),
  actualHigh: document.getElementById("actual-high"),
  forecastCount: document.getElementById("forecast-count"),
  winningError: document.getElementById("winning-error"),
  winnerName: document.getElementById("winner-name"),
  captureDate: document.getElementById("capture-date"),
  captureTime: document.getElementById("capture-time"),
  dailyTableTitle: document.getElementById("daily-table-title"),
  resultsBody: document.getElementById("results-body"),
  unavailableModels: document.getElementById("unavailable-models"),
  performanceRange: document.getElementById("performance-range"),
  periodDays: document.getElementById("period-days"),
  periodLeader: document.getElementById("period-leader"),
  periodLeaderModel: document.getElementById("period-leader-model"),
  periodBestMae: document.getElementById("period-best-mae"),
  periodMostWins: document.getElementById("period-most-wins"),
  periodWinLeader: document.getElementById("period-win-leader"),
  performanceBody: document.getElementById("performance-body"),
  periodButtons: Array.from(document.querySelectorAll(".period-button")),
  lastUpdated: document.getElementById("last-updated")
};

const ratingClass = {
  Excellent: "dot-excellent",
  "Very good": "dot-very-good",
  Good: "dot-good",
  Fair: "dot-fair",
  Poor: "dot-poor"
};

function toNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatTemperature(value) {
  const numeric = toNumber(value);
  return numeric === null ? "—" : `${numeric.toFixed(1)}°C`;
}

function formatSignedTemperature(value) {
  const numeric = toNumber(value);
  if (numeric === null) return "—";
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(1)}°C`;
}

function parseLocalDate(dateString) {
  if (!dateString) return null;
  const parsed = new Date(`${dateString}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDate(dateString) {
  const parsed = parseLocalDate(dateString);
  if (!parsed) return dateString || "—";
  return new Intl.DateTimeFormat("en-CA", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric"
  }).format(parsed);
}

function formatCompactDate(dateString) {
  const parsed = parseLocalDate(dateString);
  if (!parsed) return dateString || "—";
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(parsed);
}

function formatDateTime(dateTimeString) {
  if (!dateTimeString) return "—";
  const parsed = new Date(dateTimeString);
  if (Number.isNaN(parsed.getTime())) return dateTimeString;
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short"
  }).format(parsed);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showNotice(message, type = "info") {
  elements.notice.textContent = message;
  elements.notice.classList.remove("hidden", "error");
  if (type === "error") elements.notice.classList.add("error");
}

function hideNotice() {
  elements.notice.classList.add("hidden");
}

function errorDirection(error) {
  const value = toNumber(error);
  if (value === null) return "";
  if (Math.abs(value) < 0.05) return "Exact";
  return value > 0 ? "Too warm" : "Too cool";
}

function biasDirection(bias) {
  const value = toNumber(bias);
  if (value === null) return "No data";
  if (Math.abs(value) < 0.05) return "No average bias";
  return value > 0 ? "Warm bias" : "Cool bias";
}

function ratingForError(absoluteError) {
  const value = toNumber(absoluteError);
  if (value === null) return "Poor";
  if (value <= 0.5) return "Excellent";
  if (value <= 1.0) return "Very good";
  if (value <= 2.0) return "Good";
  if (value <= 3.0) return "Fair";
  return "Poor";
}

function dailyResultRow(result) {
  const tr = document.createElement("tr");

  const rank = document.createElement("td");
  rank.innerHTML = `<span class="rank-number">${result.rank ?? "—"}</span>`;

  const provider = document.createElement("td");
  provider.innerHTML = `
    <span class="provider-name">${escapeHtml(result.agency || result.provider || "Unknown")}</span>
    <span class="model-name">${escapeHtml(result.model || "")}</span>
  `;

  const forecast = document.createElement("td");
  forecast.className = "numeric";
  forecast.textContent = formatTemperature(result.forecast_high_c);

  const error = document.createElement("td");
  error.className = "numeric";
  error.innerHTML = `
    ${formatSignedTemperature(result.error_c)}
    <span class="error-direction">${errorDirection(result.error_c)}</span>
  `;

  const accuracy = document.createElement("td");
  const dotClass = ratingClass[result.rating] || "dot-poor";
  accuracy.innerHTML = `
    <div class="accuracy-cell">
      <span class="accuracy-dot ${dotClass}" aria-hidden="true"></span>
      <div class="accuracy-copy">
        <strong>${escapeHtml(result.rating || "Unavailable")}</strong>
        <span>${formatTemperature(result.absolute_error_c)} absolute error</span>
      </div>
    </div>
  `;

  tr.append(rank, provider, forecast, error, accuracy);
  return tr;
}

function renderDaily(record) {
  if (!record) return;

  const results = Array.isArray(record.results) ? [...record.results] : [];
  results.sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  const winner = results.length ? results[0] : null;
  const latestDate = state.latest?.verification_date;
  const isLatest = record.verification_date === latestDate;

  elements.resultContextLabel.textContent = isLatest
    ? "Latest verified result"
    : "Historical verified result";
  elements.locationName.textContent =
    record.location?.name || "Toronto Pearson International Airport";
  elements.verificationDate.textContent = record.verification_date
    ? formatDate(record.verification_date)
    : "Waiting for a verified result";
  elements.dailyTableTitle.textContent = record.verification_date
    ? `Day-1 Forecast Results — ${formatCompactDate(record.verification_date)}`
    : "Day-1 Forecast Results";

  elements.demoBadge.classList.toggle("hidden", !record.is_demo);
  elements.actualHigh.textContent = formatTemperature(record.actual_high_c);
  elements.forecastCount.textContent = String(results.length || "—");
  elements.winningError.textContent = winner
    ? formatTemperature(winner.absolute_error_c)
    : "—";
  elements.winnerName.textContent = winner
    ? `${winner.agency} — ${winner.model}`
    : "Waiting for results";
  elements.captureDate.textContent = record.forecast_capture_date
    ? formatDate(record.forecast_capture_date)
    : "—";
  elements.captureTime.textContent = record.forecast_captured_at
    ? formatDateTime(record.forecast_captured_at)
    : "Fixed daily capture";

  elements.resultsBody.replaceChildren();
  if (results.length) {
    results.forEach((result) => elements.resultsBody.appendChild(dailyResultRow(result)));
  } else {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td colspan="5" class="empty-cell">
        No forecast results are available for this date.
      </td>
    `;
    elements.resultsBody.appendChild(row);
  }

  const unavailable = Array.isArray(record.unavailable_models)
    ? record.unavailable_models
    : [];
  if (unavailable.length) {
    elements.unavailableModels.textContent =
      `Unavailable for this comparison: ${unavailable.join(", ")}.`;
    elements.unavailableModels.classList.remove("hidden");
  } else {
    elements.unavailableModels.classList.add("hidden");
  }

  elements.dateSelect.value = record.verification_date || "";
  elements.latestButton.disabled = isLatest;

  if (record.is_demo) {
    showNotice(
      "This screen uses clearly marked demonstration values. It will be replaced automatically by the first verified ForecastRank result."
    );
  } else if (record.status === "collecting") {
    showNotice(
      record.message ||
        "ForecastRank is collecting forecasts and waiting for an official observation."
    );
  } else {
    hideNotice();
  }
}

function validHistoryRecords(history) {
  if (!Array.isArray(history)) return [];
  return history
    .filter(
      (record) =>
        record &&
        record.verification_date &&
        Array.isArray(record.results) &&
        record.results.length
    )
    .sort((a, b) => a.verification_date.localeCompare(b.verification_date));
}

function populateDateSelect() {
  const records = [...state.history].sort((a, b) =>
    b.verification_date.localeCompare(a.verification_date)
  );

  elements.dateSelect.replaceChildren();
  records.forEach((record, index) => {
    const option = document.createElement("option");
    option.value = record.verification_date;
    option.textContent = `${formatCompactDate(record.verification_date)}${
      index === 0 ? " — Latest" : ""
    }`;
    elements.dateSelect.appendChild(option);
  });
}

function selectedPerformanceRecords() {
  if (state.period === "all") return [...state.history];
  return state.history.slice(-7);
}

function calculatePerformance(records) {
  const byProvider = new Map();

  records.forEach((record) => {
    const results = Array.isArray(record.results) ? record.results : [];
    results.forEach((result) => {
      const absoluteError = toNumber(result.absolute_error_c);
      const signedError = toNumber(result.error_c);
      if (absoluteError === null || signedError === null) return;

      const key = result.provider_id || `${result.agency}|${result.model}`;
      if (!byProvider.has(key)) {
        byProvider.set(key, {
          provider_id: key,
          agency: result.agency || "Unknown",
          model: result.model || "",
          days: 0,
          sumAbsoluteError: 0,
          sumSignedError: 0,
          wins: 0
        });
      }

      const item = byProvider.get(key);
      item.days += 1;
      item.sumAbsoluteError += absoluteError;
      item.sumSignedError += signedError;
      if (Number(result.rank) === 1) item.wins += 1;
    });
  });

  const stats = Array.from(byProvider.values()).map((item) => {
    const meanAbsoluteError = item.sumAbsoluteError / item.days;
    const averageBias = item.sumSignedError / item.days;
    return {
      ...item,
      meanAbsoluteError,
      averageBias,
      rating: ratingForError(meanAbsoluteError)
    };
  });

  stats.sort((a, b) => {
    if (Math.abs(a.meanAbsoluteError - b.meanAbsoluteError) > 0.000001) {
      return a.meanAbsoluteError - b.meanAbsoluteError;
    }
    if (Math.abs(Math.abs(a.averageBias) - Math.abs(b.averageBias)) > 0.000001) {
      return Math.abs(a.averageBias) - Math.abs(b.averageBias);
    }
    if (a.wins !== b.wins) return b.wins - a.wins;
    return `${a.agency} ${a.model}`.localeCompare(`${b.agency} ${b.model}`);
  });

  let previousMae = null;
  let previousRank = 0;
  stats.forEach((item, index) => {
    if (previousMae !== null && Math.abs(item.meanAbsoluteError - previousMae) < 0.000001) {
      item.rank = previousRank;
    } else {
      item.rank = index + 1;
      previousRank = item.rank;
      previousMae = item.meanAbsoluteError;
    }
  });

  return stats;
}

function performanceRow(item, totalDays) {
  const tr = document.createElement("tr");
  const dotClass = ratingClass[item.rating] || "dot-poor";

  tr.innerHTML = `
    <td><span class="rank-number">${item.rank}</span></td>
    <td>
      <span class="provider-name">${escapeHtml(item.agency)}</span>
      <span class="model-name">${escapeHtml(item.model)}</span>
    </td>
    <td>
      <div class="accuracy-cell">
        <span class="accuracy-dot ${dotClass}" aria-hidden="true"></span>
        <div class="accuracy-copy numeric">
          <strong>${formatTemperature(item.meanAbsoluteError)}</strong>
          <span>${escapeHtml(item.rating)}</span>
        </div>
      </div>
    </td>
    <td class="numeric">
      ${formatSignedTemperature(item.averageBias)}
      <span class="error-direction">${biasDirection(item.averageBias)}</span>
    </td>
    <td class="numeric">${item.wins}</td>
    <td class="numeric">
      ${item.days}/${totalDays}
      <span class="error-direction">${item.days === totalDays ? "Complete" : "Partial"}</span>
    </td>
  `;

  return tr;
}

function renderPerformance() {
  const records = selectedPerformanceRecords();
  const stats = calculatePerformance(records);
  const firstDate = records[0]?.verification_date;
  const lastDate = records[records.length - 1]?.verification_date;

  elements.performanceRange.textContent = records.length
    ? `${formatCompactDate(firstDate)} to ${formatCompactDate(lastDate)}`
    : "No verified history is available";
  elements.periodDays.textContent = String(records.length || "—");

  const leader = stats[0];
  if (leader) {
    elements.periodLeader.textContent = leader.agency;
    elements.periodLeaderModel.textContent = `${leader.model} — lowest mean absolute error`;
    elements.periodBestMae.textContent = formatTemperature(leader.meanAbsoluteError);

    const mostWins = Math.max(...stats.map((item) => item.wins));
    const winLeaders = stats.filter((item) => item.wins === mostWins);
    elements.periodMostWins.textContent = String(mostWins);
    elements.periodWinLeader.textContent = mostWins
      ? winLeaders.map((item) => item.model || item.agency).join(" / ")
      : "No first-place results in this period";
  } else {
    elements.periodLeader.textContent = "—";
    elements.periodLeaderModel.textContent = "Lowest mean absolute error";
    elements.periodBestMae.textContent = "—";
    elements.periodMostWins.textContent = "—";
    elements.periodWinLeader.textContent = "Tied first-place results count";
  }

  elements.performanceBody.replaceChildren();
  if (stats.length) {
    stats.forEach((item) =>
      elements.performanceBody.appendChild(performanceRow(item, records.length))
    );
  } else {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td colspan="6" class="empty-cell">
        Multi-day performance will appear after verified historical results are available.
      </td>
    `;
    elements.performanceBody.appendChild(row);
  }
}

function setPeriod(period) {
  state.period = period;
  elements.periodButtons.forEach((button) => {
    const active = button.dataset.period === period;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderPerformance();
}

async function fetchJson(url) {
  const response = await fetch(`${url}?v=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return response.json();
}

async function loadData() {
  try {
    const [latest, history] = await Promise.all([
      fetchJson(LATEST_URL),
      fetchJson(HISTORY_URL)
    ]);

    state.latest = latest;
    state.history = validHistoryRecords(history);

    if (
      latest?.verification_date &&
      !state.history.some(
        (record) => record.verification_date === latest.verification_date
      )
    ) {
      state.history.push(latest);
      state.history.sort((a, b) =>
        a.verification_date.localeCompare(b.verification_date)
      );
    }

    if (!state.history.length && latest) {
      state.history = [latest];
    }

    state.selectedDate = latest?.verification_date || state.history.at(-1)?.verification_date;

    populateDateSelect();
    const selectedRecord =
      state.history.find((record) => record.verification_date === state.selectedDate) ||
      latest;
    renderDaily(selectedRecord);
    renderPerformance();

    elements.lastUpdated.textContent = latest?.published_at
      ? `Data update: ${formatDateTime(latest.published_at)}`
      : "Data update: —";
  } catch (error) {
    console.error(error);
    showNotice(
      "ForecastRank could not load the latest or historical data. Confirm that data/latest.json and data/history.json are available.",
      "error"
    );
    elements.resultsBody.innerHTML = `
      <tr><td colspan="5" class="empty-cell">Unable to load ForecastRank data.</td></tr>
    `;
    elements.performanceBody.innerHTML = `
      <tr><td colspan="6" class="empty-cell">Unable to calculate performance.</td></tr>
    `;
  }
}

elements.dateSelect.addEventListener("change", () => {
  state.selectedDate = elements.dateSelect.value;
  const record = state.history.find(
    (item) => item.verification_date === state.selectedDate
  );
  renderDaily(record);
});

elements.latestButton.addEventListener("click", () => {
  state.selectedDate = state.latest?.verification_date || state.history.at(-1)?.verification_date;
  const record = state.history.find(
    (item) => item.verification_date === state.selectedDate
  );
  renderDaily(record || state.latest);
});

elements.periodButtons.forEach((button) => {
  button.addEventListener("click", () => setPeriod(button.dataset.period));
});

loadData();
