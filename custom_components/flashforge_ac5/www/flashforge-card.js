const DOMAIN = "flashforge_ac5";
const TRANSLATIONS = {
  de: {
    status: "Druckstatus", temperatures: "Temperaturen", filament: "Filament & Statistik",
    sensors: "Weitere Sensoren", camera: "Live-Kamera", controls: "Steuerung",
    pause: "Pausieren", resume: "Fortsetzen", cancel: "Abbrechen",
    clear: "Plattform freigeben", home: "Achsen referenzieren", refresh: "Kamera aktualisieren",
    confirmCancel: "Soll der aktuelle Druck wirklich abgebrochen werden?",
    confirmClear: "Soll die Druckplattform freigegeben werden?",
    confirmHome: "Sollen die Druckerachsen referenziert werden?",
    select: "FlashForge-Drucker", choose: "Drucker auswählen", loadingDevices: "Drucker werden geladen …",
    noDevices: "Keine FlashForge-Drucker gefunden.", selectDevice: "Bitte in der Kartenkonfiguration einen FlashForge-Drucker auswählen.",
    loading: "Drucker-Entitäten werden geladen …", notFound: "Der ausgewählte FlashForge-Drucker wurde nicht gefunden.",
    noEntities: "Für diesen Drucker wurden keine aktiven Entitäten gefunden.",
    noBubble: "Bubble Card ist nicht geladen. Bitte die Dashboard-Ressource prüfen.",
    loadDevicesError: "Drucker konnten nicht geladen werden", subscribeError: "Registrierung konnte nicht abonniert werden",
    loadEntitiesError: "Drucker-Entitäten konnten nicht geladen werden", ambiguous: "Mehrdeutige Entität",
  },
  en: {
    status: "Print status", temperatures: "Temperatures", filament: "Filament & statistics",
    sensors: "Other sensors", camera: "Live camera", controls: "Controls",
    pause: "Pause", resume: "Resume", cancel: "Cancel",
    clear: "Clear platform", home: "Home axes", refresh: "Refresh camera",
    confirmCancel: "Cancel the current print?", confirmClear: "Clear the print platform?",
    confirmHome: "Home the printer axes?",
    select: "FlashForge printer", choose: "Select a printer", loadingDevices: "Loading printers …",
    noDevices: "No FlashForge printers found.", selectDevice: "Select a FlashForge printer in the card settings.",
    loading: "Loading printer entities …", notFound: "The selected FlashForge printer was not found.",
    noEntities: "No active entities were found for this printer.",
    noBubble: "Bubble Card is not loaded. Check the dashboard resource.",
    loadDevicesError: "Could not load printers", subscribeError: "Could not subscribe to registry changes",
    loadEntitiesError: "Could not load printer entities", ambiguous: "Ambiguous entity",
  },
  ru: {
    status: "Состояние печати", temperatures: "Температуры", filament: "Филамент и статистика",
    sensors: "Другие датчики", camera: "Камера", controls: "Управление",
    pause: "Пауза", resume: "Продолжить", cancel: "Отменить",
    clear: "Освободить платформу", home: "Парковка осей", refresh: "Обновить камеру",
    confirmCancel: "Отменить текущую печать?", confirmClear: "Освободить платформу?",
    confirmHome: "Выполнить парковку осей?",
    select: "Принтер FlashForge", choose: "Выберите принтер", loadingDevices: "Загрузка принтеров …",
    noDevices: "Принтеры FlashForge не найдены.", selectDevice: "Выберите принтер FlashForge в настройках карточки.",
    loading: "Загрузка сущностей принтера …", notFound: "Выбранный принтер FlashForge не найден.",
    noEntities: "Для этого принтера не найдены активные сущности.",
    noBubble: "Bubble Card не загружена. Проверьте ресурс панели.",
    loadDevicesError: "Не удалось загрузить принтеры", subscribeError: "Не удалось подписаться на изменения реестра",
    loadEntitiesError: "Не удалось загрузить сущности принтера", ambiguous: "Неоднозначная сущность",
  },
};

function text(hass, key) {
  const language = (hass?.locale?.language || hass?.language || "en").split("-")[0];
  return (TRANSLATIONS[language] || TRANSLATIONS.en)[key];
}

const GROUPS = [
  {
    title: "status",
    icon: "mdi:printer-3d",
    keys: [
      "machine_state", "print_progress", "remaining_time", "print_file",
      "current_layer", "total_layers", "print_eta", "print_duration",
      "print_speed", "printing", "paused",
    ],
  },
  {
    title: "temperatures",
    icon: "mdi:thermometer",
    keys: [
      "nozzle_temperature", "nozzle_target_temperature", "bed_temperature",
      "bed_target_temperature", "chamber_temperature",
    ],
    tools: true,
  },
  {
    title: "filament",
    icon: "mdi:filament",
    keys: [
      "filament_type", "estimated_filament_length", "estimated_filament_weight",
      "total_filament_used", "total_print_time",
    ],
  },
  {
    title: "sensors",
    icon: "mdi:information-outline",
    keys: ["light_status", "camera_available", "door", "problem", "error_code", "tvoc"],
  },
];

const ACTIONS = [
  ["pause_print", "pause", "mdi:pause"],
  ["resume_print", "resume", "mdi:play"],
  ["cancel_print", "cancel", "mdi:stop", "confirmCancel"],
  ["clear_platform", "clear", "mdi:delete-sweep", "confirmClear"],
  ["home_axes", "home", "mdi:axis-arrow", "confirmHome"],
  ["refresh_camera", "refresh", "mdi:camera-retake"],
];

function printerEntries(device) {
  return (device?.identifiers || [])
    .filter(([domain]) => domain === DOMAIN)
    .map(([, entryId]) => entryId);
}

function findEntities(device, registry, states, hass) {
  const entryIds = new Set(printerEntries(device));
  const result = {};
  for (const entity of registry) {
    if (
      entity.device_id !== device.id || entity.platform !== DOMAIN ||
      entity.disabled_by || !states[entity.entity_id] ||
      !entryIds.has(entity.config_entry_id)
    ) continue;
    const prefix = `${entity.config_entry_id}_`;
    if (!entity.unique_id?.startsWith(prefix)) continue;
    const key = entity.unique_id.slice(prefix.length);
    if (result[key]) throw new Error(`${text(hass, "ambiguous")}: ${key}`);
    result[key] = entity.entity_id;
  }
  return result;
}

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

class FlashForgeCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loading && !this._devices && !this._error) this._loadDevices();
  }

  async _loadDevices() {
    this._loading = true;
    try {
      this._devices = await this._hass.callWS({ type: "config/device_registry/list" });
      this._error = undefined;
    } catch (error) {
      this._error = `${text(this._hass, "loadDevicesError")}: ${error.message}`;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.replaceChildren();
    if (this._error) {
      this.shadowRoot.append(element("p", this._error));
      return;
    }
    const label = element("label", text(this._hass, "select"));
    const select = element("select");
    select.style.cssText = "display:block;width:100%;padding:12px;margin-top:8px";
    const printers = (this._devices || []).filter((device) => printerEntries(device).length);
    const placeholder = element("option", text(this._hass,
      !this._devices ? "loadingDevices" : printers.length ? "choose" : "noDevices"));
    placeholder.value = "";
    select.append(placeholder);
    for (const device of printers) {
      const option = element("option", device.name_by_user || device.name || device.id);
      option.value = device.id;
      select.append(option);
    }
    select.value = this._config.device_id || "";
    select.addEventListener("change", () => {
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: { ...this._config, device_id: select.value } },
        bubbles: true,
        composed: true,
      }));
    });
    label.append(select);
    this.shadowRoot.append(label);
  }
}

class FlashForgeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._children = [];
    this._registry = null;
    this._devices = null;
    this._loadGeneration = 0;
    this._connectionGeneration = 0;
  }

  static getConfigElement() {
    return document.createElement("flashforge-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    if (config.device_id && typeof config.device_id !== "string") {
      throw new Error("device_id muss eine Geräte-ID sein");
    }
    this._config = config;
    this._signature = undefined;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started && this.isConnected) this._start();
    this._update();
  }

  connectedCallback() {
    if (this._hass && !this._started) this._start();
  }

  disconnectedCallback() {
    this._started = false;
    this._connectionGeneration++;
    this._loadGeneration++;
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = undefined;
  }

  async _start() {
    this._started = true;
    const generation = this._connectionGeneration;
    try {
      const unsubscribe = await this._hass.connection.subscribeEvents(
        () => this._loadRegistry(), "entity_registry_updated"
      );
      if (!this._started || generation !== this._connectionGeneration) {
        unsubscribe();
        return;
      }
      this._unsubscribe = unsubscribe;
      await this._loadRegistry();
    } catch (error) {
      if (this._started && generation === this._connectionGeneration) {
        this._error = `${text(this._hass, "subscribeError")}: ${error.message}`;
        this._update();
      }
    }
  }

  async _loadRegistry() {
    const generation = ++this._loadGeneration;
    try {
      const [devices, registry, helpers] = await Promise.all([
        this._hass.callWS({ type: "config/device_registry/list" }),
        this._hass.callWS({ type: "config/entity_registry/list" }),
        window.loadCardHelpers(),
      ]);
      if (!this._started || generation !== this._loadGeneration) return;
      this._devices = devices;
      this._registry = registry;
      this._helpers = helpers;
      this._error = undefined;
      this._signature = undefined;
      this._update();
    } catch (error) {
      if (this._started && generation === this._loadGeneration) {
        this._error = `${text(this._hass, "loadEntitiesError")}: ${error.message}`;
        this._update();
      }
    }
  }

  _showError(message) {
    this._children = [];
    this._signature = undefined;
    const card = element("ha-card");
    const text = element("p", message);
    text.style.padding = "16px";
    card.append(text);
    this.shadowRoot.replaceChildren(card);
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._config.device_id) {
      this._showError(text(this._hass, "selectDevice"));
      return;
    }
    if (this._error) {
      this._showError(this._error);
      return;
    }
    if (!this._registry || !this._devices || !this._helpers) {
      this._showError(text(this._hass, "loading"));
      return;
    }
    const device = this._devices.find((item) => item.id === this._config.device_id);
    if (!device || !printerEntries(device).length) {
      this._showError(text(this._hass, "notFound"));
      return;
    }
    if (!customElements.get("bubble-card")) {
      this._showError(text(this._hass, "noBubble"));
      if (!this._waitingForBubble) {
        this._waitingForBubble = true;
        customElements.whenDefined("bubble-card").then(() => {
          this._waitingForBubble = false;
          this._signature = undefined;
          this._update();
        });
      }
      return;
    }
    let entities;
    try {
      entities = findEntities(device, this._registry, this._hass.states, this._hass);
    } catch (error) {
      this._showError(error.message);
      return;
    }
    if (!Object.keys(entities).length) {
      this._showError(text(this._hass, "noEntities"));
      return;
    }
    const signature = JSON.stringify([device.id, entities, this._hass.locale?.language || this._hass.language]);
    if (signature !== this._signature) {
      this._signature = signature;
      this._render(entities);
    }
    for (const child of this._children) child.hass = this._hass;
  }

  _makeCard(config) {
    const card = this._helpers.createCardElement(config);
    this._children.push(card);
    return card;
  }

  _separator(title, icon) {
    return this._makeCard({ type: "custom:bubble-card", card_type: "separator", name: title, icon });
  }

  _render(entities) {
    this._children = [];
    const style = element("style");
    style.textContent = `
      :host { display:block; }
      .shell { container-type:inline-size; }
      .layout { display:grid; grid-template-columns:minmax(210px,1fr) minmax(0,2fr) minmax(210px,1fr); gap:12px; }
      .column { min-width:0; display:flex; flex-direction:column; gap:8px; }
      .controls { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:8px; }
      .sensor-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr)); gap:8px; }
      .wide { grid-column:1 / -1; }
      @container (max-width: 900px) { .layout { grid-template-columns:1fr; } .control-section { order:-2; } .camera { order:-1; } }
    `;
    const layout = element("div");
    layout.className = "layout";
    const left = element("div");
    left.className = "column";
    const camera = element("div");
    camera.className = "column camera";
    const right = element("div");
    right.className = "column";
    const controlSection = element("div");
    controlSection.className = "column wide control-section";
    const otherSensors = element("div");
    otherSensors.className = "column wide";

    if (entities.camera) {
      camera.append(
        this._separator(text(this._hass, "camera"), "mdi:video"),
        this._makeCard({
          type: "picture-entity", entity: entities.camera, camera_view: "live",
          show_name: false, show_state: false,
        })
      );
    }

    GROUPS.forEach((group, index) => {
      const keys = [...group.keys];
      if (group.tools) {
        keys.push(...Object.keys(entities)
          .filter((key) => /^nozzle_\d+_(target_)?temperature$/.test(key))
          .sort((a, b) => a.localeCompare(b, undefined, { numeric: true })));
      }
      const available = keys.filter((key) => entities[key]);
      if (!available.length) return;
      const column = group.title === "sensors" ? otherSensors : index === 0 ? left : right;
      column.append(this._separator(text(this._hass, group.title), group.icon));
      const cards = group.title === "sensors" ? element("div") : column;
      if (cards !== column) {
        cards.className = "sensor-grid";
        column.append(cards);
      }
      for (const key of available) {
        cards.append(this._makeCard({
          type: "custom:bubble-card", card_type: "button", button_type: "state",
          entity: entities[key], scrolling_effect: true,
        }));
      }
    });

    const switches = ["led", "internal_filtration"].filter((key) => entities[key]);
    const actions = ACTIONS.filter(([key]) => entities[key]);
    if (switches.length || actions.length) {
      controlSection.append(this._separator(text(this._hass, "controls"), "mdi:tune-variant"));
      const controls = element("div");
      controls.className = "controls";
      for (const key of switches) {
        controls.append(this._makeCard({
          type: "button", entity: entities[key], show_state: true,
          tap_action: { action: "toggle" },
        }));
      }
      for (const [key, name, icon, confirmation] of actions) {
        const tapAction = {
          action: "perform-action",
          perform_action: "button.press",
          target: { entity_id: entities[key] },
        };
        if (confirmation) tapAction.confirmation = { text: text(this._hass, confirmation) };
        controls.append(this._makeCard({
          type: "button", entity: entities[key], name: text(this._hass, name), icon, tap_action: tapAction,
        }));
      }
      controlSection.append(controls);
    }
    layout.append(controlSection, left, camera, right);
    if (otherSensors.children.length) layout.append(otherSensors);
    const shell = element("div");
    shell.className = "shell";
    shell.append(layout);
    this.shadowRoot.replaceChildren(style, shell);
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }
}

if (!customElements.get("flashforge-card-editor")) {
  customElements.define("flashforge-card-editor", FlashForgeCardEditor);
}
if (!customElements.get("flashforge-card")) {
  customElements.define("flashforge-card", FlashForgeCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "flashforge-card")) {
  window.customCards.push({
    type: "flashforge-card",
    name: "FlashForge Drucker",
    description: "Kamera, Sensoren und Steuerung eines FlashForge-Druckers.",
  });
}
