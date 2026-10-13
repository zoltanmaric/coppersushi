// DOM integration checks. These do not assess browser rendering or geometry.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");
const directory = process.argv[2];
assert(directory, "Pass an exported observatory directory");
const errors = [];
const console = new VirtualConsole();
console.on("jsdomError", (e) => errors.push(e.message));
console.on("error", (e) => errors.push(String(e)));
const dom = new JSDOM(
  fs.readFileSync(path.join(directory, "index.html"), "utf8"),
  {
    url: "https://observatory.invalid/",
    runScripts: "outside-only",
    virtualConsole: console,
  },
);
const { window } = dom;
window.eval(fs.readFileSync(path.join(directory, "data.js"), "utf8"));
window.eval(fs.readFileSync(path.join(directory, "app.js"), "utf8"));
const $ = (id) => window.document.getElementById(id);
const change = (id, value) => {
  $(id).value = value;
  $(id).dispatchEvent(new window.Event("change"));
};
const data = window.FORECAST;
assert($("error").hidden, $("error").textContent);
assert(
  $("metrics").textContent.includes(data.report.metrics.system.wis.toFixed(2)),
);
assert.equal(
  $("wis-explanation").closest(".metric").querySelector(".metric-label")
    .textContent,
  "Weighted interval score (WIS) ↓",
);
assert($("wis-explanation").textContent.includes("0.4"));
const diagramBefore = $("pipeline").innerHTML;
const teachingBefore = $("node-detail").innerHTML;
const month = Object.keys(data.report.breakdowns.month)[1];
change("period", month);
assert([...$("day").options].every((o) => o.value.startsWith(month)));
assert($("previous").disabled);
$("next").click();
assert.equal($("day").selectedIndex, 1);
change("day", $("day").options[$("day").options.length - 1].value);
assert($("next").disabled);
assert(
  $("metrics").textContent.includes(
    data.report.breakdowns.month[month].metrics.system.wis.toFixed(2),
  ),
);
assert.equal($("pipeline").innerHTML, diagramBefore);
assert.equal($("node-detail").innerHTML, teachingBefore);
change("method", "reference");
assert($("chart-title").textContent.includes("reference"));
$("quarter").value = 5;
$("quarter").dispatchEvent(new window.Event("input"));
assert($("point-detail").textContent.includes("Actual"));
$("reference").checked = true;
$("reference").dispatchEvent(new window.Event("change"));
assert(!$("reference-legend").hidden);
change("period", "all");
const dst = data.days.find((d) => d.points.length !== 96);
if (dst) {
  change("day", dst.date);
  assert.equal($("quarters").children.length, dst.points.length);
  assert.equal(Number($("quarter").max), dst.points.length - 1);
}
for (const node of $("pipeline").querySelectorAll("[role=button]")) {
  node.dispatchEvent(
    new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
  );
  assert.equal(node.getAttribute("aria-pressed"), "true");
  assert($("node-detail").textContent.includes("What happens, and why"));
}
window.location.hash = "#understand";
window.dispatchEvent(new window.HashChangeEvent("hashchange"));
assert(!$("understand").hidden);
assert($("explore").hidden);
window.location.hash = "#trace";
window.dispatchEvent(new window.HashChangeEvent("hashchange"));
assert(!$("trace").hidden);
assert.equal(errors.length, 0, errors.join("\n"));
dom.window.close();
process.stdout.write(
  "DOM checks passed: metrics, WIS placement, period/day navigation, clock change, model comparison, independent pipeline, keyboard stage selection and view navigation.\n",
);
