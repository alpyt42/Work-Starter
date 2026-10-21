<%*
/* Nouvelle action : ajoute une action au registre state/actions.md d'un projet.
   Lancer avec le bouton « Nouvelle action » de tasks.md,
   ou « Templater: Insert templater/nouvelle-action » (ou son raccourci), depuis n'importe quelle note :
   rien n'est inséré dans la note ouverte, l'action est écrite dans le registre choisi.
   Format et règles d'ID : kit/brain/docs/CONVENTIONS.md.
   Tous les brains de l'espace sont proposés (`brain`, `brain-perso`, `brain-<nom>`) ; le nom du brain préfixe
   le projet dès qu'il y en a plusieurs, et le responsable par défaut vient du `.data/doctor.json` du brain choisi. */
const REGISTER = /^(brain(?:-[a-z0-9][a-z0-9-]*)?)\/projects\/(.+)\/state\/actions\.md$/;
const ID = /\b([A-Z]{2,5})-(\d{3})\b/g;
const pad = (n) => String(n).padStart(3, "0");
const brainOf = (path) => path.match(REGISTER)[1];
const registers = app.vault.getMarkdownFiles().filter((f) => REGISTER.test(f.path));
if (!registers.length) { new Notice("Aucun registre state/actions.md trouvé"); return; }
// With several brains, the brain name prefixes the project label.
const severalBrains = new Set(registers.map((f) => brainOf(f.path))).size > 1;
const label = (path) => {
  const parts = path.match(REGISTER)[2].split("/");
  const project = parts[0] === "clients" && parts.length >= 4 ? `${parts[1]} / ${parts[3]}` : parts[parts.length - 1];
  return severalBrains ? `${brainOf(path)} / ${project}` : project;
};
registers.sort((a, b) => label(a.path).localeCompare(label(b.path)));
const register = await tp.system.suggester(registers.map((f) => label(f.path)), registers, false, "Projet");
if (!register) return;
const brain = brainOf(register.path);

const title = (await tp.system.prompt("Intitulé (verbe à l'infinitif)", ""))?.trim().replace(/[\r\n]+/g, " ");
if (!title) return;
let owner = "Propriétaire";
try { owner = JSON.parse(await app.vault.adapter.read(`${brain}/.data/doctor.json`)).owner || owner; } catch (e) {}
const ownerInput = await tp.system.prompt("Responsable", owner);
if (ownerInput === null || ownerInput === undefined) return;
owner = ownerInput.trim().replace(/[\r\n]+/g, " ") || owner;
const state = await tp.system.suggester(["À faire  [ ]", "En cours  [/]", "En attente  [w]"], [" ", "/", "w"], false, "État");
if (state === null || state === undefined) return;
const priority = await tp.system.suggester(["Normale", "Haute ⏫", "Moyenne 🔼", "Basse 🔽"], ["", "⏫", "🔼", "🔽"], false, "Priorité");
if (priority === null || priority === undefined) return;
const validDate = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};
let due = "";
while (true) {
  const answer = await tp.system.prompt("Échéance AAAA-MM-JJ (vide si aucune)", due);
  if (answer === null || answer === undefined) return;
  due = answer.trim();
  if (!due || validDate(due)) break;
  new Notice("Date invalide : saisir une date réelle au format AAAA-MM-JJ, ou laisser vide.");
}

// The ID prefix is the register's; the number follows the highest one in the whole client or project folder, sources included.
const text = await app.vault.read(register);
const own = [...text.matchAll(ID)].map((m) => m[1]);
let prefix = own.length ? own.sort((a, b) => own.filter((x) => x === b).length - own.filter((x) => x === a).length)[0] : "";
if (!prefix) prefix = ((await tp.system.prompt("Préfixe d'ID de ce projet (3 lettres, à valider)", "")) || "").trim().toUpperCase();
if (!/^[A-Z]{2,5}$/.test(prefix)) { new Notice("Préfixe d'ID invalide : action non ajoutée"); return; }
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
  `    - source: info du propriétaire, ${today} (ajoutée depuis Obsidian)`,
  `    - créée : ${stamp}`,
  `    - mise à jour : ${stamp}`,
];

// Append at the end of « Ouvertes », before « Terminées ».
const out = text.split("\n");
let end = out.findIndex((l) => /^## Terminées/.test(l));
if (end < 0) end = out.length;
while (end > 0 && out[end - 1].trim() === "") end--;
out.splice(end, 0, ...lines);
await app.vault.modify(register, out.join("\n"));
new Notice(`${id} ajoutée à ${label(register.path)}`);
-%>
