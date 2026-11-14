# FlashForge 3D Printer – Integration für Home Assistant

> **Hinweis: Dieses Repository ist ein Fork** von
> [kruzhkov/flashforge_3d](https://github.com/kruzhkov/flashforge_3d).
> Es wird unabhängig vom ursprünglichen Repository weiterentwickelt.

Benutzerdefinierte Integration für FlashForge-3D-Drucker (Adventurer 5M / 5M Pro, AD5X, Creator 5 / Creator 5 Pro).
Sie arbeitet lokal ohne Cloud und bietet Statusabfragen, Drucksteuerung und den Videostream der Druckerkamera.

<img src="example.png" width="500" alt="Beispielansicht">

## Sicherheit und Hardening

Dieser Fork enthält eine Absicherung gegen Server-Side Request Forgery (SSRF) bei der Kamera:

* Als Stream-URL wird nur die HTTP-Adresse des konfigurierten Druckers auf Port 8080 mit dem Pfad `/?action=stream` akzeptiert. Andere vom Drucker gemeldete URLs werden ignoriert.
* HTTP-Weiterleitungen werden bei der Kameraerkennung, beim Stream und beim Abrufen von Einzelbildern nicht verfolgt.

Die Kamera kommuniziert weiterhin über unverschlüsseltes HTTP im lokalen Netzwerk.

## Funktionen

**Sensorwerte und Druckfortschritt**

| Entität | Typ | Beschreibung |
| --- | --- | --- |
| `sensor.status` | enum | Druckerstatus: `ready`, `printing`, `paused`, `error`, … |
| `sensor.print_progress` | % | Fortschritt des aktuellen Drucks |
| `sensor.current_layer` / `sensor.total_layers` | Zahl | Aktuelle und gesamte Schichtzahl |
| `sensor.remaining_time` | min | Verbleibende Zeit laut Firmware |
| `sensor.estimated_finish` | timestamp | Geschätzter Fertigstellungszeitpunkt |
| `sensor.printing_file` | Text | Name der gedruckten Datei |
| `sensor.nozzle_temperature` / `nozzle_target_temperature` | °C | Ist- und Solltemperatur der Düse (Modelle mit einer Düse) |
| `sensor.nozzle_<n>_temperature` / `nozzle_<n>_target_temperature` | °C | Ist- und Solltemperatur jeder Düse (Modelle mit mehreren Düsen) |
| `sensor.bed_temperature` / `bed_target_temperature` | °C | Ist- und Solltemperatur des Druckbetts |
| `sensor.chamber_temperature` | °C | Temperatur des Bauraums (nur Modelle mit Sensor) |
| `sensor.filament_used_length` / `filament_used_weight` | m / g | Filamentverbrauch des aktuellen Drucks |
| `sensor.total_print_time` / `total_filament_used` | h / m | Kumulierte Statistik |
| `sensor.air_quality` | µg/m³ | TVOC |
| `binary_sensor.printing`, `paused`, `problem`, `door` | binär | Schnelle Auslöser für Automatisierungen |

**Düsen bei Modellen mit mehreren Düsen (Creator 5 / Creator 5 Pro)**

Die Firmware des Creator 5 füllt die Felder `rightTemp` / `rightTargetTemp`,
aus denen die einzelne Düsenanzeige gebildet wird, nicht aus. Stattdessen liefert
sie die Arrays `nozzleTemps` / `nozzleTargetTemps` – ein Element pro Werkzeug.
Deshalb erstellt die Integration für diese Modelle ein Entitätenpaar pro Düse:

| Entität | Typ | Beschreibung |
| --- | --- | --- |
| `sensor.nozzle_1_temperature` | °C | Isttemperatur der Düse Nr. 1 |
| `sensor.nozzle_1_target_temperature` | °C | Solltemperatur der Düse Nr. 1 |
| … | °C | Entsprechend für die übrigen Düsen |

Die Anzahl der Entitäten wird anhand der tatsächlichen Länge des von der
Firmware gelieferten Temperatur-Arrays bestimmt, nicht anhand des Modellflags
oder des Felds `nozzleCnt`. Das verhindert zwei Fehler: Das Modellflag wird aus
dem Druckernamen abgeleitet und kann beim Umbenennen fehlschlagen. Außerdem kann
`nozzleCnt` mehr Steckplätze melden, als die Firmware tatsächlich liefert –
einige Entitäten wären dann dauerhaft nicht verfügbar. Beim Creator 5 ergibt
dies vier Entitätenpaare.

Die einzelnen Entitäten `sensor.nozzle_temperature` und
`sensor.nozzle_target_temperature` werden nur angezeigt, wenn der Drucker
höchstens ein Werkzeug meldet. Bei Modellen mit mehreren Düsen würden sie immer
einen leeren Wert liefern. Beide Regeln basieren auf demselben Array, sodass
immer genau ein Satz von Entitäten aktiv ist. Für Modelle mit einer Düse bleibt
das Verhalten unverändert.

Die `unique_id` einer Entität ist an die Reihenfolge des Werkzeugs gebunden,
sodass Verlauf und Einstellungen zwischen Neustarts erhalten bleiben.

**Kamera-Videostream**

Die Druckerkamera (MJPEG, Port 8080) wird als standardmäßige `camera`-Entität
bereitgestellt. Der Stream wird unverändert und ohne Neukodierung an den
Browser weitergegeben: Die Integration deklariert `CameraEntityFeature.STREAM`
nicht, sodass Home Assistant weder `ffmpeg` startet noch MJPEG in HLS umwandelt.
Die Verzögerung bleibt innerhalb eines Einzelbilds, und die CPU wird nicht durch
Transkodierung belastet.

Der Drucker bedient die Kamera mit einem einzigen Thread. Deshalb hält die
Integration genau eine Verbindung zur Kamera: Alle Betrachter (Liveansicht,
Dashboard-Vorschaubild und Benachrichtigungen) erhalten Bilder über einen
gemeinsamen Leser. Wenn keine Betrachter vorhanden sind, wird die Verbindung nach
einer Leerlaufzeit geschlossen.

Die Stream-URL wird aus der Antwort von `/detail` übernommen, sofern sie den
oben beschriebenen Sicherheitsvorgaben entspricht. Meldet die Firmware keine
zulässige URL, wird die Adresse bei der Einrichtung einmalig durch eine
Netzwerkprüfung ermittelt. Die Schaltfläche „Videostream aktualisieren“ wiederholt
diese Prüfung manuell. Eine fehlgeschlagene Prüfung wird zehn Minuten lang
zwischengespeichert, damit die regelmäßige Sensorabfrage nicht verzögert wird.

**Steuerung**

* `button.pause_print`, `button.resume_print`, `button.cancel_print`
* `button.clear_platform`, `button.home_axes`, `button.refresh_camera_stream`
* `switch.light` (Modelle mit Beleuchtung), `switch.filtration`, `switch.camera`

## Installation

### HACS (als benutzerdefiniertes Repository)

1. Öffne Einstellungen → Marketplace → **Benutzerdefinierte Repositories** (HACS → **Integrationen** → Menü → **Benutzerdefinierte Repositories**).
2. Füge die URL dieses Forks hinzu: `https://github.com/ChristianKirchnerIlmenau/flashforge_3d`. Wähle die Kategorie *Integration*.
3. Installiere **FlashForge 3D Printer** und starte Home Assistant neu.

### Manuell

Kopiere das Verzeichnis `custom_components/flashforge_ac5` nach
`<Konfiguration>/custom_components/flashforge_ac5` und starte Home Assistant neu.

## Einrichtung

Die Integration bietet Texte auf Deutsch, Englisch und Russisch.

> **Hinweis zum Adventurer 5M (Firmware 5.1.7-2.2.3):**
> Aktiviere am Drucker unter **Einstellungen → Netzwerkmodus** den Schalter
> **Nur LAN**. Ohne diesen Modus schlug die Verbindung auch mit dem richtigen
> Prüfcode fehl. Die im selben Menü angezeigte **Drucker-ID** bzw. Geräte-ID
> ist der Prüfcode für die Einrichtung in Home Assistant.
>
> Im Modus **Nur LAN** sind externe Netzwerkverbindungen und Cloud-Dienste
> des Druckers nicht verfügbar.

1. Öffne **Einstellungen → Geräte & Dienste → Integration hinzufügen → FlashForge 3D Printer**.
2. Fülle die Felder aus:
   * **Host / IP-Adresse** – Adresse des Druckers im lokalen Netzwerk;
   * **Seriennummer** – auf dem Druckerdisplay unter `Einstellungen → Netzwerk → LAN-Modus`;
   * **Prüfcode** – im Netzwerkmenü des Druckers zu finden, gegebenenfalls als
     **Drucker-ID** oder Geräte-ID bezeichnet (normalerweise acht Zeichen).
3. Weitere Einstellungen sind über **Konfigurieren** verfügbar: das
   Abfrageintervall (5–300 s, standardmäßig 20 s) und die Änderung des Prüfcodes.

Über **Ändern** lassen sich IP-Adresse und Zugangsdaten ändern, ohne die
Integration zu entfernen. Entitäten und deren Verlauf bleiben erhalten.

### Hinweis zu FlashPrint und OrcaSlicer

Beim Adventurer 5M mit Firmware 5.1.7-2.2.3 funktionierte FlashPrint im Modus
**Nur LAN** nicht: Die Übertragung wurde mit 100 % angezeigt, die Datei erschien
aber nicht auf dem Drucker und der Druck startete nicht. Mit OrcaSlicer
funktionierten Übertragung und Druck im LAN-Modus; die Druckdetails wurden auch
in Home Assistant angezeigt. Bei diesem Fehler kann ein Wechsel zu OrcaSlicer
helfen. Das Verhalten kann je nach FlashPrint-Version und Druckermodell variieren.

## Voraussetzungen

* Home Assistant 2026.1 oder neuer
* Drucker im LAN-Modus, der aus dem Netzwerk von Home Assistant erreichbar ist
* Python-Paket [`flashforge-python-api`](https://github.com/GhostTypes/ff-5mp-api-py) – wird automatisch installiert

## Aufbau

```text
custom_components/flashforge_ac5/
├── __init__.py       # Einrichtung/Entladen, runtime_data
├── api.py            # Wrapper für flashforge-python-api, typisierte Fehler
├── coordinator.py    # DataUpdateCoordinator: eine Abfrage – ein konsistenter Snapshot
├── models.py         # PrinterSnapshot
├── entity.py         # Basisklasse: Gerät, Kennungen, Verfügbarkeit
├── config_flow.py    # Ersteinrichtung, Neukonfiguration und Optionen
├── sensor.py         # Sensorwerte und Fortschritt
├── binary_sensor.py  # Drucken, Pause, Tür, Problem
├── camera.py         # MJPEG ohne Neukodierung: ein gemeinsamer Bildleser
├── button.py         # Druck- und Wartungsbefehle
└── switch.py         # Beleuchtung und Filterung
```

Alle Entitäten lesen ihre Daten aus demselben `PrinterSnapshot`. Dadurch sind
Fortschritt, Schichtnummer und Endzeit innerhalb eines Abfragezyklus stets
konsistent. Netzwerkfehler werden in `UpdateFailed` umgewandelt und markieren
die Entitäten als nicht verfügbar, statt die letzten Werte als aktuell
auszugeben.

## Fehlerbehebung

* **„Der Drucker hat die Seriennummer oder den Prüfcode abgelehnt“** – Prüfe die
  Werte im LAN-Menü des Druckers. Nach einem Firmware-Update kann sich der
  Prüfcode ändern.
* **Entitäten sind nicht verfügbar** – Prüfe, ob der Drucker eingeschaltet ist
  und über HTTP auf Port 8898 antwortet. Verwende bei einer Änderung der
  IP-Adresse **Ändern**.
* **Keine Kameraentität** – Die Firmware meldet, dass keine Kamera vorhanden
  ist. Aktiviere die Kamera auf dem Druckerdisplay und drücke anschließend
  „Videostream aktualisieren“.
* Für Debugmeldungen ergänze die `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.flashforge_ac5: debug
      flashforge: debug
  ```

## Lizenz

Der Code der Integration steht unter der MIT-Lizenz. Auch die verwendete
Bibliothek `flashforge-python-api` steht unter der MIT-Lizenz.
