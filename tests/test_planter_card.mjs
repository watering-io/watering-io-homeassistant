import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const ROOT = path.resolve(import.meta.dirname, "..");
const CARD_PATH = path.join(
  ROOT,
  "custom_components",
  "watering_io",
  "frontend",
  "watering-io-planter-card.js",
);

function loadCardContext() {
  const context = {
    console,
    registeredElements: new Map(),
    window: { customCards: [] },
    customElements: {
      define(name, elementClass) {
        context.registeredElements.set(name, elementClass);
      },
    },
    HTMLElement: class {
      attachShadow() {
        const shadowRoot = {
          html: "",
          set innerHTML(value) {
            this.html = value;
          },
          get innerHTML() {
            return this.html;
          },
          querySelector() {
            return null;
          },
        };
        this.shadowRoot = shadowRoot;
        return shadowRoot;
      }
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(CARD_PATH, "utf8"), context, { filename: CARD_PATH });
  return context;
}

const context = loadCardContext();
const Card = context.registeredElements.get("watering-io-planter-card");

assert.equal(
  context.fertilizerStepsEntityFromConfig(
    {
      states: {
        "number.planter_3_fertilizer_steps": { state: "180" },
      },
    },
    { target_entity: "sensor.planter_3_target_moisture" },
  ),
  "number.planter_3_fertilizer_steps",
);

assert.equal(
  context.fertilizerStepsEntityFromConfig(
    {
      states: {
        "number.planter_3_fertilizer_steps": { state: "180" },
        "number.custom_fertilizer_dose": { state: "240" },
      },
    },
    {
      target_entity: "sensor.planter_3_target_moisture",
      fertilizer_steps_entity: "number.custom_fertilizer_dose",
    },
  ),
  "number.custom_fertilizer_dose",
);

assert.equal(
  context.maxDailyDosingEntityFromConfig(
    {
      states: {
        "number.planter_3_max_daily_dosing": { state: "300" },
      },
    },
    { target_entity: "sensor.planter_3_target_moisture" },
  ),
  "number.planter_3_max_daily_dosing",
);

assert.equal(
  context.maxDailyDosingEntityFromConfig(
    {
      states: {
        "number.watering_io_planter_3_max_daily_dosing_s": { state: "300" },
      },
    },
    { target_entity: "sensor.watering_io_planter_3_target_moisture" },
  ),
  "number.watering_io_planter_3_max_daily_dosing_s",
);

assert.equal(
  context.maxDailyDosingEntityFromConfig(
    {
      states: {
        "number.planter_3_max_daily_dosing_s": { state: "300" },
        "number.custom_daily_cap": { state: "600" },
      },
    },
    {
      target_entity: "sensor.planter_3_target_moisture",
      max_daily_dosing_entity: "number.custom_daily_cap",
    },
  ),
  "number.custom_daily_cap",
);

assert.ok(Card, "card should register itself as a custom element");

const renderedCard = new Card();
renderedCard.setConfig({
  crop: "generic",
  moisture_entity: "sensor.watering_io_planter_3_moisture",
  target_entity: "sensor.watering_io_planter_3_target_moisture",
});
renderedCard.hass = {
  states: {
    "sensor.watering_io_planter_3_moisture": { state: "42", attributes: {} },
    "sensor.watering_io_planter_3_target_moisture": { state: "52", attributes: {} },
    "number.watering_io_planter_3_fertilizer_steps": { state: "180", attributes: {} },
    "number.watering_io_planter_3_max_daily_dosing_s": { state: "300", attributes: {} },
  },
};

assert.match(renderedCard.shadowRoot.innerHTML, /aria-label="Edit planter settings"/);
assert.doesNotMatch(renderedCard.shadowRoot.innerHTML, />Fertilizer</);
assert.doesNotMatch(renderedCard.shadowRoot.innerHTML, /180 steps/);

renderedCard._openTargetEditor();
assert.match(renderedCard.shadowRoot.innerHTML, />Fertilizer steps</);
assert.match(renderedCard.shadowRoot.innerHTML, /class="fertilizer-input"/);
assert.match(renderedCard.shadowRoot.innerHTML, />Max daily dosing \(s\)</);
assert.match(renderedCard.shadowRoot.innerHTML, /class="max-daily-dosing-input"/);
assert.match(renderedCard.shadowRoot.innerHTML, /id="max-daily-dosing-input"[^>]*value="300"/);

const card = new Card();
const calls = [];
card.config = { target_entity: "sensor.planter_3_target_moisture" };
card._hass = {
  async callService(domain, service, data) {
    calls.push({ domain, service, data });
  },
};
card._render = () => {};
card._editingTarget = true;
card._targetDraft = 52;
card._fertilizerStepsDraft = 180;
card._maxDailyDosingDraft = 300;

await card._savePlanterSettings();

assert.deepEqual(JSON.parse(JSON.stringify(calls)), [
  {
    domain: "watering_io",
    service: "set_planter_settings",
    data: {
      planter_id: 3,
      target_moisture: 52,
      fertilizer_steps: 180,
      max_daily_dosing_s: 300,
    },
  },
]);
assert.equal(card._editingTarget, false);
