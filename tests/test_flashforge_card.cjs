const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor() {
    this.children = [];
    this.style = {};
    this.isConnected = true;
    this.listeners = {};
  }
  attachShadow() { this.shadowRoot = new Element(); return this.shadowRoot; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  dispatchEvent(event) { this.event = event; }
}

const definitions = new Map([["bubble-card", class {}]]);
const customElements = {
  define: (name, value) => {
    if (definitions.has(name)) throw new Error(`Already registered: ${name}`);
    definitions.set(name, value);
  },
  get: (name) => definitions.get(name),
  whenDefined: () => Promise.resolve(),
};
const document = { createElement: () => new Element() };
const window = { customCards: [], loadCardHelpers: async () => ({
  createCardElement: (config) => Object.assign(new Element(), { config }),
}) };
const context = vm.createContext({ HTMLElement: Element, customElements, document, window, CustomEvent: class {
  constructor(type, options) { this.type = type; Object.assign(this, options); }
} });
const source = readFileSync(path.join(__dirname, "../custom_components/flashforge_ac5/www/flashforge-card.js"), "utf8");
function loadCardModule() {
  vm.runInContext(`(function () { ${source}\n})();`, context);
}
loadCardModule();

test("registers in the card picker and tolerates an existing manual resource", () => {
  const original = definitions.get("flashforge-card");
  loadCardModule();
  assert.equal(definitions.get("flashforge-card"), original);
  assert.equal(typeof original.getConfigElement, "function");
  assert.equal(typeof original.getStubConfig, "function");
  const catalogEntries = window.customCards.filter((card) => card.type === "flashforge-card");
  assert.equal(catalogEntries.length, 1);
  assert.equal(catalogEntries[0].name, "FlashForge Drucker");
});

function fixture() {
  const devices = [
    { id: "printer1", name: "Drucker", identifiers: [["flashforge_ac5", "entry1"]] },
    { id: "printer2", name: "Anderer", identifiers: [["flashforge_ac5", "entry2"]] },
    { id: "other", name: "Other", identifiers: [["other", "x"]] },
  ];
  const registry = [
    ["printer1", "entry1", "camera", "camera.renamed"],
    ["printer1", "entry1", "machine_state", "sensor.renamed_status"],
    ["printer1", "entry1", "led", "switch.changed_name"],
    ["printer1", "entry1", "internal_filtration", "switch.filtration"],
    ["printer1", "entry1", "cancel_print", "button.cancel"],
    ["printer1", "entry1", "nozzle_1_temperature", "sensor.tool_1"],
    ["printer2", "entry2", "led", "switch.other_printer"],
  ].map(([device_id, config_entry_id, suffix, entity_id]) => ({
    device_id, config_entry_id, entity_id, platform: "flashforge_ac5",
    unique_id: `${config_entry_id}_${suffix}`, disabled_by: null,
  }));
  const states = Object.fromEntries(registry.map(({ entity_id }) => [entity_id, { entity_id }]));
  let handler;
  let unsubscribed = false;
  const hass = {
    states,
    connection: {
      subscribeEvents: async (callback) => {
        handler = callback;
        return () => { unsubscribed = true; };
      },
    },
    callWS: async ({ type }) => type.includes("device_registry") ? devices : registry,
  };
  return { devices, registry, states, hass, update: () => handler(), isUnsubscribed: () => unsubscribed };
}

async function settled() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("discovers renamed entities for the chosen printer and builds safe actions", async () => {
  const data = fixture();
  const card = new (definitions.get("flashforge-card"))();
  card.setConfig({ device_id: "printer1" });
  card.hass = data.hass;
  await settled();
  const configs = card._children.map((child) => child.config);
  assert.ok(configs.some((c) => c.type === "picture-entity" && c.entity === "camera.renamed" && c.camera_view === "live"));
  assert.ok(configs.some((c) => c.entity === "sensor.renamed_status"));
  assert.ok(configs.some((c) => c.entity === "sensor.tool_1"));
  for (const entity of ["switch.changed_name", "switch.filtration"]) {
    const control = configs.find((c) => c.entity === entity);
    assert.equal(control.type, "button");
    assert.equal(control.tap_action.action, "toggle");
    assert.equal(control.show_state, true);
  }
  assert.ok(!configs.some((c) => c.entity === "switch.other_printer"));
  const cancel = configs.find((c) => c.entity === "button.cancel");
  assert.equal(cancel.tap_action.perform_action, "button.press");
  assert.equal(cancel.tap_action.target.entity_id, "button.cancel");
  assert.ok(cancel.tap_action.confirmation);
  const layout = card.shadowRoot.children[1].children[0];
  assert.equal(layout.children[0].className, "column wide control-section");
  assert.equal(layout.children[2].className, "column camera");
  assert.equal(layout.children.length, 4);
  card.disconnectedCallback();
  assert.ok(data.isUnsubscribed());
});

test("places other sensors in a full-width section after the main content", async () => {
  const data = fixture();
  for (const [suffix, entity_id] of [
    ["light_status", "sensor.light"],
    ["door", "binary_sensor.door"],
  ]) {
    data.registry.push({
      device_id: "printer1", config_entry_id: "entry1", entity_id,
      platform: "flashforge_ac5", unique_id: `entry1_${suffix}`, disabled_by: null,
    });
    data.states[entity_id] = { entity_id };
  }
  const card = new (definitions.get("flashforge-card"))();
  card.setConfig({ device_id: "printer1" });
  card.hass = data.hass;
  await settled();
  const layout = card.shadowRoot.children[1].children[0];
  assert.equal(layout.children.length, 5);
  const section = layout.children[4];
  assert.equal(section.className, "column wide");
  assert.equal(section.children[0].config.name, "Other sensors");
  const grid = section.children[1];
  assert.equal(grid.className, "sensor-grid");
  assert.deepEqual(grid.children.map((child) => child.config.entity), ["sensor.light", "binary_sensor.door"]);
  assert.ok(grid.children.every((child) => child.config.type === "custom:bubble-card"));
  assert.ok(!layout.children[3].children.some((child) => child.config?.entity === "sensor.light"));
});

test("registry changes update cards without losing printer isolation", async () => {
  const data = fixture();
  const card = new (definitions.get("flashforge-card"))();
  card.setConfig({ device_id: "printer1" });
  card.hass = data.hass;
  await settled();
  const led = data.registry.find((entry) => entry.entity_id === "switch.changed_name");
  led.entity_id = "switch.new_name";
  data.states["switch.new_name"] = { entity_id: "switch.new_name" };
  delete data.states["switch.changed_name"];
  data.update();
  await settled();
  assert.ok(card._children.some((child) => child.config.entity === "switch.new_name"));
  assert.ok(!card._children.some((child) => child.config.entity === "switch.changed_name"));
  led.disabled_by = "user";
  data.update();
  await settled();
  assert.ok(!card._children.some((child) => child.config.entity === "switch.new_name"));
});

test("the editor shows only FlashForge devices and saves the selected ID", async () => {
  const data = fixture();
  const editor = new (definitions.get("flashforge-card-editor"))();
  editor.setConfig({ type: "custom:flashforge-card" });
  editor.hass = data.hass;
  await settled();
  const select = editor.shadowRoot.children[0].children[0];
  assert.deepEqual(select.children.map((option) => option.value), ["", "printer1", "printer2"]);
  select.value = "printer2";
  select.listeners.change();
  assert.equal(editor.event.detail.config.device_id, "printer2");
});

test("registry errors remain visible on later state updates", async () => {
  const data = fixture();
  data.hass.callWS = async () => { throw new Error("offline"); };
  const card = new (definitions.get("flashforge-card"))();
  card.setConfig({ device_id: "printer1" });
  card.hass = data.hass;
  await settled();
  card.hass = data.hass;
  assert.match(card.shadowRoot.children[0].children[0].textContent, /offline/);
});

test("missing and disabled printer entities are reported instead of showing an empty card", async () => {
  const data = fixture();
  for (const entity of data.registry) entity.disabled_by = "user";
  const card = new (definitions.get("flashforge-card"))();
  card.setConfig({ device_id: "printer1" });
  card.hass = data.hass;
  await settled();
  assert.match(card.shadowRoot.children[0].children[0].textContent, /No active entities/);
});

test("late subscription is cleaned up when the card is removed", async () => {
  const data = fixture();
  let resolveSubscription;
  let unsubscribed = false;
  data.hass.connection.subscribeEvents = () => new Promise((resolve) => {
    resolveSubscription = resolve;
  });
  const card = new (definitions.get("flashforge-card"))();
  card.setConfig({ device_id: "printer1" });
  card.hass = data.hass;
  card.disconnectedCallback();
  resolveSubscription(() => { unsubscribed = true; });
  await settled();
  assert.ok(unsubscribed);
});
