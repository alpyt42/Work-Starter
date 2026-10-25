<%*
/* New action: adds an action to the state/actions.md register of a project.
   Run it with the "New action" button of tasks.md,
   or "Templater: Insert templater/new-action" (or its hotkey), from any note:
   nothing is inserted in the open note, the action is written to the chosen register.
   Format and ID rules: kit/brain/docs/CONVENTIONS.md.
   Every brain of the workspace is offered (`brain`, `brain-perso`, `brain-<name>`); the brain name prefixes
   the project as soon as there are several, and the default owner comes from the `.data/doctor.json` of the chosen brain. */
const REGISTER = /^(brain(?:-[a-z0-9][a-z0-9-]*)?)\/projects\/(.+)\/state\/actions\.md$/;
const ID = /\b([A-Z]{2,5})-(\d{3})\b/g;
const pad = (n) => String(n).padStart(3, "0");
const brainOf = (path) => path.match(REGISTER)[1];
const registers = app.vault.getMarkdownFiles().filter((f) => REGISTER.test(f.path));
if (!registers.length) { new Notice("No state/actions.md register found"); return; }
// With several brains, the brain name prefixes the project label.
const severalBrains = new Set(registers.map((f) => brainOf(f.path))).size > 1;
const label = (path) => {
  const parts = path.match(REGISTER)[2].split("/");
  const project = parts[0] === "clients" && parts.length >= 4 ? `${parts[1]} / ${parts[3]}` : parts[parts.length - 1];
  return severalBrains ? `${brainOf(path)} / ${project}` : project;
};
registers.sort((a, b) => label(a.path).localeCompare(label(b.path)));
const register = await tp.system.suggester(registers.map((f) => label(f.path)), registers, false, "Project");
if (!register) return;
const brain = brainOf(register.path);

const title = (await tp.system.prompt("Title (start with a verb)", ""))?.trim().replace(/[\r\n]+/g, " ");
if (!title) return;
let owner = "Owner";
try { owner = JSON.parse(await app.vault.adapter.read(`${brain}/.data/doctor.json`)).owner || owner; } catch (e) {}
const ownerInput = await tp.system.prompt("Owner", owner);
if (ownerInput === null || ownerInput === undefined) return;
owner = ownerInput.trim().replace(/[\r\n]+/g, " ") || owner;
const state = await tp.system.suggester(["To do  [ ]", "In progress  [/]", "Waiting  [w]"], [" ", "/", "w"], false, "State");
if (state === null || state === undefined) return;
const priority = await tp.system.suggester(["Normal", "High ⏫", "Medium 🔼", "Low 🔽"], ["", "⏫", "🔼", "🔽"], false, "Priority");
if (priority === null || priority === undefined) return;
const validDate = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};
let due = "";
while (true) {
  const answer = await tp.system.prompt("Due date YYYY-MM-DD (empty if none)", due);
  if (answer === null || answer === undefined) return;
  due = answer.trim();
  if (!due || validDate(due)) break;
  new Notice("Invalid date: enter a real date as YYYY-MM-DD, or leave it empty.");
}

// The ID prefix is the register's; the number follows the highest one in the whole client or project folder, sources included.
const text = await app.vault.read(register);
const own = [...text.matchAll(ID)].map((m) => m[1]);
let prefix = own.length ? own.sort((a, b) => own.filter((x) => x === b).length - own.filter((x) => x === a).length)[0] : "";
if (!prefix) prefix = ((await tp.system.prompt("ID prefix of this project (3 letters, to confirm)", "")) || "").trim().toUpperCase();
if (!/^[A-Z]{2,5}$/.test(prefix)) { new Notice("Invalid ID prefix: action not added"); return; }
const inner = register.path.match(REGISTER)[2].split("/");
// clients/<client>/ or internal/<project>/, in the chosen brain
const root = `${brain}/projects/` + inner.slice(0, 2).join("/") + "/";
let highest = 0;
for (const file of app.vault.getMarkdownFiles().filter((f) => f.path.startsWith(root))) {
  for (const m of (await app.vault.cachedRead(file)).matchAll(ID)) {
    if (m[1] === prefix) highest = Math.max(highest, Number(m[2]));
  }
}
const id = `${prefix}-${pad(highest + 1)}`;

const today = tp.date.now("DD/MM");
const created = tp.date.now("YYYY-MM-DD");
const stamp = tp.date.now("YYYY-MM-DD HH:mm");
const lines = [
  `- [${state}] **${id}** — ${owner} — ${title}${priority ? ` ${priority}` : ""} ➕ ${created}${due ? ` 📅 ${due}` : ""}`,
  `    - source: owner, ${today} (added from Obsidian)`,
  `    - created: ${stamp}`,
  `    - updated: ${stamp}`,
];

// Append at the end of "Open", before "Done".
const out = text.split("\n");
let end = out.findIndex((l) => /^## Done\s*$/.test(l));
if (end < 0) end = out.length;
while (end > 0 && out[end - 1].trim() === "") end--;
out.splice(end, 0, ...lines);
await app.vault.modify(register, out.join("\n"));
new Notice(`${id} added to ${label(register.path)}`);
-%>
