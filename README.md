# Watering.IO Home Assistant Custom Integration

## HACS Installation

1. Open HACS > **Integrations**.
2. Open the menu > **Custom repositories**.
3. Add this repository URL and select category **Integration**.
4. Search for **Watering.IO Hub** and install it.
5. Restart Home Assistant.
6. Go to **Settings > Devices & services > Add integration** and add **Watering.IO Hub**.
7. Enter the MQTT root prefix. The default is `watering.io`.

> Important: schema V2 uses `<prefix>/hubs/<hub_id>/...`. The integration discovers a hub from retained `<prefix>/hubs/+/schema` or `<prefix>/hubs/+/info` messages, then uses `hub_id` as the Home Assistant identity.

## MQTT Contract Integration

This repository contains a custom Home Assistant integration (`custom_components/watering_io`) that consumes the Watering.IO Hub MQTT firmware contract directly, without Home Assistant MQTT Discovery.

Use these placeholders throughout the docs:

- `<prefix>`: MQTT root, usually `watering.io`
- `<hub_id>`: logical Home Assistant hub identity
- `<root>`: `<prefix>/hubs/<hub_id>`

The integration subscribes to these retained topics:

- `<prefix>/hubs/+/schema`
- `<prefix>/hubs/+/info`
- `<root>/availability`
- `<root>/config/schedule`
- `<root>/config/fertilizer`
- `<root>/config/planters`
- `<root>/status/system`
- `<root>/status/schedule`
- `<root>/status/pumps`
- `<root>/status/fertilizer`
- `<root>/status/sensors`
- `<root>/planters/<planter_id>/status`
- `<root>/sensors/<sensor_modbus_id>/status`

The integration also listens for V2 event and ack topics:

- `<root>/planters/<planter_id>/events/watering`
- `<root>/events/manual_dosing_unassigned`
- `<root>/events/fertilizer/move`
- `<root>/ack/#`

Entities are created for:

- System sensors: uptime, Wi-Fi RSSI, bus current, firmware/build diagnostics
- Schedule status sensors: phase, local date, schedule start times, and fertilizer run details
- Schedule binary sensors: schedule enabled, automatic moisture allowed, and time synced
- Pump binary sensors
- Per-planter sensors and binary sensors
- Per-planter dosing sensors for total dosing time and calculated total water
- Per-sensor moisture/temperature/online diagnostics
- Sensor rescan button publishing `{}` to `<root>/cmd/sensors/rescan`
- Per-planter target moisture number entities and dashboard edits that publish updates through the planter config command

Home Assistant device identifiers use `("watering_io", hub_id)`. ESP32 `device_id` values are treated as firmware metadata and are not used for entity unique IDs. Planter and sensor unique IDs are based on:

- Planters: `<hub_id>_planter_<planter_id>_<metric>`
- Sensors: `<hub_id>_sensor_<sensor_modbus_id>_<metric>`

## Planter Configuration

Planters can be added, updated, or deleted from **Settings > Devices & services > Watering.IO Hub > Configure**.

The integration publishes planter configuration commands to:

```text
<root>/cmd/config/planters/set
<root>/cmd/config/planters/delete
<root>/cmd/config/planters/get
```

The add/update form sends `planter_id`, `enabled`, `sensor_modbus_id`, `valve_route`, `target_moisture`, and `hysteresis` to the hub. The integration keeps its planter cache from retained `<root>/config/planters` and stores the latest ack received below `<root>/ack/#`.

The integration also exposes the `watering_io.set_target_moisture` service. It accepts `planter_id` and `target_moisture`, preserves the cached planter config values, and publishes the full update to `<root>/cmd/config/planters/set`.

## Dosing Measurements

For each planter, the integration reads retained dosing values from:

```text
<root>/planters/<planter_id>/status
```

Supported dosing fields:

- `total_dosing_s` -> planter metric `total_dosing_s`
- `total_dosing_s` plus pump calibration -> planter metric `total_water_ml`

`total_dosing_s` and `total_water_ml` are exposed as `total_increasing` sensors so they can be used with Home Assistant `utility_meter` helpers for daily, monthly, or seasonal totals.

The pump flow calibration is available in the integration options:

```text
pump_1_flow_ml_per_s
```

The default is `1.0 mL/s`.

Watering event messages from `<root>/planters/<planter_id>/events/watering` are logged at debug level only. They are not used for aggregation, so reconnects and retained status messages remain the source of truth for statistics.

Current firmware no longer publishes legacy dosing fields such as `total_dosing_ms`, `duration_ms`, `last_dosing_ms`, `last_dosing_unix`, or `last_event_id`. If those old entities remain in Home Assistant after updating, remove the stale entity registry entries once.

## Dashboard Card

The integration bundles a Lovelace custom card for a single planter:

```yaml
type: custom:watering-io-planter-card
name: Tomatoes
crop: tomato
moisture_entity: sensor.planter_1_moisture
target_entity: sensor.planter_1_target_moisture
online_entity: binary_sensor.planter_1_online
watering_entity: binary_sensor.planter_1_watering
```

The card always displays `target_entity`, which comes from the planter MQTT status topic. Tapping the target value opens a small editor in the card. Saving a new value calls `watering_io.set_target_moisture`, which publishes the full planter config to `<root>/cmd/config/planters/set` with only `target_moisture` changed, then refreshes the cached planter config.

Available crop presets:

- `generic`
- `tomato`
- `tomato_cherry`
- `tomato_yellow`
- `tomato_beefsteak`
- `tomato_roma`
- `tomato_black`
- `basil`
- `lettuce`
- `chili`
- `pepper_red_bell`
- `pepper_yellow_bell`
- `pepper_jalapeno`
- `pepper_mixed_chili`
- `strawberry`
- `cucumber`
- `eggplant`
- `zucchini`
- `herbs`
- `parsley`
- `mint`
- `arugula`
- `spinach`
- `radish`

### Add The Card Resource

After installing or updating the integration and restarting Home Assistant, add this dashboard resource:

```text
URL: /watering_io_static/watering-io-planter-card.js?v=0.1.19
Resource type: JavaScript module
```

In the Home Assistant UI this is under **Settings > Dashboards > Resources**.

The card also appears in the visual card picker as **Watering.IO Planter**. Use explicit entity IDs for each planter card so the dashboard remains stable even if entity names are customized.
