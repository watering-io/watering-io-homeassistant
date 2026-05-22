const CARD_VERSION = "0.1.14";
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

function targetNumberEntity(config) {
  if (config?.target_number_entity) {
    return config.target_number_entity;
  }
  if (config?.target_entity?.startsWith("sensor.")) {
    return `number.${config.target_entity.slice("sensor.".length)}`;
  }
  return undefined;
}

class WateringIoPlanterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lastRenderKey = null;
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
    return 4;
  }

  getGridOptions() {
    return {
      rows: 4,
      columns: 6,
      min_rows: 3,
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
    const targetEditEntity = targetNumberEntity(this.config);
    const targetNumberState = entityState(this._hass, targetEditEntity);
    const renderKey = JSON.stringify([
      this.config.name || "",
      this.config.crop || "",
      this.config.moisture_entity || "",
      moistureState?.state || "",
      moistureState?.attributes?.friendly_name || "",
      this.config.target_entity || "",
      targetState?.state || "",
      targetEditEntity || "",
      targetNumberState?.state || "",
      this.config.online_entity || "",
      onlineState?.state || "",
      this.config.watering_entity || "",
      wateringState?.state || "",
      this.config.state_entity || "",
      planterState?.state || "",
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
    const missingRequired = !this.config.moisture_entity || !this.config.target_entity;
    const targetEditable = Boolean(targetEditEntity && targetNumberState);

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
          border: 0;
          background: transparent;
          color: var(--secondary-text-color);
          cursor: default;
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
          display: block;
          color: var(--primary-text-color);
          font-size: 16px;
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

        .missing {
          margin-top: 12px;
          color: var(--error-color, #db4437);
          font-size: 13px;
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
              <strong>${escapeHtml(formatPercent(target))}</strong>
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
          ${missingRequired ? '<div class="missing">Configure moisture and target entities.</div>' : ""}
        </div>
      </ha-card>
    `;

    const targetButton = this.shadowRoot.querySelector(".target.editable");
    if (targetButton) {
      targetButton.addEventListener("click", () => this._openTargetEditor());
    }
  }

  _openTargetEditor() {
    const entityId = targetNumberEntity(this.config);
    if (!entityId) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId },
      })
    );
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
