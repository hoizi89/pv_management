# PV Management

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hoizi89/pv_management)](https://github.com/hoizi89/pv_management/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> The all-in-one Home Assistant integration for your PV system with **variable/spot electricity tariffs** and intelligent battery management.

> **For fixed-price tariffs** (e.g. Gruenwelt, Energie AG) there's a dedicated version:
> [pv_management_fix](https://github.com/hoizi89/pv_management_fix)

---

## What Can This Integration Do?

| Feature | Description |
|---------|-------------|
| **Battery Management** | Auto-Charge + Discharge Control based on EPEX Spot prices |
| **Traffic Light** | 5-level consumption recommendation (dark green to red) |
| **Energy Benchmark** | Compare your consumption with AT/DE/CH averages |
| **Amortization** | Real-time payback tracking with persistent storage |
| **EPEX Spot** | Integrates current market prices and quantiles |
| **Solcast** | Considers PV forecast for smart decisions |
| **Notifications** | Milestones, monthly summaries, custom automations |

---

## New in v3.21.0: Energy Benchmark

Compare your electricity consumption with the average for your country — **completely offline**, no cloud needed.

- **Countries:** Austria, Germany, Switzerland
- **Household size:** 1-6 persons
- **6 sensors:** Average, own consumption, comparison (%), CO2 avoided, efficiency score (0-100), rating
- **Heat pump optional:** HP consumption is benchmarked separately for fair comparison

| Sensor | What it shows | Example |
|--------|--------------|---------|
| Benchmark Average | Reference consumption for your country/household | 4000 kWh/year |
| Benchmark Own Consumption | Your consumption extrapolated to 1 year | 3200 kWh/year |
| Benchmark Comparison | Deviation from average | -20% |
| Benchmark CO2 Avoided | CO2 savings from PV per year | 180 kg/year |
| Benchmark Efficiency Score | Overall rating 0-100 | 72 points |
| Benchmark Rating | Text classification | "Sehr gut" |

---

## Installation

### HACS (recommended)

1. Open HACS > Integrations > 3-dot menu > **Custom repositories**
2. URL: `https://github.com/hoizi89/pv_management`
3. Category: **Integration**
4. Install and **restart** Home Assistant

### Manual

Copy `custom_components/pv_management` to `config/custom_components/`, then restart.

---

## Quick Start

1. **Settings** > Devices & Services > **Add Integration**
2. Search for "PV Management"
3. Select your sensors:
   - **PV Production** (required) — kWh counter
   - **Grid Export** (optional) — for earnings calculation
   - **Grid Import** (optional) — for cost tracking
   - **Consumption** (optional) — for autarky rate
4. Configure **electricity price** (EUR or ct/kWh)
5. Set **feed-in tariff** from your grid operator
6. Enter **installation cost** and select an **Amortization Helper** (input_number)

> All settings can be changed later under **Options**.

---

## Sensors Overview

### Main Device: PV Management

| Sensor | Unit | Description |
|--------|------|-------------|
| Consumption Recommendation | — | 5-level traffic light (dark_green/green/yellow/orange/red) |
| Next Cheap Hour | — | When is the next cheap time slot |
| Amortization | % | How much of the system is paid off |
| Total Savings | EUR | Savings from self-consumption + feed-in |
| Remaining Cost | EUR | Remaining until amortization |
| Status | — | e.g. "45.2% amortized" or "Amortized! +500 EUR profit" |
| Estimated Payback Date | Date | When the system will be paid off |
| Remaining Days | Days | Estimated days until amortization |
| Self Consumption | kWh | PV electricity consumed directly |
| Feed-in | kWh | PV electricity exported to grid |
| Self Consumption Ratio | % | Share of PV production used directly |
| Autarky Rate | % | Share of consumption covered by PV |
| Savings per Day/Month/Year | EUR | Average savings |
| CO2 Savings | kg | Avoided CO2 emissions |
| Spot vs Fixed | EUR | Savings compared to fixed-price tariff |

### Device: Electricity Prices

| Sensor | Unit | Description |
|--------|------|-------------|
| Feed-in Today | EUR | Today's feed-in earnings |
| Grid Import Today | EUR | Today's grid import cost |
| Net Electricity Cost Today | EUR | Grid import minus feed-in |
| Daily Average Price | EUR/kWh | Weighted average price today |
| Monthly Average Price | EUR/kWh | Weighted average price this month |
| Total Average Price | EUR/kWh | Overall weighted average price |

### Device: Energy Benchmark (optional)

Appears when enabled under Options > Energy Benchmark.

| Sensor | Unit | Description |
|--------|------|-------------|
| Benchmark Average | kWh/year | Reference consumption (E-Control/BDEW/BFE) |
| Benchmark Own Consumption | kWh/year | Your household consumption extrapolated |
| Benchmark Comparison | % | Deviation (negative = better than average) |
| Benchmark CO2 Avoided | kg/year | CO2 savings from PV |
| Benchmark Efficiency Score | Points | 0-100 (consumption + autarky + self-consumption) |
| Benchmark Rating | — | Hervorragend / Sehr gut / Gut / Durchschnittlich |
| Benchmark HP Average | kWh/year | Reference HP consumption (only with HP) |
| Benchmark HP Consumption | kWh/year | Your HP consumption (only with HP) |

### Auto-Charge Sensors

| Sensor | Description |
|--------|-------------|
| Auto-Charge Recommended | Binary sensor for automation trigger |
| Discharge Limit | Binary sensor for discharge control |
| Target SOC | Current target state of charge |
| Hold SOC | Minimum SOC during hold phase |
| Auto-Charge Power | Configured charge power |
| Auto-Charge Reason | Why auto-charge was activated/deactivated |

---

## Options (configurable after setup)

Under **Settings > Devices & Services > PV Management > Configure**:

| Category | What you can configure |
|----------|----------------------|
| **Sensors** | PV Production, Grid Export/Import, Consumption, Battery SOC, PV Power/Forecast |
| **Electricity Prices** | Price unit, fallback price, dynamic sensor, feed-in tariff, fixed price comparison |
| **Integrations** | EPEX Spot Price, EPEX Quantile, Solcast Forecast |
| **Amortization Helper** | input_number for persistent storage |
| **Battery Control** | Target SOC, Auto-Charge settings, Discharge Control settings |
| **Advanced** | PV peak power, winter base load, traffic light thresholds |
| **Energy Benchmark** | Country, household size, heat pump |

---

## Example Automations

### 1. Charge Battery When Cheap (Auto-Charge)

```yaml
alias: "PV: Charge battery when cheap"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    to: "on"
action:
  - service: number.set_value
    target:
      entity_id: number.battery_charge_power  # Your inverter
    data:
      value: 3000
  - service: switch.turn_on
    target:
      entity_id: switch.battery_grid_charge  # Your inverter
```

### 2. Stop Battery Charging

```yaml
alias: "PV: Stop battery charging"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    to: "off"
action:
  - service: switch.turn_off
    target:
      entity_id: switch.battery_grid_charge
  - service: number.set_value
    target:
      entity_id: number.battery_charge_power
    data:
      value: 0
```

### 3. Limit Battery Discharge for Expensive Hours

```yaml
alias: "PV: Save battery for expensive hours"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_entladung_begrenzen
    to: "on"
action:
  - service: number.set_value
    target:
      entity_id: number.battery_discharge_limit
    data:
      value: "{{ states('sensor.pv_management_halte_soc') }}"
```

### 4. GoodWe Auto-Charge

```yaml
alias: "PV: GoodWe Auto-Charge"
triggers:
  - entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    trigger: state
actions:
  - choose:
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "on"
        sequence:
          - action: select.select_option
            target:
              entity_id: select.goodwe_inverter_operation_mode
            data:
              option: eco_charge
          - action: number.set_value
            target:
              entity_id: number.goodwe_eco_mode_charge_power
            data:
              value: "{{ states('sensor.pv_management_auto_charge_leistung') | int(3000) }}"
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "off"
        sequence:
          - action: select.select_option
            target:
              entity_id: select.goodwe_inverter_operation_mode
            data:
              option: general
```

### 5. GoodWe Discharge Control

```yaml
alias: "PV: GoodWe Discharge Control"
triggers:
  - entity_id: binary_sensor.pv_management_entladung_empfehlung
    trigger: state
  - entity_id: switch.pv_management_entlade_steuerung
    trigger: state
actions:
  - choose:
      - conditions:
          - condition: or
            conditions:
              - condition: state
                entity_id: switch.pv_management_entlade_steuerung
                state: "off"
              - condition: template
                value_template: >
                  {{ state_attr('binary_sensor.pv_management_entladung_empfehlung', 'sommer_modus') == true }}
        sequence:
          - action: number.set_value
            target:
              entity_id: number.goodwe_depth_of_discharge_on_grid
            data:
              value: >
                {{ 100 - state_attr('binary_sensor.pv_management_entladung_empfehlung', 'sommer_soc') | int(10) }}
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_entladung_empfehlung
            state: "on"
        sequence:
          - action: number.set_value
            target:
              entity_id: number.goodwe_depth_of_discharge_on_grid
            data:
              value: >
                {{ 100 - state_attr('binary_sensor.pv_management_entladung_empfehlung', 'entladen_bis_soc') | int(20) }}
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_entladung_empfehlung
            state: "off"
        sequence:
          - action: number.set_value
            target:
              entity_id: number.goodwe_depth_of_discharge_on_grid
            data:
              value: >
                {{ 100 - state_attr('binary_sensor.pv_management_entladung_empfehlung', 'halten_soc') | int(90) }}
```

> **Note:** GoodWe uses "Depth of Discharge" (DoD) instead of SOC. The formula `100 - SOC` converts between them.

### 6. Start Appliance When Cheap

```yaml
alias: "PV: Washing machine when cheap"
trigger:
  - platform: state
    entity_id: input_boolean.washing_machine_waiting
    to: "on"
condition:
  - condition: or
    conditions:
      - condition: state
        entity_id: sensor.pv_management_verbrauchsempfehlung
        state: "dark_green"
      - condition: state
        entity_id: sensor.pv_management_verbrauchsempfehlung
        state: "green"
action:
  - service: switch.turn_on
    target:
      entity_id: switch.washing_machine_socket
  - service: input_boolean.turn_off
    target:
      entity_id: input_boolean.washing_machine_waiting
```

---

## Dashboard Examples

### Amortization

```yaml
type: entities
title: PV Amortization
entities:
  - entity: sensor.pv_management_status
  - entity: sensor.pv_management_amortisation
  - entity: sensor.pv_management_gesamtersparnis
  - entity: sensor.pv_management_restbetrag
  - entity: sensor.pv_management_restlaufzeit
  - type: divider
  - entity: sensor.pv_management_eigenverbrauch
  - entity: sensor.pv_management_einspeisung
  - entity: sensor.pv_management_eigenverbrauchsquote
  - type: divider
  - entity: sensor.pv_management_ersparnis_pro_monat
  - entity: sensor.pv_management_co2_ersparnis
```

### Energy Benchmark

```yaml
type: entities
title: Energy Benchmark
entities:
  - entity: sensor.pv_management_benchmark_effizienz_score
  - entity: sensor.pv_management_benchmark_bewertung
  - type: divider
  - entity: sensor.pv_management_benchmark_eigener_verbrauch
  - entity: sensor.pv_management_benchmark_durchschnitt
  - entity: sensor.pv_management_benchmark_vergleich
  - type: divider
  - entity: sensor.pv_management_benchmark_co2_vermieden
```

### Daily Costs

```yaml
type: entities
title: Electricity Costs Today
entities:
  - entity: sensor.pv_management_netzbezug_heute
  - entity: sensor.pv_management_einspeisung_heute
  - entity: sensor.pv_management_stromkosten_netto_heute
```

---

## Events (Notifications)

The integration fires `pv_management_event` events for custom automations:

### Milestone Events (25%, 50%, 75%, 100%)

```yaml
trigger:
  - platform: event
    event_type: pv_management_event
    event_data:
      type: amortisation_milestone
action:
  - service: notify.mobile_app
    data:
      title: "PV Milestone!"
      message: "{{ trigger.event.data.message }}"
```

### Monthly Summary

```yaml
trigger:
  - platform: event
    event_type: pv_management_event
    event_data:
      type: monthly_summary
action:
  - service: notify.mobile_app
    data:
      title: "PV Monthly Report"
      message: "{{ trigger.event.data.message }}"
```

---

## Comparison: pv_management vs pv_management_fix

| Feature | pv_management (Spot) | pv_management_fix (Fixed) |
|---------|:--------------------:|:-------------------------:|
| Amortization | Yes | Yes |
| Energy Tracking | Yes | Yes |
| **Energy Benchmark** | **Yes** | **Yes** |
| **Recommendation Signal** | **Yes** (5-level) | No |
| **Auto-Charge** | **Yes** | No |
| **Discharge Control** | **Yes** | No |
| **EPEX Quantile** | **Yes** | No |
| **Solcast** | **Yes** | No |
| Battery Tracking | No | **Yes** |
| ROI Calculation | No | **Yes** |
| Electricity Quota | No | **Yes** |
| Spot Comparison | Yes | Yes (optional) |

For **fixed-price tariffs** with battery tracking, ROI, and electricity quota:
[pv_management_fix](https://github.com/hoizi89/pv_management_fix)

---

## Changelog

### v3.21.0
- **NEW: Energy Benchmark** — Compare with DACH averages (AT/DE/CH), CO2 savings, efficiency score 0-100
- **NEW: Heat Pump** — Optional HP sensor for fair benchmark comparison

### v3.20.0
- Improved sensor robustness and stability

### v3.17.0
- **NEW: Helper Sync** — Required input_number for persistent savings storage
- **NEW: Milestone Events** — Automatic events at 25%, 50%, 75%, 100% amortization
- **NEW: Monthly Summary** — Event on 1st of each month with statistics
- **NEW: GoodWe Examples** — Automation examples for GoodWe inverters

### v3.16.0
- Helper sync prepared (base integration)

### v3.15.1
- Battery Target-SOC unified
- Discharge Control improved

### v3.0.0
- Auto-Charge feature
- Discharge Control feature
- EPEX Quantile integration
- Solcast integration

### v2.0.0
- Consumption recommendation traffic light
- Battery integration
- PV forecast integration

### v1.0.0
- Initial release

---

## Support

[Report issues](https://github.com/hoizi89/pv_management/issues) | [Discussions](https://github.com/hoizi89/pv_management/discussions)

## License

MIT License — see [LICENSE](LICENSE)
