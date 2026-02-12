# PV Management

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hoizi89/pv_management)](https://github.com/hoizi89/pv_management/releases)

Home Assistant Integration für **variable Stromtarife** (Spot-Tarife wie aWATTar, smartENERGY, Tibber) mit **intelligentem Batterie-Management**.

> **Für Fixpreis-Tarife** (z.B. Grünwelt, Energie AG) gibt es eine vereinfachte Version:
> 👉 [pv_management_fix](https://github.com/hoizi89/pv_management_fix)

## Features

### Batterie-Management
- **Auto-Charge** - Batterie automatisch laden wenn Strom günstig ist
- **Discharge Control** - Batterie für teure Stunden aufsparen
- **EPEX Spot Integration** - Nutzt aktuelle Börsenpreise
- **Solcast Integration** - Berücksichtigt PV-Prognose
- **Winter-Modus** - Automatische Anpassung Okt-März

### Verbrauchsempfehlung (Ampel)
- **5-stufige Ampel** - Von dunkelgrün bis rot
- **Basiert auf:**
  - Aktueller EPEX Spot Preis + Quantile
  - Batterie-Ladestand
  - PV-Leistung & Prognose
  - Tageszeit (Winter-Grundlast)

### Amortisation
- **Inkrementelle Berechnung** - Korrekt bei dynamischen Preisen
- **Persistente Speicherung** - Daten bleiben nach Neustart
- **Helper-Sync** - Speichert Werte in input_number für maximale Persistenz
- **Fixpreis-Vergleich** - Zeigt Ersparnis gegenüber Fixpreis-Tarif

### Benachrichtigungen (Events)
- **Meilenstein-Events** - Automatische Events bei 25%, 50%, 75%, 100% Amortisation
- **Monatliche Zusammenfassung** - Event am 1. jeden Monats mit Statistiken
- Events können für eigene Automationen verwendet werden (`pv_management_event`)

### Statistiken
- Ersparnis pro Tag/Monat/Jahr
- Durchschnittlicher Strompreis (gewichtet)
- CO2-Ersparnis
- Eigenverbrauchsquote & Autarkiegrad

## Installation

### HACS (empfohlen)

1. HACS öffnen → Integrationen → 3-Punkte-Menü → **Benutzerdefinierte Repositories**
2. URL eingeben: `https://github.com/hoizi89/pv_management`
3. Kategorie: **Integration**
4. "PV Management" suchen und installieren
5. Home Assistant **neu starten**

### Manuell

1. `custom_components/pv_management` Ordner nach `config/custom_components/` kopieren
2. Home Assistant neu starten

## Konfiguration

### Pflicht-Sensoren
| Sensor | Beschreibung |
|--------|--------------|
| **PV Produktion** | Gesamte PV-Produktion in kWh |

### Empfohlene Sensoren
| Sensor | Beschreibung |
|--------|--------------|
| **EPEX Spot Preis** | Aktueller Strompreis (z.B. von EPEX Spot Integration) |
| **EPEX Quantile** | Relative Position im Tagesverlauf (0-1) |
| **Batterie SOC** | Aktueller Ladestand in % |
| **Solcast Prognose** | PV-Prognose für heute in kWh |

### Batterie-Steuerung (Options)
| Einstellung | Standard | Beschreibung |
|-------------|----------|--------------|
| **Ziel-SOC** | 100% | Batterie bis hierhin laden |
| **Auto-Charge Quantile** | 0.3 | Laden wenn Preis in günstigsten 30% |
| **Min. Preisdifferenz** | 15 ct | Nur laden wenn Spread groß genug |
| **Discharge Quantile** | 0.7 | Entladen nur in teuersten 30% |
| **Winter-Modus** | Ein | Nur Okt-März aktiv |

---

## Beispiel-Automatisierungen

### 1. Batterie laden bei günstigem Strom (Auto-Charge)

```yaml
alias: "PV: Batterie laden wenn günstig"
description: "Lädt die Batterie vom Netz wenn der Strom günstig ist"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    to: "on"
action:
  - service: number.set_value
    target:
      entity_id: number.batterie_ladeleistung  # Dein Wechselrichter
    data:
      value: 3000  # 3kW Ladeleistung
  - service: switch.turn_on
    target:
      entity_id: switch.batterie_netzladen  # Dein Wechselrichter
  - service: notify.mobile_app
    data:
      message: "Batterie wird geladen (Strom günstig: {{ states('sensor.epex_spot_at_price') }} ct/kWh)"
mode: single
```

### 2. Batterie-Laden stoppen

```yaml
alias: "PV: Batterie laden stoppen"
description: "Stoppt das Netzladen wenn nicht mehr empfohlen"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_auto_charge_empfohlen
    to: "off"
action:
  - service: switch.turn_off
    target:
      entity_id: switch.batterie_netzladen
  - service: number.set_value
    target:
      entity_id: number.batterie_ladeleistung
    data:
      value: 0
mode: single
```

### 3. Batterie-Entladung bei teurem Strom begrenzen

```yaml
alias: "PV: Batterie für teuren Strom aufsparen"
description: "Verhindert Entladung bei günstigem Strom (für später aufsparen)"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_entladung_begrenzen
    to: "on"
action:
  - service: number.set_value
    target:
      entity_id: number.batterie_entlade_grenze  # Min. SOC am Wechselrichter
    data:
      value: "{{ states('sensor.pv_management_halte_soc') }}"  # z.B. 80%
  - service: notify.mobile_app
    data:
      message: "Batterie wird für teure Stunden aufgespart (Halte-SOC: {{ states('sensor.pv_management_halte_soc') }}%)"
mode: single
```

### 4. Batterie-Entladung wieder freigeben

```yaml
alias: "PV: Batterie Entladung freigeben"
description: "Gibt die Batterie wieder frei wenn Strom teuer ist"
trigger:
  - platform: state
    entity_id: binary_sensor.pv_management_entladung_begrenzen
    to: "off"
action:
  - service: number.set_value
    target:
      entity_id: number.batterie_entlade_grenze
    data:
      value: 10  # Normale Entladegrenze (10%)
mode: single
```

### 5. Komplette Batterie-Automatisierung (Blueprint-Style)

```yaml
alias: "PV: Intelligentes Batterie-Management"
description: "Kombiniert Auto-Charge und Discharge Control"
trigger:
  - platform: state
    entity_id:
      - binary_sensor.pv_management_auto_charge_empfohlen
      - binary_sensor.pv_management_entladung_begrenzen
action:
  - choose:
      # Auto-Charge aktivieren
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "on"
        sequence:
          - service: script.batterie_netzladen_starten
            data:
              leistung: "{{ states('sensor.pv_management_auto_charge_leistung') | int }}"
              ziel_soc: "{{ states('sensor.pv_management_ziel_soc') | int }}"

      # Entladung begrenzen (Batterie aufsparen)
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_entladung_begrenzen
            state: "on"
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "off"
        sequence:
          - service: script.batterie_halte_soc_setzen
            data:
              soc: "{{ states('sensor.pv_management_halte_soc') | int }}"

      # Alles normal (kein Auto-Charge, keine Begrenzung)
      - conditions:
          - condition: state
            entity_id: binary_sensor.pv_management_auto_charge_empfohlen
            state: "off"
          - condition: state
            entity_id: binary_sensor.pv_management_entladung_begrenzen
            state: "off"
        sequence:
          - service: script.batterie_normal_betrieb
mode: restart
```

### 6. Waschmaschine bei günstigem Strom starten

```yaml
alias: "PV: Waschmaschine bei günstigem Strom"
description: "Startet Waschmaschine wenn Ampel grün ist"
trigger:
  - platform: state
    entity_id: input_boolean.waschmaschine_warten
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
      entity_id: switch.waschmaschine_steckdose
  - service: input_boolean.turn_off
    target:
      entity_id: input_boolean.waschmaschine_warten
  - service: notify.mobile_app
    data:
      message: "Waschmaschine gestartet - Strom ist günstig!"
mode: single
```

---

## Sensoren

### Haupt-Sensoren
| Sensor | Beschreibung |
|--------|--------------|
| **Verbrauchsempfehlung** | 5-stufige Ampel (dark_green/green/yellow/orange/red) |
| **Nächste günstige Stunde** | Wann ist der nächste günstige Zeitpunkt |
| **Auto-Charge Empfohlen** | Binary Sensor für Automatisierung |
| **Entladung begrenzen** | Binary Sensor für Automatisierung |
| **Ziel-SOC** | Aktueller Ziel-Ladestand |
| **Halte-SOC** | Minimaler SOC während Halte-Phase |

### Amortisation
| Sensor | Beschreibung |
|--------|--------------|
| **Amortisation** | Prozent abbezahlt |
| **Gesamtersparnis** | Euro gespart |
| **Restbetrag** | Euro bis Amortisation |
| **Spot vs Fixpreis** | Ersparnis gegenüber Fixpreis |

### Statistik
| Sensor | Beschreibung |
|--------|--------------|
| **Durchschnittspreis** | Gewichteter Ø-Strompreis |
| **Ersparnis pro Tag/Monat/Jahr** | Durchschnittswerte |
| **CO2 Ersparnis** | kg CO2 eingespart |

---

## Vergleich: pv_management vs pv_management_fix

| Feature | pv_management | pv_management_fix |
|---------|:-------------:|:-----------------:|
| **Zielgruppe** | Spot-Tarife | Fixpreis-Tarife |
| Amortisation | ✅ | ✅ |
| Energie-Tracking | ✅ | ✅ |
| **Empfehlungsampel** | ✅ 5-stufig | ❌ |
| **Auto-Charge** | ✅ | ❌ |
| **Discharge Control** | ✅ | ❌ |
| **EPEX Quantile** | ✅ | ❌ |
| **Solcast** | ✅ | ❌ |
| Spot-Vergleich | ✅ | ✅ (optional) |

---

## Events (Benachrichtigungen)

Die Integration feuert `pv_management_event` Events, die für eigene Automationen verwendet werden können:

### Meilenstein-Events
```yaml
event_type: pv_management_event
event_data:
  type: "amortisation_milestone"  # oder "amortisation_complete"
  milestone: 50  # 25, 50, 75, 100
  total_savings: 3500.00
  remaining: 3500.00
  installation_cost: 7000.00
  message: "50% der PV-Anlage amortisiert!"
```

### Monatliche Zusammenfassung
```yaml
event_type: pv_management_event
event_data:
  type: "monthly_summary"
  month: "Januar 2025"
  grid_import_kwh: 180.5
  grid_import_cost: 32.50
  amortisation_percent: 52.3
  total_savings: 3661.00
  message: "PV-Bericht Januar 2025: 180 kWh Netzbezug, 52.3% amortisiert"
```

### Beispiel-Automatisierung

```yaml
alias: "PV Meilenstein Benachrichtigung"
trigger:
  - platform: event
    event_type: pv_management_event
    event_data:
      type: amortisation_milestone
action:
  - service: notify.mobile_app
    data:
      title: "PV Meilenstein erreicht!"
      message: "{{ trigger.event.data.message }}"
```

---

## Changelog

### v3.17.0
- **NEU: Helper-Sync** - Pflicht-Input_Number für persistente Speicherung der Ersparnis
- **NEU: Meilenstein-Events** - Automatische Events bei 25%, 50%, 75%, 100% Amortisation
- **NEU: Monatliche Zusammenfassung** - Event am 1. des Monats mit Statistiken

### v3.16.0
- Helper-Sync vorbereitet (Basis-Integration)

### v3.15.1
- Batterie Target-SOC vereinheitlicht
- Discharge Control verbessert

### v3.0.0
- Auto-Charge Feature
- Discharge Control Feature
- EPEX Quantile Integration
- Solcast Integration

### v2.0.0
- Verbrauchsempfehlungs-Ampel
- Batterie-Integration
- PV-Prognose-Integration

### v1.0.0
- Initiales Release
- Amortisationsberechnung

## Support

[Issues melden](https://github.com/hoizi89/pv_management/issues)

## Lizenz

MIT License - siehe [LICENSE](LICENSE)
