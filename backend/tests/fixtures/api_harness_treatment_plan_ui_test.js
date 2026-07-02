const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync(process.argv[2], "utf8");
const match = html.match(/<script>([\s\S]*)<\/script>/);
assert(match, "script block missing");

const ids = [
  "authMode",
  "treatmentPlanLimit",
  "treatmentPlanStartDate",
  "treatmentPlanEndDate",
  "treatmentPlanPatientId",
  "pullAllTreatmentPlansButton",
  "pullSingleTreatmentPlanButton",
  "treatmentPlanPullPayload",
  "treatmentPlanPullStatus",
  "treatmentPlanPullResult",
  "swaggerUiUrl",
  "apiBaseUrl",
  "openApiUrl",
  "tokenUrl",
  "tokenAuthStyle",
  "clientId",
  "apiKeyHeaderName",
  "scope",
  "timeoutSeconds",
  "loginStatus",
];
const elements = {};
for (const id of ids) elements[id] = { value: "", textContent: "", disabled: false, className: "" };
elements.treatmentPlanLimit.value = "100";
elements.treatmentPlanStartDate.value = "2000-01-01T16:03";
elements.tokenAuthStyle.value = "body";
elements.timeoutSeconds.value = "10";
elements.apiKeyHeaderName.value = "x-api-key";

const storage = {};
const context = {
  console,
  JSON,
  Number,
  Date,
  Error,
  window: {
    addEventListener() {},
    sessionStorage: {
      getItem(key) {
        return storage[key] || "";
      },
      setItem(key, value) {
        storage[key] = value;
      },
      removeItem(key) {
        delete storage[key];
      },
    },
    location: { origin: "http://127.0.0.1" },
    opener: null,
  },
  document: {
    getElementById(id) {
      if (!elements[id]) elements[id] = { value: "", textContent: "", disabled: false, className: "" };
      return elements[id];
    },
  },
  fetch: async () => {
    throw new Error("fetch not stubbed");
  },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(match[1], context);

context.updateTreatmentPlanSingleButtonState();
assert.strictEqual(elements.pullSingleTreatmentPlanButton.disabled, true);
context.prepareTreatmentPlanPull("all_treatment_plans");
const prepared = JSON.parse(elements.treatmentPlanPullPayload.value);
assert.strictEqual(prepared.report, "all_treatment_plans");
assert.strictEqual(prepared.operation_parameters.Limit, 100);
assert.strictEqual(prepared.operation_parameters.StartDate, "2000-01-01T16:03");
assert.strictEqual(prepared.operation_parameters["api-version"], "1.0");

let captured = null;
vm.runInContext("token = 'admin-session';", context);
elements.treatmentPlanPatientId.value = "";
context
  .runTreatmentPlanPull("single_treatment_plan")
  .then(async () => {
    assert.strictEqual(captured, null);
    assert(elements.treatmentPlanPullStatus.textContent.includes("Patient / Client ID is required"));
    elements.treatmentPlanPatientId.value = "PAT-HREF-001";
    context.updateTreatmentPlanSingleButtonState();
    assert.strictEqual(elements.pullSingleTreatmentPlanButton.disabled, false);
    context.fetch = async (url, options) => {
      captured = {
        url,
        body: JSON.parse(options.body),
        allDisabled: elements.pullAllTreatmentPlansButton.disabled,
        singleDisabled: elements.pullSingleTreatmentPlanButton.disabled,
      };
      return { ok: true, text: async () => JSON.stringify({ status: "ok", message: "done", returned_count: 1 }) };
    };
    await context.runTreatmentPlanPull("single_treatment_plan");
    assert.strictEqual(captured.url, "/api/api-configuration/alleva-quick-pull");
    assert.strictEqual(captured.body.report, "single_treatment_plan");
    assert.strictEqual(captured.body.patient_id, "PAT-HREF-001");
    assert.strictEqual(captured.body.operation_parameters.StartDate, "2000-01-01T16:03");
    assert.strictEqual(captured.allDisabled, true);
    assert.strictEqual(captured.singleDisabled, true);
    assert(elements.treatmentPlanPullResult.textContent.includes('"returned_count": 1'));
    process.stdout.write(JSON.stringify({ patient_id: captured.body.patient_id }));
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
