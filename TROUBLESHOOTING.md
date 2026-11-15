# Fehlerbehebung

## FlashForge fehlt im Kartenkatalog

Ab Version **1.2.2** wird die Druckerkarte automatisch geladen. Eine manuelle
FlashForge-Ressource ist nicht erforderlich, auch nicht im YAML-Modus.

1. Prüfe, dass mindestens Version 1.2.2 installiert ist und die
   FlashForge-Integration eingerichtet ist.
2. Starte Home Assistant nach dem Update vollständig neu und lade die
   Browserseite neu.
3. Suche unter **Dashboard bearbeiten → Karte hinzufügen → Nach Karte** nach
   **FlashForge Drucker**, nicht in der automatisch erzeugten Geräteansicht.

Bleibt die Karte unsichtbar oder erscheint „Custom element doesn't exist“,
prüfe die Home-Assistant-Protokolle auf Fehler bei der Einrichtung von
`flashforge_ac5` und die Browserkonsole auf JavaScript-Ladefehler. Bubble Card
muss weiterhin installiert und geladen sein.

## Druckerkarte zeigt nur die normale Geräteansicht

Die **FlashForge-Druckerkarte** ist eine eigene Dashboard-Karte und nicht die
automatisch erzeugte Geräteansicht. Falls die Auswahl über den Kartenkatalog
stattdessen die gewohnte Ansicht öffnet, hat folgender Weg funktioniert:

1. Öffne dein Dashboard und wähle **Bearbeiten → Karte hinzufügen → Nach Karte
   → Manuell**.
2. Gib diese Konfiguration ein:

   ```yaml
   type: custom:flashforge-card
   ```

3. Öffne gegebenenfalls den visuellen Editor, wähle den FlashForge-Drucker aus
   und speichere die Karte.

## Karte lokal ohne neues Release testen

Bei Versionen ab 1.2.2 ersetze die Datei
`custom_components/flashforge_ac5/www/flashforge-card.js` direkt im
Home-Assistant-Konfigurationsverzeichnis. Starte Home Assistant anschließend
neu und lade die Browserseite neu. Die Integration lädt diese Datei
automatisch; füge keine zusätzliche Testressource hinzu.

Der folgende Weg über eine separate lokale Ressource gilt nur für ältere
Versionen ohne automatisches Laden:

1. Kopiere den Inhalt von
   [flashforge-card.js](custom_components/flashforge_ac5/www/flashforge-card.js)
   in die Datei `www/flashforge-card.js` deines Home-Assistant-Konfigurationsverzeichnisses.
   Im Datei-Editor kann dieses Verzeichnis beispielsweise `/homeassistant` heißen;
   dort liegt auch die `configuration.yaml`.
2. Füge unter **Einstellungen → Dashboards → Menü (⋮) → Ressourcen** die URL
   `/local/flashforge-card.js` als **JavaScript-Modul** hinzu und lade die
   Browserseite neu. Falls der `www`-Ordner neu erstellt wurde, starte Home
   Assistant einmal neu.
3. Stelle sicher, dass auch Bubble Card installiert und als Ressource geladen
   ist. Füge anschließend die Druckerkarte wie oben beschrieben manuell hinzu.

Falls Home Assistant meldet, dass `flashforge-card` nicht existiert, prüfe die
Datei und die Ressourcen-URL und lade die Browserseite erneut. Verwende nicht
gleichzeitig die lokale Testressource und die später von der Integration
bereitgestellte Ressource `/flashforge_ac5/flashforge-card.js`: Entferne beim
Umstieg die lokale Ressource, damit die Karte nicht doppelt geladen wird.

## Änderungen an der Karte erscheinen nicht

Prüfe beim lokalen Test, ob die aktuelle Datei unter
`/homeassistant/www/flashforge-card.js` gespeichert wurde. Ändere anschließend
die bestehende Ressourcen-URL beispielsweise auf
`/local/flashforge-card.js?v=2` und lade die Browserseite neu. Erhöhe die
Versionsnummer bei späteren Änderungen erneut, um eine zwischengespeicherte
Version zu umgehen. Ab Version 1.2.2 übernimmt die Integration die
Versionierung ihrer Ressource selbst; entferne alte manuelle
FlashForge-Ressourcen und teste stattdessen wie oben durch direktes Ersetzen
der Integrationsdatei.
