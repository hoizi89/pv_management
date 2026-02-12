# PV Management

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hoizi89/pv_management)](https://github.com/hoizi89/pv_management/releases)

Home Assistant integration for **variable electricity tariffs** (spot tariffs like aWATTar, smartENERGY, Tibber) with **intelligent battery management**.

> **For fixed-price tariffs** (e.g. Gruenwelt, Energie AG) there's a simplified version:
> [pv_management_fix](https://github.com/hoizi89/pv_management_fix)

## Features

### Battery Management
- **Auto-Charge** - Automatically charge battery when electricity is cheap
- **Discharge Control** - Save battery for expensive hours
- **EPEX Spot Integration** - Uses current market prices
- **Solcast Integration** - Considers PV forecast
- **Winter Mode** - Automatic adjustment Oct-Mar

### Consumption Recommendation (Traffic Light)
- **5-level traffic light** - From dark green to red
- **Based on:**
  - Current EPEX Spot price + quantile
  - Battery state of charge
  - PV power & forecast
  - Time of day (winter base load)

### Amortization
- **Incremental calculation** - Correct for dynamic prices
- **Persistent storage** - Data survives restarts
- **Helper sync** - Stores values in input_number for maximum persistence
- **Fixed price comparison** - Shows savings vs. fixed tariff

### Notifications (Events)
- **Milestone events** - Automatic events at 25%, 50%, 75%, 100% amortization
- **Monthly summary** - Event on 1st of each month with statistics
- Events can be used for custom automations (`pv_management_event`)

### Statistics
- Savings per day/month/year
- Average electricity price (weighted)
- CO2 savings
- Self-consumption ratio & autarky rate

## Installation

### HACS (recommended)

1. Open HACS > Integrations > 3-dot menu > **Custom repositories**
2. Enter URL: `https://github.com/hoizi89/pv_management`
3. Category: **Integration**
4. Search for "PV Management" and install
5. **Restart** Home Assistant

### Manual

1. Copy `custom_components/pv_management` folder to `config/custom_components/`
2. Restart Home Assistant

## Configuration

### Required Sensors
| Sensor | Description |
|--------|-------------|
| **PV Production** | Total PV production in kWh |

### Recommended Sensors
| Sensor | Description |
|--------|-------------|
| **EPEX Spot Price** | Current electricity price (e.g. from EPEX Spot integration) |
| **EPEX Quantile** | Relative position in daily range (0-1) |
| **Battery SOC** | Current state of charge in % |
| **Solcast Forecast** | PV forecast for today in kWh |

### Battery Control (Options)
| Setting | Default | Description |
|---------|---------|-------------|
| **Target SOC** | 100% | Charge battery up to this level |
| **Auto-Charge Quantile** | 0.3 | Charge when price is in cheapest 30% |
| **Min. Price Difference** | 15 ct | Only charge when spread is large enough |
| **Discharge Quantile** | 0.7 | Discharge only in most expensive 30% |
| **Winter Mode** | On | Only active Oct-Mar |

---

## Example Automations

### 1. Charge Battery When Cheap (Auto-Charge)

```yaml
alias: "PV: Charge battery when cheap"
description: "Charges battery from grid when electricity is cheap"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    to: "on"
action:
  - service: number.set_value
    target:
      entity_id: number.battery_charge_power  # Your inverter
    data:
      value: 3000  # 3kW charge power
  - service: switch.turn_on
    target:
      entity_id: switch.battery_grid_charge  # Your inverter
  - service: notify.mobile_app
    data:
      message: "Battery charging (cheap electricity: {{ states('sensor.epex_spot_at_price') }} ct/kWh)"
mode: single
```

### 2. Stop Battery Charging

```yaml
alias: "PV: Stop battery charging"
description: "Stops grid charging when no longer recommended"
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
mode: single
```

### 3. Limit Battery Discharge for Expensive Hours

```yaml
alias: "PV: Save battery for expensive hours"
description: "Prevents discharge during cheap hours (save for later)"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_entladung_begrenzen
    to: "on"
action:
  - service: number.set_value
    target:
      entity_id: number.battery_discharge_limit  # Min SOC on inverter
    data:
      value: "{{ states('sensor.pv_management_halte_soc') }}"  # e.g. 80%
  - service: notify.mobile_app
    data:
      message: "Battery saved for expensive hours (Hold SOC: {{ states('sensor.pv_management_halte_soc') }}%)"
mode: single
```

### 4. Release Battery Discharge

```yaml
alias: "PV: Release battery discharge"
description: "Releases battery when electricity is expensive"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_entladung_begrenzen
    to: "off"
action:
  - service: number.set_value
    target:
      entity_id: number.battery_discharge_limit
    data:
      value: 10  # Normal discharge limit (10%)
mode: single
```

### 5. Complete Battery Automation (Blueprint-Style)

```yaml
alias: "PV: Intelligent Battery Management"
description: "Combines Auto-Charge and Discharge Control"
trigger:
  - platform: state
    entity_id:
      - binary_sensor.pv_management_auto_charge_empfohlen
      - binary_sensor.pv_management_entladung_begrenzen
action:
  - choose:
      # Activate Auto-Charge
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "on"
        sequence:
          - service: script.battery_grid_charge_start
            data:
              power: "{{ states('sensor.pv_management_auto_charge_leistung') | int }}"
              target_soc: "{{ states('sensor.pv_management_ziel_soc') | int }}"

      # Limit discharge (save battery)
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_entladung_begrenzen
            state: "on"
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "off"
        sequence:
          - service: script.battery_set_hold_soc
            data:
              soc: "{{ states('sensor.pv_management_halte_soc') | int }}"

      # Normal operation (no auto-charge, no limit)
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "off"
          - condition: state
            entity_id: binary_sensor.pv_management_entladung_begrenzen
            state: "off"
        sequence:
          - service: script.battery_normal_operation
mode: restart
```

### 6. Start Washing Machine When Cheap

```yaml
alias: "PV: Washing machine when cheap"
description: "Starts washing machine when traffic light is green"
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
  - service: notify.mobile_app
    data:
      message: "Washing machine started - electricity is cheap!"
mode: single
```

---

## GoodWe Inverter Examples

### 7. GoodWe Auto-Charge (Grid Charging)

```yaml
alias: "PV: GoodWe Auto-Charge"
description: "Charges GoodWe battery from grid when electricity is cheap"
triggers:
  - entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    trigger: state
conditions: []
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
mode: single
```

### 8. GoodWe Discharge Control

```yaml
alias: "PV: GoodWe Discharge Control"
description: "Controls depth of discharge based on electricity price"
triggers:
  - entity_id: binary_sensor.pv_management_entladung_empfehlung
    trigger: state
  - entity_id: switch.pv_management_entlade_steuerung
    trigger: state
actions:
  - choose:
      # Summer mode or control disabled -> standard discharge
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
          - action: select.select_option
            target:
              entity_id: select.goodwe_inverter_operation_mode
            data:
              option: general
      # Discharge recommended -> allow battery discharge
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
          - action: select.select_option
            target:
              entity_id: select.goodwe_inverter_operation_mode
            data:
              option: general
      # Don't discharge -> save battery
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
          - action: select.select_option
            target:
              entity_id: select.goodwe_inverter_operation_mode
            data:
              option: general
mode: single
```

> **Note:** GoodWe uses "Depth of Discharge" (DoD) instead of SOC. The formula `100 - SOC` converts between them.

---

## Sensors

### Main Sensors
| Sensor | Description |
|--------|-------------|
| **Consumption Recommendation** | 5-level traffic light (dark_green/green/yellow/orange/red) |
| **Next Cheap Hour** | When is the next cheap time slot |
| **Auto-Charge Recommended** | Binary sensor for automation |
| **Limit Discharge** | Binary sensor for automation |
| **Target SOC** | Current target state of charge |
| **Hold SOC** | Minimum SOC during hold phase |

### Amortization
| Sensor | Description |
|--------|-------------|
| **Amortization** | Percentage paid off |
| **Total Savings** | EUR saved |
| **Remaining Amount** | EUR until amortization |
| **Spot vs Fixed** | Savings vs. fixed price |

### Statistics
| Sensor | Description |
|--------|-------------|
| **Average Price** | Weighted average electricity price |
| **Savings per Day/Month/Year** | Average values |
| **CO2 Savings** | kg CO2 saved |

---

## Comparison: pv_management vs pv_management_fix

| Feature | pv_management | pv_management_fix |
|---------|:-------------:|:-----------------:|
| **Target** | Spot tariffs | Fixed-price tariffs |
| Amortization | Yes | Yes |
| Energy Tracking | Yes | Yes |
| **Recommendation Signal** | Yes (5-level) | No |
| **Auto-Charge** | Yes | No |
| **Discharge Control** | Yes | No |
| **EPEX Quantile** | Yes | No |
| **Solcast** | Yes | No |
| **Electricity Quota** | No | Yes |
| Spot Comparison | Yes | Yes (optional) |

---

## Events (Notifications)

The integration fires `pv_management_event` events for custom automations:

### Milestone Events
```yaml
event_type: pv_management_event
event_data:
  type: "amortisation_milestone"  # or "amortisation_complete"
  milestone: 50  # 25, 50, 75, 100
  total_savings: 3500.00
  remaining: 3500.00
  installation_cost: 7000.00
  message: "50% of PV system amortized!"
```

### Monthly Summary
```yaml
event_type: pv_management_event
event_data:
  type: "monthly_summary"
  month: "January 2025"
  grid_import_kwh: 180.5
  grid_import_cost: 32.50
  amortisation_percent: 52.3
  total_savings: 3661.00
  message: "PV report January 2025: 180 kWh grid import, 52.3% amortized"
```

### Example Automation

```yaml
alias: "PV Milestone Notification"
trigger:
  - platform: event
    event_type: pv_management_event
    event_data:
      type: amortisation_milestone
action:
  - service: notify.mobile_app
    data:
      title: "PV Milestone reached!"
      message: "{{ trigger.event.data.message }}"
```

---

## Changelog

### v3.17.0
- **NEW: Helper Sync** - Required input_number for persistent savings storage
- **NEW: Milestone Events** - Automatic events at 25%, 50%, 75%, 100% amortization
- **NEW: Monthly Summary** - Event on 1st of each month with statistics
- **NEW: GoodWe Examples** - Automation examples for GoodWe inverters

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
- Amortization calculation

## Support

[Report issues](https://github.com/hoizi89/pv_management/issues)

## License

MIT License - see [LICENSE](LICENSE)
