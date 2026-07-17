# ForecastRank

## Day-1 Maximum Temperature Accuracy

ForecastRank is a free static website that compares numerical weather-model
forecasts for Toronto Pearson International Airport with the official observed
daily maximum temperature.

The website is designed to run on:

- GitHub Pages for free public hosting
- GitHub Actions for one automatic update each day
- Open-Meteo for forecast-model data
- Environment and Climate Change Canada for observed daily maximum temperature

No API keys are required for the initial non-commercial version.

---

## What “Day-1” means in this project

ForecastRank defines Day-1 as:

> The maximum-temperature forecast for the following local calendar day,
> captured once at a fixed daily time.

The included workflow runs at **12:17 p.m. Toronto time**. During a run it:

1. Saves each model’s forecast maximum for tomorrow.
2. Looks for official ECCC observations for previously forecast dates.
3. Calculates signed and absolute errors.
4. Updates the leaderboard and historical data.
5. Commits the changed data files to the GitHub repository.

The signed error is:

```text
Forecast maximum − observed maximum
```

- Positive error: forecast was too warm.
- Negative error: forecast was too cool.
- Ranking uses the absolute error.

---

## Included forecast sources

The first version requests model data delivered through Open-Meteo:

- Open-Meteo Best Match
- Environment and Climate Change Canada GEM
- NOAA GFS
- ECMWF IFS
- Deutscher Wetterdienst ICON
- Météo-France ARPEGE
- Japan Meteorological Agency GSM

These are numerical model outputs at the Toronto Pearson coordinates. They
should not be described as identical to the human-edited public forecast
issued by an agency or a private weather company.

## Verification station

- Station: Toronto Pearson International Airport
- ECCC climate identifier: `6158731`
- Station code: `YYZ`
- Coordinates used for model forecasts: 43.677°N, 79.631°W

---

# Installation on GitHub

## 1. Create the repository

Create a new **public** GitHub repository named:

```text
ForecastRank
```

Do not add a README or other starter files when creating it, because this
package already contains them.

## 2. Upload the project

Upload the contents of this package to the root of the repository.

Important: upload the contents, not an extra outer folder. The repository
should show:

```text
.github/
data/
scripts/
app.js
index.html
styles.css
README.md
```

## 3. Allow the workflow to write data

In the repository:

1. Open **Settings**.
2. Select **Actions** and then **General**.
3. Find **Workflow permissions**.
4. Select **Read and write permissions**.
5. Save the change.

The workflow file also declares `contents: write`, but the repository setting
must permit write access.

## 4. Run the first test manually

1. Open the **Actions** tab.
2. Select **Update ForecastRank**.
3. Select **Run workflow**.
4. Run it from the main branch.

Open the completed run and inspect the log. A successful run should capture
forecasts for the following day and commit changes inside the `data` folder.

## 5. Turn on GitHub Pages

1. Open **Settings**.
2. Select **Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Select the main branch and the `/ (root)` folder.
5. Save.

GitHub will display the public website address after deployment.

---

# When the first real leaderboard appears

The included `data/latest.json` contains clearly labelled demonstration data so
the layout can be viewed immediately.

A real result needs this sequence:

1. ForecastRank captures forecasts for a future date.
2. That date passes.
3. ECCC publishes the official daily maximum.
4. A later workflow run verifies and publishes the result.

The updater checks recent unverified dates on every run, so a delayed ECCC
observation can be added automatically later.

---

# Main data files

## `data/forecast_archive.json`

Stores the forecasts exactly as captured for each target date.

## `data/latest.json`

Contains the newest completed leaderboard displayed on the home page.

## `data/history.json`

Stores every completed daily verification in structured JSON.

## `data/history.csv`

Stores one row per model per verified date for later analysis, charting and
mapping.

---

# Accuracy colours

| Absolute error | Rating | Colour |
|---:|---|---|
| 0.0–0.5°C | Excellent | Green |
| 0.6–1.0°C | Very good | Light green |
| 1.1–2.0°C | Good | Yellow |
| 2.1–3.0°C | Fair | Orange |
| More than 3.0°C | Poor | Red |

The website always includes text with each colour, so the result is not
communicated through colour alone.

---

# Local preview

Opening `index.html` directly can prevent the browser from loading the JSON
file. View it through a local web server instead.

With Python installed, open a terminal in the project folder and run:

```bash
python -m http.server 8000
```

Then visit:

```text
http://localhost:8000
```

---

# Future versions

The historical files already support later additions such as:

- 7-day and 30-day mean absolute error
- warm and cool bias
- number of daily wins
- date selector
- time-series graphs
- multiple Canadian cities
- Leaflet forecast-accuracy map

---

# Data attribution

Forecast model data: Open-Meteo and the originating national meteorological
services.

Observed daily maximum temperature: Environment and Climate Change Canada,
Meteorological Service of Canada.

Review the source licences and attribution requirements before using
ForecastRank commercially.
