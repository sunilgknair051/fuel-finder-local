"use strict";

const state = { meta: null, last: null };

const byId = (id) => document.getElementById(id);
const form = byId("search-form");
const statusBox = byId("status");
const radiusSelect = byId("radius");
const customRadiusWrap = byId("custom-radius-wrap");
const customRadius = byId("custom-radius");
const unitSelect = byId("distance-unit");
const fuelSelect = byId("fuel");
const currencySelect = byId("currency");
const sortSelect = byId("sort");
const openOnly = byId("open-only");
const refreshButton = byId("refresh");

function option(value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  return item;
}

function setStatus(message, kind = "") {
  statusBox.textContent = message;
  statusBox.className = "status" + (kind ? " " + kind : "");
}

async function loadMeta() {
  try {
    const response = await fetch("/api/meta", { credentials: "same-origin" });
    if (!response.ok) throw new Error("Metadata unavailable");
    state.meta = await response.json();
    state.meta.radii.forEach((radius) => radiusSelect.append(option(String(radius), String(radius))));
    radiusSelect.append(option("custom", "Custom…"));
    radiusSelect.value = "5";
    state.meta.distance_units.forEach((unit) => unitSelect.append(option(unit.value, unit.label)));
    state.meta.fuels.forEach((fuel) => fuelSelect.append(option(fuel.value, fuel.label)));
    state.meta.currencies.forEach((currency) => currencySelect.append(option(currency.code, currency.code)));
    setStatus("Ready. Enter a German postcode to search.");
  } catch {
    setStatus("Local configuration could not be loaded. Restart the application.", "error");
  }
}

function selectedRadius() {
  return radiusSelect.value === "custom" ? Number(customRadius.value) : Number(radiusSelect.value);
}

function requestBody(refresh) {
  return {
    postal_code: byId("postal-code").value,
    radius: selectedRadius(),
    distance_unit: unitSelect.value,
    fuel: fuelSelect.value,
    currency: currencySelect.value,
    open_only: openOnly.checked,
    sort: sortSelect.value,
    refresh
  };
}

function validForm() {
  const postcode = byId("postal-code").value;
  if (!/^[0-9]{5}$/.test(postcode)) {
    setStatus("Enter a German postal code using exactly five digits.", "error");
    byId("postal-code").focus();
    return false;
  }
  const radius = selectedRadius();
  const maximum = unitSelect.value === "mi" ? 25 / 1.609344 : 25;
  if (!Number.isFinite(radius) || radius < 0.5 || radius > maximum) {
    setStatus("Choose a radius from 0.5 up to " + maximum.toFixed(3) + " " + unitSelect.value + ".", "error");
    return false;
  }
  return true;
}

async function search(refresh = false) {
  if (!validForm()) return;
  setStatus(refresh ? "Requesting refreshed prices…" : "Searching nearby stations…", "loading");
  const buttons = form.querySelectorAll("button");
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody(refresh))
    });
    const payload = await response.json();
    if (!response.ok) {
      const suffix = payload.retry_after_seconds ? " Try again in " + payload.retry_after_seconds + " seconds." : "";
      throw new Error((payload.message || "Search failed.") + suffix);
    }
    state.last = payload;
    refreshButton.disabled = false;
    renderLocal();
  } catch (error) {
    setStatus(error instanceof Error ? error.message : "Search failed safely.", "error");
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
    refreshButton.disabled = state.last === null;
  }
}

function rateFor(code) {
  const item = state.meta.currencies.find((entry) => entry.code === code);
  return item ? Number(item.rate) : 1;
}

function priceValue(station, fuel) {
  const fuels = fuel === "all" ? ["e5", "e10", "diesel"] : [fuel];
  const values = fuels
    .map((key) => station.prices[key])
    .filter((item) => item !== null)
    .map((item) => Number(item.eur));
  return values.length ? Math.min(...values) : null;
}

function locallyProcessed() {
  if (!state.last) return [];
  const fuel = fuelSelect.value;
  const unit = unitSelect.value;
  const currency = currencySelect.value;
  const rate = rateFor(currency);
  const stations = state.last.available_stations.map((station) => {
    const copy = {
      ...station,
      distance: unit === "mi" ? station.distance_km / 1.609344 : station.distance_km,
      distance_unit: unit,
      prices: {}
    };
    ["e5", "e10", "diesel"].forEach((key) => {
      const source = station.prices[key];
      copy.prices[key] = source === null ? null : {
        eur: source.eur,
        converted: (Number(source.eur) * rate).toFixed(3),
        currency
      };
    });
    return copy;
  }).filter((station) => priceValue(station, fuel) !== null)
    .filter((station) => !openOnly.checked || station.is_open === true);

  if (sortSelect.value === "price") {
    stations.sort((a, b) => priceValue(a, fuel) - priceValue(b, fuel) || a.distance - b.distance);
  } else if (sortSelect.value === "distance") {
    stations.sort((a, b) => a.distance - b.distance || a.name.localeCompare(b.name));
  } else {
    stations.sort((a, b) => a.name.localeCompare(b.name) || a.distance - b.distance);
  }
  return stations;
}

function statusText(isOpen) {
  if (isOpen === true) return ["Open", "status-open"];
  if (isOpen === false) return ["Closed", "status-closed"];
  return ["Status unknown", "status-unknown"];
}

function appendPrice(cell, item) {
  if (item === null) {
    const unavailable = document.createElement("span");
    unavailable.className = "unavailable";
    unavailable.textContent = "Unavailable";
    cell.append(unavailable);
    return;
  }
  const main = document.createElement("span");
  main.className = "price";
  main.textContent = item.converted + " " + item.currency + "/L";
  cell.append(main);
  if (item.currency !== "EUR") {
    const original = document.createElement("span");
    original.className = "eur-original";
    original.textContent = item.eur + " EUR/L";
    cell.append(original);
  }
}

function stationRow(station) {
  const row = document.createElement("tr");
  const stationCell = document.createElement("td");
  const name = document.createElement("span");
  name.className = "station-name";
  name.textContent = station.name;
  const meta = document.createElement("span");
  meta.className = "station-meta";
  meta.textContent = (station.brand ? station.brand + " · " : "") + station.address;
  stationCell.append(name, meta);

  const statusCell = document.createElement("td");
  const [label, className] = statusText(station.is_open);
  const status = document.createElement("span");
  status.className = "status-text " + className;
  status.textContent = label;
  statusCell.append(status);

  const distance = document.createElement("td");
  distance.textContent = station.distance.toFixed(2) + " " + station.distance_unit;

  row.append(stationCell, statusCell, distance);
  ["e5", "e10", "diesel"].forEach((fuel) => {
    const cell = document.createElement("td");
    appendPrice(cell, station.prices[fuel]);
    row.append(cell);
  });
  return row;
}

function cheapestPrice(station) {
  const fuel = fuelSelect.value;
  const keys = fuel === "all" ? ["e5", "e10", "diesel"] : [fuel];
  return keys
    .map((key) => [key, station.prices[key]])
    .filter(([, item]) => item !== null)
    .sort((a, b) => Number(a[1].eur) - Number(b[1].eur))[0];
}

function renderLocal() {
  const stations = locallyProcessed();
  const body = byId("results-body");
  body.replaceChildren(...stations.map(stationRow));
  byId("results-section").hidden = stations.length === 0;
  byId("empty-state").hidden = stations.length !== 0;
  byId("summary-section").hidden = stations.length === 0;

  if (stations.length) {
    const cheapest = [...stations].sort((a, b) => priceValue(a, fuelSelect.value) - priceValue(b, fuelSelect.value))[0];
    const [fuel, price] = cheapestPrice(cheapest);
    byId("summary-heading").textContent = cheapest.name;
    byId("summary-address").textContent = cheapest.address + " · " + cheapest.distance.toFixed(2) + " " + cheapest.distance_unit;
    byId("summary-price").textContent = price.converted + " " + price.currency + "/L";
    byId("summary-detail").textContent =
      state.meta.fuels.find((item) => item.value === fuel).label +
      (price.currency === "EUR" ? "" : " · " + price.eur + " EUR/L");
  }

  const sourceLabels = {
    new_request: "New API request",
    fresh_cache: "Fresh cache",
    stale_cache: "Stale cache"
  };
  const badge = byId("source-badge");
  badge.textContent = sourceLabels[state.last.source] || "Local result";
  badge.className = "badge" + (state.last.source === "stale_cache" ? " stale" : "");
  byId("retrieved-at").textContent = "Retrieved " + new Date(state.last.retrieved_at).toLocaleString();
  const nonEuro = currencySelect.value !== "EUR";
  byId("conversion-note").textContent = nonEuro
    ? "Indicative conversion using the locally configured " + currencySelect.value + " rate as of " + state.meta.exchange_rate_as_of + ". Original EUR/L prices remain visible."
    : "Prices are shown in EUR per litre.";
  setStatus(stations.length + (stations.length === 1 ? " matching station." : " matching stations."));
}

radiusSelect.addEventListener("change", () => {
  customRadiusWrap.hidden = radiusSelect.value !== "custom";
});
unitSelect.addEventListener("change", () => {
  const maximum = unitSelect.value === "mi" ? 25 / 1.609344 : 25;
  customRadius.max = String(maximum);
  byId("radius-hint").textContent = "0.5–" + maximum.toFixed(unitSelect.value === "mi" ? 3 : 0) + " " + unitSelect.value;
  if (state.last) renderLocal();
});
[fuelSelect, currencySelect, sortSelect, openOnly].forEach((control) => {
  control.addEventListener("change", () => { if (state.last) renderLocal(); });
});
form.addEventListener("submit", (event) => {
  event.preventDefault();
  search(false);
});
refreshButton.addEventListener("click", () => search(true));

loadMeta();
