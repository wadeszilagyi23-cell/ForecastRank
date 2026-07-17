const DATA_URL = "data/latest.json";

const elements = {
  notice: document.getElementById("notice"),
  locationName: document.getElementById("location-name"),
  verificationDate: document.getElementById("verification-date"),
  demoBadge: document.getElementById("demo-badge"),
  actualHigh: document.getElementById("actual-high"),
  forecastCount: document.getElementById("forecast-count"),
  winningError: document.getElementById("winning-error"),
  winnerName: document.getElementById("winner-name"),
  captureDate: document.getElementById("capture-date"),
  captureTime: document.getElementById("capture-time"),
  resultsBody: document.getElementById("results-body"),
  unavailableModels: document.getElementById("unavailable-models"),
  lastUpdated: document.getElementById("last-updated")
};

const ratingClass = {
  "Excellent": "dot-excellent",
  "Very good": "dot-very-good",
  "Good": "dot-good",
  "Fair": "dot-fair",
  "Poor": "dot-poor"
};

function formatTemperature(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}°C` : "—";
}

function formatSignedTemperature(value) {
  if (!Number.isFinite(Number(value))) return "—";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(1)}°C`;
}

function formatDate(dateString) {
  if (!dateString) return "—";
  const parsed = new Date(`${dateString}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateString;
  return new Intl.DateTimeFormat("en-CA", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric"
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

function showNotice(message, type = "info") {
  elements.notice.textContent = message;
  elements.notice.classList.remove("hidden", "error");
  if (type === "error") elements.notice.classList.add("error");
}

function hideNotice() {
  elements.notice.classList.add("hidden");
}

function errorDirection(error) {
  const value = Number(error);
  if (!Number.isFinite(value)) return "";
  if (Math.abs(value) < 0.05) return "Exact";
  return value > 0 ? "Too warm" : "Too cool";
}

function resultRow(result) {
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function render(data) {
  const results = Array.isArray(data.results) ? data.results : [];
  const winner = results.length ? results[0] : null;

  elements.locationName.textContent =
    data.location?.name || "Toronto Pearson International Airport";
  elements.verificationDate.textContent = data.verification_date
    ? formatDate(data.verification_date)
    : "Waiting for the first verified result";

  elements.demoBadge.classList.toggle("hidden", !data.is_demo);
  elements.actualHigh.textContent = formatTemperature(data.actual_high_c);
  elements.forecastCount.textContent = String(results.length || "—");
  elements.winningError.textContent = winner
    ? formatTemperature(winner.absolute_error_c)
    : "—";
  elements.winnerName.textContent = winner
    ? `${winner.agency} — ${winner.model}`
    : "Waiting for results";

  elements.captureDate.textContent = data.forecast_capture_date
    ? formatDate(data.forecast_capture_date)
    : "—";
  elements.captureTime.textContent = data.forecast_captured_at
    ? formatDateTime(data.forecast_captured_at)
    : "Fixed daily capture";

  elements.resultsBody.replaceChildren();

  if (results.length) {
    results.forEach((result) => elements.resultsBody.appendChild(resultRow(result)));
  } else {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td colspan="5" class="empty-cell">
        ForecastRank is collecting Day-1 forecasts. The first verified leaderboard
        will appear after a stored forecast date has passed and the official maximum
        temperature is available.
      </td>
    `;
    elements.resultsBody.appendChild(row);
  }

  const unavailable = Array.isArray(data.unavailable_models)
    ? data.unavailable_models
    : [];

  if (unavailable.length) {
    elements.unavailableModels.textContent =
      `Unavailable for this comparison: ${unavailable.join(", ")}.`;
    elements.unavailableModels.classList.remove("hidden");
  } else {
    elements.unavailableModels.classList.add("hidden");
  }

  elements.lastUpdated.textContent = data.published_at
    ? `Data update: ${formatDateTime(data.published_at)}`
    : "Data update: —";

  if (data.is_demo) {
    showNotice(
      "This initial screen uses clearly marked demonstration values. It will be replaced automatically by the first verified ForecastRank result."
    );
  } else if (data.status === "collecting") {
    showNotice(
      data.message ||
        "ForecastRank is collecting forecasts and waiting for the first official observation."
    );
  } else {
    hideNotice();
  }
}

async function loadData() {
  try {
    const response = await fetch(`${DATA_URL}?v=${Date.now()}`, {
      cache: "no-store"
    });
    if (!response.ok) {
      throw new Error(`Data request returned ${response.status}`);
    }
    const data = await response.json();
    render(data);
  } catch (error) {
    console.error(error);
    showNotice(
      "ForecastRank could not load its data file. Confirm that data/latest.json exists and that the website is being viewed through a web server.",
      "error"
    );
    elements.resultsBody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-cell">Unable to load ForecastRank data.</td>
      </tr>
    `;
  }
}

loadData();
