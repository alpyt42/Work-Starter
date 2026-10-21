'use strict';

const token = document.querySelector('meta[name="csrf-token"]').content;
const ids = Object.fromEntries([
  'dueCount', 'waitingCount', 'lastSync', 'resultCount', 'searchInput',
  'projectFilter', 'ownerFilter', 'scopeFilter', 'listButton', 'boardButton', 'toolsButton',
  'filters', 'resetFilters', 'listView', 'boardView', 'boardHint', 'toolsView', 'toolsCatalog',
  'toolSearch', 'summaryChips', 'toolResult', 'toolResultTitle', 'toolResultStatus',
  'toolResultEmpty', 'toolResultOutput', 'gitButton', 'gitView', 'gitStatus', 'gitRepos', 'gitDetail',
  'gitDetailTitle', 'gitDetailStatus', 'gitDetailEmpty', 'gitDetailNote', 'gitDiff',
  'errorBanner', 'editor', 'editorForm', 'editorTitle',
  'editorHint', 'editorProject', 'editorActionTitle', 'editorHistory', 'editorHistoryList',
  'editorHistoryCount', 'addNoteButton', 'noteForm', 'noteInput', 'submitNote', 'closeNoteForm',
  'noteError', 'editorOwner', 'editorState',
  'editorGroup', 'editorGroupNew', 'editorGroupNewLabel', 'editorGroupHint', 'groupFilter', 'editorPriority', 'editorDue', 'editorScheduled', 'editorError', 'saveEditor', 'deleteEditor', 'toast',
  'detailPreview', 'detailDialog', 'detailTitle', 'detailMeta', 'detailBody', 'closeDetail',
  'editDetail', 'dismissDetail', 'undoButton',
  'searchButton', 'searchView', 'docQuery', 'docProject', 'docStatus', 'docList', 'docPane', 'docPaneTitle',
  'docPaneMeta', 'docPanePath', 'docBack', 'docEdit', 'docCancel', 'docSave', 'docPaneEmpty', 'docPaneError',
  'docArticle', 'docEditor', 'newNoteButton',
  'newNoteDialog', 'newNoteForm', 'closeNewNote', 'cancelNewNote', 'newNoteTitle', 'newNoteProject',
  'newNoteContent', 'newNoteWhere', 'newNoteError', 'saveNewNote'
].map(id => [id, document.getElementById(id)]));
const UI_STATE_KEY = 'actions-brain-ui-v1';
function readUIState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(UI_STATE_KEY));
    return saved && typeof saved === 'object' ? saved : {};
  } catch { return {}; }
}
const savedUI = readUIState();
let pendingProject = typeof savedUI.project === 'string' ? savedUI.project : '';
let pendingGroup = typeof savedUI.group === 'string' ? savedUI.group : '';
// Folded list groups, as `register|slug` ('|' alone: « Sans groupe »).
const foldedGroups = new Set(Array.isArray(savedUI.foldedGroups) ? savedUI.foldedGroups.filter(key => typeof key === 'string') : []);
let snapshot = {actions: [], registers: [], owner: '', today: ''};
let pendingDocProject = typeof savedUI.docProject === 'string' ? savedUI.docProject : typeof savedUI.notesProject === 'string' ? savedUI.notesProject : '';
let view = ['list', 'board', 'tools', 'git', 'search'].includes(savedUI.view) ? savedUI.view : savedUI.view === 'notes' ? 'search' : 'list';
let toastTimer;
let tools = [];
let detailCurrent = null;
let previewRequest = 0;
let previewTrigger = null;
let previewHideTimer;
let suppressPreviewFocus = false;
let editorHistoryRequest = 0;
let noteState = null;
let noteBusy = false;
let undoState = {available: false, label: null, depth: 0};
let undoBusy = false;
let notesData = [];
let notesLoaded = false;
let recentDocs = [];
let notesRequest = 0;
let docTimer;
let docMode = 'recent';
let docResults = [];
let docTotal = 0;
let docTerms = [];
let docError = '';
let docSearchRequest = 0;
let docSelectedId = null;
let docCurrent = null;
let docHistory = [];
let docMarks = [];
let docRenderRequest = 0;
let docEditing = false;
let docSaving = false;
let docNote = null;
const DOC_MARK_CAP = 500;
const docFoldCache = new Map();
const INBOX_REGISTER = 'inbox';
const detailCache = new Map();
const STATUS_OPTIONS = [
  [' ', 'À faire'], ['/', 'En cours'], ['w', 'En attente'], ['x', 'Terminée'], ['-', 'Annulée']
];
function saveUIState() {
  try {
    sessionStorage.setItem(UI_STATE_KEY, JSON.stringify({
      view, search: ids.searchInput.value, project: ids.projectFilter.value, group: ids.groupFilter.value || pendingGroup,
      owner: ids.ownerFilter.value, scope: ids.scopeFilter.value, toolSearch: ids.toolSearch.value,
      docQuery: ids.docQuery.value, docProject: ids.docProject.value, gitRepo: gitCurrent, foldedGroups: [...foldedGroups]
    }));
  } catch { /* The interface remains usable when browser storage is unavailable. */ }
}

function element(tag, className = '', value = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value) node.textContent = value;
  return node;
}
function formatStamp(value) {
  if (!value) return '';
  const [day, time] = value.split(' ');
  return time ? `${formatDate(day)} à ${time}` : formatDate(day);
}
function formatDate(value) {
  if (!value) return '—';
  const [year, month, day] = value.split('-');
  return `${day}/${month}/${year}`;
}
function statusLabel(state) {
  return {' ': 'À faire', '/': 'En cours', w: 'En attente', x: 'Terminée', '-': 'Annulée'}[state] || state;
}
function stateClass(state) {
  return {' ': 'state-todo', '/': 'state-progress', w: 'state-wait', x: 'state-done', '-': 'state-cancel'}[state] || '';
}
function groupLabel(slug) {
  const text = slug.replace(/-/g, ' ');
  return text.charAt(0).toLocaleUpperCase('fr') + text.slice(1);
}
// A free label (« Atelier ingestion ») becomes a slug the way the server expects it: a-z, 0-9 and single hyphens, 40 characters.
function groupSlug(text) {
  return text.toLowerCase().replace(/œ/g, 'oe').replace(/æ/g, 'ae').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+/, '').slice(0, 40).replace(/-+$/, '');
}
function dateNode(action) {
  if (!action.due) return element('span', 'cell-muted', '—');
  const className = action.state === 'x' || action.state === '-' ? '' : action.due < snapshot.today ? ' date-overdue' : action.due === snapshot.today ? ' date-today' : '';
  return element('span', `date-pill${className}`, formatDate(action.due));
}
function priorityNode(action) {
  const label = {'⏫': 'Haute', '🔼': 'Moyenne', '🔽': 'Basse'}[action.priority] || 'Normale';
  return element('span', `priority-pill${action.priority === '⏫' ? ' priority-high' : ''}`, label);
}
function statusControl(action) {
  const select = element('select', `status-select ${stateClass(action.state)}`);
  select.dataset.actionId = action.id;
  select.setAttribute('aria-label', `Changer le statut de ${action.id}`);
  select.title = 'Changer le statut sans ouvrir la tâche';
  for (const [value, label] of STATUS_OPTIONS) select.add(new Option(label, value));
  select.value = action.state;
  select.addEventListener('click', event => event.stopPropagation());
  select.addEventListener('pointerdown', event => event.stopPropagation());
  select.addEventListener('change', event => {
    event.stopPropagation();
    updateStatus(action, select.value, select);
  });
  return select;
}
function filteredBase() {
  const text = ids.searchInput.value.trim().toLocaleLowerCase('fr');
  const project = ids.projectFilter.value;
  const mine = ids.ownerFilter.value === 'mine';
  const group = ids.groupFilter.value;
  return snapshot.actions.filter(action =>
    (!text || `${action.id} ${action.title} ${action.owner} ${action.project} ${action.group ? `${groupLabel(action.group)} ${action.group}` : ''}`.toLocaleLowerCase('fr').includes(text)) &&
    (!project || action.register === project) &&
    (!group || (group === 'none' ? !action.group : Boolean(action.group) && groupKey(action) === group)) &&
    (!mine || action.owner.toLocaleLowerCase('fr').includes(snapshot.owner.toLocaleLowerCase('fr')))
  );
}
function scoped(actions) {
  const scope = ids.scopeFilter.value;
  return actions.filter(action => scope === 'all' || (scope === 'active' ? !['x', '-'].includes(action.state) : ['x', '-'].includes(action.state)));
}
function sortActions(actions) {
  const rank = {'/': 0, ' ': 1, w: 2, x: 3, '-': 4};
  const priority = {'⏫': 0, '🔼': 1, '': 2, '🔽': 3};
  return [...actions].sort((a, b) =>
    rank[a.state] - rank[b.state] ||
    priority[a.priority] - priority[b.priority] ||
    (a.due || '9999').localeCompare(b.due || '9999') ||
    a.id.localeCompare(b.id)
  );
}
function setSummary() {
  const active = snapshot.actions.filter(action => !['x', '-'].includes(action.state));
  ids.dueCount.textContent = String(active.filter(action => action.due && action.due <= snapshot.today).length);
  ids.waitingCount.textContent = String(active.filter(action => action.state === 'w').length);
}
function empty(message) {
  const box = element('div', 'empty');
  box.append(element('strong', '', 'Aucune action ici.'), element('span', '', message));
  return box;
}
async function loadDetails(action) {
  const key = `${action.id}:${action.version}`;
  if (!detailCache.has(key)) {
    const pending = request(`/api/actions/${encodeURIComponent(action.id)}/details`);
    detailCache.set(key, pending);
    pending.catch(() => detailCache.delete(key));
  }
  return detailCache.get(key);
}
function detailText(action) {
  if (!action.details.length) return 'Aucune note complémentaire dans le registre.';
  return action.details.join('\n');
}
function metadata(action) {
  const fields = [
    ['Projet', action.project], ...(action.group ? [['Groupe', groupLabel(action.group)]] : []), ['Responsable', action.owner],
    ['Statut', statusLabel(action.state)],
    ['Créée', action.created_at ? formatStamp(action.created_at) : 'Non renseignée'],
    ['Mise à jour', action.updated_at ? formatStamp(action.updated_at) : 'Non renseignée'],
    ['Priorité', {'⏫': 'Haute', '🔼': 'Moyenne', '🔽': 'Basse'}[action.priority] || 'Normale'],
    ['Échéance', action.due ? formatDate(action.due) : 'Non renseignée'],
    ['Planifiée', action.scheduled ? formatDate(action.scheduled) : 'Non renseignée']
  ];
  if (['x', '-'].includes(action.state)) fields.push(['Clôture', action.done ? formatDate(action.done) : 'Non renseignée']);
  const list = element('dl', 'action-metadata');
  for (const [label, value] of fields) {
    const pair = element('div', 'action-metadata-pair');
    pair.append(element('dt', '', label), element('dd', '', value));
    list.append(pair);
  }
  return list;
}
function positionPreview(trigger) {
  if (ids.detailPreview.hidden) return;
  const rect = trigger.getBoundingClientRect();
  const clip = trigger.closest('.list-view, .board-cards')?.getBoundingClientRect();
  if (rect.bottom < Math.max(0, clip?.top ?? 0) || rect.top > Math.min(window.innerHeight, clip?.bottom ?? window.innerHeight)) { hidePreview(); return; }
  const margin = 12;
  const gap = 10;
  const width = ids.detailPreview.getBoundingClientRect().width;
  const height = ids.detailPreview.getBoundingClientRect().height;
  let left = rect.right + gap;
  if (left + width > window.innerWidth - margin) left = rect.left - width - gap;
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
  const top = Math.max(margin, Math.min(rect.top, window.innerHeight - height - margin));
  ids.detailPreview.style.left = `${left}px`;
  ids.detailPreview.style.top = `${top}px`;
}
function hidePreview() {
  clearTimeout(previewHideTimer);
  previewRequest += 1;
  ids.detailPreview.hidden = true;
  previewTrigger?.setAttribute('aria-expanded', 'false');
  previewTrigger = null;
}
function schedulePreviewHide() {
  clearTimeout(previewHideTimer);
  previewHideTimer = setTimeout(() => {
    if (!ids.detailPreview.matches(':hover') && !ids.detailPreview.contains(document.activeElement)) hidePreview();
  }, 180);
}
async function showPreview(action, trigger) {
  clearTimeout(previewHideTimer);
  if (previewTrigger && previewTrigger !== trigger) previewTrigger.setAttribute('aria-expanded', 'false');
  previewTrigger = trigger;
  trigger.setAttribute('aria-expanded', 'true');
  const requestId = ++previewRequest;
  ids.detailPreview.textContent = 'Chargement du détail…';
  ids.detailPreview.hidden = false;
  positionPreview(trigger);
  try {
    const details = await loadDetails(action);
    if (requestId === previewRequest) {
      ids.detailPreview.setAttribute('aria-label', `Aperçu de ${details.id}`);
      const header = element('div', 'preview-header');
      header.append(element('span', 'preview-id', details.id), element('strong', 'preview-title', details.title));
      const notes = element('section', 'preview-notes');
      notes.append(element('h3', '', 'Notes et historique'), element('pre', '', detailText(details)));
      ids.detailPreview.replaceChildren(header, metadata(details), notes);
      positionPreview(trigger);
    }
  } catch (error) {
    if (requestId === previewRequest) {
      ids.detailPreview.textContent = error.message;
      positionPreview(trigger);
    }
  }
}
async function openDetail(action) {
  hidePreview();
  detailCurrent = null;
  ids.detailTitle.textContent = `${action.id} · ${action.title}`;
  ids.detailMeta.replaceChildren(metadata(action));
  ids.detailBody.textContent = 'Chargement du détail…';
  ids.editDetail.disabled = true;
  if (!ids.detailDialog.open) ids.detailDialog.showModal();
  try {
    const details = await loadDetails(action);
    if (!ids.detailDialog.open) return;
    detailCurrent = details;
    ids.detailTitle.textContent = `${details.id} · ${details.title}`;
    ids.detailMeta.replaceChildren(metadata(details));
    ids.detailBody.replaceChildren(element('pre', 'detail-lines', detailText(details)));
    ids.editDetail.disabled = false;
  } catch (error) {
    if (ids.detailDialog.open) ids.detailBody.textContent = error.message;
  }
}
function eyeButton(action) {
  const eye = element('button', 'detail-eye');
  eye.type = 'button';
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.setAttribute('viewBox', '0 0 24 24');
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = '<path d="M6 3.5h9l3 3v13a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 19.5v-14A2 2 0 0 1 6 3.5Z"/><path d="M15 3.5v4h3M8.5 11h6M8.5 14.5h7M8.5 18h4"/>';
  eye.append(icon);
  eye.setAttribute('aria-label', `Aperçu et détail de ${action.id}`);
  eye.setAttribute('aria-controls', 'detailPreview');
  eye.setAttribute('aria-expanded', 'false');
  eye.addEventListener('mouseenter', () => showPreview(action, eye));
  eye.addEventListener('mouseleave', schedulePreviewHide);
  eye.addEventListener('focus', () => { if (!suppressPreviewFocus) showPreview(action, eye); });
  eye.addEventListener('blur', event => { if (event.relatedTarget !== ids.detailPreview) schedulePreviewHide(); });
  eye.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' && !ids.detailPreview.hidden) { event.preventDefault(); ids.detailPreview.focus(); }
    if (event.key === 'Escape') hidePreview();
  });
  eye.addEventListener('click', event => { event.stopPropagation(); openDetail(action); });
  return eye;
}
ids.detailPreview.addEventListener('mouseenter', () => clearTimeout(previewHideTimer));
ids.detailPreview.addEventListener('mouseleave', schedulePreviewHide);
ids.detailPreview.addEventListener('blur', schedulePreviewHide);
ids.detailPreview.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    event.preventDefault();
    const trigger = previewTrigger;
    hidePreview();
    suppressPreviewFocus = true;
    trigger?.focus();
    queueMicrotask(() => { suppressPreviewFocus = false; });
  }
});
// Scroll events do not bubble: capture them from the list, board and page scroll containers.
window.addEventListener('scroll', () => { if (previewTrigger) positionPreview(previewTrigger); }, {passive: true, capture: true});
window.addEventListener('resize', () => { if (previewTrigger) positionPreview(previewTrigger); });
function rowTools(action) {
  const tools = element('span', 'row-tools');
  tools.append(eyeButton(action), deleteButton(action));
  return tools;
}
function deleteButton(action) {
  const button = element('button', 'row-delete');
  button.type = 'button';
  button.setAttribute('aria-label', `Supprimer ${action.id}`);
  button.title = `Supprimer ${action.id} du registre (annulable avec ↶ Annuler)`;
  button.append(trashIcon());
  button.addEventListener('click', event => { event.stopPropagation(); deleteFromBoard(action, button); });
  return button;
}
function addButton(label, preset) {
  const button = element('button', 'group-add', '+');
  button.type = 'button';
  button.setAttribute('aria-label', `Ajouter une action au groupe ${label}`);
  button.title = `Ajouter une action au groupe ${label}`;
  button.addEventListener('click', event => { event.stopPropagation(); openEditor(null, preset); });
  return button;
}
// A stable tone per group: its slug picks one of the 8 palette colours (--grp-0…7), the same everywhere (list, board, filter).
function groupTone(slug) {
  let hash = 0;
  for (const char of slug) hash = (Math.imul(hash, 72) + char.charCodeAt(0)) >>> 0;
  return `grp-${((hash ^ (hash >>> 13)) >>> 0) % 8}`;
}
const NO_GROUP = '|';
function groupKey(action) { return `${action.register}|${action.group}`; }
function compareGroups(a, b) {
  return a.project.localeCompare(b.project, 'fr') || a.label.localeCompare(b.label, 'fr') || a.key.localeCompare(b.key);
}
// Folded groups: list and board share the keys; each section carries data-fold, its toggle .fold-toggle and its body .fold-body.
function applyFolds() {
  for (const section of document.querySelectorAll('[data-fold]')) {
    const folded = foldedGroups.has(section.dataset.fold);
    section.querySelector('.fold-body').hidden = folded;
    section.querySelector('.fold-toggle').setAttribute('aria-expanded', String(!folded));
  }
  const all = ids.listView.querySelector('.fold-all');
  if (all) all.textContent = listFoldKeys().every(key => foldedGroups.has(key)) ? 'Tout déplier' : 'Tout replier';
}
function listFoldKeys() { return [...ids.listView.querySelectorAll('[data-fold]')].map(section => section.dataset.fold); }
function toggleFold(key) {
  if (foldedGroups.has(key)) foldedGroups.delete(key); else foldedGroups.add(key);
  applyFolds();
  saveUIState();
}
function setAllFolds() {
  const keys = listFoldKeys();
  const fold = !keys.every(key => foldedGroups.has(key));
  for (const key of keys) { if (fold) foldedGroups.add(key); else foldedGroups.delete(key); }
  applyFolds();
  saveUIState();
}
function foldToggle(className, key) {
  const toggle = element('button', `${className} fold-toggle`);
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', String(!foldedGroups.has(key)));
  toggle.addEventListener('click', () => toggleFold(key));
  toggle.append(element('span', 'list-group-chevron'));
  return toggle;
}
function listRow(action, grouped = false) {
  const row = element('div', grouped ? `list-row in-group ${groupTone(action.group)}` : 'list-row');
  const titleCell = element('div', 'action-main');
  const idLabel = element('span', 'action-id', action.id);
  if (action.created_at) idLabel.append(element('span', 'action-created', ` · créée le ${formatStamp(action.created_at)}`));
  if (action.updated_at && action.updated_at !== action.created_at) idLabel.append(element('span', 'action-created', ` · mise à jour le ${formatStamp(action.updated_at)}`));
  titleCell.append(idLabel);
  const button = element('button', 'action-title', action.title);
  button.type = 'button';
  button.addEventListener('click', () => openEditor(action));
  // Under a group header the project is redundant: empty cell (the grid keeps its columns), owner alone on narrow screens.
  titleCell.append(button, rowTools(action), element('span', 'action-mobile-meta', grouped ? action.owner : `${action.project} · ${action.owner}`));
  row.append(titleCell, element('span', 'cell-muted', grouped ? '' : action.project), element('span', 'cell-muted', action.owner), dateNode(action), statusControl(action), priorityNode(action));
  row.addEventListener('click', event => {
    if (!event.target.closest('button, select')) openEditor(action);
  });
  return row;
}
// Progress of a group over its members (cancelled left out, scope filter ignored): done / total, in progress, waiting, late, next due date.
function groupStats(members) {
  const open = members.filter(action => action.state !== 'x');
  return {
    done: members.length - open.length, total: members.length,
    doing: open.filter(action => action.state === '/').length, waiting: open.filter(action => action.state === 'w').length,
    late: open.filter(action => action.due && action.due < snapshot.today).length,
    next: open.map(action => action.due).filter(due => due && due >= snapshot.today).sort()[0] || ''
  };
}
function shortDate(value) {
  return value.slice(0, 4) === snapshot.today.slice(0, 4) ? formatDate(value).slice(0, 5) : formatDate(value);
}
// One header per (project, group): colour dot, label, project, « done / total », progress bar and compact counters; then « Sans groupe » last (group = null).
function listGroup(key, shown, group = null) {
  const section = element('section', group ? `list-group ${groupTone(group.slug)}` : 'list-group');
  section.dataset.fold = key;
  const head = element('div', 'list-group-head');
  const toggle = foldToggle('list-group-toggle', key);
  const rows = element('div', 'list-group-rows fold-body');
  rows.hidden = foldedGroups.has(key);
  if (!group) toggle.append(element('span', 'list-group-name', 'Sans groupe'));
  else {
    const stats = group.stats;
    const name = element('span', 'list-group-name');
    name.append(element('span', 'group-dot'), element('span', 'list-group-label', group.label), element('span', 'list-group-project', group.project));
    const meta = element('span', 'list-group-meta');
    const bar = element('span', 'grp-bar');
    bar.style.setProperty('--p', stats.total ? stats.done / stats.total : 0);
    bar.append(element('span'));
    const counters = element('span', 'list-group-stats');
    for (const [count, text, late] of [[stats.doing, 'en cours', false], [stats.waiting, 'en attente', false], [stats.late, 'en retard', true]]) {
      if (count) counters.append(element('span', `list-group-stat${late ? ' stat-late' : ''}`, `${count} ${text}`));
    }
    if (stats.next) {
      const next = element('span', 'list-group-stat', `Échéance ${shortDate(stats.next)}`);
      next.title = `Prochaine échéance du groupe : ${formatDate(stats.next)}`;
      counters.append(next);
    }
    meta.append(element('span', 'list-group-count', `${stats.done} / ${stats.total}`), bar, counters);
    toggle.append(name, meta);
    toggle.setAttribute('aria-label', `${group.label}, ${group.project}, ${stats.done} faite${stats.done > 1 ? 's' : ''} sur ${stats.total}${stats.late ? `, ${stats.late} en retard` : ''}`);
  }
  for (const action of sortActions(shown)) rows.append(listRow(action, Boolean(group)));
  head.append(toggle);
  if (group) head.append(addButton(group.label, {register: group.register, group: group.slug}));
  section.append(head, rows);
  return section;
}
function renderList(actions) {
  ids.listView.replaceChildren();
  if (!actions.length) {
    ids.listView.append(empty('Essaie un autre filtre ou crée une nouvelle action.'));
    return;
  }
  const head = element('div', 'list-head');
  ['Action', 'Projet', 'Responsable', 'Échéance', 'Statut', 'Priorité'].forEach(title => head.append(element('span', '', title)));
  ids.listView.append(head);
  if (!actions.some(action => action.group)) {
    for (const action of sortActions(actions)) ids.listView.append(listRow(action));
    return;
  }
  const members = new Map();
  for (const action of filteredBase()) {
    if (!action.group || action.state === '-') continue;
    if (!members.has(groupKey(action))) members.set(groupKey(action), []);
    members.get(groupKey(action)).push(action);
  }
  const groups = new Map();
  for (const action of actions) {
    if (!action.group) continue;
    const key = groupKey(action);
    if (!groups.has(key)) groups.set(key, {key, slug: action.group, register: action.register, project: action.project, label: groupLabel(action.group), stats: groupStats(members.get(key) || []), shown: []});
    groups.get(key).shown.push(action);
  }
  const ordered = [...groups.values()].sort(compareGroups);
  const tools = element('div', 'list-tools');
  const fold = element('button', 'button button-quiet fold-all');
  fold.type = 'button';
  fold.addEventListener('click', setAllFolds);
  tools.append(element('span', '', `${ordered.length} groupe${ordered.length > 1 ? 's' : ''}`), fold);
  ids.listView.append(tools);
  for (const group of ordered) ids.listView.append(listGroup(group.key, group.shown, group));
  const loose = actions.filter(action => !action.group);
  if (loose.length) ids.listView.append(listGroup(NO_GROUP, loose));
  applyFolds();
}
function makeCard(action) {
  const card = element('article', action.group ? `action-card in-group ${groupTone(action.group)}` : 'action-card');
  card.draggable = true;
  const top = element('span', 'card-top');
  top.append(element('span', 'action-id', action.id), rowTools(action));
  const title = element('button', 'card-title', action.title);
  title.type = 'button';
  card.append(top, title);
  const meta = element('span', 'card-meta');
  meta.append(statusControl(action));
  if (action.due) meta.append(dateNode(action));
  if (action.priority === '⏫') meta.append(priorityNode(action));
  const where = element('span', 'card-project');
  where.append(action.project);
  if (action.owner) where.append(' · ', action.owner);
  card.append(meta, where);
  card.addEventListener('click', event => {
    if (!event.target.closest('button, select') || event.target === title) openEditor(action);
  });
  // Buttons and selects inside the card must not start a drag (the title button still may); capture phase, as the status select stops pointerdown.
  card.addEventListener('pointerdown', event => { card.draggable = !event.target.closest('button:not(.card-title), select'); }, true);
  for (const type of ['pointerup', 'pointercancel', 'dragend']) card.addEventListener(type, () => { card.draggable = true; });
  card.addEventListener('dragstart', event => {
    if (event.target.closest('button, select')) { event.preventDefault(); return; }
    event.dataTransfer.setData('text/plain', action.id);
    event.dataTransfer.effectAllowed = 'move';
  });
  return card;
}
// A column's cards under one header per (project, group), « Sans groupe » last (group = null); the header folds them (keys shared with the list), its « + » adds an action to the group in the column's state.
function boardGroup(key, cards, group = null, state = ' ') {
  const section = element('section', group ? `board-group ${groupTone(group.slug)}` : 'board-group');
  section.dataset.fold = key;
  const head = element('div', 'board-group-head');
  const toggle = foldToggle('board-group-toggle', key);
  const name = group ? `${group.label}, ${group.project}` : 'Sans groupe';
  if (group) toggle.append(element('span', 'group-dot'), element('span', 'board-group-label', group.label), element('span', 'board-group-project', group.project));
  else toggle.append(element('span', 'board-group-label', 'Sans groupe'));
  toggle.append(element('span', 'board-group-count', String(cards.length)));
  toggle.setAttribute('aria-label', `${name}, ${cards.length} carte${cards.length > 1 ? 's' : ''}`);
  head.append(toggle);
  if (group) head.append(addButton(group.label, {register: group.register, group: group.slug, state}));
  const body = element('div', 'board-group-cards fold-body');
  body.hidden = foldedGroups.has(key);
  cards.forEach(action => body.append(makeCard(action)));
  section.append(head, body);
  return section;
}
function renderBoard(base) {
  ids.boardView.replaceChildren();
  const scope = ids.scopeFilter.value;
  const columns = [
    {state: ' ', title: 'À faire'},
    {state: '/', title: 'En cours'},
    {state: 'w', title: 'En attente'},
    {state: 'x', title: 'Terminées récemment'}
  ];
  for (const column of columns) {
    const panel = element('section', 'board-column');
    const heading = element('div', 'board-heading');
    const all = base.filter(action => column.state === 'x' ? ['x', '-'].includes(action.state) : action.state === column.state);
    let actions = all;
    if (column.state === 'x') {
      actions = [...all].sort((a, b) => (b.done || '').localeCompare(a.done || '') || b.id.localeCompare(a.id)).slice(0, 10);
    } else if (scope === 'closed') {
      actions = [];
    } else {
      actions = sortActions(all);
    }
    heading.append(element('span', '', column.title), element('small', '', String(actions.length)));
    panel.append(heading);
    const cards = element('div', 'board-cards');
    if (!actions.length) cards.append(element('p', 'board-empty', 'Aucune action'));
    else if (!actions.some(action => action.group)) actions.forEach(action => cards.append(makeCard(action)));
    else {
      const buckets = new Map();
      for (const action of actions) {
        if (!action.group) continue;
        const key = groupKey(action);
        if (!buckets.has(key)) buckets.set(key, {key, slug: action.group, register: action.register, project: action.project, label: groupLabel(action.group), cards: []});
        buckets.get(key).cards.push(action);
      }
      const state = column.state === 'x' ? ' ' : column.state;
      for (const group of [...buckets.values()].sort(compareGroups)) cards.append(boardGroup(group.key, group.cards, group, state));
      const loose = actions.filter(action => !action.group);
      if (loose.length) cards.append(boardGroup(NO_GROUP, loose));
    }
    panel.append(cards);
    panel.addEventListener('dragover', event => { event.preventDefault(); panel.classList.add('drag-over'); });
    panel.addEventListener('dragleave', event => { if (!panel.contains(event.relatedTarget)) panel.classList.remove('drag-over'); });
    panel.addEventListener('drop', async event => {
      event.preventDefault();
      panel.classList.remove('drag-over');
      const action = snapshot.actions.find(item => item.id === event.dataTransfer.getData('text/plain'));
      if (action && action.state !== column.state) await updateStatus(action, column.state);
    });
    ids.boardView.append(panel);
  }
  applyFolds();
}
function render() {
  if (!ids.detailPreview.hidden) hidePreview();
  if (view === 'tools') {
    filterTools();
    return;
  }
  if (view === 'git') {
    renderGit();
    return;
  }
  if (view === 'search') {
    renderSearchView();
    return;
  }
  const base = filteredBase();
  const actions = scoped(base);
  const plural = actions.length !== 1;
  const qualifier = ids.scopeFilter.value === 'active' ? (plural ? 'ouvertes' : 'ouverte') :
    ids.scopeFilter.value === 'closed' ? (plural ? 'clôturées' : 'clôturée') : 'dans la sélection';
  ids.resultCount.textContent = `${actions.length} action${plural ? 's' : ''} ${qualifier}`;
  renderList(actions);
  renderBoard(base);
}
function setView(next, persist = true) {
  view = next;
  ids.filters.hidden = ['tools', 'git', 'search'].includes(next);
  ids.listView.hidden = next !== 'list';
  ids.boardView.hidden = next !== 'board';
  ids.boardHint.hidden = next !== 'board';
  ids.toolsView.hidden = next !== 'tools';
  ids.gitView.hidden = next !== 'git';
  ids.searchView.hidden = next !== 'search';
  ids.summaryChips.hidden = !['list', 'board'].includes(next);
  ids.gitStatus.hidden = next !== 'git';
  ids.lastSync.hidden = next === 'git';
  for (const [button, selected] of [[ids.listButton, next === 'list'], [ids.boardButton, next === 'board'], [ids.toolsButton, next === 'tools'], [ids.gitButton, next === 'git'], [ids.searchButton, next === 'search']]) {
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  }
  render();
  if (next === 'tools' && !tools.length) loadTools();
  if (next === 'git') loadGit();
  if (next === 'search') {
    refreshSearchView();
    if (persist) ids.docQuery.focus();
  }
  if (persist) saveUIState();
}
function populateProjects() {
  const selected = ids.projectFilter.value || pendingProject;
  const editing = ids.editorProject.value;
  ids.projectFilter.replaceChildren(new Option('Tous les projets', ''));
  ids.editorProject.replaceChildren();
  for (const register of snapshot.registers) {
    ids.projectFilter.add(new Option(register.label, register.path));
    ids.editorProject.add(new Option(register.label, register.path));
  }
  ids.projectFilter.value = selected;
  pendingProject = '';
  populateGroupFilter();
  const docBefore = ids.docProject.value;
  const docSelected = ids.docProject.value || pendingDocProject;
  ids.docProject.replaceChildren(new Option('Tous les projets', ''), new Option('Inbox', INBOX_REGISTER), new Option('Hors projets', 'none'));
  for (const register of snapshot.registers) ids.docProject.add(new Option(register.label, register.path));
  ids.docProject.value = [...ids.docProject.options].some(option => option.value === docSelected) ? docSelected : '';
  pendingDocProject = '';
  if (view === 'search' && ids.docProject.value !== docBefore && ids.docQuery.value.trim()) runDocSearch();
  ids.editorProject.value = editing || snapshot.registers[0]?.path || '';
  fillGroupOptions();
}
// Group filter: « Tous les groupes », « Sans groupe », then the groups as `register|slug` (project label as prefix unless a project is filtered); a saved group that is gone falls back to « Tous ».
function populateGroupFilter() {
  const selected = ids.groupFilter.value || pendingGroup;
  pendingGroup = '';
  const project = ids.projectFilter.value;
  const entries = [];
  for (const register of snapshot.registers) {
    if (project && register.path !== project) continue;
    for (const slug of register.groups || []) entries.push({value: `${register.path}|${slug}`, project: register.label, label: groupLabel(slug), key: slug});
  }
  entries.sort(compareGroups);
  // Every project: one <optgroup> per project (a long « projet · libellé » would hide the chosen group in the closed select); one project: plain options.
  const nodes = [];
  for (const entry of entries) {
    if (project) { nodes.push(new Option(entry.label, entry.value)); continue; }
    if (nodes.at(-1)?.label !== entry.project) { const section = document.createElement('optgroup'); section.label = entry.project; nodes.push(section); }
    nodes.at(-1).append(new Option(entry.label, entry.value));
  }
  ids.groupFilter.replaceChildren(new Option('Tous les groupes', ''), new Option('Sans groupe', 'none'), ...nodes);
  ids.groupFilter.value = [...ids.groupFilter.options].some(option => option.value === selected) ? selected : '';
  titleGroupFilter();
}
function titleGroupFilter() {
  const chosen = ids.groupFilter.selectedOptions[0];
  ids.groupFilter.title = chosen?.value && chosen.parentElement.label ? `${chosen.parentElement.label} · ${chosen.textContent}` : '';
}
// The editor's group select: « Aucun groupe », the groups already used in the selected project (labels sorted), « Nouveau groupe… » (free label, saved as its slug).
const NEW_GROUP = '__new';
function groupChoice() {
  return ids.editorGroup.value === NEW_GROUP ? {fresh: true, text: ids.editorGroupNew.value} : {slug: ids.editorGroup.value};
}
function groupValue() {
  const choice = groupChoice();
  return choice.fresh ? groupSlug(choice.text) : choice.slug;
}
// keep: a current group missing from the project's list stays as a selected option (opening); otherwise (project change) it comes back as a new group to type.
function fillGroupOptions(choice = groupChoice(), keep = false) {
  const register = snapshot.registers.find(item => item.path === ids.editorProject.value);
  const slugs = new Set(register?.groups || []);
  if (keep && choice.slug) slugs.add(choice.slug);
  if (choice.fresh && slugs.has(groupSlug(choice.text))) choice = {slug: groupSlug(choice.text)};
  const fresh = Boolean(choice.fresh || (choice.slug && !slugs.has(choice.slug)));
  const sorted = [...slugs].sort((a, b) => groupLabel(a).localeCompare(groupLabel(b), 'fr') || a.localeCompare(b));
  ids.editorGroup.replaceChildren(new Option('Aucun groupe', ''), ...sorted.map(slug => new Option(groupLabel(slug), slug)), new Option('Nouveau groupe…', NEW_GROUP));
  ids.editorGroup.value = fresh ? NEW_GROUP : choice.slug || '';
  ids.editorGroupNew.value = choice.fresh ? choice.text : fresh ? groupLabel(choice.slug) : '';
  showGroupField();
}
function showGroupField(focus = false) {
  const choice = groupChoice();
  const slug = groupValue();
  const register = snapshot.registers.find(item => item.path === ids.editorProject.value);
  ids.editorGroupNewLabel.hidden = !choice.fresh;
  ids.editorGroupHint.textContent = !choice.fresh ? (slug ? `Groupe enregistré : ${slug}` : 'Facultatif : regroupe les actions d’un même lot.') :
    !choice.text.trim() ? 'Saisis un libellé : il sera converti en identifiant.' :
    !slug ? 'Aucune lettre ni chiffre : pas de groupe.' :
    `${(register?.groups || []).includes(slug) ? 'Groupe existant' : 'Nouveau groupe enregistré'} : ${slug}`;
  if (focus && choice.fresh) ids.editorGroupNew.focus();
}
async function request(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try { payload = await response.json(); } catch { throw new Error('Réponse locale illisible.'); }
  if (!response.ok) {
    const error = new Error(payload.error || 'Opération impossible.');
    error.status = response.status;
    throw error;
  }
  return payload;
}
async function loadTools() {
  ids.toolsCatalog.textContent = 'Chargement des outils…';
  try {
    tools = (await request('/api/tools')).tools;
    ids.toolsCatalog.replaceChildren();
    const groups = [...new Set(tools.map(tool => tool.group))];
    for (const [index, group] of groups.entries()) {
      const section = element('details', 'tool-group');
      section.open = index === 0;
      const summary = element('summary', 'tool-group-heading');
      summary.append(element('strong', '', group), element('span', '', String(tools.filter(tool => tool.group === group).length)));
      section.append(summary);
      for (const tool of tools.filter(item => item.group === group)) {
        const row = element('div', 'tool-row');
        row.dataset.search = `${tool.group} ${tool.label} ${tool.description} ${tool.command}`.toLocaleLowerCase('fr');
        const copy = element('div', 'tool-copy');
        const name = element('strong', '', tool.label);
        if (tool.confirm) name.append(' ', element('span', 'tool-writes', 'modifie le brain'));
        copy.append(name, element('p', '', tool.description), element('code', '', tool.command));
        const button = element('button', 'button button-quiet', 'Lancer');
        button.type = 'button';
        button.setAttribute('aria-label', `Lancer ${tool.label}`);
        button.addEventListener('click', () => runTool(tool, button));
        row.append(copy, button);
        section.append(row);
      }
      ids.toolsCatalog.append(section);
    }
    render();
  } catch (error) {
    ids.toolsCatalog.textContent = error.message;
  }
}
function filterTools() {
  const query = ids.toolSearch.value.trim().toLocaleLowerCase('fr');
  let count = 0;
  for (const group of ids.toolsCatalog.querySelectorAll('.tool-group')) {
    let visible = 0;
    for (const row of group.querySelectorAll('.tool-row')) {
      row.hidden = Boolean(query) && !row.dataset.search.includes(query);
      if (!row.hidden) visible += 1;
    }
    group.hidden = visible === 0;
    group.querySelector('.tool-group-heading span').textContent = String(visible);
    if (query && visible) group.open = true;
    count += visible;
  }
  ids.resultCount.textContent = `${count} outil${count === 1 ? '' : 's'}`;
}
async function runTool(tool, button) {
  if (tool.confirm && !confirm(tool.confirm)) return;
  const buttons = ids.toolsCatalog.querySelectorAll('button');
  buttons.forEach(item => { item.disabled = true; });
  button.textContent = 'En cours…';
  ids.toolResultTitle.textContent = tool.label;
  ids.toolResultStatus.textContent = 'Exécution en cours';
  ids.toolResultStatus.className = '';
  ids.toolResult.classList.add('has-result');
  ids.toolResultEmpty.hidden = true;
  ids.toolResultOutput.hidden = false;
  ids.toolResultOutput.textContent = 'La commande travaille. Son résultat apparaîtra ici.';
  try {
    const result = await request('/api/tools/run', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({id: tool.id})
    });
    ids.toolResultStatus.textContent = result.ok ? 'Terminée' : 'Échec';
    ids.toolResultStatus.className = result.ok ? 'tool-status-ok' : 'tool-status-error';
    ids.toolResultOutput.textContent = result.output + (result.truncated ? '\n\n[Sortie tronquée]' : '');
    if (tool.confirm && result.ok) {
      detailCache.clear();
      await refresh();
    }
  } catch (error) {
    ids.toolResultStatus.textContent = 'Échec';
    ids.toolResultStatus.className = 'tool-status-error';
    ids.toolResultOutput.textContent = error.message;
  } finally {
    buttons.forEach(item => { item.disabled = false; });
    button.textContent = 'Lancer';
  }
}
const GIT_LABELS = {M: 'Modifié', A: 'Ajouté', D: 'Supprimé', R: 'Renommé', C: 'Copié', U: 'Conflit', '?': 'Non suivi'};
const GIT_GROUPS = [
  {key: 'staged', title: 'Indexés', test: file => file.staged},
  {key: 'unstaged', title: 'Modifiés', test: file => file.unstaged},
  {key: 'untracked', title: 'Non suivis', test: file => file.untracked}
];
let gitRepos = [];
let gitLoaded = false;
let gitCurrent = typeof savedUI.gitRepo === 'string' ? savedUI.gitRepo : 'work';
let gitLoading = null;
let gitSelected = null;
let gitDiffRequest = 0;
const gitRowSelections = new WeakMap();
const gitScrolls = new Map();
function gitPlural(count, word) { return `${count} ${word}${count === 1 ? '' : 's'}`; }
function gitBadgeClass(letter) {
  return {A: 'add', M: 'mod', D: 'del', R: 'ren', C: 'ren', U: 'del', '?': 'new'}[letter] || 'mod';
}
function gitLetter(file, group) {
  return group === 'staged' ? file.index : group === 'untracked' ? '?' : file.worktree;
}
function gitPathNode(file) {
  const path = element('span', 'git-path');
  if (file.orig_path) path.append(element('span', 'git-orig', file.orig_path), ' → ');
  const slash = file.path.lastIndexOf('/');
  if (slash >= 0) path.append(element('span', 'git-dir', file.path.slice(0, slash + 1)));
  path.append(element('span', 'git-name', file.path.slice(slash + 1)));
  return path;
}
function gitCountsNode(file, group) {
  const counts = element('span', 'git-counts');
  let added = file.added;
  let deleted = file.deleted;
  if (group === 'staged' && file.staged_added !== null) [added, deleted] = [file.staged_added, file.staged_deleted];
  if (group === 'unstaged' && file.unstaged_added !== null) [added, deleted] = [file.unstaged_added, file.unstaged_deleted];
  if (file.sensitive) counts.textContent = 'masqué';
  else if (file.binary) counts.textContent = 'binaire';
  else if (added !== null && deleted !== null) counts.append(element('span', 'git-plus', `+${added}`), ' ', element('span', 'git-minus', `−${deleted}`));
  return counts;
}
function gitRelativeDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = (date.getTime() - Date.now()) / 1000;
  const formatter = new Intl.RelativeTimeFormat('fr', {numeric: 'auto'});
  const steps = [[60, 'second', 1], [3600, 'minute', 60], [86400, 'hour', 3600], [2592000, 'day', 86400]];
  for (const [limit, unit, size] of steps) {
    if (Math.abs(seconds) < limit) return formatter.format(Math.round(seconds / size), unit);
  }
  return new Intl.DateTimeFormat('fr-FR', {day: 'numeric', month: 'short', year: 'numeric'}).format(date);
}
function gitSameSelection(a, b) {
  return Boolean(a && b) && a.repo === b.repo && a.kind === b.kind &&
    (a.kind === 'commit' ? a.hash === b.hash : a.path === b.path && a.group === b.group);
}
function gitRow(className) {
  const row = element('button', `git-row ${className}`);
  row.type = 'button';
  return row;
}
function gitFileRow(repo, file, group) {
  const row = gitRow('git-file');
  const letter = gitLetter(file, group);
  const badge = element('span', `git-badge git-badge-${gitBadgeClass(letter)}`, letter);
  badge.title = GIT_LABELS[letter] || letter;
  row.append(badge, gitPathNode(file), gitCountsNode(file, group));
  row.setAttribute('aria-label', `${GIT_LABELS[letter] || letter} : ${file.orig_path ? `${file.orig_path} → ` : ''}${file.path}`);
  const selection = {repo: repo.id, kind: 'file', path: file.path, group};
  gitRowSelections.set(row, selection);
  row.setAttribute('aria-pressed', String(gitSameSelection(selection, gitSelected)));
  row.addEventListener('click', () => selectGit(selection));
  return row;
}
function gitCommitRow(repo, commit) {
  const row = gitRow('git-commit');
  const subject = element('span', 'git-subject', commit.subject || '(sans message)');
  if (commit.unpushed) subject.append(element('span', 'git-pill', 'non poussé'));
  const meta = element('span', 'git-commit-meta', `${commit.author} · ${gitRelativeDate(commit.date)}`);
  meta.title = commit.date;
  const main = element('span', 'git-commit-main');
  main.append(subject, meta);
  row.append(element('span', 'git-hash', commit.short), main);
  const selection = {repo: repo.id, kind: 'commit', hash: commit.hash, short: commit.short, subject: commit.subject};
  gitRowSelections.set(row, selection);
  row.setAttribute('aria-pressed', String(gitSameSelection(selection, gitSelected)));
  row.addEventListener('click', () => selectGit(selection));
  return row;
}
function gitSyncNode(repo) {
  const sync = element('span', 'git-sync');
  if (repo.upstream && repo.ahead !== null && repo.behind !== null) {
    sync.textContent = `↑${repo.ahead} ↓${repo.behind}`;
    sync.title = `${gitPlural(repo.ahead, 'commit')} à pousser, ${gitPlural(repo.behind, 'commit')} à récupérer, par rapport à ${repo.upstream} (dernière synchro locale)`;
  } else if (repo.upstream) {
    sync.textContent = 'branche distante introuvable';
    sync.title = repo.upstream;
  } else {
    sync.textContent = 'pas de branche distante';
  }
  return sync;
}
function gitRepoCard(repo) {
  const card = element('section', 'git-card');
  card.setAttribute('aria-label', `Dépôt ${repo.label}`);
  const head = element('div', 'git-card-head');
  head.append(element('h3', '', repo.label));
  if (!repo.available) {
    card.append(head, element('p', 'git-unavailable', 'Dépôt Git introuvable sur cette machine.'));
    return card;
  }
  if (repo.error) {
    card.append(head, element('p', 'git-error', repo.error));
    return card;
  }
  const branch = element('span', 'git-branch', repo.detached ? `HEAD détachée (${repo.branch})` : repo.branch || '(aucune branche)');
  const sync = gitSyncNode(repo);
  sync.title = 'Avance et retard sur la branche distante, depuis la dernière synchro locale (aucun fetch depuis cette page).';
  head.append(branch, sync, element('span', 'git-count', repo.files.length ? gitPlural(repo.files.length, 'changement') : 'propre'));
  card.append(head);
  const changes = element('div', 'git-changes');
  const populated = GIT_GROUPS.map(group => [group, repo.files.filter(group.test)]).filter(([, files]) => files.length);
  if (!populated.length) changes.append(element('p', 'git-empty', 'Aucun changement local.'));
  for (const [group, files] of populated) {
    const section = element('div', 'git-group');
    const heading = element('h4', '', `${group.title} (${files.length})`);
    const list = element('ul', 'git-list');
    for (const file of files) {
      const item = element('li');
      item.append(gitFileRow(repo, file, group.key));
      list.append(item);
    }
    section.append(heading, list);
    changes.append(section);
  }
  const body = element('div', 'git-card-body');
  body.dataset.repo = repo.id;
  body.tabIndex = 0;
  body.setAttribute('aria-label', `Changements et commits de ${repo.label}`);
  body.append(changes);
  const commits = element('div', 'git-group git-commits');
  commits.append(element('h4', '', 'Derniers commits'));
  const list = element('ul', 'git-list');
  for (const commit of repo.commits) {
    const item = element('li');
    item.append(gitCommitRow(repo, commit));
    list.append(item);
  }
  commits.append(list.children.length ? list : element('p', 'git-empty', 'Aucun commit.'));
  card.append(body, commits);
  return card;
}
function renderGit() {
  const files = gitRepos.reduce((total, repo) => total + (repo.files ? repo.files.length : 0), 0);
  ids.resultCount.textContent = gitLoaded ? gitPlural(files, 'changement') + ' locaux' : '';
  if (!gitLoaded) return;
  const focused = ids.gitRepos.contains(document.activeElement) ? gitRowSelections.get(document.activeElement) : null;
  // Each repository scrolls on its own; keep each scroll position across refreshes.
  for (const body of ids.gitRepos.querySelectorAll('.git-card-body')) gitScrolls.set(body.dataset.repo, body.scrollTop);
  if (!gitRepos.some(repo => repo.id === gitCurrent) && gitRepos.length) gitCurrent = gitRepos[0].id;
  const toggle = element('div', 'git-switch');
  toggle.setAttribute('role', 'group');
  toggle.setAttribute('aria-label', 'Dépôt affiché');
  for (const repo of gitRepos) {
    const button = element('button', '', repo.label);
    button.type = 'button';
    button.setAttribute('aria-pressed', String(repo.id === gitCurrent));
    const count = repo.files ? repo.files.length : 0;
    if (count) button.append(element('span', 'git-switch-count', String(count)));
    if (repo.ahead) button.append(element('span', 'git-switch-ahead', `↑${repo.ahead}`));
    button.title = !repo.available ? 'Dépôt introuvable' : count ? gitPlural(count, 'changement') + ' locaux' : 'Aucun changement local';
    button.addEventListener('click', () => {
      if (gitCurrent === repo.id) return;
      gitCurrent = repo.id;
      saveUIState();
      renderGit();
    });
    toggle.append(button);
  }
  const current = gitRepos.find(repo => repo.id === gitCurrent);
  ids.gitRepos.replaceChildren(toggle, ...(current ? [gitRepoCard(current)] : []));
  for (const body of ids.gitRepos.querySelectorAll('.git-card-body')) body.scrollTop = gitScrolls.get(body.dataset.repo) || 0;
  if (focused) {
    const row = [...ids.gitRepos.querySelectorAll('.git-row')].find(item => gitSameSelection(gitRowSelections.get(item), focused));
    if (row) row.focus();
  }
}
function markGitSelection() {
  for (const row of ids.gitRepos.querySelectorAll('.git-row')) {
    row.setAttribute('aria-pressed', String(gitSameSelection(gitRowSelections.get(row), gitSelected)));
  }
}
function gitStillListed() {
  if (!gitSelected) return false;
  const repo = gitRepos.find(item => item.id === gitSelected.repo);
  if (!repo || !repo.available || repo.error) return false;
  if (gitSelected.kind === 'commit') return repo.commits.some(commit => commit.hash === gitSelected.hash);
  const group = GIT_GROUPS.find(item => item.key === gitSelected.group);
  return repo.files.some(file => file.path === gitSelected.path && group.test(file));
}
function loadGit() {
  if (gitLoading) return gitLoading;
  ids.gitStatus.textContent = gitLoaded ? 'Actualisation…' : 'Chargement…';
  ids.gitStatus.classList.remove('git-status-error');
  if (!gitLoaded) ids.gitRepos.textContent = 'Chargement des dépôts…';
  gitLoading = (async () => {
    try {
      gitRepos = (await request('/api/git')).repos;
      gitLoaded = true;
      ids.gitStatus.textContent = `Actualisé à ${new Intl.DateTimeFormat('fr-FR', {hour: '2-digit', minute: '2-digit'}).format(new Date())}`;
      if (view === 'git') renderGit();
      if (gitSelected && !gitStillListed()) {
        gitSelected = null;
        showGitDetail({message: 'Ce changement n\'est plus présent. Choisis un autre fichier ou commit.'});
      } else if (gitSelected) loadGitDiff();
    } catch (error) {
      ids.gitStatus.textContent = 'Échec';
      ids.gitStatus.classList.add('git-status-error');
      if (!gitLoaded) {
        const message = element('p', 'git-error', error.message);
        message.setAttribute('role', 'alert');
        ids.gitRepos.replaceChildren(message);
      } else showToast(`Git : ${error.message}`);
    } finally {
      gitLoading = null;
    }
  })();
  return gitLoading;
}
function selectGit(selection) {
  gitSelected = selection;
  markGitSelection();
  loadGitDiff();
}
function showGitDetail({title = 'Différences', status = 'Prêt', failed = false, message = '', note = '', lines = null}) {
  ids.gitDetailTitle.textContent = title;
  ids.gitDetailStatus.textContent = status;
  ids.gitDetailStatus.className = failed ? 'git-status-error' : '';
  ids.gitDetailEmpty.hidden = !message;
  ids.gitDetailEmpty.textContent = message;
  ids.gitDetailNote.hidden = !note;
  ids.gitDetailNote.textContent = note;
  ids.gitDiff.hidden = lines === null;
  if (lines === null) { ids.gitDiff.replaceChildren(); return; }
  const container = element('div', 'git-lines');
  let inDiff = false;
  let inHunk = false;
  const fragment = document.createDocumentFragment();
  for (const text of lines) {
    let kind = '';
    if (text.startsWith('diff --git')) { inDiff = true; inHunk = false; kind = 'head'; }
    else if (inDiff && text.startsWith('@@')) { inHunk = true; kind = 'hunk'; }
    else if (inHunk) kind = text.startsWith('+') ? 'add' : text.startsWith('-') ? 'del' : '';
    else if (inDiff) kind = 'head';
    const line = element('span', kind ? `git-line git-line-${kind}` : 'git-line');
    line.textContent = text;
    fragment.append(line);
  }
  container.append(fragment);
  ids.gitDiff.replaceChildren(container);
  ids.gitDiff.scrollTop = 0;
  ids.gitDiff.scrollLeft = 0;
}
async function loadGitDiff() {
  const selection = gitSelected;
  if (!selection) return;
  const repo = gitRepos.find(item => item.id === selection.repo);
  const label = repo ? repo.label : selection.repo;
  const groupTitle = selection.kind === 'file' ? GIT_GROUPS.find(group => group.key === selection.group).title.replace(/s$/, '') : '';
  const title = selection.kind === 'commit' ? `${label} · ${selection.short} ${selection.subject || ''}`.trim() : `${label} · ${selection.path} · ${groupTitle}`;
  const requestId = ++gitDiffRequest;
  showGitDetail({title, status: 'Chargement…', message: 'Chargement des différences…'});
  try {
    const params = new URLSearchParams({repo: selection.repo});
    let url;
    if (selection.kind === 'commit') {
      params.set('hash', selection.hash);
      url = `/api/git/commit?${params}`;
    } else {
      params.set('path', selection.path);
      params.set('staged', selection.group === 'staged' ? '1' : '0');
      url = `/api/git/diff?${params}`;
    }
    const result = await request(url);
    if (requestId !== gitDiffRequest) return;
    if (selection.kind === 'commit') {
      showGitDetail({title, note: result.truncated ? 'Aperçu tronqué à 300 Ko.' : '', lines: result.show.replace(/\n$/, '').split('\n')});
    } else if (result.hidden) {
      showGitDetail({title, message: 'Contenu masqué : ce fichier est considéré comme sensible (clé, secret, .env…). Rien n\'est affiché.'});
    } else if (result.binary && !result.diff.trim()) {
      showGitDetail({title, message: 'Fichier binaire : aucun aperçu des différences.'});
    } else {
      const notes = [];
      if (result.binary) notes.push('Fichier binaire : pas de détail ligne à ligne.');
      if (result.staged && selection.group !== 'staged') notes.push('Aucun changement non indexé : différences indexées affichées.');
      if (result.truncated) notes.push('Aperçu tronqué à 300 Ko.');
      showGitDetail({title, note: notes.join(' '), message: result.diff ? '' : 'Aucune différence à afficher.', lines: result.diff ? result.diff.replace(/\n$/, '').split('\n') : null});
    }
  } catch (error) {
    if (requestId !== gitDiffRequest) return;
    showGitDetail({title, status: 'Échec', failed: true, message: error.message});
  }
}
function setUndo(state) {
  undoState = state || {available: false, label: null, depth: 0};
  renderUndo();
}
function renderUndo() {
  const text = undoState.available ? `Annuler : ${undoState.label}` : 'Rien à annuler';
  ids.undoButton.disabled = undoBusy || !undoState.available;
  ids.undoButton.setAttribute('aria-busy', String(undoBusy));
  ids.undoButton.title = text;
  ids.undoButton.setAttribute('aria-label', text);
}
async function loadUndo() {
  try { setUndo(await request('/api/undo')); } catch { /* The button keeps its last known state. */ }
}
async function undoLast() {
  if (undoBusy || !undoState.available) return;
  const hadFocus = document.activeElement === ids.undoButton;
  undoBusy = true;
  renderUndo();
  try {
    const result = await request('/api/undo', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({label: undoState.label})
    });
    setUndo(result.undo);
    detailCache.clear();
    await refresh();
    showToast(`Annulé : ${result.undone}`);
  } catch (error) {
    showToast(error.message);
    await refresh();
  } finally {
    undoBusy = false;
    renderUndo();
    if (hadFocus && ids.undoButton.disabled) ids.resultCount.focus();
  }
}
// A refresh redraws the list and the board: keep each scroll position (list, board, every column).
function listScrolls() {
  return {
    list: [ids.listView.scrollTop, ids.listView.scrollLeft],
    board: ids.boardView.scrollLeft,
    columns: [...ids.boardView.querySelectorAll('.board-cards')].map(cards => cards.scrollTop)
  };
}
function restoreListScrolls(scrolls) {
  [ids.listView.scrollTop, ids.listView.scrollLeft] = scrolls.list;
  ids.boardView.scrollLeft = scrolls.board;
  ids.boardView.querySelectorAll('.board-cards').forEach((cards, index) => { cards.scrollTop = scrolls.columns[index] || 0; });
}
async function refresh() {
  if (view === 'git') loadGit();
  if (view === 'search') refreshSearchView();
  try {
    snapshot = await request('/api/actions');
    detailCache.clear();
    loadUndo();
    ids.errorBanner.hidden = true;
    ids.lastSync.textContent = `Actualisé à ${new Intl.DateTimeFormat('fr-FR', {hour: '2-digit', minute: '2-digit'}).format(new Date())}`;
    populateProjects();
    setSummary();
    const scrolls = listScrolls();
    render();
    restoreListScrolls(scrolls);
  } catch (error) {
    ids.errorBanner.textContent = error.message;
    ids.errorBanner.hidden = false;
  }
}
function docFoldChar(char) {
  let folded = docFoldCache.get(char);
  if (folded === undefined) {
    folded = char.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/ß/g, 'ss').replace(/\p{M}/gu, '');
    docFoldCache.set(char, folded);
  }
  return folded;
}
// Same normalisation as the server (accents, case, whitespace runs); starts/ends map each folded unit back to the source text.
function docFoldMap(text) {
  let folded = '';
  const starts = [];
  const ends = [];
  let spaced = false;
  for (let index = 0; index < text.length;) {
    const char = String.fromCodePoint(text.codePointAt(index));
    const next = index + char.length;
    const piece = docFoldChar(char);
    if (piece) {
      if (/^\s+$/u.test(piece)) {
        if (!spaced) { folded += ' '; starts.push(index); ends.push(next); }
        spaced = true;
      } else {
        spaced = false;
        for (let unit = 0; unit < piece.length; unit += 1) {
          folded += piece[unit];
          starts.push(index);
          ends.push(next);
        }
      }
    }
    index = next;
  }
  return {folded, starts, ends};
}
function docFindRanges(text, terms) {
  if (!terms.length || !text) return [];
  const {folded, starts, ends} = docFoldMap(text);
  const found = [];
  for (const term of terms) {
    for (let at = folded.indexOf(term); at !== -1; at = folded.indexOf(term, at + term.length)) {
      found.push([starts[at], ends[at + term.length - 1]]);
    }
  }
  found.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const merged = [];
  for (const range of found) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([range[0], range[1]]);
  }
  return merged;
}
function docMarked(text, ranges) {
  const fragment = document.createDocumentFragment();
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (start > cursor) fragment.append(text.slice(cursor, start));
    fragment.append(element('mark', '', text.slice(start, end)));
    cursor = end;
  }
  if (cursor < text.length) fragment.append(text.slice(cursor));
  return fragment;
}
function docSnippetNode(snippet) {
  const chars = Array.from(snippet.text);
  const node = element('span', 'doc-item-snippet');
  let cursor = 0;
  for (const [start, end] of snippet.ranges) {
    if (start < cursor || end > chars.length) continue;
    if (start > cursor) node.append(chars.slice(cursor, start).join(''));
    node.append(element('mark', '', chars.slice(start, end).join('')));
    cursor = end;
  }
  if (cursor < chars.length) node.append(chars.slice(cursor).join(''));
  return node;
}
function docShortPath(id) {
  return id.replace(/^projects\//, '').replace(/^clients\//, '');
}
function setDocStatus(message, failed = false) {
  ids.docStatus.textContent = message;
  ids.docStatus.className = failed ? 'doc-status doc-status-error' : 'doc-status';
}
function docItem(item, searching) {
  const li = element('li');
  const button = element('button', 'doc-item');
  button.type = 'button';
  button.dataset.docId = item.id;
  button.setAttribute('aria-pressed', String(item.id === docSelectedId));
  const title = element('strong', 'doc-item-title');
  if (searching) title.append(docMarked(item.title, docFindRanges(item.title, docTerms)));
  else title.textContent = item.title;
  const meta = element('span', 'doc-item-meta');
  if (item.project) meta.append(element('span', 'doc-pill', item.project));
  if (item.date) meta.append(element('span', 'doc-date', formatDate(item.date)));
  const path = element('span', 'doc-item-path');
  if (searching) path.append(docMarked(docShortPath(item.id), docFindRanges(docShortPath(item.id), docTerms)));
  else path.textContent = docShortPath(item.id);
  meta.append(path);
  button.append(title, meta);
  if (searching) for (const snippet of item.snippets || []) button.append(docSnippetNode(snippet));
  else if (item.excerpt) button.append(element('span', 'doc-item-excerpt', item.excerpt));
  button.addEventListener('click', () => openDoc(item.id, {nav: 'root', terms: searching ? docTerms : []}));
  li.append(button);
  return li;
}
function docEmpty(heading, message) {
  const box = element('div', 'empty');
  box.append(element('strong', '', heading), element('span', '', message));
  return box;
}
function renderDocList() {
  const searching = docMode === 'search';
  const focused = ids.docList.contains(document.activeElement) ? document.activeElement.dataset.docId : null;
  if (searching && docError) {
    ids.docList.replaceChildren(docEmpty('Recherche impossible.', docError));
    return;
  }
  if (!searching && !notesLoaded) { ids.docList.replaceChildren(); return; }
  const project = ids.docProject.value;
  const items = searching ? docResults : recentDocs;
  if (!items.length) {
    ids.docList.replaceChildren(searching
      ? docEmpty('Aucun résultat.', 'Aucun document ne contient ces termes.')
      : docEmpty('Aucun document ici.', project ? 'Aucun document pour ce filtre.' : 'Le brain ne contient encore aucun document.'));
    return;
  }
  const list = element('ul', 'doc-items');
  list.append(...items.map(item => docItem(item, searching)));
  if (searching) ids.docList.replaceChildren(list);
  else ids.docList.replaceChildren(element('h4', 'doc-list-heading', 'Modifiés récemment'), list);
  if (focused) ids.docList.querySelector(`.doc-item[data-doc-id="${CSS.escape(focused)}"]`)?.focus();
}
function renderSearchView() {
  if (docMode === 'search') {
    ids.resultCount.textContent = docError ? '' : `${docTotal} résultat${docTotal === 1 ? '' : 's'}${docTotal > docResults.length ? ` (${docResults.length} affichés)` : ''}`;
  } else {
    const project = ids.docProject.value;
    const count = recentDocs.length;
    ids.resultCount.textContent = notesLoaded ? `${count} document${count === 1 ? '' : 's'} récent${count === 1 ? '' : 's'}` : '';
  }
  renderDocList();
}
function markDocSelection() {
  for (const button of ids.docList.querySelectorAll('.doc-item')) {
    button.setAttribute('aria-pressed', String(button.dataset.docId === docSelectedId));
  }
}
async function loadNotes() {
  const requestId = ++notesRequest;
  if (docMode === 'recent') setDocStatus(notesLoaded ? 'Actualisation…' : 'Chargement…');
  try {
    const project = ids.docProject.value;
    const [data, recent] = await Promise.all([request('/api/notes'), request(`/api/docs/recent?project=${encodeURIComponent(project)}`)]);
    if (requestId !== notesRequest) return;
    notesData = data.notes;
    recentDocs = recent.docs;
    notesLoaded = true;
    if (docMode === 'recent') setDocStatus(`Actualisé à ${new Intl.DateTimeFormat('fr-FR', {hour: '2-digit', minute: '2-digit'}).format(new Date())}`);
    if (view === 'search') renderSearchView();
  } catch (error) {
    if (requestId !== notesRequest) return;
    if (docMode === 'recent') setDocStatus(`Échec : ${error.message}`, true);
  }
}
async function runDocSearch() {
  clearTimeout(docTimer);
  const query = ids.docQuery.value.trim();
  const requestId = ++docSearchRequest;
  docError = '';
  if (!query) {
    docMode = 'recent';
    docResults = [];
    docTotal = 0;
    docTerms = [];
    renderSearchView();
    loadNotes();
    return;
  }
  docMode = 'search';
  setDocStatus('Recherche…');
  try {
    const data = await request(`/api/search?${new URLSearchParams({q: query, project: ids.docProject.value})}`);
    if (requestId !== docSearchRequest) return;
    docResults = data.results;
    docTotal = data.total;
    docTerms = data.terms;
    setDocStatus(data.truncated ? `Les ${data.results.length} meilleurs résultats sont affichés.` : '');
  } catch (error) {
    if (requestId !== docSearchRequest) return;
    docResults = [];
    docTotal = 0;
    docTerms = [];
    docError = error.message;
    setDocStatus('');
  }
  renderSearchView();
}
function scheduleDocSearch() {
  clearTimeout(docTimer);
  docTimer = setTimeout(runDocSearch, 200);
}
function setDocError(message) {
  ids.docPaneError.textContent = message;
  ids.docPaneError.hidden = !message;
}
function docDirty() {
  return docEditing && docNote !== null && ids.docEditor.value !== docNote.content;
}
function renderDocPane() {
  const doc = docCurrent;
  ids.docBack.hidden = !docHistory.length;
  ids.docPaneEmpty.hidden = Boolean(doc);
  ids.docArticle.hidden = !doc || docEditing;
  ids.docEditor.hidden = !doc || !docEditing;
  ids.docEdit.hidden = !doc || !doc.note || docEditing;
  ids.docCancel.hidden = !doc || !docEditing;
  ids.docSave.hidden = !doc || !docEditing;
  ids.docSave.disabled = docSaving;
  ids.docCancel.disabled = docSaving;
  ids.docEditor.disabled = docSaving;
  ids.docPaneMeta.hidden = !doc;
  ids.docPanePath.hidden = !doc;
  if (!doc) {
    ids.docPaneTitle.textContent = 'Document';
    return;
  }
  const listed = notesData.find(item => item.id === doc.id) || recentDocs.find(item => item.id === doc.id);
  ids.docPaneTitle.textContent = doc.title;
  ids.docPaneMeta.textContent = `${doc.project || 'Hors projets'}${listed ? ` · ${formatDate(listed.date)}` : ''}`;
  ids.docPanePath.textContent = doc.id;
}
function scrollDocTo(node, center) {
  const box = ids.docArticle;
  if (box.scrollHeight > box.clientHeight + 1) {
    const offset = node.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
    box.scrollTo({top: Math.max(0, offset - (center ? box.clientHeight / 3 : 8))});
  } else node.scrollIntoView({block: center ? 'center' : 'start'});
}
function scrollDocAnchor(anchor) {
  const target = [...ids.docArticle.querySelectorAll('[id]')].find(node => node.id === anchor);
  if (target) scrollDocTo(target, false);
  return Boolean(target);
}
function highlightDocArticle(terms) {
  if (!terms.length) return 0;
  const walker = document.createTreeWalker(ids.docArticle, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  let count = 0;
  for (const node of nodes) {
    if (count >= DOC_MARK_CAP) break;
    const text = node.nodeValue;
    const ranges = docFindRanges(text, terms).slice(0, DOC_MARK_CAP - count);
    if (!ranges.length) continue;
    count += ranges.length;
    node.replaceWith(docMarked(text, ranges));
  }
  return count;
}
function showDocArticle(html, terms, anchor, keepScroll) {
  const scroll = ids.docArticle.scrollTop;
  const template = document.createElement('template');
  template.innerHTML = html;
  ids.docArticle.replaceChildren(template.content);
  highlightDocArticle(terms);
  ids.docArticle.scrollTop = keepScroll ? scroll : 0;
  if (keepScroll) return;
  if (anchor && scrollDocAnchor(anchor)) return;
  const first = ids.docArticle.querySelector('mark');
  if (first) scrollDocTo(first, true);
}
// nav: 'root' (picked from the list or created), 'link' (internal link, pushes history), 'back', 'keep' (reload in place).
async function openDoc(id, {nav = 'root', terms = [], anchor = ''} = {}) {
  if (nav !== 'keep' && docDirty() && !confirm('Abandonner les modifications non enregistrées de cette note ?')) return;
  if (nav === 'root') docHistory = [];
  else if (nav === 'link' && docCurrent) docHistory.push({id: docCurrent.id, terms: docMarks});
  else if (nav === 'back') docHistory.pop();
  const quiet = nav === 'keep' && docCurrent !== null;
  if (nav !== 'keep') { docEditing = false; docNote = null; docMarks = terms; }
  docSelectedId = id;
  const requestId = ++docRenderRequest;
  setDocError('');
  if (!quiet) {
    docCurrent = null;
    ids.docPaneEmpty.textContent = 'Chargement du document…';
    renderDocPane();
  }
  markDocSelection();
  try {
    const doc = await request(`/api/docs/render?id=${encodeURIComponent(id)}`);
    if (requestId !== docRenderRequest) return;
    docCurrent = doc;
    renderDocPane();
    showDocArticle(doc.html, docMarks, anchor, quiet);
  } catch (error) {
    if (requestId !== docRenderRequest) return;
    if (error.status === 404) {
      docSelectedId = null;
      docCurrent = null;
      docEditing = false;
      docNote = null;
      ids.docPaneEmpty.textContent = 'Ce document n’existe plus.';
    } else if (!quiet) {
      ids.docPaneEmpty.textContent = 'Document indisponible.';
      setDocError(error.message);
    } else setDocError(error.message);
    renderDocPane();
    markDocSelection();
  }
}
function docGoBack() {
  const entry = docHistory[docHistory.length - 1];
  if (entry) openDoc(entry.id, {nav: 'back', terms: entry.terms});
}
async function startDocEdit() {
  if (!docCurrent || !docCurrent.note || docEditing) return;
  const id = docCurrent.id;
  ids.docEdit.disabled = true;
  setDocError('');
  try {
    const note = await request(`/api/notes/content?id=${encodeURIComponent(id)}`);
    if (!docCurrent || docCurrent.id !== id) return;
    docNote = note;
    docEditing = true;
    ids.docEditor.value = note.content;
    renderDocPane();
    ids.docEditor.focus();
  } catch (error) {
    setDocError(error.status === 404 ? 'Cette note n’existe plus.' : error.message);
  } finally {
    ids.docEdit.disabled = false;
  }
}
function cancelDocEdit() {
  if (docSaving) return;
  if (docDirty() && !confirm('Abandonner les modifications non enregistrées de cette note ?')) return;
  docEditing = false;
  docNote = null;
  setDocError('');
  renderDocPane();
  ids.docEdit.focus();
}
async function saveDoc() {
  if (!docCurrent || !docEditing || docNote === null || docSaving) return;
  docSaving = true;
  setDocError('');
  renderDocPane();
  try {
    const result = await request('/api/notes', {
      method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({id: docNote.id, version: docNote.version, content: ids.docEditor.value})
    });
    setUndo(result.undo);
    docEditing = false;
    docNote = null;
    docSaving = false;
    showToast('Note enregistrée');
    await Promise.all([loadNotes(), openDoc(docCurrent.id, {nav: 'keep'})]);
    if (docMode === 'search') runDocSearch();
    ids.docEdit.focus();
  } catch (error) {
    setDocError(error.status === 409
      ? `${error.message} Tes modifications restent dans le champ : copie-les, puis annule et rouvre la note.`
      : error.message);
  } finally {
    docSaving = false;
    renderDocPane();
  }
}
function refreshSearchView() {
  loadNotes();
  if (ids.docQuery.value.trim() || docMode === 'search') runDocSearch();
  else { docMode = 'recent'; docError = ''; renderSearchView(); }
  if (docSelectedId && !docEditing && !docSaving) openDoc(docSelectedId, {nav: 'keep'});
}
function newNoteFolder() {
  const register = ids.newNoteProject.value;
  if (register === INBOX_REGISTER) return 'inbox/';
  return register ? register.replace(/state\/actions\.md$/, 'notes/') : '';
}
function updateNewNoteWhere() {
  ids.newNoteWhere.textContent = `Fichier créé : ${newNoteFolder()}AAAA-MM-JJ-titre.md`;
}
function openNewNote() {
  ids.newNoteProject.replaceChildren(new Option('Inbox (à trier)', INBOX_REGISTER), ...snapshot.registers.map(register => new Option(register.label, register.path)));
  const paths = [...ids.newNoteProject.options].map(option => option.value);
  ids.newNoteProject.value = paths.includes(ids.docProject.value) ? ids.docProject.value : INBOX_REGISTER;
  ids.newNoteTitle.value = '';
  ids.newNoteContent.value = '';
  ids.newNoteError.hidden = true;
  ids.saveNewNote.disabled = false;
  updateNewNoteWhere();
  ids.newNoteDialog.showModal();
  ids.newNoteTitle.focus();
}
async function createNote(event) {
  event.preventDefault();
  if (!ids.newNoteForm.reportValidity()) return;
  ids.saveNewNote.disabled = true;
  ids.newNoteError.hidden = true;
  try {
    const result = await request('/api/notes', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({title: ids.newNoteTitle.value.trim(), register: ids.newNoteProject.value, content: ids.newNoteContent.value})
    });
    setUndo(result.undo);
    ids.newNoteDialog.close();
    if (docDirty() && !confirm('Abandonner les modifications non enregistrées du document ouvert ?')) {
      if (view === 'search') await loadNotes();
      showToast('Note créée');
      return;
    }
    docEditing = false;
    docNote = null;
    docSelectedId = null;
    docCurrent = null;
    ids.docQuery.value = '';
    ids.docProject.value = '';
    setView('search');
    showToast('Note créée');
    await openDoc(result.id, {nav: 'root'});
  } catch (error) {
    ids.newNoteError.textContent = error.message;
    ids.newNoteError.hidden = false;
  } finally {
    ids.saveNewNote.disabled = false;
  }
}
function showToast(message) {
  ids.toast.textContent = message;
  ids.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { ids.toast.hidden = true; }, 3500);
}
function formAction() {
  return {
    title: ids.editorActionTitle.value.replace(/[\r\n]+/g, ' ').trim(), owner: ids.editorOwner.value.trim(),
    state: ids.editorState.value, priority: ids.editorPriority.value,
    due: ids.editorDue.value, scheduled: ids.editorScheduled.value, group: groupValue()
  };
}
function sizeTitleField() {
  ids.editorActionTitle.style.height = 'auto';
  ids.editorActionTitle.style.height = `${Math.min(ids.editorActionTitle.scrollHeight + 2, 400)}px`;
}
// preset (creation only): {register, group (slug), state} pre-fills the form; the top bar's « + Task » passes none.
function openEditor(action = null, preset = null) {
  hidePreview();
  const historyRequest = ++editorHistoryRequest;
  ids.editor.dataset.actionId = action?.id || '';
  ids.editor.dataset.version = action?.version || '';
  ids.editor.dataset.title = action?.title || '';
  ids.editorTitle.textContent = action ? `Modifier ${action.id}` : 'Nouvelle action';
  const target = !action && preset?.register && snapshot.registers.find(register => register.path === preset.register);
  ids.editorHint.textContent = action ? `${action.project} · les changements seront enregistrés dans son registre.` :
    target ? `${target.label}${preset.group ? ` · groupe ${groupLabel(preset.group)}` : ''} · décris l’action.` : 'Choisis un projet puis décris l’action.';
  ids.editorProject.disabled = Boolean(action);
  ids.editorProject.value = action?.register || preset?.register || ids.projectFilter.value || snapshot.registers[0]?.path || '';
  ids.editorActionTitle.value = action?.raw_title || '';
  fillGroupOptions({slug: action?.group || (!action && preset?.group) || ''}, true);
  ids.editorHistory.hidden = !action;
  noteState = null;
  noteBusy = false;
  closeNoteForm(false);
  ids.noteInput.value = '';
  ids.addNoteButton.disabled = true;
  ids.editorHistoryList.replaceChildren(element('li', 'note-empty', 'Chargement…'));
  ids.editorHistoryCount.textContent = '';
  ids.editorOwner.value = action?.owner || snapshot.owner;
  ids.editorState.value = action?.state || (!action && preset?.state) || ' ';
  ids.editorPriority.value = action?.priority || '';
  ids.editorDue.value = action?.due || '';
  ids.editorScheduled.value = action?.scheduled || '';
  ids.saveEditor.textContent = action ? 'Enregistrer' : 'Créer l’action';
  ids.deleteEditor.hidden = !action;
  setEditorBusy(false);
  ids.editorError.hidden = true;
  ids.editor.showModal();
  sizeTitleField();
  ids.editorActionTitle.focus();
  if (action) {
    loadDetails(action).then(details => {
      if (historyRequest !== editorHistoryRequest || !ids.editor.open) return;
      renderNotes(details);
    }).catch(error => {
      if (historyRequest !== editorHistoryRequest || !ids.editor.open) return;
      ids.editorHistoryList.replaceChildren(element('li', 'note-empty', `Historique indisponible : ${error.message}`));
    });
  }
}
function trashIcon() {
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.setAttribute('viewBox', '0 0 24 24');
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v6M14 11v6"/>';
  return icon;
}
function renderNotes(details) {
  noteState = {id: details.id, version: details.details_version, notes: details.notes};
  ids.editorHistoryList.replaceChildren();
  if (!details.notes.length) ids.editorHistoryList.append(element('li', 'note-empty', 'Aucune note pour l’instant.'));
  for (const note of details.notes) {
    const item = element('li', `note-item${note.deletable ? '' : ' note-source'}`);
    item.append(element('span', 'note-text', note.text.replace(/^-\s+/, '')));
    if (note.deletable) {
      const button = element('button', 'note-delete');
      button.type = 'button';
      button.setAttribute('aria-label', 'Supprimer la note');
      button.title = 'Supprimer la note';
      button.append(trashIcon());
      button.addEventListener('click', () => deleteNote(note));
      item.append(button);
    }
    ids.editorHistoryList.append(item);
  }
  const count = details.notes.length;
  ids.editorHistoryCount.textContent = count ? `${count} note${count > 1 ? 's' : ''}` : '';
  setNoteBusy(false);
}
function setNoteBusy(busy) {
  noteBusy = busy;
  ids.addNoteButton.disabled = busy || !noteState;
  ids.submitNote.disabled = busy || !noteState;
  ids.editorHistoryList.querySelectorAll('.note-delete').forEach(button => { button.disabled = busy; });
}
function showNoteError(error) {
  ids.noteError.textContent = error.status === 409 ? 'L’historique a changé dans le registre : ferme puis rouvre l’action pour le recharger.' : error.message;
  ids.noteError.hidden = false;
}
function forgetDetails(id, fresh) {
  for (const key of [...detailCache.keys()]) if (key.startsWith(`${id}:`)) detailCache.delete(key);
  detailCache.set(`${id}:${fresh.version}`, Promise.resolve(fresh));
}
function openNoteForm() {
  ids.noteForm.hidden = false;
  ids.addNoteButton.setAttribute('aria-expanded', 'true');
  ids.noteInput.focus();
  ids.noteForm.scrollIntoView({block: 'nearest'});
}
function closeNoteForm(focus = true) {
  ids.noteForm.hidden = true;
  ids.noteError.hidden = true;
  ids.addNoteButton.setAttribute('aria-expanded', 'false');
  if (focus && ids.editor.open) ids.addNoteButton.focus();
}
async function changeNotes(send) {
  const session = editorHistoryRequest;
  const id = noteState.id;
  setNoteBusy(true);
  ids.noteError.hidden = true;
  try {
    const fresh = await send();
    setUndo(fresh.undo);
    forgetDetails(id, fresh);
    if (session !== editorHistoryRequest || !ids.editor.open) return null;
    renderNotes(fresh);
    return fresh;
  } catch (error) {
    if (session === editorHistoryRequest && ids.editor.open) {
      setNoteBusy(false);
      showNoteError(error);
    }
    return null;
  }
}
async function submitNote() {
  if (noteBusy || !noteState) return;
  const note = ids.noteInput.value.replace(/\s*[\r\n\u2028\u2029]+\s*/g, ' ').trim();
  if (!note) {
    showNoteError(new Error('Saisis une note avant d’ajouter.'));
    ids.noteInput.focus();
    return;
  }
  const {id, version} = noteState;
  const fresh = await changeNotes(() => request(`/api/actions/${encodeURIComponent(id)}/notes`, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
    body: JSON.stringify({details_version: version, note})
  }));
  if (fresh) {
    ids.noteInput.value = '';
    ids.noteInput.focus();
    ids.editorHistoryList.scrollTop = ids.editorHistoryList.scrollHeight;
  } else if (ids.editor.open) ids.noteInput.focus();
}
async function deleteNote(note) {
  if (noteBusy || !noteState || !confirm('Supprimer cette note du registre ?')) return;
  const {id, version} = noteState;
  const fresh = await changeNotes(() => request(`/api/actions/${encodeURIComponent(id)}/notes/${note.index}`, {
    method: 'DELETE', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
    body: JSON.stringify({details_version: version, text: note.text})
  }));
  if (!ids.editor.open) return;
  if (fresh) (ids.editorHistoryList.querySelectorAll('.note-delete')[Math.max(0, note.index - 1)] || ids.addNoteButton).focus();
  else (ids.editorHistoryList.querySelectorAll('.note-delete')[note.index] || ids.addNoteButton).focus();
}
function setEditorBusy(busy) {
  for (const button of [ids.saveEditor, ids.deleteEditor]) button.disabled = busy;
}
// No confirmation: ↶ Annuler (and Git) restore a deleted action.
// Shared by the editor and the list/board buttons: checks `version` and `details_version`, then stacks the undo.
async function removeAction(id, version, detailsVersion = null) {
  const details = detailsVersion ?? (await loadDetails({id, version})).details_version;
  const result = await request(`/api/actions/${encodeURIComponent(id)}`, {
    method: 'DELETE', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
    body: JSON.stringify({version, details_version: details})
  });
  for (const key of [...detailCache.keys()]) if (key.startsWith(`${id}:`)) detailCache.delete(key);
  setUndo(result.undo);
}
async function deleteEditor() {
  const id = ids.editor.dataset.actionId;
  if (!id || ids.deleteEditor.disabled || noteBusy) return;
  setEditorBusy(true);
  ids.editorError.hidden = true;
  try {
    await removeAction(id, ids.editor.dataset.version, noteState?.id === id ? noteState.version : null);
    ids.editor.close();
    await refresh();
    showToast(`${id} supprimée · ↶ Annuler pour la restaurer`);
  } catch (error) {
    ids.editorError.textContent = error.status === 409 ? 'Le registre a changé : ferme puis rouvre l’action avant de la supprimer.' : error.message;
    ids.editorError.hidden = false;
  } finally {
    setEditorBusy(false);
  }
}
async function deleteFromBoard(action, button) {
  if (button.disabled) return;
  hidePreview();
  button.disabled = true;
  try {
    await removeAction(action.id, action.version);
    await refresh();
    showToast(`${action.id} supprimée · ↶ Annuler pour la restaurer`);
  } catch (error) {
    const conflict = error.status === 409;
    if (conflict) await refresh();
    ids.errorBanner.textContent = conflict ? `Le registre a changé : la liste a été actualisée, vérifie ${action.id} puis recommence.` : error.message;
    ids.errorBanner.hidden = false;
    button.disabled = false;
  }
}
async function saveEditor(event) {
  event.preventDefault();
  if (!ids.editorForm.reportValidity()) return;
  const action = formAction();
  const id = ids.editor.dataset.actionId;
  setEditorBusy(true);
  try {
    if (id) {
      setUndo((await request(`/api/actions/${encodeURIComponent(id)}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
        body: JSON.stringify({version: ids.editor.dataset.version, action})
      })).undo);
      showToast(`${id} enregistrée`);
    } else {
      const result = await request('/api/actions', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
        body: JSON.stringify({register: ids.editorProject.value, action})
      });
      setUndo(result.undo);
      showToast(`${result.id} créée`);
    }
    ids.editor.close();
    await refresh();
  } catch (error) {
    ids.editorError.textContent = error.message;
    ids.editorError.hidden = false;
  } finally {
    setEditorBusy(false);
  }
}
async function updateStatus(action, state, source = null) {
  if (state === action.state) return;
  if (source) source.disabled = true;
  try {
    setUndo((await request(`/api/actions/${encodeURIComponent(action.id)}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({version: action.version, action: {
        title: action.raw_title, owner: action.owner, state, priority: action.priority,
        due: action.due, scheduled: action.scheduled
      }})
    })).undo);
    showToast(`${action.id} : statut « ${statusLabel(state)} » enregistré`);
    await refresh();
    if (source) {
      const activeView = view === 'board' ? ids.boardView : ids.listView;
      const next = activeView.querySelector(`.status-select[data-action-id="${action.id}"]`);
      (next || ids.resultCount).focus({preventScroll: true});
    }
  } catch (error) {
    await refresh();
    ids.errorBanner.textContent = error.message;
    ids.errorBanner.hidden = false;
    if (source) {
      const activeView = view === 'board' ? ids.boardView : ids.listView;
      (activeView.querySelector(`.status-select[data-action-id="${action.id}"]`) || ids.resultCount).focus({preventScroll: true});
    }
  }
}

ids.listButton.addEventListener('click', () => setView('list'));
ids.boardButton.addEventListener('click', () => setView('board'));
ids.toolsButton.addEventListener('click', () => setView('tools'));
ids.gitButton.addEventListener('click', () => setView('git'));
ids.searchButton.addEventListener('click', () => setView('search'));
ids.newNoteButton.addEventListener('click', openNewNote);
ids.docQuery.addEventListener('input', () => { scheduleDocSearch(); saveUIState(); });
ids.docQuery.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); runDocSearch(); }
});
ids.docProject.addEventListener('change', () => { runDocSearch(); saveUIState(); });
ids.docBack.addEventListener('click', docGoBack);
ids.docEdit.addEventListener('click', startDocEdit);
ids.docCancel.addEventListener('click', cancelDocEdit);
ids.docSave.addEventListener('click', saveDoc);
ids.docEditor.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); saveDoc(); }
});
ids.docArticle.addEventListener('click', event => {
  const link = event.target.closest('a.doc-link');
  if (!link || !ids.docArticle.contains(link)) return;
  event.preventDefault();
  const id = link.dataset.doc;
  const anchor = link.dataset.anchor || '';
  if (docCurrent && id === docCurrent.id) { if (anchor) scrollDocAnchor(anchor); return; }
  openDoc(id, {nav: 'link', anchor});
});
ids.newNoteForm.addEventListener('submit', createNote);
ids.newNoteProject.addEventListener('change', updateNewNoteWhere);
ids.closeNewNote.addEventListener('click', () => ids.newNoteDialog.close());
ids.cancelNewNote.addEventListener('click', () => ids.newNoteDialog.close());
ids.projectFilter.addEventListener('change', populateGroupFilter);
ids.groupFilter.addEventListener('change', titleGroupFilter);
for (const node of [ids.searchInput, ids.projectFilter, ids.groupFilter, ids.ownerFilter, ids.scopeFilter]) {
  node.addEventListener(node === ids.searchInput ? 'input' : 'change', () => { render(); saveUIState(); });
}
ids.resetFilters.addEventListener('click', () => {
  ids.searchInput.value = '';
  ids.projectFilter.value = '';
  ids.groupFilter.value = '';
  populateGroupFilter();
  ids.ownerFilter.value = '';
  ids.scopeFilter.value = 'active';
  render();
  saveUIState();
  ids.searchInput.focus();
});
ids.toolSearch.addEventListener('input', () => { filterTools(); saveUIState(); });
document.getElementById('refreshButton').addEventListener('click', refresh);
ids.undoButton.addEventListener('click', undoLast);
document.getElementById('quitButton').addEventListener('click', async () => {
  const button = document.getElementById('quitButton');
  button.disabled = true;
  try {
    await request('/api/shutdown', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: '{}'
    });
    document.body.replaceChildren(element('main', 'stopped-screen', 'Actions Brain est arrêté. Tu peux fermer cet onglet. Relance l’app depuis le Dock pour le rouvrir.'));
    window.close();
  } catch (error) {
    button.disabled = false;
    showToast(`Arrêt impossible : ${error.message}`);
  }
});
document.getElementById('newButton').addEventListener('click', () => openEditor());
document.getElementById('closeEditor').addEventListener('click', () => ids.editor.close());
document.getElementById('cancelEditor').addEventListener('click', () => ids.editor.close());
ids.editorForm.addEventListener('submit', saveEditor);
ids.deleteEditor.addEventListener('click', deleteEditor);
ids.editorActionTitle.addEventListener('input', sizeTitleField);
ids.editorProject.addEventListener('change', () => fillGroupOptions());
ids.editorGroup.addEventListener('change', () => showGroupField(true));
ids.editorGroupNew.addEventListener('input', () => showGroupField());
ids.addNoteButton.addEventListener('click', openNoteForm);
ids.closeNoteForm.addEventListener('click', () => closeNoteForm());
ids.submitNote.addEventListener('click', submitNote);
ids.noteInput.addEventListener('keydown', event => {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeNoteForm(); }
  else if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); if (!event.shiftKey) submitNote(); }
});
ids.editor.addEventListener('cancel', event => {
  if (!ids.noteForm.hidden && ids.noteForm.contains(document.activeElement)) { event.preventDefault(); closeNoteForm(); }
});
ids.closeDetail.addEventListener('click', () => ids.detailDialog.close());
ids.dismissDetail.addEventListener('click', () => ids.detailDialog.close());
ids.editDetail.addEventListener('click', () => {
  if (!detailCurrent) return;
  ids.detailDialog.close();
  openEditor(detailCurrent);
});
ids.detailDialog.addEventListener('close', () => {
  detailCurrent = null;
  suppressPreviewFocus = true;
  hidePreview();
  setTimeout(() => { suppressPreviewFocus = false; }, 0);
});
ids.searchInput.value = typeof savedUI.search === 'string' ? savedUI.search : '';
ids.ownerFilter.value = savedUI.owner === 'mine' ? 'mine' : '';
ids.scopeFilter.value = ['active', 'all', 'closed'].includes(savedUI.scope) ? savedUI.scope : 'active';
ids.toolSearch.value = typeof savedUI.toolSearch === 'string' ? savedUI.toolSearch : '';
ids.docQuery.value = typeof savedUI.docQuery === 'string' ? savedUI.docQuery : '';
setView(view, false);
refresh();
