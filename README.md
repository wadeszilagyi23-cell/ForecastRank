# ForecastRank

## Day-1 Maximum Temperature Accuracy — Version 1.1

ForecastRank is a free automated website that compares numerical weather-model forecasts for Toronto Pearson International Airport with the official observed daily maximum temperature.

## Version 1.1 additions

Version 1.1 keeps the original daily leaderboard and adds:

- A historical date selector for every verified day
- A rolling last-7-days performance ranking
- An all-verified-days performance option
- Mean absolute error for each model
- Average warm or cool forecast bias
- Daily win counts, including tied first-place finishes
- Days-available counts so incomplete model records remain transparent
- A responsive navigation bar and Version 1.1 identification

All Version 1.1 statistics are calculated in the browser from the existing `data/history.json` file. The daily Python updater and archived forecast data do not need to be changed.

---

## What “Day-1” means

ForecastRank defines Day-1 as:

> The maximum-temperature forecast for the following local calendar day, captured once at a fixed daily time.

The scheduled workflow saves tomorrow’s model forecasts, retrieves official observations for completed dates, calculates signed and absolute errors, updates the history files and deploys the website.

The signed error is:

```text
Forecast maximum − observed maximum
```

- Positive error: the forecast was too warm.
- Negative error: the forecast was too cool.
- Daily ranking uses absolute error.
- Multi-day ranking uses mean absolute error.

## Multi-day statistics

### Mean absolute error

The average size of a model’s forecast errors, without regard to whether they were warm or cool. Lower is better.

### Average bias

The average signed forecast error.

- Positive bias means the model tended to forecast too warm.
- Negative bias means the model tended to forecast too cool.
- A value near zero means little average directional bias.

### Daily wins

A win is recorded whenever a model has rank 1 for a verified date. If models tie for first, each receives a win.

### Days available

The model’s number of usable daily results divided by the number of days in the selected period.

---

## Data sources

Forecast model data are delivered through Open-Meteo from:

- Open-Meteo Best Match
- Environment and Climate Change Canada GEM
- NOAA GFS
- ECMWF IFS
- Deutscher Wetterdienst ICON
- Météo-France ARPEGE
- Japan Meteorological Agency GSM

Observed daily maximum temperature comes from Environment and Climate Change Canada.

These are numerical model outputs at the Toronto Pearson coordinates. They are not necessarily identical to the human-edited public forecasts issued by the agencies.

## Verification station

- Station: Toronto Pearson International Airport
- ECCC climate identifier: `6158731`
- Station code: `YYZ`
- Forecast coordinates: 43.677°N, 79.631°W

---

## Version 1.1 upgrade

The Version 1.1 upgrade replaces only these website files:

```text
index.html
app.js
styles.css
README.md
```

Do not replace or delete:

```text
data/
scripts/
.github/
```

Those folders contain the live history, forecast archive, updater and deployment workflow.

After the four replacement files are committed to the main branch, the existing push-triggered GitHub Actions workflow should deploy the upgraded website automatically.

---

## Main data files

- `data/forecast_archive.json` — forecasts exactly as captured for each target date
- `data/latest.json` — newest completed daily leaderboard
- `data/history.json` — all completed daily verifications used by Version 1.1 statistics
- `data/history.csv` — one row per model per verified date

## Accuracy colours

| Absolute error | Rating | Colour |
|---:|---|---|
| 0.0–0.5°C | Excellent | Green |
| 0.6–1.0°C | Very good | Light green |
| 1.1–2.0°C | Good | Yellow |
| 2.1–3.0°C | Fair | Orange |
| More than 3.0°C | Poor | Red |

Colour is always paired with text.

## Local preview

Run a local web server in the project folder:

```bash
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

## Future versions

Possible later additions include:

- 30-day and seasonal rankings
- time-series performance graphs
- minimum temperature and precipitation verification
- multiple Canadian cities
- a Leaflet forecast-accuracy map
