# Planter Card Max Daily Dosing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `max_daily_dosing_s` editing to the existing Watering.IO planter card settings modal.

**Architecture:** Extend the existing planter card editor state with one more numeric draft, inferred from the standard max daily dosing number entity. Extend the existing Home Assistant `set_planter_settings` service so the card can submit the value through the same full-config publish path already used by target moisture and fertilizer steps.

**Tech Stack:** Plain JavaScript custom Lovelace card tested with Node's `node:assert`, Python Home Assistant custom integration code, and lightweight unittest/source tests already present in this repo.

---

## File Structure

- Modify `tests/test_planter_card.mjs`: add failing expectations for max daily dosing entity inference, modal input markup, and service payload.
- Modify `custom_components/watering_io/frontend/watering-io-planter-card.js`: add max daily dosing constants/helpers, draft state, modal input, input listeners, render key, and service payload field.
- Modify `tests/test_dosing_helpers.py`: add source-level regression coverage for the service accepting and forwarding `max_daily_dosing_s`, because importing `__init__.py` requires Home Assistant runtime packages that this lightweight test suite avoids.
- Modify `custom_components/watering_io/__init__.py`: add service validation and forward the optional value into `planter_config_set_payload`.
- Modify `custom_components/watering_io/services.yaml`: document the optional service field in Home Assistant's service UI.
- Modify `README.md`: update the dashboard card description and YAML example.

### Task 1: Card Test

**Files:**
- Modify: `tests/test_planter_card.mjs`

- [ ] **Step 1: Write the failing test**

Add these expectations near the existing fertilizer entity tests:

```javascript
assert.equal(
  context.maxDailyDosingEntityFromConfig(
    {
      states: {
        "number.planter_3_max_daily_dosing_s": { state: "300" },
      },
    },
    { target_entity: "sensor.planter_3_target_moisture" },
  ),
  "number.planter_3_max_daily_dosing_s",
);
```

Add the max daily state to the rendered card fixture:

```javascript
"number.planter_3_max_daily_dosing_s": { state: "300", attributes: {} },
```

Add modal markup assertions after opening the editor:

```javascript
assert.match(renderedCard.shadowRoot.innerHTML, />Max daily dosing \(s\)</);
assert.match(renderedCard.shadowRoot.innerHTML, /class="max-daily-dosing-input"/);
```

Add the draft and payload expectation in the save test:

```javascript
card._maxDailyDosingDraft = 300;
```

```javascript
max_daily_dosing_s: 300,
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
node tests/test_planter_card.mjs
```

Expected: fail because `maxDailyDosingEntityFromConfig` is not defined or the modal/input/payload is missing.

### Task 2: Card Implementation

**Files:**
- Modify: `custom_components/watering_io/frontend/watering-io-planter-card.js`

- [ ] **Step 1: Add constants and entity helpers**

Add:

```javascript
const MAX_DAILY_DOSING_SECONDS = 86400;
```

Add functions mirroring fertilizer entity inference:

```javascript
function candidateMaxDailyDosingEntity(entityId) {
  if (!entityId?.startsWith("sensor.")) {
    return undefined;
  }
  if (entityId.endsWith("_target_moisture")) {
    return entityId.replace(/^sensor\./, "number.").replace(/_target_moisture$/, "_max_daily_dosing_s");
  }
  if (entityId.endsWith("_moisture")) {
    return entityId.replace(/^sensor\./, "number.").replace(/_moisture$/, "_max_daily_dosing_s");
  }
  return undefined;
}

function maxDailyDosingEntityFromConfig(hass, config) {
  const planterId = planterIdFromConfig(config);
  const candidates = [
    candidateMaxDailyDosingEntity(config?.target_entity),
    candidateMaxDailyDosingEntity(config?.moisture_entity),
    planterId ? `number.planter_${planterId}_max_daily_dosing_s` : undefined,
  ].filter(Boolean);

  return candidates.find((entityId) => hass?.states?.[entityId]) || candidates[0];
}
```

- [ ] **Step 2: Add parsing helpers**

Add:

```javascript
function parseMaxDailyDosing(stateObj) {
  if (isUnknown(stateObj)) {
    return null;
  }
  const value = Number(stateObj.state);
  if (!Number.isFinite(value)) {
    return null;
  }
  return Math.round(clamp(value, 0, MAX_DAILY_DOSING_SECONDS));
}

function normalizeMaxDailyDosing(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return null;
  }
  return Math.round(clamp(number, 0, MAX_DAILY_DOSING_SECONDS));
}
```

- [ ] **Step 3: Wire draft state and render**

Add constructor state:

```javascript
this._maxDailyDosingDraft = null;
```

Add the draft to `renderKey`:

```javascript
this._maxDailyDosingDraft ?? "",
```

Add a local render variable:

```javascript
const maxDailyDosingDraft = this._maxDailyDosingDraft;
```

Add the modal field below fertilizer steps:

```html
<div class="dialog-field">
  <label for="max-daily-dosing-input">Max daily dosing (s)</label>
  <input id="max-daily-dosing-input" class="max-daily-dosing-input" type="number" min="0" max="${MAX_DAILY_DOSING_SECONDS}" step="1" value="${escapeHtml(maxDailyDosingDraft ?? "")}" aria-label="Max daily dosing seconds">
</div>
```

- [ ] **Step 4: Wire modal open, listeners, and save payload**

Read the inferred state in `_openTargetEditor`:

```javascript
const maxDailyDosingEntity = maxDailyDosingEntityFromConfig(this._hass, this.config);
const maxDailyDosing = parseMaxDailyDosing(entityState(this._hass, maxDailyDosingEntity));
this._maxDailyDosingDraft = maxDailyDosing;
```

Add the input lookup:

```javascript
const maxDailyDosingInput = this.shadowRoot.querySelector(".max-daily-dosing-input");
```

Add listener logic:

```javascript
const updateMaxDailyDosingDraft = (value) => {
  this._maxDailyDosingDraft = value === "" ? null : normalizeMaxDailyDosing(value);
  this._targetError = "";
  if (maxDailyDosingInput) {
    maxDailyDosingInput.value = this._maxDailyDosingDraft ?? "";
  }
  if (error) {
    error.textContent = "";
  }
};

if (maxDailyDosingInput) {
  maxDailyDosingInput.addEventListener("input", (event) => updateMaxDailyDosingDraft(event.target.value));
}
```

Add payload field in `_savePlanterSettings`:

```javascript
if (this._maxDailyDosingDraft !== null && this._maxDailyDosingDraft !== undefined) {
  data.max_daily_dosing_s = Number(this._maxDailyDosingDraft);
}
```

- [ ] **Step 5: Run card test to verify it passes**

Run:

```powershell
node tests/test_planter_card.mjs
```

Expected: pass.

### Task 3: Service Test

**Files:**
- Modify: `tests/test_dosing_helpers.py`

- [ ] **Step 1: Write the failing source regression test**

Add:

```python
    def test_set_planter_settings_service_accepts_max_daily_dosing(self) -> None:
        source = (ROOT / "custom_components/watering_io/__init__.py").read_text(encoding="utf-8")

        self.assertIn('max_daily_dosing_s = call.data.get("max_daily_dosing_s")', source)
        self.assertIn("max_daily_dosing_s=max_daily_dosing_s", source)
        self.assertIn('vol.Optional("max_daily_dosing_s")', source)
        self.assertIn("vol.Range(min=0, max=MAX_DAILY_DOSING_SECONDS)", source)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_dosing_helpers.DosingHelperTests.test_set_planter_settings_service_accepts_max_daily_dosing
```

Expected: fail because the service does not yet read, validate, or forward `max_daily_dosing_s`.

### Task 4: Service Implementation

**Files:**
- Modify: `custom_components/watering_io/__init__.py`
- Modify: `custom_components/watering_io/services.yaml`

- [ ] **Step 1: Add service constant and forwarding**

Add:

```python
MAX_DAILY_DOSING_SECONDS = 86400
```

Update `async_set_planter_settings`:

```python
max_daily_dosing_s = call.data.get("max_daily_dosing_s")
if target_moisture is None and fertilizer_steps is None and max_daily_dosing_s is None:
    raise HomeAssistantError("At least one planter setting must be provided")
```

Pass:

```python
max_daily_dosing_s=int(max_daily_dosing_s) if max_daily_dosing_s is not None else None,
```

Update the schema:

```python
vol.Optional("max_daily_dosing_s"): vol.All(
    vol.Coerce(int),
    vol.Range(min=0, max=MAX_DAILY_DOSING_SECONDS),
),
```

Update `_async_update_planter_settings` signature and helper call:

```python
max_daily_dosing_s: int | None = None,
```

```python
max_daily_dosing_s=max_daily_dosing_s,
```

- [ ] **Step 2: Document service field**

Add to `services.yaml` under `set_planter_settings.fields`:

```yaml
    max_daily_dosing_s:
      name: Max daily dosing
      description: New automatic watering cap in seconds. Use 0 to disable the cap.
      required: false
      selector:
        number:
          min: 0
          max: 86400
          step: 1
          unit_of_measurement: s
          mode: box
```

- [ ] **Step 3: Run service test to verify it passes**

Run:

```powershell
python -m unittest tests.test_dosing_helpers.DosingHelperTests.test_set_planter_settings_service_accepts_max_daily_dosing
```

Expected: pass.

### Task 5: README And Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update dashboard card docs**

Add the optional entity to the YAML example:

```yaml
max_daily_dosing_entity: number.planter_1_max_daily_dosing_s
```

Update the dashboard card text to say the modal edits target moisture, fertilizer steps, and max daily dosing seconds.

- [ ] **Step 2: Run full lightweight test suite**

Run:

```powershell
node tests/test_planter_card.mjs
python -m unittest tests.test_dosing_helpers
```

Expected: both commands pass.

- [ ] **Step 3: Inspect diff**

Run:

```powershell
git diff -- custom_components/watering_io/frontend/watering-io-planter-card.js custom_components/watering_io/__init__.py custom_components/watering_io/services.yaml tests/test_planter_card.mjs tests/test_dosing_helpers.py README.md
```

Expected: only scoped max daily dosing card/service/docs/test changes.
