# Planter Card Max Daily Dosing Design

## Goal

Allow a user to edit a planter's `max_daily_dosing_s` value from the existing Watering.IO planter card settings modal, next to target moisture and fertilizer steps.

## Scope

- Add a `Max daily dosing (s)` numeric field to the existing planter settings modal.
- Use seconds as the displayed and submitted unit.
- Preserve the firmware behavior where `0` disables the automatic daily dosing cap.
- Reuse the existing `watering_io.set_planter_settings` service and planter config update helper.
- Keep the modal opened from the current target value button.

## User Experience

When the user taps the target value on a planter card, the modal shows:

1. Target moisture slider and number input.
2. Fertilizer steps number input.
3. Max daily dosing seconds number input.

The new field appears below fertilizer steps. It accepts integer seconds from `0` to `86400`, matching the existing Home Assistant max daily dosing number entity.

## Data Flow

The card infers the planter id from `target_entity`, as it already does for editing target moisture and fertilizer steps. It then infers the matching max daily dosing number entity from the standard integration entity id:

```text
number.planter_<planter_id>_max_daily_dosing_s
```

When the modal opens, the card reads that entity state and initializes the max daily dosing draft. On save, the card calls:

```text
watering_io.set_planter_settings
```

with `planter_id`, `target_moisture`, `fertilizer_steps` when present, and `max_daily_dosing_s` when present.

The service accepts `max_daily_dosing_s`, passes it to `_async_update_planter_settings`, and `planter_config_set_payload` publishes a full planter config while preserving all other cached values.

## Error Handling

The card clamps invalid numeric input to the allowed range and clears the field to omit it only if the existing entity state is unknown or unavailable. Service validation rejects values outside `0..86400`.

Existing modal error display continues to show service failures, such as missing planter config.

## Tests

- Extend the planter card JavaScript test to confirm the modal includes the new input.
- Extend the card save test to confirm `max_daily_dosing_s` is included in the service payload.
- Add or update Python service/helper coverage so the service accepts `max_daily_dosing_s` and forwards it to the existing payload helper.
