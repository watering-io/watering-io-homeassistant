const CARD_VERSION = "0.1.20";
const STATIC_BASE = "/watering_io_static";
const UNKNOWN_STATES = new Set(["unknown", "unavailable", "", null, undefined]);
const CROPS = [
  { value: "generic", label: "Generic plant" },
  { value: "tomato", label: "Tomato" },
  { value: "tomato_cherry", label: "Cherry tomato" },
  { value: "tomato_yellow", label: "Yellow tomato" },
  { value: "tomato_beefsteak", label: "Beefsteak tomato" },
  { value: "tomato_roma", label: "Roma tomato" },
  { value: "tomato_black", label: "Dark heirloom tomato" },
  { value: "basil", label: "Basil" },
  { value: "lettuce", label: "Lettuce" },
  { value: "chili", label: "Chili" },
  { value: "pepper_red_bell", label: "Red bell pepper" },
  { value: "pepper_yellow_bell", label: "Yellow bell pepper" },
  { value: "pepper_jalapeno", label: "Jalapeno pepper" },
  { value: "pepper_mixed_chili", label: "Mixed chili peppers" },
  { value: "strawberry", label: "Strawberry" },
  { value: "cucumber", label: "Cucumber" },
  { value: "eggplant", label: "Eggplant" },
  { value: "zucchini", label: "Zucchini" },
  { value: "herbs", label: "Herbs" },
  { value: "parsley", label: "Parsley" },
  { value: "mint", label: "Mint" },
  { value: "arugula", label: "Arugula" },
  { value: "spinach", label: "Spinach" },
  { value: "radish", label: "Radish" },
];
const CROP_VALUES = new Set(CROPS.map((crop) => crop.value));
const FORM_LABELS = {
  name: "Name",
  crop: "Crop picture",
  moisture_entity: "Moisture entity",
  target_entity: "Target entity",
  online_entity: "Online entity",
  watering_entity: "Watering entity",
  state_entity: "State entity",
  water_history_entity: "Water history entity",
};

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function entityState(hass, entityId) {
  if (!hass || !entityId) {
    return undefined;
  }
  return hass.states[entityId];
}

function isUnknown(stateObj) {
  return !stateObj || UNKNOWN_STATES.has(stateObj.state);
}

function parsePercent(stateObj) {
  if (isUnknown(stateObj)) {
    return null;
  }
  const value = Number(stateObj.state);
  if (!Number.isFinite(value)) {
    return null;
  }
  return clamp(value, 0, 100);
}

function formatPercent(value) {
  if (value === null) {
    return "--";
  }
  return `${Math.round(value)}%`;
}

function cssPercent(value) {
  return `${clamp(value, 0, 100).toFixed(2)}%`;
}

function formatWaterMl(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "--";
  }
  return `${Math.round(number)} mL`;
}

function moistureGradient(target) {
  if (target === null) {
    return "linear-gradient(90deg, #c7473f 0%, #dfad4d 22%, #58ad63 50%, #dfad4d 78%, #c7473f 100%)";
  }

  const greenStart = clamp(target - 4, 0, 100);
  const greenEnd = clamp(target + 4, 0, 100);
  const leftAmber = greenStart * 0.44;
  const rightAmber = greenEnd + (100 - greenEnd) * 0.56;
  return `linear-gradient(90deg, #c7473f 0%, #dfad4d ${cssPercent(leftAmber)}, #58ad63 ${cssPercent(greenStart)}, #58ad63 ${cssPercent(greenEnd)}, #dfad4d ${cssPercent(rightAmber)}, #c7473f 100%)`;
}

function cropUrl(crop) {
  const safeCrop = CROP_VALUES.has(crop) ? crop : "generic";
  return `${STATIC_BASE}/crops/${safeCrop}.webp?v=${CARD_VERSION}`;
}

function stateText(stateObj, fallback = "Unknown") {
  if (isUnknown(stateObj)) {
    return fallback;
  }
  return stateObj.state;
}

function chipClass(base, stateObj, activeState = "on") {
  if (isUnknown(stateObj)) {
    return `${base} muted`;
  }
  return stateObj.state === activeState ? `${base} active` : base;
}

function planterIdFromConfig(config) {
  if (!config?.target_entity?.startsWith("sensor.")) {
    return undefined;
  }

  const sensorSlug = config.target_entity.slice("sensor.".length);
  const planterMatch = sensorSlug.match(/(?:^|_)planter_(\d+)(?:_|$)/);
  return planterMatch?.[1];
}

function candidateDailyWaterEntity(entityId) {
  if (!entityId?.startsWith("sensor.")) {
    return undefined;
  }
  if (entityId.endsWith("_target_moisture")) {
    return entityId.replace(/_target_moisture$/, "_daily_water");
  }
  if (entityId.endsWith("_moisture")) {
    return entityId.replace(/_moisture$/, "_daily_water");
  }
  return undefined;
}

function waterHistoryEntityFromConfig(hass, config) {
  if (config?.water_history_entity) {
    return config.water_history_entity;
  }

  const planterId = planterIdFromConfig(config);
  const candidates = [
    candidateDailyWaterEntity(config?.target_entity),
    candidateDailyWaterEntity(config?.moisture_entity),
    planterId ? `sensor.planter_${planterId}_daily_water` : undefined,
  ].filter(Boolean);

  return candidates.find((entityId) => hass?.states?.[entityId]) || candidates[0];
}

function parseWaterHistory(stateObj) {
  if (isUnknown(stateObj)) {
    return [];
  }

  const raw = Array.isArray(stateObj.attributes?.daily_water)
    ? stateObj.attributes.daily_water
    : Array.isArray(stateObj.attributes?.history)
      ? stateObj.attributes.history
      : [];

  return raw
    .map((item) => {
      const date = String(item?.date || "").trim();
      const waterMl = Number(item?.water_ml);
      if (!date || !Number.isFinite(waterMl)) {
        return null;
      }
      return { date, waterMl };
    })
    .filter(Boolean)
    .slice(-7);
}

function formatShortDate(date) {
  const parts = String(date || "").split("-");
  if (parts.length !== 3) {
    return date || "";
  }
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const month = monthNames[Number(parts[1]) - 1] || parts[1];
  return `${month} ${Number(parts[2])}`;
}

function formatDayLabel(date) {
  const parts = String(date || "").split("-");
  if (parts.length !== 3) {
    return "";
  }
  const day = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])).toLocaleDateString(undefined, {
    weekday: "short",
  });
  return day.slice(0, 1);
}

function waterHistoryMarkup(history) {
  if (!history.length) {
    return "";
  }

  const maxWater = Math.max(...history.map((item) => item.waterMl), 1);
  const today = history[history.length - 1];
  const bars = history
    .map((item) => {
      const percent = item.waterMl <= 0 ? 2 : clamp((item.waterMl / maxWater) * 100, 8, 100);
      const tooltip = `${formatShortDate(item.date)}: ${formatWaterMl(item.waterMl)}`;
      return `
        <div class="water-bar" tabindex="0" role="img" aria-label="${escapeHtml(tooltip)}" data-tooltip="${escapeHtml(tooltip)}">
          <div class="water-bar-fill" style="height: ${percent.toFixed(2)}%"></div>
        </div>
      `;
    })
    .join("");
  const labels = history.map((item) => `<span>${escapeHtml(formatDayLabel(item.date))}</span>`).join("");

  return `
    <div class="water-history">
      <div class="water-history-head">
        <span>Water</span>
        <strong>${escapeHtml(formatWaterMl(today.waterMl))}</strong>
      </div>
      <div class="water-bars">${bars}</div>
      <div class="water-days">${labels}</div>
    </div>
  `;
}

class WateringIoPlanterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lastRenderKey = null;
    this._editingTarget = false;
    this._targetDraft = null;
    this._targetError = "";
    this._targetSubmitting = false;
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "name", selector: { text: {} } },
        {
          name: "crop",
          selector: {
            select: {
              mode: "dropdown",
              options: CROPS,
            },
          },
        },
        { name: "moisture_entity", required: true, selector: { entity: { domain: "sensor" } } },
        { name: "target_entity", required: true, selector: { entity: { domain: "sensor" } } },
        { name: "online_entity", selector: { entity: { domain: "binary_sensor" } } },
        { name: "watering_entity", selector: { entity: { domain: "binary_sensor" } } },
        { name: "state_entity", selector: { entity: { domain: "sensor" } } },
        { name: "water_history_entity", selector: { entity: { domain: "sensor" } } },
      ],
      computeLabel: (schema) => FORM_LABELS[schema.name] || schema.name,
    };
  }

  static getStubConfig() {
    return {
      name: "Planter",
      crop: "generic",
    };
  }

  setConfig(config) {
    this.config = {
      crop: "generic",
      ...config,
    };
    this._lastRenderKey = null;
    this._render(true);
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return {
      rows: 5,
      columns: 6,
      min_rows: 4,
      min_columns: 3,
    };
  }

  _render(force = false) {
    if (!this.shadowRoot || !this.config) {
      return;
    }

    const moistureState = entityState(this._hass, this.config.moisture_entity);
    const targetState = entityState(this._hass, this.config.target_entity);
    const onlineState = entityState(this._hass, this.config.online_entity);
    const wateringState = entityState(this._hass, this.config.watering_entity);
    const planterState = entityState(this._hass, this.config.state_entity);
    const waterHistoryEntity = waterHistoryEntityFromConfig(this._hass, this.config);
    const waterHistoryState = entityState(this._hass, waterHistoryEntity);
    const planterId = planterIdFromConfig(this.config);
    const renderKey = JSON.stringify([
      this.config.name || "",
      this.config.crop || "",
      this.config.moisture_entity || "",
      moistureState?.state || "",
      moistureState?.attributes?.friendly_name || "",
      this.config.target_entity || "",
      targetState?.state || "",
      planterId || "",
      this.config.online_entity || "",
      onlineState?.state || "",
      this.config.watering_entity || "",
      wateringState?.state || "",
      this.config.state_entity || "",
      planterState?.state || "",
      this.config.water_history_entity || "",
      waterHistoryEntity || "",
      waterHistoryState?.state || "",
      JSON.stringify(waterHistoryState?.attributes?.daily_water || waterHistoryState?.attributes?.history || []),
      this._editingTarget ? "editing" : "",
      this._targetDraft ?? "",
      this._targetError || "",
      this._targetSubmitting ? "submitting" : "",
    ]);
    if (!force && renderKey === this._lastRenderKey) {
      return;
    }
    this._lastRenderKey = renderKey;

    const moisture = parsePercent(moistureState);
    const target = parsePercent(targetState);
    const moistureWidth = moisture === null ? 0 : moisture;
    const moistureLeft = moisture === null ? 0 : moisture;
    const barGradient = moistureGradient(target);
    const title =
      this.config.name ||
      moistureState?.attributes?.friendly_name?.replace(/\s+moisture$/i, "") ||
      "Planter";
    const onlineLabel = onlineState?.state === "on" ? "Online" : "Offline";
    const wateringLabel = wateringState?.state === "on" ? "Watering" : "Idle";
    const stateLabel = stateText(planterState, "No state");
    const waterHistory = parseWaterHistory(waterHistoryState);
    const missingRequired = !this.config.moisture_entity || !this.config.target_entity;
    const targetEditable = Boolean(planterId);
    const targetDraft = this._targetDraft ?? target ?? 50;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        ha-card {
          overflow: hidden;
          border-radius: var(--ha-card-border-radius, 12px);
          background: var(--ha-card-background, var(--card-background-color, #fff));
          color: var(--primary-text-color);
        }

        .image {
          position: relative;
          aspect-ratio: 4 / 3;
          overflow: hidden;
          background: linear-gradient(135deg, rgba(83, 125, 93, 0.16), rgba(230, 203, 130, 0.18));
        }

        .image img {
          width: 100%;
          height: 100%;
          display: block;
          object-fit: cover;
        }

        .image::after {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, rgba(0, 0, 0, 0) 42%, rgba(0, 0, 0, 0.42) 100%);
          pointer-events: none;
        }

        .header {
          position: absolute;
          inset: auto 18px 16px 18px;
          z-index: 1;
          min-width: 0;
        }

        .title {
          color: #fff;
          font-size: 22px;
          line-height: 1.12;
          font-weight: 700;
          text-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
          overflow-wrap: anywhere;
        }

        .content {
          padding: 16px 18px 18px;
        }

        .chips {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 16px;
        }

        .chip {
          display: inline-flex;
          align-items: center;
          min-height: 26px;
          padding: 0 10px;
          border-radius: 999px;
          background: rgba(105, 118, 112, 0.12);
          color: var(--secondary-text-color);
          font-size: 12px;
          font-weight: 650;
          line-height: 1;
        }

        .chip.active.online {
          background: rgba(34, 139, 94, 0.15);
          color: #1b7b52;
        }

        .chip.active.watering {
          background: rgba(16, 126, 191, 0.15);
          color: #0d6ea6;
        }

        .chip.muted {
          opacity: 0.62;
        }

        .reading-row {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 10px;
        }

        .reading {
          min-width: 0;
        }

        .label {
          color: var(--secondary-text-color);
          font-size: 12px;
          font-weight: 650;
          text-transform: uppercase;
        }

        .value {
          margin-top: 2px;
          font-size: 38px;
          line-height: 1;
          font-weight: 760;
          letter-spacing: 0;
        }

        .target {
          align-items: flex-end;
          border: 0;
          background: transparent;
          color: var(--secondary-text-color);
          cursor: default;
          display: inline-flex;
          flex-direction: column;
          font-size: 13px;
          font-family: inherit;
          line-height: 1.25;
          margin: 0;
          padding: 0;
          text-align: right;
          white-space: nowrap;
        }

        .target.editable {
          cursor: pointer;
        }

        .target.editable:hover strong,
        .target.editable:focus-visible strong {
          color: var(--primary-color);
        }

        .target:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: 4px;
          border-radius: 6px;
        }

        .target strong {
          align-items: center;
          display: inline-flex;
          gap: 5px;
          justify-content: flex-end;
          color: var(--primary-text-color);
          font-size: 16px;
        }

        .target ha-icon {
          --mdc-icon-size: 15px;
          color: var(--secondary-text-color);
        }

        .bar {
          position: relative;
          height: 18px;
          border-radius: 999px;
          overflow: visible;
          background: ${barGradient};
          box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
        }

        .fill-mask {
          position: absolute;
          inset: 0;
          border-radius: inherit;
          overflow: hidden;
        }

        .fill-mask::after {
          content: "";
          position: absolute;
          inset: 0;
          left: ${moistureWidth}%;
          background: rgba(124, 129, 126, 0.28);
          backdrop-filter: saturate(0.75);
        }

        .marker {
          position: absolute;
          top: -5px;
          bottom: -5px;
          left: ${moistureLeft}%;
          width: 3px;
          transform: translateX(-50%);
          border-radius: 999px;
          background: var(--primary-text-color);
          box-shadow: 0 0 0 2px var(--card-background-color, #fff), 0 2px 7px rgba(0, 0, 0, 0.25);
          display: ${moisture === null ? "none" : "block"};
        }

        .scale {
          display: flex;
          justify-content: space-between;
          margin-top: 7px;
          color: var(--secondary-text-color);
          font-size: 11px;
        }

        .water-history {
          margin-top: 16px;
          padding-top: 12px;
          border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        }

        .water-history-head {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 10px;
          color: var(--secondary-text-color);
          font-size: 12px;
          font-weight: 650;
          line-height: 1.2;
          text-transform: uppercase;
        }

        .water-history-head strong {
          color: var(--primary-text-color);
          font-size: 13px;
          font-weight: 760;
          text-transform: none;
          white-space: nowrap;
        }

        .water-bars {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          align-items: end;
          gap: 7px;
          height: 58px;
          margin-top: 8px;
        }

        .water-bar {
          position: relative;
          display: flex;
          align-items: flex-end;
          justify-content: center;
          height: 58px;
          min-width: 0;
          border-radius: 4px;
          outline: 0;
        }

        .water-bar-fill {
          width: min(100%, 18px);
          min-height: 2px;
          border-radius: 4px 4px 0 0;
          background: #7cc7f6;
          background: color-mix(in srgb, var(--primary-color, #03a9f4) 58%, white);
          box-shadow: inset 0 -1px 0 rgba(0, 0, 0, 0.08);
          transition: background 120ms ease, transform 120ms ease;
        }

        .water-bar:hover .water-bar-fill,
        .water-bar:focus-visible .water-bar-fill {
          background: #55b5ee;
          background: color-mix(in srgb, var(--primary-color, #03a9f4) 76%, white);
          transform: translateY(-1px);
        }

        .water-bar::after {
          content: attr(data-tooltip);
          position: absolute;
          left: 50%;
          bottom: calc(100% + 8px);
          z-index: 2;
          max-width: 120px;
          padding: 6px 8px;
          border-radius: 6px;
          background: var(--primary-text-color);
          color: var(--card-background-color, #fff);
          font-size: 11px;
          font-weight: 650;
          line-height: 1.2;
          opacity: 0;
          pointer-events: none;
          text-align: center;
          transform: translate(-50%, 4px);
          transition: opacity 120ms ease, transform 120ms ease;
          white-space: nowrap;
        }

        .water-bar:hover::after,
        .water-bar:focus-visible::after {
          opacity: 1;
          transform: translate(-50%, 0);
        }

        .water-days {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 7px;
          margin-top: 5px;
          color: var(--secondary-text-color);
          font-size: 10px;
          line-height: 1;
          text-align: center;
        }

        .missing {
          margin-top: 12px;
          color: var(--error-color, #db4437);
          font-size: 13px;
        }

        .dialog-backdrop {
          position: fixed;
          inset: 0;
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 18px;
          background: rgba(0, 0, 0, 0.42);
        }

        .dialog {
          width: min(360px, 100%);
          border-radius: 12px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          color: var(--primary-text-color);
          box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
          padding: 18px;
        }

        .dialog-title {
          font-size: 18px;
          font-weight: 700;
          line-height: 1.2;
        }

        .dialog-value {
          margin: 16px 0 10px;
          font-size: 34px;
          font-weight: 760;
          line-height: 1;
        }

        .dialog input[type="range"] {
          width: 100%;
        }

        .dialog input[type="number"] {
          box-sizing: border-box;
          width: 100%;
          margin-top: 12px;
          border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.18));
          border-radius: 8px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          font: inherit;
          padding: 10px;
        }

        .dialog-error {
          min-height: 18px;
          margin-top: 10px;
          color: var(--error-color, #db4437);
          font-size: 13px;
        }

        .dialog-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 18px;
        }

        .dialog-actions button {
          border: 0;
          border-radius: 8px;
          cursor: pointer;
          font: inherit;
          font-weight: 650;
          min-height: 38px;
          padding: 0 14px;
        }

        .dialog-actions .cancel {
          background: transparent;
          color: var(--primary-text-color);
        }

        .dialog-actions .save {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }

        .dialog-actions button:disabled {
          cursor: progress;
          opacity: 0.7;
        }

        @media (max-width: 420px) {
          .content {
            padding: 14px;
          }

          .value {
            font-size: 34px;
          }
        }
      </style>
      <ha-card>
        <div class="image">
          <img src="${escapeHtml(cropUrl(this.config.crop))}" alt="">
          <div class="header">
            <div class="title">${escapeHtml(title)}</div>
          </div>
        </div>
        <div class="content">
          <div class="chips">
            ${this.config.online_entity ? `<span class="${chipClass("chip online", onlineState)}">${escapeHtml(onlineLabel)}</span>` : ""}
            ${this.config.watering_entity ? `<span class="${chipClass("chip watering", wateringState)}">${escapeHtml(wateringLabel)}</span>` : ""}
            ${this.config.state_entity ? `<span class="chip state ${isUnknown(planterState) ? "muted" : ""}">${escapeHtml(stateLabel)}</span>` : ""}
          </div>
          <div class="reading-row">
            <div class="reading">
              <div class="label">Moisture</div>
              <div class="value">${escapeHtml(formatPercent(moisture))}</div>
            </div>
            <button class="target ${targetEditable ? "editable" : ""}" type="button" aria-label="${targetEditable ? "Edit target moisture" : "Target moisture"}">
              Target
              <strong>
                ${escapeHtml(formatPercent(target))}
                ${targetEditable ? '<ha-icon icon="mdi:pencil"></ha-icon>' : ""}
              </strong>
            </button>
          </div>
          <div class="bar" role="img" aria-label="Moisture ${escapeHtml(formatPercent(moisture))}, target ${escapeHtml(formatPercent(target))}">
            <div class="fill-mask"></div>
            <div class="marker"></div>
          </div>
          <div class="scale">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
          ${waterHistoryMarkup(waterHistory)}
          ${missingRequired ? '<div class="missing">Configure moisture and target entities.</div>' : ""}
        </div>
        ${
          this._editingTarget
            ? `<div class="dialog-backdrop">
                <div class="dialog" role="dialog" aria-modal="true" aria-label="Edit target moisture">
                  <div class="dialog-title">Target moisture</div>
                  <div class="dialog-value">${escapeHtml(formatPercent(targetDraft))}</div>
                  <input class="target-range" type="range" min="0" max="100" step="1" value="${escapeHtml(targetDraft)}">
                  <input class="target-input" type="number" min="0" max="100" step="1" value="${escapeHtml(targetDraft)}" aria-label="Target moisture percentage">
                  <div class="dialog-error">${escapeHtml(this._targetError)}</div>
                  <div class="dialog-actions">
                    <button class="cancel" type="button" ${this._targetSubmitting ? "disabled" : ""}>Cancel</button>
                    <button class="save" type="button" ${this._targetSubmitting ? "disabled" : ""}>Save</button>
                  </div>
                </div>
              </div>`
            : ""
        }
      </ha-card>
    `;

    const targetButton = this.shadowRoot.querySelector(".target.editable");
    if (targetButton) {
      targetButton.addEventListener("click", () => this._openTargetEditor());
    }
    this._attachTargetEditorListeners();
  }

  _openTargetEditor() {
    if (!planterIdFromConfig(this.config)) {
      return;
    }
    const target = parsePercent(entityState(this._hass, this.config.target_entity));
    this._targetDraft = target ?? 50;
    this._targetError = "";
    this._editingTarget = true;
    this._render(true);
  }

  _attachTargetEditorListeners() {
    const range = this.shadowRoot.querySelector(".target-range");
    const input = this.shadowRoot.querySelector(".target-input");
    const valueLabel = this.shadowRoot.querySelector(".dialog-value");
    const error = this.shadowRoot.querySelector(".dialog-error");
    const cancel = this.shadowRoot.querySelector(".dialog-actions .cancel");
    const save = this.shadowRoot.querySelector(".dialog-actions .save");
    const updateDraft = (value) => {
      const number = Number(value);
      this._targetDraft = Number.isFinite(number) ? clamp(number, 0, 100) : 0;
      this._targetError = "";
      if (range) {
        range.value = this._targetDraft;
      }
      if (input) {
        input.value = this._targetDraft;
      }
      if (valueLabel) {
        valueLabel.textContent = formatPercent(this._targetDraft);
      }
      if (error) {
        error.textContent = "";
      }
    };

    if (range) {
      range.addEventListener("input", (event) => updateDraft(event.target.value));
    }
    if (input) {
      input.addEventListener("input", (event) => updateDraft(event.target.value));
    }
    if (cancel) {
      cancel.addEventListener("click", () => {
        this._editingTarget = false;
        this._targetError = "";
        this._render(true);
      });
    }
    if (save) {
      save.addEventListener("click", () => this._saveTargetMoisture());
    }
  }

  async _saveTargetMoisture() {
    const planterId = planterIdFromConfig(this.config);
    if (!this._hass || !planterId) {
      return;
    }
    this._targetSubmitting = true;
    this._targetError = "";
    this._render(true);
    try {
      await this._hass.callService("watering_io", "set_target_moisture", {
        planter_id: Number(planterId),
        target_moisture: Number(this._targetDraft),
      });
      this._editingTarget = false;
    } catch (error) {
      this._targetError = error?.message || "Could not update target moisture.";
    } finally {
      this._targetSubmitting = false;
      this._render(true);
    }
  }
}

customElements.define("watering-io-planter-card", WateringIoPlanterCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "watering-io-planter-card",
  name: "Watering.IO Planter",
  preview: true,
  description: "Shows one planter with a crop picture, status chips, and a moisture target bar.",
  documentationURL: "https://github.com/watering-io/wateringio-homeassistant",
});

console.info(`%c WATERING-IO-PLANTER-CARD %c ${CARD_VERSION} `, "color: #fff; background: #2f8d74; font-weight: 700;", "color: #2f8d74; background: transparent;");
