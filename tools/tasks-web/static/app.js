'use strict';

const token = document.querySelector('meta[name="csrf-token"]').content;
const ids = Object.fromEntries([
  'app', 'sidebar', 'scrim', 'sidebarToggle', 'brainMini', 'sidebarClose', 'mainContent',
  'brainSwitch', 'brainStatic', 'brainStaticName', 'brainButton', 'brainName', 'brainMenu',
  'todayButton', 'listButton', 'boardButton', 'timelineButton', 'notesButton', 'searchButton', 'toolsButton', 'gitButton',
  'todayCount', 'openCount', 'gitCount', 'projectNav', 'lastSync',
  'moreButton', 'moreMenu', 'refreshButton', 'undoButton', 'undoLabel', 'shortcutsButton', 'quitButton',
  'viewTitle', 'resultCount', 'gitStatus', 'searchField', 'searchInput', 'docQuery', 'toolSearch', 'newNoteButton', 'newButton',
  'filters', 'projectChip', 'projectChipValue', 'projectChipClear', 'ownerChip', 'ownerFilter', 'scopeChip', 'scopeFilter',
  'groupChip', 'groupFilter', 'docProjectChip', 'docProject', 'resetFilters', 'foldAllButton', 'errorBanner',
  'todayView', 'listView', 'boardView', 'timelineView', 'timelineBack', 'timelineToday', 'timelineForward', 'timelineLate', 'timelineDone', 'timelineScale', 'timelineSummary',
  'timelineScroll', 'timelineTray', 'timelineTrayToggle', 'timelineTrayCount', 'timelineTrayMore', 'timelineTrayHint', 'timelineTraySearch',
  'timelineTrayBody', 'timelineTrayList', 'docsView', 'docStatus', 'docList', 'docPane', 'docBack', 'docPaneTitle', 'docPaneMeta',
  'docPanePath', 'docEdit', 'docDelete', 'docCancel', 'docSave', 'docPaneEmpty', 'docPaneError', 'docArticle', 'docEditorToolbar', 'docEditor',
  'toolsView', 'toolsCatalog', 'toolResult', 'toolResultTitle', 'toolResultCommand', 'toolResultStatus', 'toolResultEmpty', 'toolResultOutput',
  'gitView', 'gitCards', 'syncInfo', 'gitConfirmDialog', 'gitConfirmText', 'gitConfirmList', 'gitConfirmGo',
  'gitChangesDialog', 'gitChangesTitle', 'gitChangesMeta', 'gitChangesBody', 'gitChangesClose',
  'editor', 'editorForm', 'editorTitle', 'editorHint', 'closeEditor', 'editorProjectField', 'editorProject', 'editorActionTitle',
  'editorState', 'editorOwner', 'editorDue', 'editorScheduled', 'editorPriority', 'editorGroup', 'editorGroupNewLabel',
  'editorGroupNew', 'editorGroupHint', 'editorHistory', 'editorHistoryCount', 'addNoteButton', 'editorHistoryList', 'noteForm',
  'noteInput', 'submitNote', 'closeNoteForm', 'noteError', 'editorStamps', 'editorError', 'deleteEditor', 'cancelEditor', 'saveEditor',
  'popover', 'newNoteDialog', 'newNoteForm', 'closeNewNote', 'newNoteTitle', 'newNoteProject', 'newNoteWhere', 'newNoteToolbar', 'newNoteContent',
  'newNoteError', 'cancelNewNote', 'saveNewNote', 'deleteNoteDialog', 'deleteNoteHeading', 'deleteNoteText', 'deleteNoteLinks', 'deleteNoteError', 'deleteNoteCancel', 'deleteNoteConfirm', 'quitDialog', 'quitConfirm', 'shortcutsDialog', 'toast', 'toastText', 'toastAction'
].map(id => [id, document.getElementById(id)]));

// The interface text is English; dates, relative times, case changes and sorting follow the browser's locale.
const LOCALE = navigator.language || undefined;

// ---------- Session state (view and filters of this tab; no task content) ----------
const UI_STATE_KEY = 'actions-brain-ui-v1';
function readUIState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(UI_STATE_KEY));
    return saved && typeof saved === 'object' ? saved : {};
  } catch { return {}; }
}
const savedUI = readUIState();
const VIEWS = ['today', 'list', 'board', 'timeline', 'notes', 'search', 'tools', 'git'];
const ACTION_VIEWS = ['today', 'list', 'board', 'timeline'];
const VIEW_TITLES = {today: 'Today', list: 'Actions', board: 'Board', timeline: 'Timeline', notes: 'Notes', search: 'Search', tools: 'Tools', git: 'Sync'};
const NAV_BUTTONS = {today: 'todayButton', list: 'listButton', board: 'boardButton', timeline: 'timelineButton', notes: 'notesButton', search: 'searchButton', tools: 'toolsButton', git: 'gitButton'};
let view = VIEWS.includes(savedUI.view) ? savedUI.view : 'today';
// The project filter of the sidebar: '' (all), a register path, or a folder prefix ending with '/' (a client and its missions).
let projectScope = typeof savedUI.project === 'string' ? savedUI.project : '';
let pendingGroup = typeof savedUI.group === 'string' ? savedUI.group : '';
// Folded sections, shared by the list and the board: `register|slug` for a group, `register|` for the loose actions of a project,
// `p:register` for a project, '|' for "No group" in a board column.
const foldedGroups = new Set(Array.isArray(savedUI.foldedGroups) ? savedUI.foldedGroups.filter(key => typeof key === 'string') : []);
// Timeline: the range (two, six, quarter), whether done actions show, whether the next draw brings today into view, the last layout.
let timelineRange = ['two', 'six', 'quarter'].includes(savedUI.timelineRange) ? savedUI.timelineRange : 'six';
let timelineDone = savedUI.timelineDone === true;
let timelineAnchor = true;
let timelineModel = null;
let timelineNarrow = false;
let timelineSpot = ''; // 'overdue', 'week', 'next': the others dim
let timelineTrayOpen = typeof savedUI.timelineTray === 'boolean' ? savedUI.timelineTray : null; // null: open on a wide page, closed on a narrow one
let timelineBase = []; // the actions the view was last drawn from
let timelineWidth = 0;
let timelineDrag = null;
let snapshot = {actions: [], registers: [], owner: '', today: ''};
let toastTimer;
let tools = [];
let editorHistoryRequest = 0;
let noteState = null;
let noteBusy = false;
let undoState = {available: false, label: null, depth: 0};
let undoBusy = false;
let selectedId = null;
let notesData = [];
let notesLoaded = false;
let recentDocs = [];
let notesRequest = 0;
let docTimer;
let docMode = 'recent';
let docResults = [];
let docTotal = 0;
let docTruncated = false;
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
function saveUIState() {
  try {
    sessionStorage.setItem(UI_STATE_KEY, JSON.stringify({
      view, search: ids.searchInput.value, project: projectScope, group: ids.groupFilter.value || pendingGroup,
      owner: ids.ownerFilter.value, scope: ids.scopeFilter.value, toolSearch: ids.toolSearch.value,
      docQuery: ids.docQuery.value, docProject: ids.docProject.value, foldedGroups: [...foldedGroups], brain: currentBrain, timelineRange, timelineDone, timelineTray: timelineTrayOpen
    }));
  } catch { /* The interface remains usable when browser storage is unavailable. */ }
}

// ---------- Small helpers ----------
const SVG_NS = 'http://www.w3.org/2000/svg';
function element(tag, className = '', value = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value) node.textContent = value;
  return node;
}
function svgIcon(markup, className = '') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('aria-hidden', 'true');
  if (className) svg.setAttribute('class', className);
  svg.innerHTML = markup;
  return svg;
}
function iconButton(className, label, icon, title = label) {
  const button = element('button', className);
  button.type = 'button';
  button.setAttribute('aria-label', label);
  button.title = title;
  button.append(svgIcon(icon));
  return button;
}
const ICONS = {
  open: '<path d="M9.5 3h3.5v3.5M13 3 8.5 7.5M7 4H4.5A1.5 1.5 0 0 0 3 5.5v6A1.5 1.5 0 0 0 4.5 13h6a1.5 1.5 0 0 0 1.5-1.5V9"/>',
  trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5"/>',
  plus: '<path d="M8 3.5v9M3.5 8h9"/>',
  chevron: '<path d="M4.5 6.25 8 9.75l3.5-3.5"/>',
  calendar: '<rect x="2.75" y="3.5" width="10.5" height="9.5" rx="1.5"/><path d="M2.75 6.5h10.5M5.5 2.5v2M10.5 2.5v2"/>',
  check: '<path d="M3.5 8.5l3 3 6-6.5"/>',
  // Markdown toolbar
  bold: '<path stroke-width="1.9" d="M4.75 3h3.5a2.25 2.25 0 0 1 0 4.5h-3.5zM4.75 7.5h4a2.5 2.5 0 0 1 0 5h-4z"/>',
  italic: '<path d="M10 3H7M9 13H6M9.2 3 6.8 13"/>',
  underline: '<path d="M4.75 2.75v5a3.25 3.25 0 0 0 6.5 0v-5M3.5 13.5h9"/>',
  strike: '<path d="M2.5 8h11M10.8 5.3c-.2-1.3-1.3-2.1-2.8-2.1-1.6 0-2.7.9-2.7 2.1 0 1 .6 1.6 1.7 2M8.6 8.5c1.4.4 2.1 1.1 2.1 2.2 0 1.3-1.2 2.2-2.7 2.2-1.5 0-2.6-.8-2.8-2.1"/>',
  bullets: '<path d="M6.5 4.5h7M6.5 8h7M6.5 11.5h7"/><path stroke-width="2.4" d="M2.75 4.5h.01M2.75 8h.01M2.75 11.5h.01"/>',
  numbers: '<path d="M7.25 4h6.25M7.25 8.2h6.25M7.25 12.4h6.25M2.3 3.2l1.3-1v3.3M2.3 7.2c.3-.6.8-.9 1.4-.9.7 0 1.2.4 1.2 1 0 1.2-1.8 1.7-2.6 2.9h2.7M2.3 11.7c.2-.5.7-.8 1.3-.8.7 0 1.1.4 1.1.9s-.5.9-1.2.9c.8 0 1.3.4 1.3 1s-.6 1-1.3 1c-.7 0-1.2-.3-1.3-.8"/>',
  tasks: '<rect x="2.25" y="2.75" width="4" height="4" rx="1"/><path d="M3.3 4.8l.8.8 1.3-1.5M8 4.75h5.5M8 11.25h5.5"/><rect x="2.25" y="9.25" width="4" height="4" rx="1"/>',
  quote: '<path d="M3.5 7.5V4h2.7v3.5c0 1.7-.7 2.9-2.4 3.5M9.8 7.5V4h2.7v3.5c0 1.7-.7 2.9-2.4 3.5"/>',
  code: '<path d="M5.25 4.5 1.75 8l3.5 3.5M10.75 4.5 14.25 8l-3.5 3.5M9 3.25 7 12.75"/>',
  link: '<path d="M6.75 9.25a2.5 2.5 0 0 0 3.5 0l2.25-2.25a2.5 2.5 0 0 0-3.5-3.5l-.75.75M9.25 6.75a2.5 2.5 0 0 0-3.5 0L3.5 9a2.5 2.5 0 0 0 3.5 3.5l.75-.75"/>',
  arrow: '<path d="M2.5 8h11M9.5 4l4 4-4 4"/>',
  // Timeline
  late: '<circle cx="8" cy="8" r="5.75"/><path d="M8 4.9v3.6M8 10.9h.01"/>',
  hourglass: '<path d="M4.75 2.75h6.5M4.75 13.25h6.5M5.5 2.75v1.6c0 1.7 2.5 2.4 2.5 3.65s-2.5 1.95-2.5 3.65v1.6M10.5 2.75v1.6c0 1.7-2.5 2.4-2.5 3.65s2.5 1.95 2.5 3.65v1.6"/>',
  info: '<circle cx="8" cy="8" r="5.75"/><path d="M8 7.2v3.6M8 5.2h.01"/>',
  // Git: save and send
  gitSaved: '<circle cx="8" cy="8" r="5.75"/><path d="M5.4 8.3l1.9 1.9 3.5-3.9"/>',
  gitEdited: '<path d="M3 13l.8-3.2L10.6 3a1.5 1.5 0 0 1 2.1 0l.3.3a1.5 1.5 0 0 1 0 2.1L6.2 12.2z"/><path d="M9.2 4.4l2.4 2.4"/>',
  gitSend: '<path d="M8 10.5V3M4.9 5.9 8 2.8l3.1 3.1M3 10.5v1.8c0 .5.4.9.9.9h8.2c.5 0 .9-.4.9-.9v-1.8"/>',
  gitBehind: '<path d="M8 2.8v7.7M4.9 7.4 8 10.5l3.1-3.1M3 10.5v1.8c0 .5.4.9.9.9h8.2c.5 0 .9-.4.9-.9v-1.8"/>',
  gitOff: '<circle cx="8" cy="8" r="5.75"/><path d="M4 12 12 4"/>'
};
function plural(count, word, words = `${word}s`) { return `${count} ${count === 1 ? word : words}`; }
const TIME_FORMAT = new Intl.DateTimeFormat(LOCALE, {hour: '2-digit', minute: '2-digit'});
const DAY_FORMAT = new Intl.DateTimeFormat(LOCALE, {weekday: 'short', day: 'numeric', month: 'short'});
const DAY_YEAR_FORMAT = new Intl.DateTimeFormat(LOCALE, {day: 'numeric', month: 'short', year: 'numeric'});
const LONG_FORMAT = new Intl.DateTimeFormat(LOCALE, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
function parseDay(iso) {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day, 12);
}
function isoDay(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
function today() { return snapshot.today || isoDay(new Date()); }
function addDays(iso, count) {
  const date = parseDay(iso);
  date.setDate(date.getDate() + count);
  return isoDay(date);
}
function dayDiff(from, to) { return Math.round((parseDay(to) - parseDay(from)) / 86400000); }
function formatDay(iso) { return iso ? DAY_YEAR_FORMAT.format(parseDay(iso)) : ''; }
function formatStamp(value) {
  if (!value) return '';
  const [day, time] = value.split(' ');
  return time ? `${formatDay(day)} at ${time}` : formatDay(day);
}
// "today", "tomorrow", "yesterday", otherwise "Mon, Oct 27" ("Jan 12, 2027" in another year), in the browser's locale.
function relativeDay(iso) {
  const diff = dayDiff(today(), iso);
  if (diff === 0) return 'today';
  if (diff === 1) return 'tomorrow';
  if (diff === -1) return 'yesterday';
  return iso.slice(0, 4) === today().slice(0, 4) ? DAY_FORMAT.format(parseDay(iso)) : DAY_YEAR_FORMAT.format(parseDay(iso));
}
function closed(action) { return action.state === 'x' || action.state === '-'; }
// The mission part of "client / mission" (the whole label otherwise), for narrow places; the full label goes in the tooltip.
function shortProject(label) { return label.split(' / ').at(-1); }
function dueState(action) {
  if (!action.due) return '';
  if (closed(action)) return 'closed';
  return action.due < today() ? 'late' : action.due === today() ? 'today' : '';
}
function dueTitle(action) {
  const late = dueState(action) === 'late' ? dayDiff(action.due, today()) : 0;
  return `Due on ${LONG_FORMAT.format(parseDay(action.due))}${late ? `, ${plural(late, 'day')} overdue` : ''}`;
}
function dueNode(action) {
  const state = dueState(action);
  const node = element('span', `due${state ? ` due-${state}` : ''}`, relativeDay(action.due));
  node.title = dueTitle(action);
  return node;
}

// ---------- Status and priority ----------
const STATUS = {
  ' ': {label: 'To do', cls: 's-todo', icon: '<circle class="ring" cx="8" cy="8" r="5.75"/>'},
  '/': {label: 'In progress', cls: 's-doing', icon: '<circle class="ring" cx="8" cy="8" r="5.75"/><path class="fill" d="M8 4.25a3.75 3.75 0 0 1 0 7.5z"/>'},
  w: {label: 'Waiting', cls: 's-wait', icon: '<circle class="ring" cx="8" cy="8" r="5.75"/><path class="bar" d="M6.6 6.1v3.8M9.4 6.1v3.8"/>'},
  x: {label: 'Done', cls: 's-done', icon: '<circle class="fill" cx="8" cy="8" r="6.5"/><path class="knock" d="M5.3 8.2l1.8 1.8 3.6-3.8"/>'},
  '-': {label: 'Cancelled', cls: 's-cancel', icon: '<circle class="fill" cx="8" cy="8" r="6.5"/><path class="knock" d="M5.9 5.9l4.2 4.2M10.1 5.9l-4.2 4.2"/>'}
};
const STATUS_ORDER = [' ', '/', 'w', 'x', '-'];
function statusInfo(state) { return STATUS[state] || STATUS[' ']; }
function statusLabel(state) { return STATUS[state]?.label || state; }
function statusIcon(state) { return svgIcon(statusInfo(state).icon, `status-icon ${statusInfo(state).cls}`); }
const PRIORITY = {
  '⏫': {label: 'High', cls: 'prio-high', icon: '<path d="M4 8.5l4-4 4 4M4 12.5l4-4 4 4"/>'},
  '🔼': {label: 'Medium', cls: 'prio-medium', icon: '<path d="M4.5 10 8 6.5l3.5 3.5"/>'},
  '🔽': {label: 'Low', cls: 'prio-low', icon: '<path d="M4.5 6.5 8 10l3.5-3.5"/>'}
};
function priorityNode(action) {
  const info = PRIORITY[action.priority];
  const node = element('span', info ? `priority ${info.cls}` : 'priority');
  if (info) {
    node.setAttribute('role', 'img');
    node.setAttribute('aria-label', `${info.label} priority`);
    node.title = `${info.label} priority`;
    node.append(svgIcon(info.icon));
  }
  return node;
}

// ---------- Groups ----------
function groupLabel(slug) {
  const text = slug.replace(/-/g, ' ');
  return text.charAt(0).toLocaleUpperCase(LOCALE) + text.slice(1);
}
// A free label ("Ingestion workshop") becomes a slug the way the server expects it: a-z, 0-9 and single hyphens, 40 characters.
function groupSlug(text) {
  return text.toLowerCase().replace(/œ/g, 'oe').replace(/æ/g, 'ae').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+/, '').slice(0, 40).replace(/-+$/, '');
}
// A stable tone per group: its slug picks one of the 8 palette colours (--grp-0…7), the same everywhere.
function groupTone(slug) {
  let hash = 0;
  for (const char of slug) hash = (Math.imul(hash, 72) + char.charCodeAt(0)) >>> 0;
  return `grp-${((hash ^ (hash >>> 13)) >>> 0) % 8}`;
}
const NO_GROUP = '|';
function groupKey(action) { return `${action.register}|${action.group}`; }
function compareGroups(a, b) {
  return a.project.localeCompare(b.project, LOCALE) || a.label.localeCompare(b.label, LOCALE) || a.key.localeCompare(b.key);
}

// ---------- Filters ----------
function inScope(register, scope = projectScope) {
  return !scope || register === scope || (scope.endsWith('/') && typeof register === 'string' && register.startsWith(scope));
}
function isMine(action) {
  const me = snapshot.owner.toLocaleLowerCase(LOCALE);
  return action.owner.toLocaleLowerCase(LOCALE).includes(me);
}
function filteredBase() {
  const text = ids.searchInput.value.trim().toLocaleLowerCase(LOCALE);
  const mine = ids.ownerFilter.value === 'mine';
  const group = ids.groupFilter.value;
  return snapshot.actions.filter(action =>
    (!text || `${action.id} ${action.title} ${action.owner} ${action.project} ${action.group ? `${groupLabel(action.group)} ${action.group}` : ''}`.toLocaleLowerCase(LOCALE).includes(text)) &&
    inScope(action.register) &&
    (!group || (group === 'none' ? !action.group : Boolean(action.group) && groupKey(action) === group)) &&
    (!mine || isMine(action))
  );
}
function scoped(actions) {
  const scope = ids.scopeFilter.value;
  return actions.filter(action => scope === 'all' || (scope === 'active' ? !closed(action) : closed(action)));
}
const STATE_RANK = {'/': 0, ' ': 1, w: 2, x: 3, '-': 4};
const PRIORITY_RANK = {'⏫': 0, '🔼': 1, '': 2, '🔽': 3};
function sortActions(actions) {
  return [...actions].sort((a, b) =>
    STATE_RANK[a.state] - STATE_RANK[b.state] ||
    PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
    (a.due || '9999').localeCompare(b.due || '9999') ||
    a.id.localeCompare(b.id)
  );
}
function byDue(actions) {
  return [...actions].sort((a, b) =>
    (a.due || '9999').localeCompare(b.due || '9999') || PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || a.id.localeCompare(b.id));
}
// Today: my late, due or scheduled work, my work in progress, what waits on others (state w or someone else's), then the week ahead.
function todaySections(actions) {
  const day = today();
  const week = addDays(day, 7);
  const sections = {late: [], today: [], doing: [], waiting: [], week: []};
  for (const action of actions) {
    if (closed(action)) continue;
    if (action.state === 'w' || !isMine(action)) sections.waiting.push(action);
    else if (action.due && action.due < day) sections.late.push(action);
    else if (action.due === day || (action.scheduled && action.scheduled <= day)) sections.today.push(action);
    else if (action.state === '/') sections.doing.push(action);
    else if ((action.due && action.due <= week) || (action.scheduled && action.scheduled <= week)) sections.week.push(action);
  }
  return {late: byDue(sections.late), today: sortActions(sections.today), doing: byDue(sections.doing), waiting: byDue(sections.waiting), week: byDue(sections.week)};
}

// ---------- Projects (sidebar) ----------
const PARENT_LABELS = {internal: 'Internal', archive: 'Archive'};
// Registers as a tree: a client and its missions, a folder of internal projects, or a project on its own.
function projectTree() {
  const parents = [];
  const byKey = new Map();
  for (const register of snapshot.registers) {
    const parts = register.path.split('/');
    const client = parts[1] === 'clients' && parts.length >= 7;
    const nested = !client && parts.length > 4;
    const key = client ? `projects/clients/${parts[2]}/` : nested ? `projects/${parts[1]}/` : register.path;
    const labels = register.label.split(' / ');
    const label = client ? labels[0] : nested ? PARENT_LABELS[parts[1]] || parts[1] : register.label;
    const child = client ? labels.slice(1).join(' / ') || parts[4] : register.label;
    if (!byKey.has(key)) {
      const node = {key, label, children: []};
      byKey.set(key, node);
      parents.push(node);
    }
    byKey.get(key).children.push({key: register.path, label: child});
  }
  return parents;
}
function scopeLabel(scope) {
  if (!scope) return '';
  const register = snapshot.registers.find(item => item.path === scope);
  if (register) return register.label;
  return projectTree().find(node => node.key === scope)?.label || scope;
}
function validateScope() {
  if (projectScope && !snapshot.registers.some(register => inScope(register.path))) projectScope = '';
}
function projectButton(scope, label, count, className = '') {
  const button = element('button', `project-item${className ? ` ${className}` : ''}`);
  button.type = 'button';
  button.dataset.scope = scope;
  button.setAttribute('aria-current', String(scope === projectScope));
  button.append(element('span', 'nav-label', label), element('span', 'nav-count', count ? String(count) : ''));
  button.title = scope ? `${label}: ${plural(count, 'open action')}` : 'All the actions of the brain';
  button.addEventListener('click', () => setProjectScope(scope));
  return button;
}
function renderProjectNav() {
  const counts = new Map();
  for (const action of snapshot.actions) if (!closed(action)) counts.set(action.register, (counts.get(action.register) || 0) + 1);
  const total = [...counts.values()].reduce((sum, count) => sum + count, 0);
  const all = element('li');
  all.append(projectButton('', 'All projects', total, 'project-all'));
  const items = [all];
  for (const parent of projectTree()) {
    const item = element('li');
    if (parent.children.length === 1 && parent.children[0].key === parent.key) {
      item.append(projectButton(parent.key, parent.label, counts.get(parent.key) || 0));
    } else {
      item.append(projectButton(parent.key, parent.label, parent.children.reduce((sum, child) => sum + (counts.get(child.key) || 0), 0)));
      const list = element('ul');
      for (const child of parent.children) {
        const entry = element('li');
        entry.append(projectButton(child.key, child.label, counts.get(child.key) || 0, 'project-child'));
        list.append(entry);
      }
      item.append(list);
    }
    items.push(item);
  }
  if (items.length === 1 && snapshot.registers.length === 0) items.push(element('li', 'project-empty', 'No register'));
  ids.projectNav.replaceChildren(...items);
}
function setProjectScope(scope) {
  projectScope = scope;
  if (scope) ids.docProject.value = ''; // A project of the sidebar and "Inbox" or "Outside projects" exclude each other.
  populateGroupFilter();
  renderProjectNav();
  saveUIState();
  closeDrawer(false);
  if (isDocsView()) refreshDocLists();
  render();
}

// ---------- Counters ----------
function setSummary() {
  const open = snapshot.actions.filter(action => !closed(action));
  ids.openCount.textContent = open.length ? String(open.length) : '';
  const sections = todaySections(open);
  const urgent = sections.late.length + sections.today.length;
  ids.todayCount.textContent = urgent ? String(urgent) : '';
  ids.todayButton.title = `Today (1): ${plural(sections.late.length, 'overdue action')}, ${plural(sections.today.length, 'due today', 'due today')}`;
  renderProjectNav();
}

// ---------- Rows and cards ----------
function loadDetails(action) {
  const key = `${action.id}:${action.version}`;
  if (!detailCache.has(key)) {
    const pending = request(`/api/actions/${encodeURIComponent(action.id)}/details`);
    detailCache.set(key, pending);
    pending.catch(() => detailCache.delete(key));
  }
  return detailCache.get(key);
}
function findAction(id) { return snapshot.actions.find(action => action.id === id); }
function statusButton(action) {
  const button = element('button', 'status-button');
  button.type = 'button';
  button.tabIndex = -1;
  button.setAttribute('aria-haspopup', 'menu');
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-label', `Status: ${statusLabel(action.state).toLowerCase()}. Change the status of ${action.id}`);
  button.title = `${statusLabel(action.state)}: change the status (s)`;
  button.append(statusIcon(action.state));
  button.addEventListener('click', event => {
    event.stopPropagation();
    selectAction(action.id, {focus: false, scroll: false});
    openStatusMenu(action, button);
  });
  return button;
}
function dueButton(action) {
  const button = element('button', action.due ? 'due-button' : 'due-button is-empty');
  button.type = 'button';
  button.tabIndex = -1;
  button.setAttribute('aria-haspopup', 'dialog');
  button.setAttribute('aria-expanded', 'false');
  if (action.due) {
    button.append(dueNode(action));
    button.setAttribute('aria-label', `${dueTitle(action)}. Change the due date of ${action.id}`);
    button.title = `${dueTitle(action)} (d to change)`;
  } else {
    button.append(svgIcon(ICONS.calendar));
    button.setAttribute('aria-label', `Add a due date to ${action.id}`);
    button.title = 'Add a due date (d)';
  }
  button.addEventListener('click', event => {
    event.stopPropagation();
    selectAction(action.id, {focus: false, scroll: false});
    openDueMenu(action, button);
  });
  return button;
}
function deleteButton(action) {
  const button = iconButton('row-action row-delete', `Delete ${action.id}`, ICONS.trash, `Delete ${action.id} (can be undone)`);
  button.tabIndex = -1;
  button.addEventListener('click', event => { event.stopPropagation(); deleteFromRow(action, button); });
  return button;
}
function rowActions(action) {
  const wrap = element('span', 'row-actions');
  const open = iconButton('row-action', `Open the details of ${action.id}`, ICONS.open, 'Open the details (Enter)');
  open.tabIndex = -1;
  open.addEventListener('click', event => { event.stopPropagation(); selectAction(action.id, {focus: false}); openEditor(action); });
  wrap.append(open, deleteButton(action));
  return wrap;
}
function actionClasses(base, action) {
  return `${base}${closed(action) ? ' is-closed' : ''}${action.state === '-' ? ' is-cancelled' : ''}`;
}
function actionRow(action, {project = false} = {}) {
  const row = element('div', actionClasses(project ? 'row with-project' : 'row', action));
  row.dataset.id = action.id;
  row.setAttribute('role', 'listitem');
  const title = element('button', 'row-title', action.title);
  title.type = 'button';
  title.tabIndex = -1;
  title.title = action.title;
  const parts = [statusButton(action), element('span', 'row-id', action.id), title];
  if (project) {
    const where = element('span', 'row-project', action.project);
    where.title = action.project;
    parts.push(where);
  }
  const owner = element('span', 'row-owner', action.owner);
  owner.title = `Owner: ${action.owner}`;
  const meta = element('span', 'row-meta');
  meta.append(element('span', '', action.id));
  if (project) meta.append(element('span', '', action.project));
  meta.append(element('span', '', action.owner));
  parts.push(owner, dueButton(action), priorityNode(action), rowActions(action), meta);
  row.append(...parts);
  row.addEventListener('click', event => {
    if (event.target.closest('.status-button, .due-button, .row-action')) return;
    selectAction(action.id, {focus: false, scroll: false});
    openEditor(action);
  });
  return row;
}
function rowList(actions, options) {
  const list = element('div', 'rows');
  list.setAttribute('role', 'list');
  for (const action of actions) list.append(actionRow(action, options));
  return list;
}

// Fold sections (list and board share the keys).
function applyFolds() {
  for (const section of document.querySelectorAll('[data-fold]')) {
    const folded = foldedGroups.has(section.dataset.fold);
    section.querySelector(':scope > .fold-body').hidden = folded;
    section.querySelector(':scope > :first-child > .fold-toggle')?.setAttribute('aria-expanded', String(!folded));
  }
  const keys = listProjectKeys();
  ids.foldAllButton.textContent = keys.length && keys.every(key => foldedGroups.has(key)) ? 'Expand all' : 'Collapse all';
}
function listProjectKeys() { return [...ids.listView.querySelectorAll('[data-fold^="p:"]')].map(section => section.dataset.fold); }
function toggleFold(key) {
  if (foldedGroups.has(key)) foldedGroups.delete(key); else foldedGroups.add(key);
  applyFolds();
  markSelection();
  saveUIState();
}
function setAllFolds() {
  const keys = listProjectKeys();
  if (keys.every(key => foldedGroups.has(key))) {
    for (const section of ids.listView.querySelectorAll('[data-fold]')) foldedGroups.delete(section.dataset.fold);
  } else for (const key of keys) foldedGroups.add(key);
  applyFolds();
  markSelection();
  saveUIState();
}
function foldToggle(key, label) {
  const toggle = element('button', 'fold-toggle');
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', String(!foldedGroups.has(key)));
  toggle.addEventListener('click', () => toggleFold(key));
  toggle.append(svgIcon(ICONS.chevron, 'fold-chevron'));
  if (label) toggle.setAttribute('aria-label', label);
  return toggle;
}
function addButton(label, preset) {
  const button = iconButton('icon-button fold-add', `Add an action to ${label}`, ICONS.plus);
  button.addEventListener('click', event => { event.stopPropagation(); openEditor(null, preset); });
  return button;
}
// Progress over the members of a project or group (cancelled left out, Status filter ignored).
function progressStats(members) {
  const counted = members.filter(action => action.state !== '-');
  const done = counted.filter(action => action.state === 'x').length;
  const late = counted.filter(action => action.state !== 'x' && action.due && action.due < today()).length;
  return {done, total: counted.length, late};
}
function foldMeta(stats) {
  const meta = element('span', 'fold-meta');
  if (stats.late) meta.append(element('span', 'fold-late', plural(stats.late, 'overdue', 'overdue')));
  const fraction = element('span', '', `${stats.done}/${stats.total}`);
  fraction.title = `${stats.done} of ${stats.total} done`;
  const bar = element('span', 'fold-progress');
  bar.style.setProperty('--p', stats.total ? stats.done / stats.total : 0);
  bar.append(element('span'));
  meta.append(fraction, bar);
  return meta;
}
function foldSection(key, headClass, toggle, extra, body) {
  const section = element('section', 'fold-section');
  section.dataset.fold = key;
  const head = element('div', `fold-head ${headClass}`);
  head.append(toggle, ...extra);
  body.classList.add('fold-body');
  body.hidden = foldedGroups.has(key);
  section.append(head, body);
  return section;
}

// ---------- Today ----------
function actionFiltersActive() {
  return Boolean(projectScope || ids.searchInput.value.trim() || ids.ownerFilter.value || ids.groupFilter.value || (view !== 'today' && view !== 'timeline' && ids.scopeFilter.value !== 'active'));
}
// With filters on, the empty view offers to clear them; otherwise to create an action.
function emptyState(title, text, withButton = true) {
  const box = element('div', 'empty-state');
  if (actionFiltersActive()) {
    box.append(element('h2', '', 'No actions match these filters.'), element('p', '', 'Clear the filters to see everything again.'));
    const button = element('button', 'button', 'Clear filters');
    button.type = 'button';
    button.addEventListener('click', () => ids.resetFilters.click());
    box.append(button);
    return box;
  }
  box.append(element('h2', '', title), element('p', '', text));
  if (withButton) {
    const button = element('button', 'button button-primary');
    button.type = 'button';
    button.append(svgIcon(ICONS.plus), element('span', '', 'New action'));
    button.addEventListener('click', () => openEditor());
    box.append(button);
  }
  return box;
}
function renderToday(base) {
  const sections = todaySections(base);
  const definitions = [
    ['late', 'Overdue', sections.late, ''],
    ['today', 'Today', sections.today, ''],
    ['doing', 'In progress', sections.doing, ''],
    ['waiting', 'Waiting on others', sections.waiting, 'waiting, or assigned to someone else'],
    ['week', 'This week', sections.week, `until ${DAY_FORMAT.format(parseDay(addDays(today(), 7)))}`]
  ];
  const total = definitions.reduce((sum, [, , actions]) => sum + actions.length, 0);
  ids.resultCount.textContent = plural(total, 'action');
  if (!total) {
    ids.todayView.replaceChildren(emptyState('Nothing urgent for today.', 'Overdue actions, actions due today, work in progress and what waits on others appear here.'));
    return;
  }
  const nodes = [];
  for (const [key, title, actions, note] of definitions) {
    if (!actions.length) continue;
    const section = element('section', `section section-${key}`);
    section.setAttribute('aria-labelledby', `today-${key}`);
    const head = element('div', 'section-head');
    const heading = element('h2', '', title);
    heading.id = `today-${key}`;
    head.append(heading, element('span', 'section-count', String(actions.length)));
    if (note) head.append(element('span', 'section-note', note));
    section.append(head, rowList(actions, {project: true}));
    nodes.push(section);
  }
  ids.todayView.replaceChildren(...nodes);
}

// ---------- Actions (list) ----------
function renderList(actions) {
  const qualifier = ids.scopeFilter.value === 'active' ? 'open ' : ids.scopeFilter.value === 'closed' ? 'closed ' : '';
  ids.resultCount.textContent = plural(actions.length, `${qualifier}action`);
  if (!actions.length) {
    ids.listView.replaceChildren(emptyState('No actions here.', 'Try another filter or create an action.'));
    return;
  }
  const base = filteredBase();
  const order = new Map(snapshot.registers.map((register, index) => [register.path, index]));
  const byRegister = new Map();
  for (const action of actions) {
    if (!byRegister.has(action.register)) byRegister.set(action.register, []);
    byRegister.get(action.register).push(action);
  }
  const nodes = [];
  for (const [register, shown] of [...byRegister.entries()].sort((a, b) => (order.get(a[0]) ?? 0) - (order.get(b[0]) ?? 0))) {
    const label = shown[0].project;
    const members = base.filter(action => action.register === register);
    const body = element('div');
    const groups = new Map();
    for (const action of shown) {
      if (!action.group) continue;
      if (!groups.has(action.group)) groups.set(action.group, []);
      groups.get(action.group).push(action);
    }
    const loose = shown.filter(action => !action.group);
    const sorted = [...groups.entries()].sort((a, b) => groupLabel(a[0]).localeCompare(groupLabel(b[0]), LOCALE) || a[0].localeCompare(b[0]));
    for (const [slug, groupActions] of sorted) {
      const key = `${register}|${slug}`;
      const name = groupLabel(slug);
      const stats = progressStats(members.filter(action => action.group === slug));
      const toggle = foldToggle(key, `Group ${name}, ${stats.done} of ${stats.total} done`);
      toggle.append(element('span', `group-dot ${groupTone(slug)}`), element('span', 'fold-label', name), foldMeta(stats));
      const rows = rowList(sortActions(groupActions), {});
      rows.classList.add('in-group');
      body.append(foldSection(key, 'group-head', toggle, [addButton(`${name} (${label})`, {register, group: slug})], rows));
    }
    if (loose.length && sorted.length) {
      const key = `${register}|`;
      const toggle = foldToggle(key, 'No group');
      toggle.append(element('span', 'group-dot'), element('span', 'fold-label', 'No group'), foldMeta(progressStats(members.filter(action => !action.group))));
      const rows = rowList(sortActions(loose), {});
      rows.classList.add('in-group');
      body.append(foldSection(key, 'group-head', toggle, [addButton(`${label}, no group`, {register})], rows));
    } else if (loose.length) body.append(rowList(sortActions(loose), {}));
    const stats = progressStats(members);
    const toggle = foldToggle(`p:${register}`, `${label}, ${stats.done} of ${stats.total} done`);
    toggle.append(element('span', 'fold-label', label), foldMeta(stats));
    nodes.push(foldSection(`p:${register}`, 'project-head', toggle, [addButton(label, {register})], body));
  }
  ids.listView.replaceChildren(...nodes);
  applyFolds();
}

// ---------- Board ----------
function makeCard(action, grouped = false) {
  const card = element('article', actionClasses(`card ${statusInfo(action.state).cls}`, action));
  card.dataset.id = action.id;
  card.draggable = true;
  const top = element('div', 'card-top');
  const title = element('button', 'card-title', action.title);
  title.type = 'button';
  title.tabIndex = -1;
  title.title = `${action.title}\nOwner: ${action.owner}`;
  top.append(statusButton(action), title);
  const meta = element('div', 'card-meta');
  meta.append(element('span', 'row-id', action.id));
  if (!grouped) {
    const where = element('span', 'card-project', shortProject(action.project));
    where.title = action.project;
    meta.append(where);
  }
  if (grouped) {
    const owner = element('span', 'card-project', action.owner);
    owner.title = `Owner: ${action.owner}`;
    meta.append(owner);
  }
  if (action.due) meta.append(dueNode(action));
  if (PRIORITY[action.priority]) meta.append(priorityNode(action));
  const actions = element('div', 'card-actions');
  actions.append(deleteButton(action));
  card.append(top, meta, actions);
  card.addEventListener('click', event => {
    if (event.target.closest('.status-button, .row-action')) return;
    selectAction(action.id, {focus: false, scroll: false});
    openEditor(action);
  });
  // Buttons inside the card must not start a drag (the title still may); capture phase, as the status button stops its own events.
  card.addEventListener('pointerdown', event => { card.draggable = !event.target.closest('button:not(.card-title)'); }, true);
  for (const type of ['pointerup', 'pointercancel', 'dragend']) card.addEventListener(type, () => { card.draggable = true; });
  card.addEventListener('dragstart', event => {
    if (event.target.closest?.('button:not(.card-title)')) { event.preventDefault(); return; }
    closePopover(false);
    event.dataTransfer.setData('text/plain', action.id);
    event.dataTransfer.effectAllowed = 'move';
  });
  return card;
}
// A column's cards under one header per (project, group), "No group" last; the header folds them (keys shared with the list).
function boardGroup(key, cards, group = null, state = ' ') {
  const toggle = foldToggle(key, group ? `${group.label}, ${group.project}, ${plural(cards.length, 'card')}` : `No group, ${plural(cards.length, 'card')}`);
  if (group) {
    const where = element('span', 'board-group-project', shortProject(group.project));
    where.title = group.project;
    toggle.append(element('span', `group-dot ${groupTone(group.slug)}`), element('span', 'fold-label', group.label), where);
  }
  else toggle.append(element('span', 'group-dot'), element('span', 'fold-label', 'No group'));
  toggle.append(element('span', 'board-group-count', String(cards.length)));
  const body = element('div', 'board-group-cards');
  cards.forEach(action => body.append(makeCard(action, Boolean(group))));
  const section = foldSection(key, 'board-group-head', toggle, group ? [addButton(`${group.label} (${group.project})`, {register: group.register, group: group.slug, state})] : [], body);
  section.className = 'board-group fold-section';
  section.firstChild.className = 'board-group-head';
  return section;
}
function renderBoard(base) {
  const scope = ids.scopeFilter.value;
  const columns = [
    {state: ' ', title: 'To do'},
    {state: '/', title: 'In progress'},
    {state: 'w', title: 'Waiting'},
    {state: 'x', title: 'Recently done'}
  ];
  let shownTotal = 0;
  const panels = [];
  for (const column of columns) {
    const panel = element('section', 'board-column');
    const all = base.filter(action => column.state === 'x' ? closed(action) : action.state === column.state);
    let actions;
    if (column.state === 'x') actions = [...all].sort((a, b) => (b.done || '').localeCompare(a.done || '') || b.id.localeCompare(a.id)).slice(0, 10);
    else if (scope === 'closed') actions = [];
    else actions = sortActions(all);
    shownTotal += actions.length;
    const heading = element('h2', 'board-heading');
    heading.id = `column-${column.state === ' ' ? 'todo' : column.state === '/' ? 'doing' : column.state}`;
    heading.append(statusIcon(column.state), element('span', '', column.title), element('span', 'board-count', String(actions.length)));
    panel.setAttribute('aria-labelledby', heading.id);
    const cards = element('div', 'board-cards');
    if (!actions.length) cards.append(element('p', 'board-empty', 'No actions'));
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
    panel.append(heading, cards);
    panel.addEventListener('dragover', event => { event.preventDefault(); panel.classList.add('drag-over'); });
    panel.addEventListener('dragleave', event => { if (!panel.contains(event.relatedTarget)) panel.classList.remove('drag-over'); });
    panel.addEventListener('drop', async event => {
      event.preventDefault();
      panel.classList.remove('drag-over');
      const action = findAction(event.dataTransfer.getData('text/plain'));
      if (action && action.state !== column.state) await updateStatus(action, column.state);
    });
    panels.push(panel);
  }
  ids.resultCount.textContent = plural(shownTotal, 'action');
  ids.boardView.replaceChildren(...panels);
  applyFolds();
}

// ---------- Timeline ----------
// The logic is in timeline-view.js (range, scale, placement, lanes, summary, tray, keyboard neighbours); this draws it. Wide: a frieze fitted
// to the width, one lane per project, a sticky overdue zone, a tray of the actions with no deadline under it. Narrow (under 700 px): an
// agenda, one row per day. Dates are formatted like everywhere else in the app (the browser's locale).
const TL = {chipH: 56, gap: 6, pad: 6, minLane: 46, agenda: 700, slim: 44};
const SHORT_FORMAT = new Intl.DateTimeFormat(LOCALE, {day: 'numeric', month: 'short'});
const WHEN_FORMAT = new Intl.DateTimeFormat(LOCALE, {weekday: 'short', day: 'numeric'});
const WEEKDAY_FORMAT = new Intl.DateTimeFormat(LOCALE, {weekday: 'short'});
const WEEKDAY_NARROW = new Intl.DateTimeFormat(LOCALE, {weekday: 'narrow'});
const MONTH_FORMAT = new Intl.DateTimeFormat(LOCALE, {month: 'long'});
const MONTH_YEAR_FORMAT = new Intl.DateTimeFormat(LOCALE, {month: 'long', year: 'numeric'});
const TL_STATS = [
  {key: 'overdue', label: 'Overdue', spot: true},
  {key: 'week', label: 'This week', spot: true},
  {key: 'next', label: 'Next 2 weeks', spot: true},
  {key: 'none', label: 'No deadline'},
  {key: 'vague', label: 'Vague'}
];
function dayText(iso, format = LONG_FORMAT) { return format.format(parseDay(iso)); }
function entryName(entry) {
  const action = entry.action;
  const parts = [`${action.id}: ${action.title}`, `Status: ${statusLabel(action.state)}`];
  if (entry.done && TimelineView.isPlainDate(action.done)) parts.push(`Done on ${dayText(action.done)}`);
  else parts.push(`Due ${dayText(entry.date)}${entry.overdue ? `, ${plural(entry.overdue, 'day')} overdue` : ''}${entry.done ? ' (done)' : ''}`);
  if (entry.scheduled) parts.push(`Scheduled ${dayText(entry.scheduled)}`);
  parts.push(`Project: ${action.project}`, `Owner: ${action.owner}`);
  return `${parts.join('. ')}.`;
}
function entryTitle(entry) {
  const action = entry.action;
  const lines = [`${action.id} ${action.title}`, `${action.project} · ${action.owner}`];
  if (entry.done && TimelineView.isPlainDate(action.done)) lines.push(`Done on ${dayText(action.done)}`);
  else lines.push(`Due on ${dayText(entry.date)}${entry.overdue ? ` (${plural(entry.overdue, 'day')} overdue)` : ''}`);
  if (entry.scheduled) lines.push(`Scheduled for ${dayText(entry.scheduled)}`);
  if (!entry.done) lines.push('Drag onto a day to move it, Alt+← → to move it by a day');
  return lines.join('\n');
}
function openFromTimeline(action) {
  selectAction(action.id, {focus: false, scroll: false});
  openEditor(action);
}
// Initials of the owner, only when it is not the person of this brain (the others are who the eye looks for).
function ownerBadge(action) {
  if (isMine(action)) return null;
  const badge = element('span', 'tl-who', TimelineView.initials(action.owner));
  badge.setAttribute('aria-hidden', 'true');
  return badge;
}
function toneOf(action) { return groupTone(action.register); } // the project's thin accent: a colour of the group palette, by register

// Dragging: a chip or a tray card is picked up by its action ID; a day of the frieze takes it.
function startTimelineDrag(event, action, kind) {
  if (event.target.closest?.('button:not(.tl-chip, .tl-card-main)')) { event.preventDefault(); return; }
  closePopover(false);
  timelineDrag = {id: action.id, kind};
  event.dataTransfer.setData('text/plain', action.id);
  event.dataTransfer.effectAllowed = 'move';
  const source = event.currentTarget;
  setTimeout(() => source.classList.add('is-dragging'), 0); // after the browser has taken the drag image
  ids.timelineView.classList.add(kind === 'chip' ? 'is-dragging-chip' : 'is-dragging-card');
}
function endTimelineDrag() {
  timelineDrag = null;
  ids.timelineView.classList.remove('is-dragging-chip', 'is-dragging-card');
  ids.timelineView.querySelectorAll('.is-dragging, .is-drop').forEach(node => node.classList.remove('is-dragging', 'is-drop'));
  showTimelineDrop(null);
}
// A chip: status, ID, owner initials, a short title on up to two lines. In the days it stands on its due day (its edge is the date).
function timelineChip(entry, {when = false, where = false, spot = ''} = {}) {
  const action = entry.action;
  const dim = spot && !TimelineView.inSpot(action, spot, today());
  const cell = element('div', `tl-cell ${statusInfo(action.state).cls} ${toneOf(action)}${entry.overdue ? ' is-overdue' : ''}${entry.done ? ' is-done' : ''}${entry.flip ? ' is-flip' : ''}${dim ? ' is-dim' : ''}`);
  cell.dataset.id = action.id;
  cell.setAttribute('role', 'listitem');
  const button = element('button', 'tl-chip');
  button.type = 'button';
  button.tabIndex = -1;
  button.setAttribute('aria-label', entryName(entry));
  button.title = entryTitle(entry);
  const top = element('span', 'tl-chip-top');
  top.append(statusIcon(action.state), element('span', 'tl-chip-id', action.id));
  const badge = ownerBadge(action);
  if (badge) top.append(badge);
  // The overdue zone says "overdue" and has little room: its chips carry no flag and no hourglass (the tooltip has the scheduled date).
  if (entry.sched && !entry.marker && !entry.late) top.append(svgIcon(ICONS.hourglass, 'tl-chip-sched'));
  if (entry.overdue && !entry.late) top.append(svgIcon(ICONS.late, 'tl-chip-flag'));
  // The date leads the title when the chip's position does not say it (overdue zone, crowded axis).
  const title = element('span', 'tl-chip-title');
  if (when) title.append(element('span', 'tl-chip-when', `${dayText(entry.date, entry.late ? SHORT_FORMAT : WHEN_FORMAT)} · `));
  title.append(action.title);
  button.append(top, title);
  if (where) button.append(element('span', 'tl-chip-where', shortProject(action.project)));
  cell.append(button);
  cell.addEventListener('click', () => openFromTimeline(action));
  if (!entry.done) {
    cell.draggable = true;
    cell.addEventListener('dragstart', event => startTimelineDrag(event, action, 'chip'));
  }
  return cell;
}
// The scheduled date: a small hollow marker on its day, a dashed line to the chip it belongs to.
function timelineMarker(entry, top) {
  const marker = element('div', `tl-marker ${statusInfo(entry.action.state).cls}`);
  marker.setAttribute('aria-hidden', 'true');
  marker.title = `${entry.id} is scheduled for ${dayText(entry.scheduled)}, due on ${dayText(entry.date)}`;
  marker.append(svgIcon(ICONS.hourglass, 'tl-marker-icon'));
  marker.style.left = `${entry.marker.x - 9}px`;
  marker.style.top = `${top + TL.chipH / 2 - 9}px`;
  marker.addEventListener('click', () => openFromTimeline(entry.action));
  return marker;
}
function absolute(className, left, width) {
  const node = element('div', className);
  node.setAttribute('aria-hidden', 'true');
  node.style.left = `${left}px`;
  node.style.width = `${width}px`;
  return node;
}
function timelineHead(span, sc, late, summary) {
  const dense = sc.density === 'day';
  const head = element('div', 'tl-head');
  head.setAttribute('aria-hidden', 'true');
  head.style.height = `${dense ? 78 : 46}px`;
  const corner = element('div', 'tl-corner');
  const slim = sc.lateW <= TL.slim;
  const lateHead = element('div', `tl-late-head${summary.overdue ? ' has-late' : ''}${slim ? ' is-slim' : ''}`);
  lateHead.title = slim ? `No overdue action before ${dayText(span.start, SHORT_FORMAT)}` : '';
  if (slim) lateHead.append(svgIcon(ICONS.check, 'tl-late-ok'));
  else lateHead.append(element('span', 'tl-late-title', 'Overdue'), element('span', 'tl-late-count', String(late)), element('span', 'tl-late-caption', `before ${dayText(span.start, SHORT_FORMAT)}`));
  const days = element('div', 'tl-days-head');
  days.style.width = `${sc.total}px`;
  const todayDay = span.days.find(day => day.today);
  if (todayDay) days.append(absolute('tl-today-head', sc.xs[todayDay.index], sc.xs[todayDay.index + 1] - sc.xs[todayDay.index]));
  span.months.forEach((month, index) => {
    const cell = absolute('tl-month', sc.xs[month.start], sc.xs[month.start + month.span] - sc.xs[month.start]);
    const date = parseDay(`${month.year}-${String(month.month).padStart(2, '0')}-01`);
    cell.append(element('span', '', (index === 0 || month.month === 1 ? MONTH_YEAR_FORMAT : MONTH_FORMAT).format(date)));
    days.append(cell);
  });
  for (const week of span.weekSpans) {
    const width = sc.xs[week.start + week.span] - sc.xs[week.start];
    const cell = absolute('tl-week', sc.xs[week.start], width);
    const first = span.days[week.start];
    cell.title = `Week ${week.week}, from ${dayText(first.iso)}`;
    cell.append(element('span', 'tl-week-no', `W${week.week}`));
    if (width >= 120) cell.append(element('span', 'tl-week-from', dayText(first.iso, SHORT_FORMAT)));
    days.append(cell);
  }
  for (const day of span.days) {
    const cell = absolute(`tl-day${day.weekend ? ' is-weekend' : ''}${day.today ? ' is-today' : ''}`, sc.xs[day.index], sc.xs[day.index + 1] - sc.xs[day.index]);
    if (dense) {
      if (!day.weekend || sc.endW >= 15) {
        cell.append(element('span', 'tl-dow', WEEKDAY_NARROW.format(parseDay(day.iso))), element('span', 'tl-dom', String(day.day)));
      }
      cell.title = dayText(day.iso);
    }
    if (dense) days.append(cell);
  }
  head.append(corner, lateHead, days);
  return head;
}
function timelineLane(lane, span, sc, spot) {
  const node = element('div', `tl-lane ${groupTone(lane.register)}`);
  node.dataset.register = lane.register;
  node.setAttribute('role', 'group');
  node.setAttribute('aria-label', lane.project);
  const rows = Math.max(lane.tracks, lane.lateTracks);
  node.style.height = `${rows ? Math.max(TL.minLane, TL.pad * 2 + rows * TL.chipH + (rows - 1) * TL.gap) : TL.minLane}px`;
  const trackTop = track => TL.pad + track * (TL.chipH + TL.gap);

  const label = element('div', 'tl-label');
  label.title = lane.project;
  const [client, ...rest] = lane.project.split(' / ');
  const head = element('span', 'tl-label-head');
  head.append(element('span', 'group-dot'), element('span', 'tl-label-client', rest.length ? client : ''));
  if (lane.undated) {
    const count = element('button', 'tl-label-count', `${lane.undated} undated`);
    count.type = 'button';
    count.tabIndex = -1;
    count.title = `Show the ${plural(lane.undated, 'open action')} of ${lane.project} that have no date, in the tray below`;
    count.addEventListener('click', () => showTray(lane.project));
    head.append(count);
  } else head.append(element('span', 'tl-label-done', 'all dated'));
  label.append(head, element('span', 'tl-label-mission', rest.length ? rest.join(' / ') : lane.project));
  // The two buttons of a label are for the pointer: the summary strip, the tray's search and `n` do the same from the keyboard.
  const add = iconButton('icon-button tl-label-add', `Add an action to ${lane.project}`, ICONS.plus);
  add.tabIndex = -1;
  add.addEventListener('click', () => openEditor(null, {register: lane.register}));
  label.append(add);

  const late = element('div', 'tl-late');
  late.setAttribute('role', 'list');
  late.setAttribute('aria-label', `${lane.project}, overdue`);
  const body = element('div', 'tl-days');
  body.setAttribute('role', 'list');
  body.setAttribute('aria-label', `${lane.project}, planned`);
  body.style.width = `${sc.total}px`;
  for (let week = 0; week < span.weeks; week += 1) {
    body.append(absolute('tl-weekline', sc.xs[week * 7], 1), absolute('tl-shade', sc.xs[week * 7 + 5], sc.xs[week * 7 + 7] - sc.xs[week * 7 + 5]));
  }
  const today = span.days.find(day => day.today);
  if (today) body.append(absolute('tl-today', sc.xs[today.index], sc.xs[today.index + 1] - sc.xs[today.index]));
  const showWhen = sc.dayW < 40;
  for (const entry of lane.entries) {
    const top = trackTop(entry.track);
    if (entry.late) {
      const chip = timelineChip(entry, {when: true, spot});
      chip.style.top = `${top}px`;
      late.append(chip);
      continue;
    }
    const chip = timelineChip(entry, {when: showWhen, spot});
    chip.style.left = `${entry.x}px`;
    chip.style.width = `${entry.w}px`;
    chip.style.top = `${top}px`;
    body.append(chip);
    if (entry.marker) {
      const join = absolute('tl-join', entry.marker.x, Math.max(0, entry.x - entry.marker.x));
      join.style.top = `${top + TL.chipH / 2}px`;
      body.append(join, timelineMarker(entry, top));
    }
  }
  node.append(label, late, body);
  return node;
}
function timelineFrieze(span, sc, result, summary, late) {
  const canvas = element('div', 'tl-canvas');
  canvas.style.width = `${sc.labelW + sc.lateW + sc.total}px`;
  canvas.style.setProperty('--label-w', `${sc.labelW}px`);
  canvas.style.setProperty('--late-w', `${sc.lateW}px`);
  canvas.style.setProperty('--head-h', `${sc.density === 'day' ? 78 : 46}px`);
  canvas.append(timelineHead(span, sc, late, summary));
  if (!result.total) {
    const guide = element('p', 'tl-guide');
    const undated = TimelineView.tray(timelineBase).counts;
    guide.textContent = undated.none + undated.vague > 0
      ? 'Nothing is planned in this range. Drag an action from the tray below onto a day to give it a deadline.'
      : 'Nothing is planned in this range. Give an action a due date, or click a day to create one.';
    canvas.append(guide);
  }
  canvas.append(...result.lanes.map(lane => timelineLane(lane, span, sc, timelineSpot)));
  const drop = element('div', 'tl-drop');
  drop.hidden = true;
  drop.setAttribute('aria-hidden', 'true');
  drop.append(element('span', 'tl-drop-label'));
  canvas.append(drop);
  return canvas;
}
function agendaList(label, entries, options) {
  const list = element('div', 'tl-ag-items');
  list.setAttribute('role', 'list');
  list.setAttribute('aria-label', label);
  list.append(...entries.map(entry => timelineChip(entry, options)));
  return list;
}
// One row per day, weekends shaded; the overdue actions first, the weeks under their own headings.
function timelineAgenda(span, result, spot) {
  const root = element('div', 'tl-agenda');
  if (result.late.length) {
    const section = element('section', 'tl-ag-section tl-ag-late');
    section.setAttribute('aria-labelledby', 'tl-ag-late-title');
    const title = element('h3', '', `Overdue (${result.late.length})`);
    title.id = 'tl-ag-late-title';
    section.append(title, agendaList('Overdue actions', result.late, {when: true, where: true, spot}));
    root.append(section);
  }
  const days = TimelineView.agenda(result, span.days);
  for (let first = 0; first < days.length; first += 7) {
    const week = days.slice(first, first + 7);
    const section = element('section', 'tl-ag-section');
    const head = week[0].day;
    const title = element('h3', '', `W${head.week} · ${dayText(week[0].day.iso, SHORT_FORMAT)} to ${dayText(week[6].day.iso, SHORT_FORMAT)}`);
    title.id = `tl-ag-week-${head.weekYear}-${head.week}`;
    section.setAttribute('aria-labelledby', title.id);
    section.append(title);
    for (const {day, entries, markers} of week) {
      const empty = !entries.length && !markers.length;
      const row = element('div', `tl-ag-day${day.weekend ? ' is-weekend' : ''}${day.today ? ' is-today' : ''}${empty ? ' is-empty' : ''}`);
      const date = element('div', 'tl-ag-date');
      date.append(element('span', 'tl-dow', WEEKDAY_FORMAT.format(parseDay(day.iso))), element('span', 'tl-dom', String(day.day)));
      if (day.today) date.append(element('span', 'tl-ag-today', 'Today'));
      row.append(date);
      if (empty) row.setAttribute('aria-hidden', 'true');
      else {
        const list = agendaList(dayText(day.iso), entries, {where: true, spot});
        for (const entry of markers) {
          const marker = element('div', `tl-marker tl-marker-wide ${statusInfo(entry.action.state).cls}`);
          marker.setAttribute('aria-hidden', 'true');
          marker.title = `${entry.id} is scheduled for ${dayText(entry.scheduled)}, due on ${dayText(entry.date)}`;
          marker.append(svgIcon(ICONS.hourglass, 'tl-marker-icon'), element('span', '', entry.id));
          marker.addEventListener('click', () => openFromTimeline(entry.action));
          list.append(marker);
        }
        row.append(list);
      }
      section.append(row);
    }
    root.append(section);
  }
  return root;
}

// The strip under the toolbar: counts of the open actions. Overdue, this week and the next two weeks spotlight those actions (the
// others dim); No deadline and Vague open the tray.
function renderSummary(summary) {
  const windows = {
    overdue: `Due before ${dayText(summary.today, SHORT_FORMAT)}`,
    week: `Due from ${dayText(summary.today, SHORT_FORMAT)} to ${dayText(summary.weekEnd, SHORT_FORMAT)}`,
    next: `Due from ${dayText(summary.nextStart, SHORT_FORMAT)} to ${dayText(summary.nextEnd, SHORT_FORMAT)}`,
    none: 'Open actions with no due date: see the tray',
    vague: 'Open actions whose deadline is a wording, not a date: see the tray'
  };
  ids.timelineSummary.replaceChildren(...TL_STATS.map(stat => {
    const count = summary[stat.key];
    const button = element('button', `tl-stat tl-stat-${stat.key}${count ? '' : ' is-zero'}`);
    button.type = 'button';
    button.dataset.stat = stat.key;
    button.title = windows[stat.key];
    button.append(element('span', 'tl-stat-n', String(count)), element('span', 'tl-stat-label', stat.label));
    if (stat.spot) button.setAttribute('aria-pressed', String(timelineSpot === stat.key));
    else button.setAttribute('aria-controls', 'timelineTray');
    return button;
  }));
}
function setTimelineSpot(kind) {
  timelineSpot = timelineSpot === kind ? '' : kind;
  render();
  if (timelineSpot) ids.timelineScroll.querySelector('.tl-cell:not(.is-dim), .tl-ag-day .tl-cell:not(.is-dim)')?.scrollIntoView({block: 'nearest', inline: 'nearest'});
}

// The tray: open actions with no date, by project, vague deadlines first. Cards are dragged onto a day, or get a date from the menu.
function applyTray() {
  ids.timelineView.classList.toggle('tray-collapsed', !timelineTrayOpen);
  ids.timelineTray.classList.toggle('is-collapsed', !timelineTrayOpen);
  ids.timelineTrayBody.hidden = !timelineTrayOpen;
  ids.timelineTrayToggle.setAttribute('aria-expanded', String(timelineTrayOpen));
}
function setTrayOpen(open) {
  timelineTrayOpen = open;
  applyTray();
  saveUIState();
}
function showTray(query = '') {
  ids.timelineTraySearch.value = query;
  setTrayOpen(true);
  renderTray(timelineBase);
  ids.timelineTray.scrollIntoView({block: 'nearest'});
  ids.timelineTraySearch.focus({preventScroll: true});
}
function trayCard(action, text) {
  const item = element('li', `tl-card ${statusInfo(action.state).cls} ${toneOf(action)}`);
  item.dataset.id = action.id;
  item.draggable = true;
  item.addEventListener('dragstart', event => startTimelineDrag(event, action, 'card'));
  const main = element('button', 'tl-card-main');
  main.type = 'button';
  main.tabIndex = -1;
  main.setAttribute('aria-label', `${action.id}: ${action.title}. Status: ${statusLabel(action.state)}. ${text ? `Deadline: ${text}` : 'No deadline'}. Project: ${action.project}. Owner: ${action.owner}.`);
  main.title = `${action.id} ${action.title}\n${action.project} · ${action.owner}${text ? `\nDeadline: ${text}` : ''}\nDrag onto a day to plan it`;
  const top = element('span', 'tl-chip-top');
  top.append(statusIcon(action.state), element('span', 'tl-chip-id', action.id));
  const badge = ownerBadge(action);
  if (badge) top.append(badge);
  main.append(top, element('span', 'tl-chip-title', action.title));
  if (text) main.append(element('span', 'tl-card-note', text));
  const date = iconButton('icon-button tl-card-date', `Set a due date for ${action.id}`, ICONS.calendar, 'Set a due date (d)');
  date.tabIndex = -1;
  date.addEventListener('click', event => { event.stopPropagation(); selectAction(action.id, {focus: false, scroll: false}); openDueMenu(action, date); });
  item.append(main, date);
  item.addEventListener('click', event => { if (!event.target.closest('.tl-card-date')) openFromTimeline(action); });
  return item;
}
function traySection(id, title, groups, count) {
  const section = element('section', 'tl-tray-section');
  section.id = id;
  section.setAttribute('aria-labelledby', `${id}-title`);
  const head = element('h3', '');
  head.id = `${id}-title`;
  head.append(element('span', '', title), element('span', 'section-count', String(count)));
  section.append(head);
  const columns = element('div', 'tl-tray-groups');
  for (const group of groups) {
    const box = element('div', `tl-group ${groupTone(group.register)}`);
    const name = element('h4', 'tl-group-name');
    name.append(element('span', 'group-dot'), element('span', 'tl-group-text', group.project), element('span', 'tl-group-count', String(group.items.length)));
    name.title = group.project;
    const list = element('ul', 'tl-cards');
    list.append(...group.items.map(item => trayCard(item.action, item.text)));
    box.append(name, list);
    columns.append(box);
  }
  section.append(columns);
  return section;
}
function renderTray(base) {
  const data = TimelineView.tray(base, {query: ids.timelineTraySearch.value, order: snapshot.registers.map(register => register.path)});
  const all = TimelineView.tray(base, {order: []}).counts;
  ids.timelineTrayCount.textContent = String(all.none);
  ids.timelineTrayMore.textContent = all.vague ? `+ ${all.vague} vague` : '';
  const nodes = [];
  if (data.counts.vague) nodes.push(traySection('tl-tray-vague', 'Vague deadlines', data.vague, data.counts.vague));
  if (data.counts.none) nodes.push(traySection('tl-tray-none', 'No deadline', data.none, data.counts.none));
  if (!nodes.length) {
    nodes.push(element('p', 'tl-tray-empty', all.none + all.vague ? 'No action matches this search.' : 'Every open action has a deadline.'));
  }
  ids.timelineTrayList.replaceChildren(...nodes);
  ids.timelineTray.hidden = false;
  ids.timelineTrayHint.hidden = !(all.none + all.vague);
}

// The time axis follows the width of the page: the frieze is measured, drawn, and drawn again once if a scrollbar took some room.
function timelineMetrics(width) { return width < 900 ? {labelW: 124, lateW: 120, chipW: 118} : {labelW: 150, lateW: 148, chipW: 132}; }
function syncTimelineControls(summary, span, sc) {
  for (const button of ids.timelineView.querySelectorAll('[data-range]')) button.setAttribute('aria-pressed', String(button.dataset.range === timelineRange));
  ids.timelineDone.setAttribute('aria-checked', String(timelineDone));
  ids.timelineLate.hidden = !summary.overdue;
  ids.timelineLate.textContent = `${summary.overdue} overdue`;
  ids.timelineScale.textContent = `${dayText(span.start, SHORT_FORMAT)} – ${dayText(span.end, DAY_YEAR_FORMAT)} · ${plural(span.weeks, 'week')}${sc && sc.density === 'week' ? ', one tick per week' : ''}`;
  const scrolls = Boolean(sc && sc.overflow);
  ids.timelineBack.hidden = ids.timelineForward.hidden = !scrolls;
  ids.timelineView.classList.toggle('is-agenda', timelineNarrow);
}
function renderTimeline(base) {
  timelineBase = base;
  const now = today();
  const span = TimelineView.range(now, timelineRange);
  timelineNarrow = ids.mainContent.getBoundingClientRect().width < TL.agenda;
  const summary = TimelineView.summary(base, now);
  const late = base.filter(action => !closed(action) && TimelineView.isPlainDate(action.due) && action.due < span.start).length;
  const focused = document.activeElement?.closest?.('#timelineView [data-id]')?.dataset.id || null;
  if (timelineTrayOpen === null) timelineTrayOpen = !timelineNarrow;
  const order = snapshot.registers.map(register => register.path);
  const options = {today: now, start: span.start, end: span.end, showDone: timelineDone, order};
  let sc = null;
  let result;
  const draw = () => {
    const width = Math.floor(ids.timelineScroll.clientWidth || ids.mainContent.getBoundingClientRect().width);
    const metrics = timelineMetrics(width);
    sc = timelineNarrow ? null : TimelineView.scale({width, weeks: span.weeks, key: span.key, labelW: metrics.labelW, lateW: late ? metrics.lateW : TL.slim});
    result = TimelineView.layout(base, {...options, scale: sc, chipW: sc && span.key === 'quarter' ? metrics.chipW - 14 : metrics.chipW, gap: TL.gap});
    timelineModel = {span, sc, result, summary};
    ids.timelineScroll.replaceChildren(timelineNarrow ? timelineAgenda(span, result, timelineSpot) : timelineFrieze(span, sc, result, summary, late));
    ids.timelineScroll.style.scrollPaddingLeft = sc ? `${sc.labelW + sc.lateW}px` : '0';
    ids.timelineScroll.style.scrollPaddingTop = sc ? (sc.density === 'day' ? '80px' : '48px') : '0';
    return width;
  };
  applyTray();
  ids.timelineView.classList.toggle('is-agenda', timelineNarrow);
  if (!base.some(action => !closed(action)) && !(timelineDone && base.length)) {
    timelineModel = null;
    ids.resultCount.textContent = plural(0, 'action');
    renderSummary(summary);
    syncTimelineControls(summary, span, null);
    ids.timelineTray.hidden = true;
    ids.timelineScroll.replaceChildren(emptyState('No open actions.', 'Open actions appear here as lanes, with a deadline on a day or in the tray.'));
    return;
  }
  const width = draw();
  if (!timelineNarrow && Math.abs(Math.floor(ids.timelineScroll.clientWidth) - width) > 1) draw(); // a scrollbar appeared: fit the new width
  timelineWidth = Math.floor(ids.timelineScroll.clientWidth);
  ids.resultCount.textContent = plural(result.total, 'action');
  syncTimelineControls(summary, span, sc);
  renderSummary(summary);
  renderTray(base);
  if (timelineAnchor) {
    timelineAnchor = false;
    scrollTimelineToToday();
  }
  if (focused) rowFor(focused)?.querySelector(ROW_MAIN)?.focus({preventScroll: true});
}
// Bring today into view: only the scroll case (a range that does not fit), or the agenda, has anything to move.
function scrollTimelineToToday(animate = false) {
  const scroll = ids.timelineScroll;
  const cell = scroll.querySelector(timelineNarrow ? '.tl-ag-day.is-today' : '.tl-today-head');
  if (!cell) return;
  cell.classList.add('is-ping');
  setTimeout(() => cell.classList.remove('is-ping'), 1200);
  const box = scroll.getBoundingClientRect();
  const at = cell.getBoundingClientRect();
  if (timelineNarrow) {
    const top = Math.max(0, at.top - box.top + scroll.scrollTop - 44); // under the sticky week heading
    if (animate) scroll.scrollTo(timelineScrollOptions(0, top)); else scroll.scrollTop = top;
    return;
  }
  if (!timelineModel.sc.overflow) return;
  const left = Math.max(0, at.left - box.left + scroll.scrollLeft - timelineModel.sc.labelW - timelineModel.sc.lateW - at.width * 1.5);
  if (animate) scroll.scrollTo(timelineScrollOptions(left, scroll.scrollTop)); else scroll.scrollLeft = left;
}
function timelineScrollOptions(left, top) {
  return {left, top, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'};
}
function scrollTimelineByWeeks(direction) {
  if (timelineModel?.sc) ids.timelineScroll.scrollBy(timelineScrollOptions(direction * timelineModel.sc.xs[7], 0));
}
// The overdue pill: the first overdue chip, focused.
function focusFirstOverdue() {
  const first = timelineModel?.result.late[0] || timelineModel?.result.lanes.flatMap(lane => lane.entries).find(entry => entry.overdue);
  const chip = first && rowFor(first.id)?.querySelector('.tl-chip');
  if (!chip) return;
  chip.focus({preventScroll: true});
  chip.scrollIntoView({block: 'nearest', inline: 'nearest'});
  selectAction(first.id, {focus: false, scroll: false});
}

// Keyboard: left and right walk a project by date (then by ID), up and down change project on the closest date, Home and End go to the
// ends of the project; Alt+← → moves the deadline by a day (with Shift, a week). In the agenda the arrows follow the list.
const TIMELINE_KEYS = {ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down', Home: 'home', End: 'end'};
function timelineKey(event) {
  const cell = event.target instanceof Element ? event.target.closest('.tl-chip')?.closest('[data-id]') : null;
  if (!cell || event.ctrlKey || event.metaKey || !timelineModel) return;
  if (event.altKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
    event.preventDefault();
    if (pendingWrites > 0) return; // one move at a time: the next one starts from the register as it is after this one
    const action = findAction(cell.dataset.id);
    const next = action && !closed(action) ? TimelineView.moveDue(action.due, (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 7 : 1)) : null;
    if (next) updateDue(action, next);
    return;
  }
  const direction = TIMELINE_KEYS[event.key];
  if (!direction || event.altKey || event.shiftKey) return;
  event.preventDefault();
  if (timelineNarrow) {
    if (direction === 'home' || direction === 'end') return;
    moveSelection(direction === 'left' || direction === 'up' ? -1 : 1);
    return;
  }
  const next = TimelineView.neighbour(timelineModel.result.lanes, cell.dataset.id, direction);
  if (next) selectAndFollow(next);
}
// The tray: up and down walk the cards, Home and End jump to the first and last.
function trayKey(event) {
  if (!event.target.closest?.('.tl-card-main') || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const cards = [...ids.timelineTrayList.querySelectorAll('.tl-card')].filter(card => card.offsetParent !== null);
  const index = cards.indexOf(event.target.closest('.tl-card'));
  const next = event.key === 'ArrowDown' ? cards[index + 1] : event.key === 'ArrowUp' ? cards[index - 1] : event.key === 'Home' ? cards[0] : event.key === 'End' ? cards.at(-1) : undefined;
  if (next === undefined) return;
  event.preventDefault();
  if (next) selectAndFollow(next.dataset.id);
}

// Dropping: the day under the pointer, from the geometry of the axis.
function timelineDayAt(event) {
  const canvas = ids.timelineScroll.querySelector('.tl-canvas');
  const sc = timelineModel?.sc;
  if (!canvas || !sc) return null;
  const index = TimelineView.dayAt(sc, event.clientX - canvas.getBoundingClientRect().left - sc.labelW - sc.lateW);
  return index < 0 ? null : {index, day: timelineModel.span.days[index], canvas};
}
function showTimelineDrop(target) {
  const drop = ids.timelineScroll.querySelector('.tl-drop');
  if (!drop) return;
  drop.hidden = !target;
  if (!target) return;
  const sc = timelineModel.sc;
  drop.style.left = `${sc.labelW + sc.lateW + sc.xs[target.index]}px`;
  drop.style.width = `${sc.xs[target.index + 1] - sc.xs[target.index]}px`;
  drop.firstChild.textContent = dayText(target.day.iso, DAY_FORMAT);
}

// ---------- Selection and keyboard navigation over rows and cards ----------
function activeRoot() {
  return view === 'today' ? ids.todayView : view === 'list' ? ids.listView : view === 'board' ? ids.boardView : view === 'timeline' ? ids.timelineView : null;
}
function visibleRows() {
  const root = activeRoot();
  return root ? [...root.querySelectorAll('[data-id]')].filter(row => row.offsetParent !== null) : [];
}
const ROW_MAIN = '.row-title, .card-title, .tl-chip, .tl-card-main';
const ROW_CONTROLS = `.status-button, ${ROW_MAIN}, .due-button, .row-action, .tl-card-date`;
function setStops(row, on) { for (const control of row.querySelectorAll(ROW_CONTROLS)) control.tabIndex = on ? 0 : -1; }
// The selected row (else the first one) is the list's single tab stop: its controls are reachable with Tab, the others with j/k.
function markSelection() {
  const root = activeRoot();
  if (!root) return;
  const rows = [...root.querySelectorAll('[data-id]')];
  let current = null;
  for (const row of rows) {
    const selected = row.dataset.id === selectedId;
    row.classList.toggle('is-selected', selected);
    setStops(row, false);
    if (selected && row.offsetParent !== null) current = row;
  }
  const stop = current || rows.find(row => row.offsetParent !== null);
  if (stop) setStops(stop, true);
  if (view === 'timeline') markTimelineStops();
}
// The frieze and the tray are two places to Tab to: each keeps one stop, on its selected row (else its first).
function markTimelineStops() {
  for (const zone of [ids.timelineScroll, ids.timelineTray]) {
    const rows = [...zone.querySelectorAll('[data-id]')].filter(row => row.offsetParent !== null);
    const row = rows.find(item => item.dataset.id === selectedId) || rows[0];
    if (row) setStops(row, true);
  }
}
function rowFor(id) {
  const root = activeRoot();
  return root ? root.querySelector(`[data-id="${CSS.escape(id)}"]`) : null;
}
function selectAction(id, {focus = true, scroll = true} = {}) {
  selectedId = id;
  markSelection();
  const row = rowFor(id);
  if (!row) return;
  if (scroll) row.scrollIntoView({block: 'nearest'});
  if (focus) row.querySelector(ROW_MAIN)?.focus({preventScroll: true});
}
function moveSelection(delta) {
  const rows = visibleRows();
  if (!rows.length) return;
  const index = rows.findIndex(row => row.dataset.id === selectedId);
  const next = rows[index === -1 ? (delta > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, index + delta))];
  selectAndFollow(next.dataset.id);
}
// Select an action, and let an open (unmodified) detail panel follow it.
function selectAndFollow(id) {
  selectAction(id);
  if (editorOpen() && editorAction && editorAction.id !== id && !editorDirty()) {
    const action = findAction(id);
    if (action) openEditor(action, null, {focus: 'none'});
  }
}
function selectedAction() {
  const row = selectedId && rowFor(selectedId);
  return row && row.offsetParent !== null ? findAction(selectedId) : null;
}
// After a write and a refresh: the same action again, else the row now at its former place.
function focusAction(id, part = 'title', formerIndex = -1) {
  let row = rowFor(id);
  if (!row || row.offsetParent === null) {
    const rows = visibleRows();
    row = formerIndex >= 0 && rows.length ? rows[Math.min(formerIndex, rows.length - 1)] : null;
  }
  if (!row) { ids.resultCount.focus({preventScroll: true}); return; }
  selectedId = row.dataset.id;
  markSelection();
  const target = part === 'status' ? row.querySelector('.status-button') : part === 'due' ? row.querySelector('.due-button') : null;
  (target || row.querySelector(ROW_MAIN)).focus({preventScroll: true});
}

// ---------- Popovers: status menu and due date ----------
let popoverState = null;
function popoverItems() { return [...ids.popover.querySelectorAll('.menu-item, input')]; }
function openPopover(anchor, nodes, {role = 'menu', label = ''} = {}) {
  closePopover(false);
  closeMoreMenu(false);
  ids.popover.replaceChildren(...nodes);
  ids.popover.setAttribute('role', role);
  ids.popover.setAttribute('aria-label', label);
  ids.popover.hidden = false;
  anchor.setAttribute('aria-expanded', 'true');
  popoverState = {anchor};
  const rect = anchor.getBoundingClientRect();
  const box = ids.popover.getBoundingClientRect();
  let left = Math.min(rect.left, window.innerWidth - box.width - 12);
  left = Math.max(12, left);
  let top = rect.bottom + 4;
  if (top + box.height > window.innerHeight - 12) top = Math.max(12, rect.top - box.height - 4);
  ids.popover.style.left = `${left}px`;
  ids.popover.style.top = `${top}px`;
  (ids.popover.querySelector('[aria-checked="true"]') || popoverItems()[0])?.focus();
}
function closePopover(refocus = true) {
  if (!popoverState) return;
  const {anchor} = popoverState;
  popoverState = null;
  ids.popover.hidden = true;
  ids.popover.replaceChildren();
  anchor.setAttribute('aria-expanded', 'false');
  if (refocus && anchor.isConnected) anchor.focus({preventScroll: true});
}
function menuItem(content, onPick, {role = 'menuitem', checked = null, hint = ''} = {}) {
  const item = element('button', 'menu-item');
  item.type = 'button';
  item.setAttribute('role', role);
  if (checked !== null) item.setAttribute('aria-checked', String(checked));
  item.append(...content);
  if (hint) item.append(element('span', 'menu-item-hint', hint));
  item.addEventListener('click', () => { closePopover(false); onPick(); });
  return item;
}
function openStatusMenu(action, anchor) {
  const items = STATUS_ORDER.map((state, index) => menuItem(
    [statusIcon(state), element('span', 'menu-item-text', statusLabel(state))],
    () => updateStatus(action, state, anchor),
    {role: 'menuitemradio', checked: state === action.state, hint: String(index + 1)}
  ));
  openPopover(anchor, items, {label: `Status of ${action.id}`});
}
function nextMonday(day) {
  const date = parseDay(day);
  date.setDate(date.getDate() + ((8 - date.getDay()) % 7 || 7));
  return isoDay(date);
}
function openDueMenu(action, anchor) {
  const day = today();
  const choices = [['Today', day], ['Tomorrow', addDays(day, 1)]];
  if (nextMonday(day) !== addDays(day, 1)) choices.push(['Next Monday', nextMonday(day)]);
  choices.push(['In a week', addDays(day, 7)]);
  const nodes = [element('p', 'menu-heading', `Due date of ${action.id}`)];
  for (const [label, value] of choices) {
    nodes.push(menuItem([element('span', 'menu-item-text', label)], () => updateDue(action, value, anchor), {hint: DAY_FORMAT.format(parseDay(value))}));
  }
  const pick = element('label', 'menu-date');
  const input = element('input');
  input.type = 'date';
  input.value = action.due || '';
  input.setAttribute('aria-label', 'Other date');
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && input.value) { event.preventDefault(); closePopover(false); updateDue(action, input.value, anchor); }
  });
  input.addEventListener('change', () => {
    // A picked date applies at once; typing digits waits for Enter (each keystroke fires change in some browsers).
    if (input.value && input.dataset.typed !== '1') { closePopover(false); updateDue(action, input.value, anchor); }
  });
  input.addEventListener('keydown', event => { if (/^\d$/.test(event.key)) input.dataset.typed = '1'; });
  pick.append(input);
  nodes.push(element('div', 'menu-separator'), pick);
  if (action.due) nodes.push(menuItem([element('span', 'menu-item-text', 'Remove the due date')], () => updateDue(action, '', anchor)));
  openPopover(anchor, nodes, {role: 'dialog', label: `Due date of ${action.id}`});
}
ids.popover.addEventListener('keydown', event => {
  const items = popoverItems();
  const index = items.indexOf(document.activeElement);
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    if (document.activeElement?.tagName === 'INPUT' && event.target.type === 'date') return;
    event.preventDefault();
    items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
  } else if (event.key === 'Home' || event.key === 'End') {
    if (document.activeElement?.tagName === 'INPUT') return;
    event.preventDefault();
    items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
  } else if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    closePopover();
  } else if (event.key === 'Tab') {
    // Focus stays in the popover: Tab and Shift+Tab cycle through its items.
    event.preventDefault();
    items[(index + (event.shiftKey ? -1 : 1) + items.length) % items.length]?.focus();
  } else if (/^[1-5]$/.test(event.key) && ids.popover.getAttribute('role') === 'menu') {
    event.preventDefault();
    ids.popover.querySelectorAll('.menu-item')[Number(event.key) - 1]?.click();
  }
});
document.addEventListener('pointerdown', event => {
  if (popoverState && !ids.popover.contains(event.target) && !popoverState.anchor.contains(event.target)) closePopover(false);
  if (!ids.moreMenu.hidden && !ids.moreMenu.parentElement.contains(event.target)) closeMoreMenu(false);
  if (brainMenuOpen() && !ids.brainSwitch.contains(event.target)) closeBrainMenu(false);
});
window.addEventListener('resize', () => closePopover(false));
for (const root of [ids.todayView, ids.listView, ids.boardView, ids.timelineScroll]) root.addEventListener('scroll', () => closePopover(false), {passive: true, capture: true});

// ---------- Render ----------
function isDocsView() { return view === 'notes' || view === 'search'; }
function renderFilterChips() {
  const actionView = ACTION_VIEWS.includes(view);
  const docs = isDocsView();
  ids.filters.classList.toggle('is-empty', !actionView && !docs);
  ids.projectChip.hidden = !projectScope || !(actionView || docs);
  ids.projectChipValue.textContent = scopeLabel(projectScope);
  ids.ownerChip.hidden = !actionView;
  ids.scopeChip.hidden = !(view === 'list' || view === 'board');
  ids.groupChip.hidden = !actionView;
  ids.docProjectChip.hidden = !docs;
  ids.ownerChip.classList.toggle('is-active', ids.ownerFilter.value !== '');
  ids.scopeChip.classList.toggle('is-active', ids.scopeFilter.value !== 'active');
  ids.groupChip.classList.toggle('is-active', ids.groupFilter.value !== '');
  ids.docProjectChip.classList.toggle('is-active', ids.docProject.value !== '');
  for (const select of [ids.ownerFilter, ids.scopeFilter, ids.groupFilter, ids.docProject]) {
    select.parentElement.querySelector('.chip-value').textContent = select.selectedOptions[0]?.textContent || '';
  }
  const active = actionView ? actionFiltersActive() : docs ? Boolean(projectScope || ids.docProject.value) : false;
  ids.resetFilters.hidden = !active;
  ids.foldAllButton.hidden = view !== 'list' || !listProjectKeys().length;
}
function render() {
  closePopover(false);
  if (view === 'tools') filterTools();
  else if (view === 'git') renderGit();
  else if (isDocsView()) renderDocsView();
  else {
    const base = filteredBase();
    if (view === 'today') renderToday(base);
    else if (view === 'list') renderList(scoped(base));
    else if (view === 'timeline') renderTimeline(base);
    else renderBoard(base);
    markSelection();
  }
  renderFilterChips();
}
function setView(next, persist = true) {
  if (!VIEWS.includes(next)) next = 'today';
  view = next;
  closePopover(false);
  ids.todayView.hidden = next !== 'today';
  ids.listView.hidden = next !== 'list';
  ids.boardView.hidden = next !== 'board';
  ids.timelineView.hidden = next !== 'timeline';
  if (next === 'timeline') timelineAnchor = true;
  ids.docsView.hidden = !isDocsView();
  ids.toolsView.hidden = next !== 'tools';
  ids.gitView.hidden = next !== 'git';
  ids.syncInfo.hidden = next !== 'git';
  for (const [name, id] of Object.entries(NAV_BUTTONS)) {
    if (name === next) ids[id].setAttribute('aria-current', 'page'); else ids[id].removeAttribute('aria-current');
  }
  ids.viewTitle.textContent = VIEW_TITLES[next];
  ids.searchInput.hidden = !ACTION_VIEWS.includes(next);
  ids.docQuery.hidden = next !== 'search';
  ids.toolSearch.hidden = next !== 'tools';
  ids.mainContent.classList.toggle('view-searchless', next === 'notes' || next === 'git');
  ids.gitStatus.hidden = next !== 'git';
  ids.resultCount.textContent = '';
  render();
  if (next === 'tools' && !tools.length) loadTools();
  if (next === 'git') loadGit();
  if (isDocsView()) {
    refreshDocsView();
    if (persist && next === 'search') ids.docQuery.focus();
  }
  if (persist) {
    saveUIState();
    closeDrawer(false);
  }
}
function populateProjects() {
  const editing = ids.editorProject.value;
  ids.editorProject.replaceChildren(...snapshot.registers.map(register => new Option(register.label, register.path)));
  populateGroupFilter();
  ids.editorProject.value = editing || defaultRegister();
  if (!editorOpen()) fillGroupOptions();
}
function defaultRegister() {
  if (snapshot.registers.some(register => register.path === projectScope)) return projectScope;
  return snapshot.registers.find(register => inScope(register.path))?.path || snapshot.registers[0]?.path || '';
}
// Group filter: "All", "No group", then the groups as `register|slug`; one <optgroup> per project unless one register is selected.
function populateGroupFilter() {
  const selected = ids.groupFilter.value || pendingGroup;
  pendingGroup = '';
  const single = snapshot.registers.some(register => register.path === projectScope);
  const entries = [];
  for (const register of snapshot.registers) {
    if (!inScope(register.path)) continue;
    for (const slug of register.groups || []) entries.push({value: `${register.path}|${slug}`, project: register.label, label: groupLabel(slug), key: slug});
  }
  entries.sort(compareGroups);
  const nodes = [];
  for (const entry of entries) {
    if (single) { nodes.push(new Option(entry.label, entry.value)); continue; }
    if (nodes.at(-1)?.label !== entry.project) { const section = document.createElement('optgroup'); section.label = entry.project; nodes.push(section); }
    nodes.at(-1).append(new Option(entry.label, entry.value));
  }
  ids.groupFilter.replaceChildren(new Option('All', ''), new Option('No group', 'none'), ...nodes);
  ids.groupFilter.value = [...ids.groupFilter.options].some(option => option.value === selected) ? selected : '';
  titleGroupFilter();
}
function titleGroupFilter() {
  const chosen = ids.groupFilter.selectedOptions[0];
  ids.groupFilter.title = chosen?.value && chosen.parentElement.label ? `${chosen.parentElement.label}: ${chosen.textContent}` : '';
}

// ---------- Editor: the detail panel (create and edit) ----------
const NEW_GROUP = '__new';
let editorAction = null;
let editorInitial = '';
let editorReturnFocus = null;
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
  const sorted = [...slugs].sort((a, b) => groupLabel(a).localeCompare(groupLabel(b), LOCALE) || a.localeCompare(b));
  ids.editorGroup.replaceChildren(new Option('No group', ''), ...sorted.map(slug => new Option(groupLabel(slug), slug)), new Option('New group…', NEW_GROUP));
  ids.editorGroup.value = fresh ? NEW_GROUP : choice.slug || '';
  ids.editorGroupNew.value = choice.fresh ? choice.text : fresh ? groupLabel(choice.slug) : '';
  showGroupField();
}
function showGroupField(focus = false) {
  const choice = groupChoice();
  const slug = groupValue();
  const register = snapshot.registers.find(item => item.path === ids.editorProject.value);
  ids.editorGroupNewLabel.hidden = !choice.fresh;
  ids.editorGroupHint.textContent = !choice.fresh ? (slug ? `Saved as: ${slug}` : 'Optional: groups related actions together.') :
    !choice.text.trim() ? 'Enter a label: it will be converted to an identifier.' :
    !slug ? 'No letter or digit: no group.' :
    `${(register?.groups || []).includes(slug) ? 'Existing group' : 'New group'}: ${slug}`;
  if (focus && choice.fresh) ids.editorGroupNew.focus();
}
function formAction() {
  return {
    title: ids.editorActionTitle.value.replace(/[\r\n]+/g, ' ').trim(), owner: ids.editorOwner.value.trim(),
    state: ids.editorState.value, priority: ids.editorPriority.value,
    due: ids.editorDue.value, scheduled: ids.editorScheduled.value, group: groupValue()
  };
}
function editorOpen() { return !ids.editor.hidden; }
function editorSignature() { return JSON.stringify([ids.editorProject.value, formAction()]); }
function editorDirty() { return editorOpen() && editorSignature() !== editorInitial; }
function updateEditorButtons() {
  ids.saveEditor.disabled = Boolean(editorAction) && !editorDirty();
}
function sizeTitleField() {
  ids.editorActionTitle.style.height = 'auto';
  ids.editorActionTitle.style.height = `${Math.min(ids.editorActionTitle.scrollHeight + 2, 320)}px`;
}
function renderStamps(action) {
  if (!action) { ids.editorStamps.hidden = true; ids.editorStamps.replaceChildren(); return; }
  const pairs = [
    ['Created', action.created_at ? formatStamp(action.created_at) : 'Not set'],
    ['Updated', action.updated_at ? formatStamp(action.updated_at) : 'Not set']
  ];
  if (closed(action)) pairs.push(['Closed', action.done ? formatDay(action.done) : 'Not set']);
  ids.editorStamps.replaceChildren(...pairs.flatMap(([label, value]) => [element('dt', '', label), element('dd', '', value)]));
  ids.editorStamps.hidden = false;
}
// preset (creation only): {register, group (slug), state}. focus: 'auto' (title when creating, heading when editing), 'title', 'none'.
function openEditor(action = null, preset = null, {focus = 'auto'} = {}) {
  const same = action && editorAction && editorAction.id === action.id;
  if (editorDirty() && !same && !confirm('Discard the unsaved changes to this action?')) return false;
  closePopover(false);
  if (!editorOpen()) editorReturnFocus = document.activeElement;
  const historyRequest = ++editorHistoryRequest;
  editorAction = action;
  ids.editor.dataset.actionId = action?.id || '';
  ids.editor.dataset.version = action?.version || '';
  ids.editorTitle.textContent = action ? action.id : 'New action';
  const target = !action && preset?.register && snapshot.registers.find(register => register.path === preset.register);
  ids.editorHint.textContent = action ? action.project : target ? `${target.label}${preset.group ? `, group ${groupLabel(preset.group)}` : ''}${preset.due ? `, due ${formatDay(preset.due)}` : ''}` : '';
  ids.editorProjectField.hidden = Boolean(action);
  ids.editorProject.disabled = Boolean(action);
  ids.editorProject.value = action?.register || preset?.register || defaultRegister();
  ids.editorActionTitle.value = action?.raw_title || '';
  fillGroupOptions({slug: action?.group || (!action && preset?.group) || ''}, true);
  ids.editorHistory.hidden = !action;
  noteState = null;
  noteBusy = false;
  closeNoteForm(false);
  ids.noteInput.value = '';
  ids.addNoteButton.disabled = true;
  ids.editorHistoryList.replaceChildren(element('li', 'note-empty', 'Loading…'));
  ids.editorHistoryCount.textContent = '';
  ids.editorOwner.value = action?.owner || snapshot.owner;
  ids.editorState.value = action?.state || (!action && preset?.state) || ' ';
  ids.editorPriority.value = action?.priority || '';
  ids.editorDue.value = action?.due || (!action && preset?.due) || '';
  ids.editorScheduled.value = action?.scheduled || '';
  ids.saveEditor.textContent = action ? 'Save' : 'Create action';
  ids.cancelEditor.textContent = action ? 'Close' : 'Cancel';
  ids.deleteEditor.hidden = !action;
  renderStamps(action);
  setEditorBusy(false);
  ids.editorError.hidden = true;
  ids.editor.hidden = false;
  ids.editor.setAttribute('aria-label', action ? `Action ${action.id}` : 'New action');
  sizeTitleField();
  editorInitial = editorSignature();
  updateEditorButtons();
  if (focus === 'title' || (focus === 'auto' && !action)) ids.editorActionTitle.focus();
  else if (focus === 'auto') ids.editorTitle.focus({preventScroll: true});
  if (action) {
    loadDetails(action).then(details => {
      if (historyRequest !== editorHistoryRequest || !editorOpen()) return;
      renderNotes(details);
    }).catch(error => {
      if (historyRequest !== editorHistoryRequest || !editorOpen()) return;
      ids.editorHistoryList.replaceChildren(element('li', 'note-empty', `History unavailable: ${error.message}`));
    });
  }
  return true;
}
function closeEditor({force = false, refocus = true} = {}) {
  if (!editorOpen()) return true;
  if (!force && editorDirty() && !confirm('Discard the unsaved changes to this action?')) return false;
  const wasEditing = editorAction?.id;
  ids.editor.hidden = true;
  editorHistoryRequest += 1;
  editorAction = null;
  noteState = null;
  if (refocus) {
    const row = wasEditing && rowFor(wasEditing);
    const target = row?.querySelector(ROW_MAIN) || (editorReturnFocus?.isConnected && !ids.editor.contains(editorReturnFocus) ? editorReturnFocus : null);
    (target || ids.resultCount).focus({preventScroll: true});
  }
  editorReturnFocus = null;
  return true;
}
// After a refresh: an unchanged panel follows the register (new version), a vanished action closes it.
function syncEditorAfterRefresh() {
  if (!editorOpen() || !editorAction) return;
  const fresh = findAction(editorAction.id);
  if (!fresh) { closeEditor({force: true, refocus: false}); return; }
  if (fresh.version !== editorAction.version && !editorDirty()) openEditor(fresh, null, {focus: 'none'});
}
function renderNotes(details) {
  noteState = {id: details.id, version: details.details_version, notes: details.notes};
  const shown = details.notes.filter(note => !/^-?\s*(created|updated)\s*:/i.test(note.text));
  ids.editorHistoryList.replaceChildren();
  if (!shown.length) ids.editorHistoryList.append(element('li', 'note-empty', 'No notes yet.'));
  for (const note of shown) {
    const item = element('li', `note-item${note.deletable ? '' : ' note-source'}`);
    const text = note.text.replace(/^-\s+/, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
    const body = element('span', 'note-text');
    const dated = text.match(/^(\d{2}\/\d{2}): ([\s\S]*)$/);
    if (dated) body.append(element('span', 'note-date', dated[1]), dated[2]);
    else body.textContent = text;
    item.append(body);
    if (note.deletable) {
      const button = iconButton('icon-button note-delete', 'Delete the note', ICONS.trash);
      button.addEventListener('click', () => deleteNote(note));
      item.append(button);
    }
    ids.editorHistoryList.append(item);
  }
  const count = shown.filter(note => note.deletable).length;
  ids.editorHistoryCount.textContent = count ? String(count) : '';
  setNoteBusy(false);
}
function setNoteBusy(busy) {
  noteBusy = busy;
  ids.addNoteButton.disabled = busy || !noteState;
  ids.submitNote.disabled = busy || !noteState;
  ids.editorHistoryList.querySelectorAll('.note-delete').forEach(button => { button.disabled = busy; });
}
function showNoteError(error) {
  ids.noteError.textContent = error.status === 409 ? 'The history changed in the register: close and reopen the action to reload it.' : error.message;
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
  if (focus && editorOpen()) ids.addNoteButton.focus();
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
    if (session !== editorHistoryRequest || !editorOpen()) return null;
    renderNotes(fresh);
    // The action line changed ("updated"): its new version keeps the panel and later saves in step.
    editorAction = {...editorAction, version: fresh.version, updated_at: fresh.updated_at};
    ids.editor.dataset.version = fresh.version;
    renderStamps(editorAction);
    refreshQuietly();
    return fresh;
  } catch (error) {
    if (session === editorHistoryRequest && editorOpen()) {
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
    showNoteError(new Error('Enter a note before adding it.'));
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
  } else if (editorOpen()) ids.noteInput.focus();
}
async function deleteNote(note) {
  if (noteBusy || !noteState || !confirm('Delete this note from the register?')) return;
  const {id, version} = noteState;
  const fresh = await changeNotes(() => request(`/api/actions/${encodeURIComponent(id)}/notes/${note.index}`, {
    method: 'DELETE', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
    body: JSON.stringify({details_version: version, text: note.text})
  }));
  if (!editorOpen()) return;
  (ids.editorHistoryList.querySelector('.note-delete') || ids.addNoteButton).focus();
}
function setEditorBusy(busy) {
  ids.saveEditor.disabled = busy || (Boolean(editorAction) && !editorDirty());
  ids.deleteEditor.disabled = busy;
  ids.saveEditor.setAttribute('aria-busy', String(busy));
}
// No confirmation: Undo (and Git) restore a deleted action. Checks `version` and `details_version`, then stacks the undo.
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
  const index = visibleRows().findIndex(row => row.dataset.id === id);
  setEditorBusy(true);
  ids.editorError.hidden = true;
  try {
    await removeAction(id, ids.editor.dataset.version, noteState?.id === id ? noteState.version : null);
    closeEditor({force: true, refocus: false});
    await refresh();
    showToast('Action deleted', {undo: true});
    focusAction(id, 'title', index);
  } catch (error) {
    ids.editorError.textContent = error.status === 409 ? 'The register changed: close and reopen the action before deleting it.' : error.message;
    ids.editorError.hidden = false;
  } finally {
    setEditorBusy(false);
  }
}
async function deleteFromRow(action, button) {
  if (button.disabled) return;
  closePopover(false);
  const index = visibleRows().findIndex(row => row.dataset.id === action.id);
  button.disabled = true;
  try {
    await removeAction(action.id, action.version);
    if (editorAction?.id === action.id) closeEditor({force: true, refocus: false});
    await refresh();
    showToast('Action deleted', {undo: true});
    focusAction(action.id, 'title', index);
  } catch (error) {
    const conflict = error.status === 409;
    if (conflict) await refresh();
    showError(conflict ? `The register changed: the list was refreshed, check ${action.id} and try again.` : error.message);
    button.disabled = false;
  }
}
async function saveEditor(event) {
  event.preventDefault();
  if (ids.saveEditor.disabled) return;
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
      editorInitial = editorSignature(); // saved: the panel follows the fresh line after the refresh
      showToast('Action updated', {undo: true});
      await refresh();
      if (editorOpen()) ids.editorTitle.focus({preventScroll: true});
    } else {
      const result = await request('/api/actions', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
        body: JSON.stringify({register: ids.editorProject.value, action})
      });
      setUndo(result.undo);
      closeEditor({force: true, refocus: false});
      await refresh();
      showToast(`Action ${result.id} created`, {undo: true});
      focusAction(result.id);
    }
  } catch (error) {
    ids.editorError.textContent = error.status === 409 ? 'The register changed since you opened it: copy your changes, close the panel, then reopen the action.' : error.message;
    ids.editorError.hidden = false;
  } finally {
    setEditorBusy(false);
    updateEditorButtons();
  }
}
// Quick edits from a row or a card: the whole line goes back with one field changed (the group is left as it is).
async function patchAction(action, changes, message, {anchor = null, part = 'title'} = {}) {
  const index = visibleRows().findIndex(row => row.dataset.id === action.id);
  const keepFocus = anchor !== null || (document.activeElement && activeRoot()?.contains(document.activeElement));
  if (anchor) anchor.disabled = true;
  try {
    setUndo((await request(`/api/actions/${encodeURIComponent(action.id)}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({version: action.version, action: {
        title: action.raw_title, owner: action.owner, state: action.state, priority: action.priority,
        due: action.due, scheduled: action.scheduled, ...changes
      }})
    })).undo);
    showToast(message, {undo: true});
    await refresh();
  } catch (error) {
    await refresh();
    showError(error.status === 409 ? `The register changed: the list was refreshed, check ${action.id} and try again.` : error.message);
  }
  if (keepFocus && ACTION_VIEWS.includes(view)) focusAction(action.id, part, index);
}
function updateStatus(action, state, anchor = null) {
  if (state === action.state) return Promise.resolve();
  return patchAction(action, {state}, 'Status updated', {anchor, part: 'status'});
}
function updateDue(action, due, anchor = null) {
  if (due === action.due) return Promise.resolve();
  return patchAction(action, {due}, due ? 'Due date updated' : 'Due date removed', {anchor, part: 'due'});
}

// ---------- Brains ----------
const BRAIN_STORAGE_KEY = 'actions-brain-current-v1';
// Routes that do not depend on the selected brain: their answers are never dropped when the brain changes.
const BRAIN_NEUTRAL = new Set(['/api/brains', '/api/tools', '/api/shutdown']);
let brains = [];
let currentBrain = '';
let brainEpoch = 0;
let brainMenuIndex = -1;
let pendingWrites = 0;
function brainUrl(url, brain = currentBrain) {
  if (!brain || !url.startsWith('/api/')) return url;
  return `${url}${url.includes('?') ? '&' : '?'}brain=${encodeURIComponent(brain)}`;
}
// A read that answers after a brain change belongs to the previous brain: it is dropped (error.stale) instead of overwriting the new views.
// Writes are never dropped: the brain switch waits for them (switchBrain).
// `brain` names another brain than the current one (the Git cards act on the brain they are about).
async function request(url, options = {}, brain = currentBrain) {
  const epoch = brainEpoch;
  const write = (options.method || 'GET').toUpperCase() !== 'GET';
  if (write) pendingWrites += 1;
  try {
    const response = await fetch(brainUrl(url, brain), options);
    if (!write && epoch !== brainEpoch && !BRAIN_NEUTRAL.has(url.split('?')[0])) {
      const stale = new Error('Response from another brain ignored.');
      stale.stale = true;
      throw stale;
    }
    let payload;
    try { payload = await response.json(); } catch { throw new Error('Unreadable local response.'); }
    if (!response.ok) {
      const error = new Error(payload.error || 'Operation failed.');
      error.status = response.status;
      error.data = payload; // the rest of the answer (the pages that link to a note that cannot be deleted)
      throw error;
    }
    return payload;
  } finally {
    if (write) pendingWrites -= 1;
  }
}
function readStoredBrain() {
  try { return localStorage.getItem(BRAIN_STORAGE_KEY) || ''; } catch { return ''; }
}
function storeBrain(name) {
  try { localStorage.setItem(BRAIN_STORAGE_KEY, name); } catch { /* The choice is simply not remembered. */ }
}
function brainFromUrl() {
  try { return new URL(location.href).searchParams.get('brain') || ''; } catch { return ''; }
}
function syncBrainUrl() {
  try {
    const url = new URL(location.href);
    url.searchParams.set('brain', currentBrain);
    history.replaceState(history.state, '', url.href);
  } catch { /* The address bar keeps its value. */ }
}
// One accent per brain, stable: steel for the default brain (or `brain` before the list is loaded), plum for
// `brain-perso`, then a hash over four more.
const EXTRA_ACCENTS = ['teal', 'olive', 'rust', 'slate'];
function accentFor(name) {
  const listed = brains.find(brain => brain.name === name);
  if (!name || listed?.default || (!listed && name === 'brain')) return 'steel';
  if (name === 'brain-perso') return 'plum';
  let hash = 0;
  for (const char of name) hash = (Math.imul(hash, 31) + char.charCodeAt(0)) >>> 0;
  return EXTRA_ACCENTS[hash % EXTRA_ACCENTS.length];
}
function applyAccent(name) { document.documentElement.dataset.accent = accentFor(name); }
// What the page shows for a brain: the short label of the server (`Perso` for `brain-perso`); the folder name stays the technical value.
function brainLabel(name) {
  return brains.find(brain => brain.name === name)?.label || name;
}
// Tooltip of a brain: its folder name and scope, then its description. The scope is not displayed otherwise.
function brainTitle(brain) {
  return [brain.scope ? `${brain.name} (${brain.scope})` : brain.name, brain.description].filter(Boolean).join(': ');
}
function brainOption(brain, index) {
  const option = element('li', 'brain-option');
  option.id = `brainOption${index}`;
  option.setAttribute('role', 'option');
  option.setAttribute('aria-selected', String(brain.name === currentBrain));
  option.dataset.brain = brain.name;
  const swatch = element('span', 'brain-swatch');
  swatch.dataset.accent = accentFor(brain.name);
  const text = element('span', 'brain-option-text');
  text.append(element('span', 'brain-option-name', brain.label || brain.name));
  option.append(swatch, text, svgIcon(ICONS.check, 'brain-check'));
  option.title = brainTitle(brain);
  option.addEventListener('click', () => chooseBrain(brain.name));
  return option;
}
// The switcher: the brain's name as plain text when the Work has one brain, otherwise a button that opens the list.
function renderBrainSwitch() {
  const several = brains.length > 1;
  const known = brains.find(brain => brain.name === currentBrain);
  const active = ids.brainMenu.children[brainMenuIndex]?.dataset.brain || currentBrain;
  ids.brainStatic.hidden = several;
  ids.brainStaticName.textContent = brainLabel(currentBrain) || 'Brain';
  ids.brainStatic.title = known ? brainTitle(known) : '';
  ids.brainButton.hidden = !several;
  ids.brainName.textContent = brainLabel(currentBrain);
  ids.brainMini.textContent = brainLabel(currentBrain) || 'Brain';
  ids.brainButton.title = known ? brainTitle(known) : '';
  ids.brainMenu.replaceChildren(...brains.map(brainOption));
  if (!several) closeBrainMenu(false);
  else if (brainMenuOpen()) setBrainActive(Math.max(0, brains.findIndex(brain => brain.name === active)));
  document.title = several && currentBrain ? `Actions – ${brainLabel(currentBrain)}` : 'Actions';
}
function brainMenuOpen() { return !ids.brainMenu.hidden; }
function setBrainActive(index) {
  const options = [...ids.brainMenu.children];
  if (!options.length) return;
  brainMenuIndex = Math.max(0, Math.min(index, options.length - 1));
  options.forEach((option, position) => option.classList.toggle('is-active', position === brainMenuIndex));
  ids.brainMenu.setAttribute('aria-activedescendant', options[brainMenuIndex].id);
  options[brainMenuIndex].scrollIntoView({block: 'nearest'});
}
function openBrainMenu() {
  if (brains.length < 2 || brainMenuOpen()) return;
  closePopover(false);
  ids.brainMenu.hidden = false;
  ids.brainButton.setAttribute('aria-expanded', 'true');
  setBrainActive(brains.findIndex(brain => brain.name === currentBrain));
  ids.brainMenu.focus();
  loadBrains(); // A brain added since the page was opened shows up.
}
function closeBrainMenu(refocus = true) {
  if (!brainMenuOpen()) return;
  ids.brainMenu.hidden = true;
  ids.brainButton.setAttribute('aria-expanded', 'false');
  ids.brainMenu.removeAttribute('aria-activedescendant');
  brainMenuIndex = -1;
  if (refocus) ids.brainButton.focus();
}
function chooseBrain(name) {
  closeBrainMenu();
  if (name) switchBrain(name);
}
function adoptBrain(name) {
  currentBrain = name;
  brainEpoch += 1;
  storeBrain(name);
  syncBrainUrl();
  applyAccent(name);
  renderBrainSwitch();
}
// What a brain owns: project filter, group folds, selection, panel, open documents and Git detail, tool output, undo.
// The text typed in the search boxes and the owner and scope filters are not tied to a brain: they stay.
function resetBrainState() {
  projectScope = '';
  pendingGroup = '';
  ids.groupFilter.value = '';
  ids.docProject.value = '';
  ids.editorProject.replaceChildren();
  foldedGroups.clear();
  snapshot = {actions: [], registers: [], owner: '', today: ''};
  detailCache.clear();
  selectedId = null;
  timelineAnchor = true;
  timelineModel = null;
  timelineSpot = '';
  timelineBase = [];
  ids.timelineTraySearch.value = '';
  closePopover(false);
  closeEditor({force: true, refocus: false});
  // The Git cards are the same for every brain (only their order follows the current one): kept, drawn again by the render below.
  gitLoadId += 1;
  gitLoading = null;
  closeGitDialogs();
  clearTimeout(docTimer);
  notesRequest += 1;
  docSearchRequest += 1;
  docRenderRequest += 1;
  notesData = [];
  recentDocs = [];
  notesLoaded = false;
  docMode = 'recent';
  docResults = [];
  docTotal = 0;
  docTruncated = false;
  docTerms = [];
  docError = '';
  docSelectedId = null;
  docCurrent = null;
  docHistory = [];
  docMarks = [];
  docEditing = false;
  docNote = null;
  ids.docPaneEmpty.textContent = 'Choose a document to read it.';
  ids.docList.replaceChildren();
  ids.docArticle.replaceChildren();
  ids.docEditor.value = '';
  setDocError('');
  setDocStatus('');
  renderDocPane();
  ids.toolResultTitle.textContent = 'Result';
  ids.toolResultCommand.hidden = true;
  ids.toolResultStatus.textContent = 'Ready';
  ids.toolResultStatus.className = '';
  ids.toolResultEmpty.hidden = false;
  ids.toolResultOutput.hidden = true;
  ids.toolResultOutput.textContent = '';
  setUndo(null);
  ids.errorBanner.hidden = true;
  ids.lastSync.textContent = 'Loading…';
  ids.todayCount.textContent = '';
  ids.openCount.textContent = '';
  populateProjects();
  renderProjectNav();
  render();
  saveUIState();
}
function enterBrain(name) {
  adoptBrain(name);
  resetBrainState();
  refresh();
}
// A change waits for the writes in flight and keeps an action or a note being edited unless the user lets it go.
function switchBrain(name) {
  if (name === currentBrain) return false;
  if (pendingWrites > 0) {
    showToast('An operation is in progress: wait for it to finish before switching brain.');
    return false;
  }
  if (editorDirty() && !confirm('Discard the unsaved changes to this action?')) return false;
  if (docDirty() && !confirm('Discard the unsaved changes to this note?')) return false;
  enterBrain(name);
  showToast(`Brain ${brainLabel(name)} opened`);
  return true;
}
// Reads the brains of the Work (rediscovered by the server each time). Startup: the brain comes from the URL, then the browser's memory,
// then the server's default. Later: a brain that disappeared sends the page back to the default one. Returns true when it reloaded the views.
async function loadBrains({initial = false} = {}) {
  let data;
  try { data = await request('/api/brains'); } catch { return false; }
  if (!Array.isArray(data.brains)) return false;
  const previousLabel = brainLabel(currentBrain);
  brains = data.brains;
  const names = brains.map(brain => brain.name);
  const fallback = names.includes(data.default) ? data.default : names[0];
  if (initial) {
    const choice = [brainFromUrl(), readStoredBrain()].find(name => names.includes(name)) || fallback;
    if (choice) adoptBrain(choice);
    // Filters kept by this tab belong to the brain they were saved with.
    if (savedUI.brain && savedUI.brain !== currentBrain) {
      projectScope = '';
      pendingGroup = '';
      ids.docProject.value = '';
      foldedGroups.clear();
    }
  } else if (fallback && !names.includes(currentBrain)) {
    if (currentBrain) showToast(`Brain ${previousLabel} no longer exists: back to ${brainLabel(fallback)}.`);
    enterBrain(fallback);
    return true;
  }
  renderBrainSwitch();
  return false;
}

// ---------- Tools ----------
async function loadTools() {
  ids.toolsCatalog.replaceChildren(element('p', 'loading-note', 'Loading tools…'));
  try {
    tools = (await request('/api/tools')).tools;
    const groups = [...new Set(tools.map(tool => tool.group))];
    const sections = [];
    for (const group of groups) {
      const section = element('details', 'tool-group');
      section.open = true;
      const summary = element('summary', 'tool-group-heading');
      summary.append(svgIcon(ICONS.chevron, 'fold-chevron'), element('span', '', group), element('span', 'tool-group-count', String(tools.filter(tool => tool.group === group).length)));
      section.append(summary);
      for (const tool of tools.filter(item => item.group === group)) {
        const row = element('div', 'tool-row');
        row.dataset.search = `${tool.group} ${tool.label} ${tool.description} ${tool.command}`.toLocaleLowerCase(LOCALE);
        const copy = element('div', 'tool-copy');
        const name = element('div', 'tool-name');
        name.append(element('span', '', tool.label));
        if (tool.confirm) name.append(element('span', 'tool-writes', 'writes to the brain'));
        const description = element('p', '', tool.description);
        description.title = `${tool.description}\n${tool.command}`;
        copy.append(name, description);
        const button = element('button', 'button button-small', 'Run');
        button.type = 'button';
        button.setAttribute('aria-label', `Run ${tool.label}`);
        button.title = tool.command;
        button.addEventListener('click', () => runTool(tool, button));
        row.append(copy, button);
        section.append(row);
      }
      sections.push(section);
    }
    ids.toolsCatalog.replaceChildren(...sections);
    render();
  } catch (error) {
    ids.toolsCatalog.replaceChildren(element('p', 'error-note', error.message));
  }
}
function filterTools() {
  const query = ids.toolSearch.value.trim().toLocaleLowerCase(LOCALE);
  let count = 0;
  for (const group of ids.toolsCatalog.querySelectorAll('.tool-group')) {
    let visible = 0;
    for (const row of group.querySelectorAll('.tool-row')) {
      row.hidden = Boolean(query) && !row.dataset.search.includes(query);
      if (!row.hidden) visible += 1;
    }
    group.hidden = visible === 0;
    group.querySelector('.tool-group-count').textContent = String(visible);
    if (query && visible) group.open = true;
    count += visible;
  }
  ids.resultCount.textContent = tools.length ? plural(count, 'tool') : '';
}
async function runTool(tool, button) {
  if (tool.confirm && !confirm(tool.confirm)) return;
  const buttons = ids.toolsCatalog.querySelectorAll('button');
  buttons.forEach(item => { item.disabled = true; });
  button.textContent = 'Running…';
  ids.toolResultTitle.textContent = tool.label;
  ids.toolResultCommand.textContent = tool.command;
  ids.toolResultCommand.hidden = false;
  ids.toolResultStatus.textContent = 'Running';
  ids.toolResultStatus.className = '';
  ids.toolResultEmpty.hidden = true;
  ids.toolResultOutput.hidden = false;
  ids.toolResultOutput.textContent = 'The command is running. Its output will appear here.';
  try {
    const result = await request('/api/tools/run', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({id: tool.id})
    });
    ids.toolResultStatus.textContent = result.ok ? 'Done' : 'Failed';
    ids.toolResultStatus.className = result.ok ? 'tool-status-ok' : 'tool-status-error';
    ids.toolResultOutput.textContent = result.output + (result.truncated ? '\n\n[Output truncated]' : '');
    if (tool.confirm && result.ok) {
      detailCache.clear();
      await refresh();
    }
  } catch (error) {
    ids.toolResultStatus.textContent = 'Failed';
    ids.toolResultStatus.className = 'tool-status-error';
    ids.toolResultOutput.textContent = error.message;
  } finally {
    buttons.forEach(item => { item.disabled = false; });
    button.textContent = 'Run';
  }
}

// ---------- Info tips and popovers ----------
// A small ⓘ button with something to read. Two kinds, both closed by Esc:
// - a tooltip (the title of the view): opens on hover and on keyboard focus, linked to its button by aria-describedby, no interaction inside;
// - a popover (the online copy of a brain), for a panel that holds a link: a disclosure. The button has aria-expanded and aria-controls and
//   toggles the panel (click, Enter, Space); the pointer opens it too and may move from the button into the panel; Tab from the button
//   reaches the link; Esc, a click outside, or the focus leaving the button and the panel closes it.
function infoOf(node) { return node instanceof Element ? node.closest('.info') : null; }
function isPopover(info) { return info.classList.contains('info-pop'); }
function infoButton(info) { return info.querySelector('.info-button'); }
// Open the panel under its button, kept inside the window (above the button when there is no room below).
function openInfo(info) {
  if (info.classList.contains('is-dismissed')) return;
  info.classList.add('is-open');
  if (isPopover(info)) infoButton(info).setAttribute('aria-expanded', 'true');
  const tip = info.querySelector('.info-tip');
  info.classList.remove('is-above');
  tip.style.left = '0px';
  const rect = tip.getBoundingClientRect();
  const over = rect.right - (document.documentElement.clientWidth - 12);
  if (over > 0) tip.style.left = `${-over}px`;
  if (rect.bottom > document.documentElement.clientHeight - 8 && info.getBoundingClientRect().top > rect.height) info.classList.add('is-above');
}
function closeInfo(info) {
  info.classList.remove('is-open', 'is-dismissed', 'is-above');
  delete info.dataset.pinned;
  if (isPopover(info)) infoButton(info).setAttribute('aria-expanded', 'false');
}
// Closed on purpose (Esc, a second click): it stays closed until the pointer and the focus have left and returned.
function dismissInfo(info) {
  closeInfo(info);
  info.classList.add('is-dismissed');
}
// Esc closes the panel that is open, and nothing else that time. A popover gives the focus back to its button.
function dismissInfoTip() {
  const info = document.querySelector('.info.is-open');
  if (!info) return false;
  dismissInfo(info);
  if (isPopover(info)) infoButton(info).focus();
  return true;
}
function togglePopover(info) {
  if (info.classList.contains('is-open') && info.dataset.pinned) { dismissInfo(info); return; }
  info.classList.remove('is-dismissed');
  openInfo(info);
  info.dataset.pinned = '1';
}
document.addEventListener('pointerover', event => { const info = infoOf(event.target); if (info) openInfo(info); });
document.addEventListener('focusin', event => { const info = infoOf(event.target); if (info && !isPopover(info)) openInfo(info); });
document.addEventListener('pointerout', event => {
  const info = infoOf(event.target);
  if (info && !info.contains(event.relatedTarget) && !info.dataset.pinned && !info.matches(':focus-within')) closeInfo(info);
});
document.addEventListener('focusout', event => {
  const info = infoOf(event.target);
  if (!info || info.contains(event.relatedTarget)) return;
  delete info.dataset.pinned;
  if (!info.matches(':hover')) closeInfo(info);
});
document.addEventListener('click', event => {
  const button = event.target instanceof Element ? event.target.closest('.info-pop .info-button') : null;
  if (button) togglePopover(infoOf(button));
});
document.addEventListener('pointerdown', event => {
  for (const info of document.querySelectorAll('.info-pop[data-pinned]')) if (!info.contains(event.target)) closeInfo(info);
});
// The online copy of a brain: "Git", then its URL as a link to the repository's page (plain text when there is no safe page), or why there is none.
// A page served by an older server sends no `url` at all: it is asked to restart rather than told there is no online copy.
// A URL may wrap after a slash (not in the middle of a word when it can be avoided).
function breakableUrl(node, text) {
  for (const part of text.split(/(?<=\/)/)) node.append(part, document.createElement('wbr'));
  return node;
}
function onlineCopyPopover(card) {
  const id = `gitInfo-${card.name}`;
  const known = 'url' in card;
  const label = !known ? 'Restart tasks-web to see the online copy' : card.url ? `Online copy: ${card.url}` : 'No online copy';
  const info = element('span', 'info info-pop');
  const button = element('button', 'info-button');
  button.type = 'button';
  button.id = id;
  button.dataset.focusKey = `info:${card.name}`;
  button.setAttribute('aria-label', label);
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-controls', `${id}Panel`);
  button.append(svgIcon(ICONS.info));
  const panel = element('span', 'info-tip');
  panel.id = `${id}Panel`;
  panel.setAttribute('role', 'group');
  panel.setAttribute('aria-label', 'Online copy');
  const box = element('span', 'info-tip-box');
  box.append(element('span', 'info-tip-line info-tip-head', 'Git'));
  if (known && card.url && typeof card.web_url === 'string' && /^https?:\/\//i.test(card.web_url)) {
    const link = element('a', 'info-tip-line info-link');
    link.href = card.web_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.append(breakableUrl(element('span', 'info-link-text'), card.url), element('span', 'sr-only', ' (opens in a new tab)'), svgIcon(ICONS.open));
    box.append(link);
  } else {
    const line = element('span', 'info-tip-line');
    if (known && card.url) breakableUrl(line, card.url); else line.textContent = known ? 'No online copy' : 'Restart tasks-web to see the online copy';
    box.append(line);
  }
  panel.append(box);
  info.append(button, panel);
  return info;
}

// ---------- Git: save and send ----------
// One card per brain of the Work, the chosen one first (never Work itself). The server says what is possible (`state`, `action`)
// and writes the sentences; this draws them, with the changed notes in plain words (title, project, New / Edited / Deleted / Renamed),
// and runs the one button of a card after a confirmation. No path, branch, hash or line count is shown.
const GIT_STATE_ICONS = {clean: 'gitSaved', changes: 'gitEdited', unsent: 'gitSend', behind: 'gitBehind', unavailable: 'gitOff'};
const GIT_VISIBLE_NOTES = 8;
const GIT_VISIBLE_LINES = 3000; // the server cuts a comparison there
const GIT_CHANGE_TEXT = {New: 'New', Edited: 'Edited', Deleted: 'Deleted', Renamed: 'Renamed'};
let gitCards = [];
let gitLoaded = false;
let gitLoading = null;
let gitLoadId = 0; // bumped when the brain changes: a load started before it no longer owns `gitLoading`
let gitChangesRequest = 0;
let gitConfirmCard = null; // the card the open confirmation is about, as the person saw it
const gitResults = new Map(); // brain name -> what the last save or send said (shown in its card)
const gitBusy = new Set(); // brain names being saved or sent
const gitExpanded = new Set(); // brain names whose whole list of notes is shown
// "2 hours ago", "yesterday", "3 days ago"; a date after a month.
function relativeTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = (date.getTime() - Date.now()) / 1000;
  const formatter = new Intl.RelativeTimeFormat(LOCALE, {numeric: 'auto'});
  for (const [limit, unit, size] of [[60, 'second', 1], [3600, 'minute', 60], [86400, 'hour', 3600], [2592000, 'day', 86400]]) {
    if (Math.abs(seconds) < limit) return formatter.format(Math.round(seconds / size), unit);
  }
  return DAY_YEAR_FORMAT.format(date);
}
function orderedGitCards() {
  return [...gitCards].sort((a, b) => Number(b.name === currentBrain) - Number(a.name === currentBrain));
}
function gitPendingCount() { return gitCards.filter(card => card.pending).length; }
function gitNoteRow(card, note) {
  const row = element('button', 'git-note');
  row.type = 'button';
  row.dataset.focusKey = `note:${card.name}:${note.path}`;
  const change = element('span', `git-change git-change-${note.change.toLowerCase()}`, GIT_CHANGE_TEXT[note.change] || note.change);
  const main = element('span', 'git-note-main');
  main.append(element('span', 'git-note-title', note.title));
  if (note.project) main.append(element('span', 'git-note-project', note.project));
  const see = element('span', 'git-note-see', 'See changes');
  see.append(svgIcon(ICONS.chevron));
  row.append(change, main, see);
  row.title = note.from ? `${note.from} → ${note.path}` : note.path;
  row.setAttribute('aria-label', `${GIT_CHANGE_TEXT[note.change] || note.change}: ${note.title}${note.project ? `, ${note.project}` : ''}. See changes`);
  row.addEventListener('click', () => openGitChanges(card, note));
  return row;
}
function gitResultBox(card, result) {
  const tone = result.ok ? 'ok' : result.saved ? 'partial' : 'failed';
  const box = element('div', `git-result git-result-${tone}`);
  box.setAttribute('role', result.ok ? 'status' : 'alert');
  const body = element('div', 'git-result-body');
  body.append(element('p', 'git-result-message', result.message));
  if (result.details) {
    const details = element('details', 'git-details');
    details.append(element('summary', '', 'Details'), element('pre', '', result.details));
    body.append(details);
  }
  const dismiss = iconButton('icon-button', 'Dismiss this message', '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>');
  dismiss.dataset.focusKey = `dismiss:${card.name}`;
  dismiss.addEventListener('click', () => { gitResults.delete(card.name); renderGit(`card:${card.name}`); });
  box.append(body, dismiss);
  return box;
}
function gitCardNode(card) {
  const section = element('section', 'git-card');
  section.dataset.state = card.state;
  section.dataset.accent = accentFor(card.name);
  section.dataset.focusKey = `card:${card.name}`;
  section.tabIndex = -1;
  section.setAttribute('aria-labelledby', `gitTitle-${card.name}`);
  const head = element('div', 'git-head');
  const title = element('h2', '', card.label);
  title.id = `gitTitle-${card.name}`;
  head.append(title);
  head.append(onlineCopyPopover(card));
  if (card.name === currentBrain && gitCards.length > 1) head.append(element('span', 'git-current', 'Current brain'));
  const status = element('div', 'git-status');
  const badge = element('span', 'git-badge');
  badge.append(svgIcon(ICONS[GIT_STATE_ICONS[card.state] || 'gitOff']));
  const text = element('div', 'git-status-text');
  text.append(element('p', 'git-sentence', card.message));
  if (card.last_saved) {
    const last = element('p', 'git-last', `Last saved: ${relativeTime(card.last_saved)}`);
    last.title = formatStamp(card.last_saved.slice(0, 16).replace('T', ' '));
    text.append(last);
  }
  status.append(badge, text);
  section.append(head, status);
  const result = gitResults.get(card.name);
  if (result) section.append(gitResultBox(card, result));
  if (card.changes.length) {
    const total = card.count;
    const heading = element('div', 'git-notes-head');
    heading.append(element('h3', '', plural(total, 'changed note')));
    section.append(heading);
    const expanded = gitExpanded.has(card.name);
    const shown = expanded ? card.changes : card.changes.slice(0, GIT_VISIBLE_NOTES);
    const list = element('ul', 'git-notes');
    for (const note of shown) {
      const item = element('li');
      item.append(gitNoteRow(card, note));
      list.append(item);
    }
    section.append(list);
    if (card.changes.length > GIT_VISIBLE_NOTES) {
      const toggle = element('button', 'link-button git-more', expanded ? 'Show fewer' : `Show all ${plural(card.changes.length, 'note')}`);
      toggle.type = 'button';
      toggle.dataset.focusKey = `more:${card.name}`;
      toggle.setAttribute('aria-expanded', String(expanded));
      toggle.addEventListener('click', () => {
        if (gitExpanded.has(card.name)) gitExpanded.delete(card.name); else gitExpanded.add(card.name);
        renderGit(`more:${card.name}`);
      });
      section.append(toggle);
    }
    if (card.more) section.append(element('p', 'git-last', `and ${plural(card.more, 'more note')}`));
  }
  if (card.action) {
    const busy = gitBusy.has(card.name);
    const actions = element('div', 'git-actions');
    const label = card.action === 'save' ? 'Save and send' : 'Send';
    const verb = card.action === 'save' ? 'Saving and sending' : 'Sending';
    const button = element('button', 'button button-primary', busy ? `${verb}…` : label);
    button.type = 'button';
    button.dataset.focusKey = `go:${card.name}`;
    button.disabled = busy;
    button.setAttribute('aria-busy', String(busy));
    button.setAttribute('aria-label', busy ? `${verb} ${card.label}` : `${label} for ${card.label}`);
    button.addEventListener('click', () => card.action === 'save' ? askGitSave(card) : runGit(card, 'send'));
    actions.append(button);
    section.append(actions);
  }
  return section;
}
// Draws the cards again, keeping the scroll position and the focus (`fallbackKey`: where the focus goes when its control is gone).
function renderGit(fallbackKey = '') {
  const pending = gitPendingCount();
  ids.gitCount.textContent = gitLoaded && pending ? String(pending) : '';
  ids.gitButton.setAttribute('aria-label', gitLoaded && pending ? `Sync, ${plural(pending, 'brain')} to save or send` : 'Sync');
  if (view !== 'git') return;
  ids.resultCount.textContent = !gitLoaded ? '' : pending ? `${plural(pending, 'brain')} to save or send` : 'Everything is saved';
  if (!gitLoaded) return;
  const focused = ids.gitCards.contains(document.activeElement) ? document.activeElement.dataset.focusKey || '' : '';
  const scroll = ids.gitView.scrollTop;
  ids.gitCards.replaceChildren(...orderedGitCards().map(gitCardNode));
  ids.gitView.scrollTop = scroll;
  const find = key => key ? [...ids.gitCards.querySelectorAll('[data-focus-key]')].find(node => node.dataset.focusKey === key) : null;
  const target = find(focused) || find(fallbackKey);
  if (target && (focused || fallbackKey)) target.focus({preventScroll: true});
}
// A message tied to a state of the brain goes when that state does; the others stay for one more look.
function dropStaleGitResults() {
  for (const [name, result] of [...gitResults]) {
    const card = gitCards.find(item => item.name === name);
    if (!card) gitResults.delete(name);
    else if (result.version) { if (card.version !== result.version) gitResults.delete(name); }
    else if (result.seen) gitResults.delete(name);
    else result.seen = true;
  }
}
function loadGit({quiet = false} = {}) {
  if (gitLoading) return gitLoading;
  if (!quiet) {
    ids.gitStatus.textContent = gitLoaded ? 'Refreshing…' : 'Loading…';
    ids.gitStatus.classList.remove('git-status-error');
    if (!gitLoaded && view === 'git') ids.gitCards.replaceChildren(element('p', 'loading-note', 'Loading…'));
  }
  const loadId = gitLoadId;
  gitLoading = (async () => {
    try {
      const data = await request('/api/git');
      if (!Array.isArray(data.brains)) throw new Error('Restart tasks-web: this page is newer than the server that is running.');
      gitCards = data.brains;
      gitLoaded = true;
      dropStaleGitResults();
      ids.gitStatus.textContent = `Refreshed at ${TIME_FORMAT.format(new Date())}`;
      renderGit();
    } catch (error) {
      if (error.stale || loadId !== gitLoadId || (quiet && gitLoaded)) return;
      ids.gitStatus.textContent = 'Failed';
      ids.gitStatus.classList.add('git-status-error');
      if (!gitLoaded && view === 'git') {
        const message = element('p', 'error-note', error.message);
        message.setAttribute('role', 'alert');
        ids.gitCards.replaceChildren(message);
      } else if (view === 'git') showToast(`Sync: ${error.message}`);
    } finally {
      if (loadId === gitLoadId) gitLoading = null;
    }
  })();
  return gitLoading;
}
function replaceGitCard(card) {
  const index = gitCards.findIndex(item => item.name === card.name);
  if (index >= 0) gitCards[index] = card; else gitCards.push(card);
}
// The confirmation says what will happen, in the person's words, and lists the notes (the server refuses if they have changed since).
function askGitSave(card) {
  const count = card.count;
  ids.gitConfirmText.textContent = `Save ${plural(count, 'changed note')} of ${card.label} and send ${count === 1 ? 'it' : 'them'} to its online copy?`
    + (card.unsent ? ' What was saved earlier and not sent yet goes with it.' : '');
  const shown = card.changes.slice(0, GIT_VISIBLE_NOTES);
  ids.gitConfirmList.replaceChildren(...shown.map(note => element('li', '', note.title)));
  const rest = count - shown.length;
  if (rest > 0) ids.gitConfirmList.append(element('li', 'git-confirm-more', `and ${plural(rest, 'more note')}`));
  ids.gitConfirmDialog.dataset.accent = accentFor(card.name);
  gitConfirmCard = card;
  ids.gitConfirmDialog.showModal();
}
async function runGit(card, action) {
  if (gitBusy.has(card.name)) return;
  gitBusy.add(card.name);
  gitResults.delete(card.name);
  renderGit(`go:${card.name}`);
  try {
    const result = await request(`/api/git/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({version: card.version})
    }, card.name);
    replaceGitCard(result.brain);
    gitResults.set(card.name, {ok: result.ok, saved: result.saved, message: result.message, details: result.details, version: result.ok ? '' : result.brain.version});
  } catch (error) {
    // Refused before anything ran (the notes changed, the brain is behind, another save is running…): say so, and show the brain as it is now.
    gitResults.set(card.name, {ok: false, saved: false, message: error.message, details: '', version: ''});
    await loadGit({quiet: true});
  } finally {
    gitBusy.delete(card.name);
    renderGit(`card:${card.name}`);
  }
}
async function openGitChanges(card, note) {
  const requestId = ++gitChangesRequest;
  ids.gitChangesTitle.textContent = note.title;
  ids.gitChangesMeta.textContent = [GIT_CHANGE_TEXT[note.change] || note.change, note.project, card.label].filter(Boolean).join(' · ');
  ids.gitChangesBody.replaceChildren(element('p', 'git-changes-message', 'Loading…'));
  ids.gitChangesDialog.dataset.accent = accentFor(card.name);
  if (!ids.gitChangesDialog.open) ids.gitChangesDialog.showModal();
  ids.gitChangesBody.scrollTop = 0;
  try {
    const data = await request(`/api/git/changes?${new URLSearchParams({path: note.path})}`, {}, card.name);
    if (requestId === gitChangesRequest) renderGitChanges(data);
  } catch (error) {
    if (requestId !== gitChangesRequest || error.stale) return;
    ids.gitChangesBody.replaceChildren(element('p', 'git-changes-message', error.status === 404 ? 'This note has no change to save any more. Refresh the list.' : error.message));
  }
}
function gitChangesMessage(data) {
  if (data.hidden) return 'This file may hold a secret, so its content is not shown.';
  if (data.binary) return 'This file is not text, so there is nothing to compare here.';
  if (data.too_large) return 'This note is too large to compare here.';
  if (data.unchanged) {
    return {New: 'This note is empty.', Deleted: 'This note was empty.', Renamed: 'This note was moved or renamed. Its text did not change.'}[data.change]
      || 'Nothing to show: the text of this note did not change.';
  }
  return '';
}
function renderGitChanges(data) {
  const message = gitChangesMessage(data);
  if (message) { ids.gitChangesBody.replaceChildren(element('p', 'git-changes-message', message)); return; }
  const lines = element('div', 'git-lines');
  for (const [kind, value] of data.blocks) {
    if (kind === 'gap') {
      lines.append(element('span', 'git-gap', `${plural(value, 'unchanged line')} not shown`));
      continue;
    }
    const line = element('span', `git-line git-line-${kind}`);
    if (kind !== 'ctx') line.append(element('span', 'sr-only', kind === 'add' ? 'Added: ' : 'Removed: '));
    line.append(element('span', 'git-line-text', value));
    lines.append(line);
  }
  const nodes = [element('p', 'git-legend', 'What was saved last time against what is there now: removed lines are struck through, added lines are highlighted.'), lines];
  if (data.truncated) nodes.push(element('p', 'git-truncated', `Only the first ${GIT_VISIBLE_LINES} lines are shown.`));
  ids.gitChangesBody.replaceChildren(...nodes);
}
function closeGitDialogs() {
  gitChangesRequest += 1;
  gitConfirmCard = null;
  for (const dialog of [ids.gitConfirmDialog, ids.gitChangesDialog]) if (dialog.open) dialog.close();
}
ids.gitConfirmGo.addEventListener('click', () => {
  const card = gitConfirmCard;
  gitConfirmCard = null;
  ids.gitConfirmDialog.close();
  if (card) runGit(card, 'save');
});
ids.gitChangesClose.addEventListener('click', () => ids.gitChangesDialog.close());
// A click on the backdrop closes the comparison, as it does for the other dialogs of the page.
ids.gitChangesDialog.addEventListener('click', event => { if (event.target === ids.gitChangesDialog) ids.gitChangesDialog.close(); });

// ---------- Undo ----------
// Undo labels come from the server ("status of ABC-001 → In progress"): the arrow is shown as "to" in the interface.
function undoText(label) { return String(label || '').replace(/\s*→\s*/g, ' to '); }
function setUndo(state) {
  undoState = state || {available: false, label: null, depth: 0};
  renderUndo();
}
function renderUndo() {
  const text = undoState.available ? `Undo: ${undoText(undoState.label)}` : 'Nothing to undo';
  ids.undoLabel.textContent = text;
  ids.undoButton.setAttribute('aria-disabled', String(undoBusy || !undoState.available));
  ids.undoButton.title = text;
  if (!undoState.available || undoBusy) ids.toastAction.hidden = true;
}
async function loadUndo() {
  try { setUndo(await request('/api/undo')); } catch { /* The menu keeps its last known state. */ }
}
async function undoLast() {
  if (undoBusy || !undoState.available) return;
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
    if (result.restored && isDocsView()) openDoc(result.action_id, {nav: 'root'}); // a deleted note is back: show it
    showToast(`Undone: ${undoText(result.undone)}`);
  } catch (error) {
    showToast(error.message);
    await refresh();
  } finally {
    undoBusy = false;
    renderUndo();
  }
}

// ---------- Refresh ----------
// A refresh redraws the active view: keep its scroll positions (rows, board, every column).
function viewScrolls() {
  return {
    today: ids.todayView.scrollTop, list: ids.listView.scrollTop, board: ids.boardView.scrollLeft,
    // Not while the next draw still has to bring today into view.
    timeline: timelineAnchor ? null : {left: ids.timelineScroll.scrollLeft, top: ids.timelineScroll.scrollTop},
    columns: [...ids.boardView.querySelectorAll('.board-cards')].map(cards => cards.scrollTop)
  };
}
function restoreViewScrolls(scrolls) {
  ids.todayView.scrollTop = scrolls.today;
  ids.listView.scrollTop = scrolls.list;
  ids.boardView.scrollLeft = scrolls.board;
  if (scrolls.timeline) { ids.timelineScroll.scrollLeft = scrolls.timeline.left; ids.timelineScroll.scrollTop = scrolls.timeline.top; }
  ids.boardView.querySelectorAll('.board-cards').forEach((cards, index) => { cards.scrollTop = scrolls.columns[index] || 0; });
}
function showError(message) {
  ids.errorBanner.textContent = message;
  ids.errorBanner.hidden = false;
}
async function refresh() {
  loadGit({quiet: view !== 'git'}); // the number next to Git follows the writes made from the page
  if (isDocsView()) refreshDocsView();
  try {
    snapshot = await request('/api/actions');
    detailCache.clear();
    loadUndo();
    ids.errorBanner.hidden = true;
    ids.lastSync.textContent = `Refreshed at ${TIME_FORMAT.format(new Date())}`;
    validateScope();
    populateProjects();
    setSummary();
    const scrolls = viewScrolls();
    render();
    restoreViewScrolls(scrolls);
    syncEditorAfterRefresh();
  } catch (error) {
    if (error.stale) return;
    showError(error.message);
  }
}
// Counters and rows follow a write made from the panel (a note), without moving the focus.
async function refreshQuietly() {
  try {
    snapshot = await request('/api/actions');
    loadGit({quiet: true});
    setSummary();
    const scrolls = viewScrolls();
    if (ACTION_VIEWS.includes(view)) { render(); restoreViewScrolls(scrolls); }
  } catch { /* The next refresh will catch up. */ }
}

// ---------- Documents: Notes and Search ----------
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
// Where the documents come from: "Inbox" or "Outside projects" of the chip, else the sidebar project (a client prefix is filtered here).
function docProjectParam() {
  if (ids.docProject.value) return ids.docProject.value;
  return snapshot.registers.some(register => register.path === projectScope) ? projectScope : '';
}
function docScopeMatch(item) {
  const place = ids.docProject.value;
  if (place === INBOX_REGISTER) return item.register === INBOX_REGISTER;
  if (place === 'none') return !item.register;
  return !projectScope || (Boolean(item.register) && item.register !== INBOX_REGISTER && inScope(item.register));
}
function docItem(item, searching) {
  const li = element('li');
  const button = element('button', 'doc-item');
  button.type = 'button';
  button.dataset.docId = item.id;
  button.setAttribute('aria-pressed', String(item.id === docSelectedId));
  const title = element('span', 'doc-item-title');
  if (searching) title.append(docMarked(item.title, docFindRanges(item.title, docTerms)));
  else title.textContent = item.title;
  const meta = element('span', 'doc-item-meta');
  meta.append(element('span', '', item.project || 'Outside projects'));
  if (item.date) meta.append(element('span', 'doc-item-date', formatDay(item.date)));
  button.append(title, meta);
  if (searching) {
    const path = element('span', 'doc-item-path');
    path.append(docMarked(docShortPath(item.id), docFindRanges(docShortPath(item.id), docTerms)));
    button.append(path);
    for (const snippet of item.snippets || []) button.append(docSnippetNode(snippet));
  } else if (item.excerpt) button.append(element('span', 'doc-item-excerpt', item.excerpt));
  button.addEventListener('click', () => openDoc(item.id, {nav: 'root', terms: searching ? docTerms : []}));
  li.append(button);
  return li;
}
function docEmpty(heading, message) {
  const box = element('div', 'empty-state');
  box.append(element('h2', '', heading), element('p', '', message));
  return box;
}
function renderDocList() {
  const focused = ids.docList.contains(document.activeElement) ? document.activeElement.dataset.docId : null;
  const filtering = Boolean(projectScope || ids.docProject.value);
  if (view === 'notes') {
    if (!notesLoaded) { ids.docList.replaceChildren(); return; }
    const items = notesData.filter(docScopeMatch);
    ids.resultCount.textContent = plural(items.length, 'note');
    if (!items.length) {
      ids.docList.replaceChildren(docEmpty('No notes here.', filtering ? 'No notes for this filter.' : 'Create a note: it is saved in the chosen project or in the Inbox.'));
      return;
    }
    const list = element('ul', 'doc-items');
    list.append(...items.map(item => docItem(item, false)));
    ids.docList.replaceChildren(list);
  } else {
    const searching = docMode === 'search';
    if (searching && docError) {
      ids.resultCount.textContent = '';
      ids.docList.replaceChildren(docEmpty('Search failed.', docError));
      return;
    }
    if (!searching && !notesLoaded) { ids.docList.replaceChildren(); return; }
    const items = (searching ? docResults : recentDocs).filter(docScopeMatch);
    ids.resultCount.textContent = searching
      ? `${plural(docTotal, 'result')}${docTotal > items.length ? `, ${items.length} shown` : ''}`
      : plural(items.length, 'recent document');
    if (!items.length) {
      ids.docList.replaceChildren(searching
        ? docEmpty('No results.', 'No document contains these terms.')
        : docEmpty('No documents here.', filtering ? 'No documents for this filter.' : 'The brain does not contain any document yet.'));
      return;
    }
    const list = element('ul', 'doc-items');
    list.append(...items.map(item => docItem(item, searching)));
    if (searching) ids.docList.replaceChildren(list);
    else ids.docList.replaceChildren(element('h2', 'doc-list-heading', 'Recently modified'), list);
  }
  if (focused) ids.docList.querySelector(`.doc-item[data-doc-id="${CSS.escape(focused)}"]`)?.focus();
}
function renderDocsView() { renderDocList(); }
function markDocSelection() {
  for (const button of ids.docList.querySelectorAll('.doc-item')) {
    button.setAttribute('aria-pressed', String(button.dataset.docId === docSelectedId));
  }
}
async function loadNotes() {
  const requestId = ++notesRequest;
  if (!notesLoaded) setDocStatus('Loading…');
  try {
    const [data, recent] = await Promise.all([request('/api/notes'), request(`/api/docs/recent?project=${encodeURIComponent(docProjectParam())}`)]);
    if (requestId !== notesRequest) return;
    notesData = data.notes;
    recentDocs = recent.docs;
    notesLoaded = true;
    if (view === 'notes' || docMode === 'recent') setDocStatus('');
    if (isDocsView()) renderDocsView();
  } catch (error) {
    if (requestId !== notesRequest || error.stale) return;
    setDocStatus(`Failed: ${error.message}`, true);
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
    docTruncated = false;
    docTerms = [];
    setDocStatus('');
    renderDocsView();
    loadNotes();
    return;
  }
  docMode = 'search';
  setDocStatus('Searching…');
  try {
    const data = await request(`/api/search?${new URLSearchParams({q: query, project: docProjectParam()})}`);
    if (requestId !== docSearchRequest) return;
    docResults = data.results;
    docTotal = data.total;
    docTruncated = data.truncated;
    docTerms = data.terms;
    setDocStatus(data.truncated ? `The ${data.results.length} best results are shown.` : '');
  } catch (error) {
    if (requestId !== docSearchRequest || error.stale) return;
    docResults = [];
    docTotal = 0;
    docTerms = [];
    docError = error.message;
    setDocStatus('');
  }
  if (isDocsView()) renderDocsView();
}
function scheduleDocSearch() {
  clearTimeout(docTimer);
  docTimer = setTimeout(runDocSearch, 200);
}
// The lists of the documents views after a filter change.
function refreshDocLists() {
  if (view === 'search' && ids.docQuery.value.trim()) runDocSearch();
  else loadNotes();
  renderDocsView();
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
  ids.docsView.classList.toggle('has-doc', Boolean(doc));
  ids.docBack.hidden = !docHistory.length;
  ids.docPaneEmpty.hidden = Boolean(doc);
  ids.docArticle.hidden = !doc || docEditing;
  ids.docEditor.hidden = !doc || !docEditing;
  ids.docEditorToolbar.hidden = ids.docEditor.hidden;
  ids.docEdit.hidden = !doc || !doc.note || docEditing;
  ids.docDelete.hidden = !doc || !doc.deletable || docEditing;
  ids.docCancel.hidden = !doc || !docEditing;
  ids.docSave.hidden = !doc || !docEditing;
  ids.docSave.disabled = docSaving;
  ids.docCancel.disabled = docSaving;
  ids.docEditor.disabled = docSaving;
  ids.docEditorToolbar.inert = docSaving;
  ids.docPaneMeta.hidden = !doc;
  ids.docPanePath.hidden = !doc;
  if (!doc) {
    ids.docPaneTitle.textContent = 'Document';
    return;
  }
  const listed = notesData.find(item => item.id === doc.id) || recentDocs.find(item => item.id === doc.id);
  ids.docPaneTitle.textContent = doc.title;
  ids.docPaneMeta.replaceChildren(element('span', '', doc.project || 'Outside projects'), ...(listed?.date ? [element('span', 'doc-item-date', formatDay(listed.date))] : []));
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
  if (nav !== 'keep' && docDirty() && !confirm('Discard the unsaved changes to this note?')) return;
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
    ids.docPaneEmpty.textContent = 'Loading the document…';
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
    if (requestId !== docRenderRequest || error.stale) return;
    if (error.status === 404) {
      docSelectedId = null;
      docCurrent = null;
      docEditing = false;
      docNote = null;
      ids.docPaneEmpty.textContent = 'This document no longer exists.';
    } else if (!quiet) {
      ids.docPaneEmpty.textContent = 'Document unavailable.';
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
    if (!error.stale) setDocError(error.status === 404 ? 'This note no longer exists.' : error.message);
  } finally {
    ids.docEdit.disabled = false;
  }
}
function cancelDocEdit() {
  if (docSaving) return;
  if (docDirty() && !confirm('Discard the unsaved changes to this note?')) return;
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
    showToast('Note saved', {undo: true});
    await Promise.all([loadNotes(), openDoc(docCurrent.id, {nav: 'keep'})]);
    if (docMode === 'search' && view === 'search') runDocSearch();
    ids.docEdit.focus();
  } catch (error) {
    setDocError(error.status === 409
      ? `${error.message} Your changes stay in the field: copy them, then cancel and reopen the note.`
      : error.message);
  } finally {
    docSaving = false;
    renderDocPane();
  }
}
// ---------- Deleting a note ----------
// Only a working note has a Delete button (the server says so: `deletable`). The dialog asks first; when other pages still link to the note it
// lists them instead (each opens in the reader) and offers no Delete, so that nothing breaks the next save. The toast offers Undo.
let noteToDelete = null; // {id, version, title} of the note the open dialog is about
function showDeleteNoteDialog(title, count, pages, error = '') {
  const linked = count > 0;
  ids.deleteNoteHeading.textContent = `Delete the note “${title}”?`;
  ids.deleteNoteText.textContent = linked
    ? `This note is linked from ${plural(count, 'page')}. Remove those links first, or ask your agent.`
    : 'The note is removed from this brain. You can undo it right after.';
  ids.deleteNoteLinks.hidden = !linked;
  ids.deleteNoteLinks.replaceChildren(...pages.map(page => {
    const item = element('li');
    const open = element('button', 'link-button', page.title);
    open.type = 'button';
    open.title = `Open ${page.id}`;
    open.addEventListener('click', () => openLinkingPage(page.id));
    item.append(open, element('span', 'delete-note-path', page.id));
    return item;
  }));
  if (count > pages.length) ids.deleteNoteLinks.append(element('li', 'delete-note-more', `and ${plural(count - pages.length, 'more page')}`));
  ids.deleteNoteError.textContent = error;
  ids.deleteNoteError.hidden = !error;
  ids.deleteNoteConfirm.hidden = linked;
  ids.deleteNoteConfirm.disabled = false;
  ids.deleteNoteCancel.textContent = linked ? 'Close' : 'Cancel';
}
function openLinkingPage(id) {
  ids.deleteNoteDialog.close();
  if (view !== 'notes' && view !== 'search') setView('notes');
  openDoc(id, {nav: 'root'});
}
async function askDeleteNote() {
  const doc = docCurrent;
  if (!doc || !doc.deletable || docEditing || docSaving || ids.docDelete.getAttribute('aria-busy') === 'true') return;
  ids.docDelete.setAttribute('aria-busy', 'true'); // not `disabled`: a disabled button would lose the focus the dialog gives back to it
  setDocError('');
  try {
    const info = await request(`/api/notes/backlinks?id=${encodeURIComponent(doc.id)}`);
    if (!docCurrent || docCurrent.id !== doc.id) return;
    noteToDelete = {id: doc.id, version: doc.version, title: info.title};
    showDeleteNoteDialog(info.title, info.count, info.pages);
    ids.deleteNoteDialog.showModal();
  } catch (error) {
    if (!error.stale) setDocError(error.status === 404 ? 'This note no longer exists.' : error.message);
  } finally {
    ids.docDelete.removeAttribute('aria-busy');
  }
}
// The pane after the note is gone: nothing selected, the lists read again (and with them the number next to Sync).
function clearDocPane() {
  docRenderRequest += 1;
  docSelectedId = null;
  docCurrent = null;
  docHistory = [];
  docEditing = false;
  docNote = null;
  ids.docPaneEmpty.textContent = 'Choose a document to read it.';
  setDocError('');
  renderDocPane();
  markDocSelection();
}
async function confirmDeleteNote() {
  const target = noteToDelete;
  if (!target) return;
  ids.deleteNoteConfirm.disabled = true;
  ids.deleteNoteError.hidden = true;
  try {
    const result = await request('/api/notes', {
      method: 'DELETE', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: JSON.stringify({id: target.id, version: target.version})
    });
    noteToDelete = null;
    setUndo(result.undo);
    ids.deleteNoteDialog.close();
    clearDocPane();
    showToast('Note deleted', {undo: true});
    await refresh();
    await loadNotes(); // the list as it is drawn last: the focus goes to its first note (or, with none left, to New note)
    (ids.docList.querySelector('.doc-item') || ids.newNoteButton).focus();
  } catch (error) {
    const data = error.data || {};
    if (error.status === 409 && Array.isArray(data.backlinks)) showDeleteNoteDialog(target.title, data.count, data.backlinks);
    else if (error.status === 409 || error.status === 404) {
      // The note is not what the person saw (or is gone): say so in the pane, which shows it as it is now.
      ids.deleteNoteDialog.close();
      await openDoc(target.id, {nav: 'keep'});
      setDocError(error.message);
    } else showDeleteNoteDialog(target.title, 0, [], error.message);
  }
}
ids.docDelete.addEventListener('click', askDeleteNote);
ids.deleteNoteConfirm.addEventListener('click', confirmDeleteNote);
ids.deleteNoteDialog.addEventListener('close', () => { noteToDelete = null; });

function refreshDocsView() {
  loadNotes();
  if (view === 'search' && (ids.docQuery.value.trim() || docMode === 'search')) runDocSearch();
  else {
    if (view === 'search') { docMode = 'recent'; docError = ''; }
    renderDocsView();
  }
  if (docSelectedId && !docEditing && !docSaving) openDoc(docSelectedId, {nav: 'keep'});
}
function newNoteFolder() {
  const register = ids.newNoteProject.value;
  if (register === INBOX_REGISTER) return 'inbox/';
  return register ? register.replace(/state\/actions\.md$/, 'notes/') : '';
}
function updateNewNoteWhere() {
  ids.newNoteWhere.textContent = `File created: ${newNoteFolder()}YYYY-MM-DD-title.md`;
}
function openNewNote() {
  closePopover(false);
  ids.newNoteProject.replaceChildren(new Option('Inbox (to triage)', INBOX_REGISTER), ...snapshot.registers.map(register => new Option(register.label, register.path)));
  const paths = [...ids.newNoteProject.options].map(option => option.value);
  const preferred = ids.docProject.value === INBOX_REGISTER ? INBOX_REGISTER : projectScope;
  ids.newNoteProject.value = paths.includes(preferred) ? preferred : INBOX_REGISTER;
  ids.newNoteTitle.value = '';
  ids.newNoteContent.value = '';
  newNoteBar.closeMenu(false);
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
    if (docDirty() && !confirm('Discard the unsaved changes to the open document?')) {
      if (isDocsView()) await loadNotes();
      showToast('Note created', {undo: true});
      return;
    }
    docEditing = false;
    docNote = null;
    docSelectedId = null;
    docCurrent = null;
    if (!docScopeMatch({register: ids.newNoteProject.value})) {
      projectScope = '';
      ids.docProject.value = '';
      renderProjectNav();
    }
    setView('notes');
    showToast('Note created', {undo: true});
    await openDoc(result.id, {nav: 'root'});
  } catch (error) {
    ids.newNoteError.textContent = error.message;
    ids.newNoteError.hidden = false;
  } finally {
    ids.saveNewNote.disabled = false;
  }
}

// ---------- Toast ----------
function hideToast() { ids.toast.hidden = true; }
function showToast(message, {undo = false} = {}) {
  ids.toastText.textContent = message;
  ids.toastAction.hidden = !undo || !undoState.available;
  ids.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, undo ? 6000 : 3500);
}
ids.toast.addEventListener('mouseenter', () => clearTimeout(toastTimer));
ids.toast.addEventListener('focusin', () => clearTimeout(toastTimer));
ids.toast.addEventListener('mouseleave', () => { clearTimeout(toastTimer); toastTimer = setTimeout(hideToast, 2500); });
ids.toastAction.addEventListener('click', () => { ids.toastAction.hidden = true; hideToast(); undoLast(); });

// ---------- Sidebar, drawer and the "More options" menu ----------
const SIDEBAR_KEY = 'actions-brain-sidebar-v1';
const narrowQuery = window.matchMedia('(max-width: 900px)');
function readSidebarCollapsed() {
  try { return localStorage.getItem(SIDEBAR_KEY) === 'collapsed'; } catch { return false; }
}
function updateSidebarToggle() {
  const narrow = narrowQuery.matches;
  const open = narrow ? ids.app.classList.contains('drawer-open') : !ids.app.classList.contains('sidebar-collapsed');
  ids.sidebarToggle.setAttribute('aria-expanded', String(open));
  const label = narrow ? (open ? 'Close menu' : 'Open menu') : open ? 'Hide the sidebar' : 'Show the sidebar';
  ids.sidebarToggle.setAttribute('aria-label', label);
  ids.sidebarToggle.title = `${label} ([)`;
  ids.mainContent.inert = narrow && open;
}
function openDrawer() {
  ids.app.classList.add('drawer-open');
  ids.scrim.hidden = false;
  updateSidebarToggle();
  (ids.sidebar.querySelector('.nav-item[aria-current="page"]') || ids.todayButton).focus();
}
function closeDrawer(refocus = true) {
  if (!ids.app.classList.contains('drawer-open')) return;
  ids.app.classList.remove('drawer-open');
  ids.scrim.hidden = true;
  updateSidebarToggle();
  if (refocus) ids.sidebarToggle.focus();
}
function toggleSidebar() {
  if (narrowQuery.matches) {
    if (ids.app.classList.contains('drawer-open')) closeDrawer(); else openDrawer();
    return;
  }
  const collapsed = ids.app.classList.toggle('sidebar-collapsed');
  try { localStorage.setItem(SIDEBAR_KEY, collapsed ? 'collapsed' : 'open'); } catch { /* Not remembered. */ }
  updateSidebarToggle();
}
narrowQuery.addEventListener('change', () => { closeDrawer(false); updateSidebarToggle(); });
function moreItems() { return [...ids.moreMenu.querySelectorAll('.menu-item')]; }
function openMoreMenu() {
  closePopover(false);
  ids.moreMenu.hidden = false;
  ids.moreButton.setAttribute('aria-expanded', 'true');
  moreItems()[0].focus();
}
function closeMoreMenu(refocus = true) {
  if (ids.moreMenu.hidden) return;
  ids.moreMenu.hidden = true;
  ids.moreButton.setAttribute('aria-expanded', 'false');
  if (refocus) ids.moreButton.focus();
}
ids.moreButton.addEventListener('click', () => { if (ids.moreMenu.hidden) openMoreMenu(); else closeMoreMenu(); });
ids.moreMenu.addEventListener('keydown', event => {
  const items = moreItems();
  const index = items.indexOf(document.activeElement);
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
  } else if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault();
    items[event.key === 'Home' ? 0 : items.length - 1].focus();
  } else if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    closeMoreMenu();
  } else if (event.key === 'Tab') closeMoreMenu(false);
});
ids.refreshButton.addEventListener('click', async () => {
  closeMoreMenu();
  if (!await loadBrains()) refresh();
});
ids.undoButton.addEventListener('click', () => {
  if (ids.undoButton.getAttribute('aria-disabled') === 'true') return;
  closeMoreMenu();
  undoLast();
});
ids.shortcutsButton.addEventListener('click', () => { closeMoreMenu(false); ids.shortcutsDialog.showModal(); });
ids.quitButton.addEventListener('click', () => { closeMoreMenu(false); ids.quitDialog.showModal(); });
ids.quitConfirm.addEventListener('click', async () => {
  ids.quitConfirm.disabled = true;
  try {
    await request('/api/shutdown', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},
      body: '{}'
    });
    ids.quitDialog.close();
    document.body.replaceChildren(element('main', 'stopped-screen', 'Actions Brain has stopped. You can close this tab. Relaunch the app from the Dock to open it again.'));
    window.close();
  } catch (error) {
    ids.quitConfirm.disabled = false;
    ids.quitDialog.close();
    showToast(`Could not stop: ${error.message}`);
  }
});

// ---------- Keyboard ----------
function isTyping(target) {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
}
function focusSearch() {
  if (view === 'notes' || view === 'git') setView('search');
  const input = view === 'search' ? ids.docQuery : view === 'tools' ? ids.toolSearch : ids.searchInput;
  input.focus();
  input.select();
}
function handleEscape(event) {
  if (document.querySelector('dialog[open]')) return;
  if (dismissInfoTip()) { event.preventDefault(); return; }
  if (popoverState) { event.preventDefault(); closePopover(); return; }
  if (!ids.moreMenu.hidden) { event.preventDefault(); closeMoreMenu(); return; }
  if (ids.app.classList.contains('drawer-open')) { event.preventDefault(); closeDrawer(); return; }
  if (editorOpen() && (ids.editor.contains(document.activeElement) || !isTyping(document.activeElement))) {
    if (!ids.noteForm.hidden && ids.noteForm.contains(document.activeElement)) { event.preventDefault(); closeNoteForm(); return; }
    event.preventDefault();
    closeEditor();
  }
}
document.addEventListener('keydown', event => {
  if (event.defaultPrevented || event.isComposing) return;
  const key = event.key;
  const typing = isTyping(event.target);
  if ((event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey && key.toLowerCase() === 'z') {
    if (typing || document.querySelector('dialog[open]')) return;
    event.preventDefault();
    undoLast();
    return;
  }
  if ((event.metaKey || event.ctrlKey) && key === 'Enter' && editorOpen() && ids.editor.contains(event.target) && !ids.noteForm.contains(event.target)) {
    event.preventDefault();
    ids.editorForm.requestSubmit();
    return;
  }
  if (key === 'Escape') { handleEscape(event); return; }
  if (event.metaKey || event.ctrlKey || typing) return;
  if (document.querySelector('dialog[open]') || popoverState || brainMenuOpen() || !ids.moreMenu.hidden) return;
  const digit = /^[1-6]$/.test(key) ? key : /^Digit[1-6]$/.test(event.code) && !event.altKey ? event.code.slice(5) : null;
  const inRows = ACTION_VIEWS.includes(view);
  const onBody = event.target === document.body || event.target === ids.mainContent || event.target === ids.editorTitle;
  if (key === '/') { event.preventDefault(); focusSearch(); }
  else if (key === '?') { event.preventDefault(); ids.shortcutsDialog.showModal(); }
  else if (key === '[') { event.preventDefault(); toggleSidebar(); }
  else if (digit && !event.altKey) { event.preventDefault(); setView(['today', 'list', 'board', 'timeline', 'notes', 'search'][Number(digit) - 1]); }
  else if (key === 'n' && !event.altKey) { event.preventDefault(); openEditor(); }
  else if (inRows && (key === 'j' || key === 'ArrowDown') && !event.altKey) {
    if (key === 'ArrowDown' && !onBody && !activeRoot().contains(event.target)) return;
    event.preventDefault();
    moveSelection(1);
  } else if (inRows && (key === 'k' || key === 'ArrowUp') && !event.altKey) {
    if (key === 'ArrowUp' && !onBody && !activeRoot().contains(event.target)) return;
    event.preventDefault();
    moveSelection(-1);
  } else if (inRows && key === 'Enter' && onBody && event.target !== ids.editorTitle) {
    const action = selectedAction();
    if (action) { event.preventDefault(); openEditor(action); }
  } else if (inRows && (key === 's' || key === 'd') && !event.altKey) {
    const action = selectedAction();
    const row = action && rowFor(action.id);
    if (!row) return;
    event.preventDefault();
    // A timeline chip has no status or date button of its own: the menus open from the chip.
    const main = row.querySelector(ROW_MAIN) || row;
    if (key === 's') openStatusMenu(action, row.querySelector('.status-button') || main);
    else openDueMenu(action, row.querySelector('.due-button') || row.querySelector('.status-button') || main);
  }
});

// ---------- Markdown toolbar (new note dialog and note editor share it) ----------
// The text edits live in md-edit.js; this is the buttons, the arrow menu and the keyboard.
const MAC_KEYS = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgentData?.platform || navigator.platform || '');
const MD_TOOLS = [
  [
    {id: 'bold', label: 'Bold', icon: ICONS.bold, key: 'b'},
    {id: 'italic', label: 'Italic', icon: ICONS.italic, key: 'i'},
    {id: 'underline', label: 'Underline', icon: ICONS.underline, key: 'u'},
    {id: 'strike', label: 'Strikethrough', icon: ICONS.strike, key: 'x', shift: true}
  ],
  [
    {id: 'bullets', label: 'Bulleted list', icon: ICONS.bullets},
    {id: 'numbers', label: 'Numbered list', icon: ICONS.numbers},
    {id: 'tasks', label: 'Checklist', icon: ICONS.tasks},
    {id: 'quote', label: 'Quote', icon: ICONS.quote}
  ],
  [
    {id: 'code', label: 'Inline code', icon: ICONS.code},
    {id: 'link', label: 'Link', icon: ICONS.link, key: 'k'},
    {id: 'arrow', label: 'Arrow', icon: ICONS.arrow, title: 'Arrow (hold for more)'}
  ]
];
const MD_ARROWS = [['→', 'Right arrow'], ['←', 'Left arrow'], ['⇒', 'Double arrow'], ['↔', 'Both directions']];
// The shortcut is ⌘ on a Mac (Ctrl+B, F, K... are text-editing keys there) and Ctrl elsewhere.
function mdKeys(tool) {
  const letter = tool.key.toUpperCase();
  return MAC_KEYS
    ? {label: `${tool.shift ? '⇧' : ''}⌘${letter}`, aria: `Meta+${tool.shift ? 'Shift+' : ''}${letter}`}
    : {label: `Ctrl+${tool.shift ? 'Shift+' : ''}${letter}`, aria: `Control+${tool.shift ? 'Shift+' : ''}${letter}`};
}
function mountMarkdownToolbar(bar, area) {
  const buttons = [];
  for (const group of MD_TOOLS) {
    const box = element('div', 'md-group');
    for (const tool of group) {
      const keys = tool.key ? mdKeys(tool) : null;
      const button = iconButton('icon-button md-tool', tool.label, tool.icon, keys ? `${tool.label} (${keys.label})` : tool.title || tool.label);
      button.dataset.tool = tool.id;
      button.tabIndex = buttons.length ? -1 : 0; // roving tabindex: one stop in the Tab order
      if (keys) button.setAttribute('aria-keyshortcuts', keys.aria);
      buttons.push(button);
      box.append(button);
    }
    bar.append(box);
  }
  const arrowButton = buttons.find(button => button.dataset.tool === 'arrow');
  arrowButton.setAttribute('aria-haspopup', 'menu');
  arrowButton.setAttribute('aria-expanded', 'false');
  const menu = element('div', 'menu md-menu');
  menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-label', 'Arrows');
  menu.hidden = true;
  for (const [symbol, name] of MD_ARROWS) {
    const item = element('button', 'menu-item');
    item.type = 'button';
    item.setAttribute('role', 'menuitem');
    const glyph = element('span', 'md-glyph', symbol);
    glyph.setAttribute('aria-hidden', 'true');
    item.append(glyph, element('span', 'menu-item-text', name));
    item.addEventListener('click', () => { closeMenu(false); run('arrow', symbol); });
    menu.append(item);
  }
  bar.append(menu);

  // One edit, applied the way typing is, so the browser's undo and redo keep working; setRangeText is the fallback.
  function run(id, argument) {
    if (area.disabled || area.readOnly) return;
    const value = area.value;
    const change = MarkdownEdit.edit(id, value, area.selectionStart, area.selectionEnd, argument);
    if (!change.text && change.from === change.to) return;
    const expected = value.slice(0, change.from) + change.text + value.slice(change.to);
    area.focus();
    area.setSelectionRange(change.from, change.to);
    try { if (change.text) document.execCommand('insertText', false, change.text); else document.execCommand('delete'); } catch { /* handled below */ }
    if (area.value !== expected) {
      if (area.value !== value) area.value = value;
      area.setRangeText(change.text, change.from, change.to, 'end');
      area.dispatchEvent(new Event('input', {bubbles: true}));
    }
    area.setSelectionRange(change.select[0], change.select[1]);
  }
  let held = false;
  function openMenu() {
    menu.hidden = false;
    arrowButton.setAttribute('aria-expanded', 'true');
    menu.style.left = `${Math.max(0, Math.min(arrowButton.offsetLeft, bar.clientWidth - menu.offsetWidth))}px`;
    menu.style.top = `${arrowButton.offsetTop + arrowButton.offsetHeight + 2}px`;
    menu.firstElementChild.focus();
  }
  function closeMenu(refocus = true) {
    held = false;
    if (menu.hidden) return;
    menu.hidden = true;
    arrowButton.setAttribute('aria-expanded', 'false');
    if (refocus) arrowButton.focus();
  }

  // Keep the field focused (and its selection) while a button is pressed with the mouse.
  bar.addEventListener('mousedown', event => { if (event.target.closest('.md-tool, .menu-item')) event.preventDefault(); });
  bar.addEventListener('click', event => {
    const button = event.target.closest('.md-tool');
    if (!button) return;
    if (held) { held = false; return; } // the press that opened the menu is not a click on the arrow
    run(button.dataset.tool);
  });
  // A long press on the arrow opens the menu of the other arrows (the contextual menu key does too).
  let pressTimer = 0;
  arrowButton.addEventListener('pointerdown', event => {
    held = false;
    if (event.button === 0) pressTimer = setTimeout(() => { held = true; openMenu(); }, 450);
  });
  for (const type of ['pointerup', 'pointerleave', 'pointercancel']) arrowButton.addEventListener(type, () => clearTimeout(pressTimer));
  arrowButton.addEventListener('contextmenu', event => { event.preventDefault(); openMenu(); });
  bar.addEventListener('focusin', event => {
    const index = buttons.indexOf(event.target);
    if (index >= 0) buttons.forEach((button, position) => { button.tabIndex = position === index ? 0 : -1; });
  });
  bar.addEventListener('focusout', event => { if (!bar.contains(event.relatedTarget)) closeMenu(false); });
  bar.addEventListener('keydown', event => {
    if (menu.contains(event.target) || event.altKey || event.ctrlKey || event.metaKey) return;
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    const last = buttons.length - 1;
    if (event.key === 'ArrowRight') buttons[index === last ? 0 : index + 1].focus();
    else if (event.key === 'ArrowLeft') buttons[index === 0 ? last : index - 1].focus();
    else if (event.key === 'Home') buttons[0].focus();
    else if (event.key === 'End') buttons[last].focus();
    else if (event.key === 'ArrowDown' && event.target === arrowButton) openMenu();
    else return;
    event.preventDefault();
  });
  menu.addEventListener('keydown', event => {
    const items = [...menu.children];
    const index = items.indexOf(document.activeElement);
    if (event.key === 'ArrowDown') items[(index + 1) % items.length].focus();
    else if (event.key === 'ArrowUp') items[(index + items.length - 1) % items.length].focus();
    else if (event.key === 'Home') items[0].focus();
    else if (event.key === 'End') items[items.length - 1].focus();
    else if (event.key === 'Escape') { event.stopPropagation(); closeMenu(); } // closes the menu, not the dialog
    else if (event.key === 'Tab') { closeMenu(false); return; }
    else return;
    event.preventDefault();
  });
  document.addEventListener('pointerdown', event => { if (!menu.hidden && !menu.contains(event.target) && !arrowButton.contains(event.target)) closeMenu(false); });

  area.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.isComposing || event.altKey) return;
    if (MAC_KEYS ? !event.metaKey || event.ctrlKey : !event.ctrlKey || event.metaKey) return;
    const key = /^[a-z]$/i.test(event.key) ? event.key.toLowerCase() : /^Key[A-Z]$/.test(event.code) ? event.code.slice(3).toLowerCase() : '';
    const tool = MD_TOOLS.flat().find(item => item.key === key && Boolean(item.shift) === event.shiftKey);
    if (!tool) return;
    event.preventDefault();
    run(tool.id);
  });
  return {closeMenu};
}

// ---------- Wiring ----------
const newNoteBar = mountMarkdownToolbar(ids.newNoteToolbar, ids.newNoteContent);
mountMarkdownToolbar(ids.docEditorToolbar, ids.docEditor);
for (const [name, id] of Object.entries(NAV_BUTTONS)) ids[id].addEventListener('click', () => setView(name));
ids.newButton.addEventListener('click', () => openEditor());
ids.newNoteButton.addEventListener('click', openNewNote);
ids.sidebarToggle.addEventListener('click', toggleSidebar);
ids.sidebarClose.addEventListener('click', () => closeDrawer());
ids.scrim.addEventListener('click', () => closeDrawer());
ids.projectChipClear.addEventListener('click', () => { setProjectScope(''); ids.searchInput.focus(); });
ids.docQuery.addEventListener('input', () => { scheduleDocSearch(); saveUIState(); });
ids.docQuery.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); runDocSearch(); }
});
ids.docProject.addEventListener('change', () => {
  if (ids.docProject.value && projectScope) { projectScope = ''; populateGroupFilter(); renderProjectNav(); }
  refreshDocLists();
  renderFilterChips();
  saveUIState();
});
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
ids.groupFilter.addEventListener('change', titleGroupFilter);
for (const node of [ids.searchInput, ids.groupFilter, ids.ownerFilter, ids.scopeFilter]) {
  node.addEventListener(node === ids.searchInput ? 'input' : 'change', () => { render(); saveUIState(); });
}
ids.resetFilters.addEventListener('click', () => {
  projectScope = '';
  if (isDocsView()) {
    ids.docProject.value = '';
    refreshDocLists();
  } else {
    ids.searchInput.value = '';
    ids.groupFilter.value = '';
    ids.ownerFilter.value = '';
    ids.scopeFilter.value = 'active';
  }
  populateGroupFilter();
  renderProjectNav();
  render();
  saveUIState();
  (isDocsView() ? ids.docProject : ids.searchInput).focus();
});
ids.foldAllButton.addEventListener('click', setAllFolds);
ids.toolSearch.addEventListener('input', () => { filterTools(); saveUIState(); });
ids.brainButton.addEventListener('click', () => { if (brainMenuOpen()) closeBrainMenu(); else openBrainMenu(); });
ids.brainButton.addEventListener('keydown', event => {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); openBrainMenu(); }
});
ids.brainMenu.addEventListener('keydown', event => {
  const key = event.key;
  if (key === 'ArrowDown') setBrainActive(brainMenuIndex + 1);
  else if (key === 'ArrowUp') setBrainActive(brainMenuIndex - 1);
  else if (key === 'Home') setBrainActive(0);
  else if (key === 'End') setBrainActive(brains.length - 1);
  else if (key === 'Enter' || key === ' ') chooseBrain(ids.brainMenu.children[brainMenuIndex]?.dataset.brain);
  else if (key === 'Escape') { event.stopPropagation(); closeBrainMenu(); }
  else if (key === 'Tab') closeBrainMenu(false);
  else if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    // Type-ahead: the next brain whose name starts with the typed letter.
    const letter = key.toLocaleLowerCase(LOCALE);
    const ordered = [...brains.keys()].map(offset => (brainMenuIndex + 1 + offset) % brains.length);
    const next = ordered.find(position => (brains[position].label || brains[position].name).toLocaleLowerCase(LOCALE).startsWith(letter));
    if (next !== undefined) setBrainActive(next);
    return;
  } else return;
  event.preventDefault();
});
ids.brainMenu.addEventListener('focusout', event => {
  if (!ids.brainSwitch.contains(event.relatedTarget)) closeBrainMenu(false);
});
ids.editorTitle.tabIndex = -1;
ids.closeEditor.addEventListener('click', () => closeEditor());
ids.cancelEditor.addEventListener('click', () => closeEditor());
ids.editorForm.addEventListener('submit', saveEditor);
ids.editorForm.addEventListener('input', updateEditorButtons);
ids.editorForm.addEventListener('change', updateEditorButtons);
ids.deleteEditor.addEventListener('click', deleteEditor);
ids.editorActionTitle.addEventListener('input', sizeTitleField);
ids.editorActionTitle.addEventListener('keydown', event => {
  // The title is one line in the register: Enter saves (Shift+Enter is ignored as well).
  if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); if (!event.shiftKey) ids.editorForm.requestSubmit(); }
});
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

// Timeline controls
for (const button of ids.timelineView.querySelectorAll('[data-range]')) {
  button.addEventListener('click', () => {
    if (timelineRange === button.dataset.range) return;
    timelineRange = button.dataset.range;
    timelineAnchor = true;
    saveUIState();
    render();
  });
}
ids.timelineToday.addEventListener('click', () => scrollTimelineToToday(true));
ids.timelineBack.addEventListener('click', () => scrollTimelineByWeeks(-1));
ids.timelineForward.addEventListener('click', () => scrollTimelineByWeeks(1));
ids.timelineLate.addEventListener('click', focusFirstOverdue);
ids.timelineDone.addEventListener('click', () => { timelineDone = !timelineDone; saveUIState(); render(); });
ids.timelineSummary.addEventListener('click', event => {
  const stat = event.target.closest('.tl-stat');
  if (!stat) return;
  if (stat.dataset.stat === 'none' || stat.dataset.stat === 'vague') {
    showTray();
    ids.timelineTrayList.querySelector(`#tl-tray-${stat.dataset.stat}`)?.scrollIntoView({block: 'nearest'});
  } else if (!stat.classList.contains('is-zero')) setTimelineSpot(stat.dataset.stat);
});
ids.timelineTrayToggle.addEventListener('click', () => setTrayOpen(!timelineTrayOpen));
ids.timelineTraySearch.addEventListener('input', () => renderTray(timelineBase));
ids.timelineTraySearch.addEventListener('keydown', event => {
  const first = event.key === 'ArrowDown' ? ids.timelineTrayList.querySelector('.tl-card') : null;
  if (!first) return;
  event.preventDefault();
  selectAndFollow(first.dataset.id);
});
ids.timelineScroll.addEventListener('keydown', timelineKey);
// Focusing a chip or a card selects it, so the quick edits (`s`, `d`) apply to the one you are on.
ids.timelineView.addEventListener('focusin', event => {
  const cell = event.target instanceof Element ? event.target.closest('.tl-chip, .tl-card-main')?.closest('[data-id]') : null;
  if (!cell || cell.dataset.id === selectedId) return;
  selectedId = cell.dataset.id;
  markSelection();
});
ids.timelineTray.addEventListener('keydown', trayKey);
// A plain wheel scrolls the frieze sideways when sideways is the only way it can scroll (Shift+wheel and a trackpad already do).
ids.timelineScroll.addEventListener('wheel', event => {
  const scroll = ids.timelineScroll;
  if (event.ctrlKey || event.deltaX !== 0 || event.deltaY === 0 || scroll.scrollWidth <= scroll.clientWidth + 1 || scroll.scrollHeight > scroll.clientHeight + 1) return;
  scroll.scrollLeft += event.deltaY;
  event.preventDefault();
}, {passive: false});
// Planning by dragging: a day takes a chip or a tray card; the tray takes a chip back (no deadline). The write is the one of the panel.
ids.timelineScroll.addEventListener('dragover', event => {
  if (!timelineDrag) return;
  const target = timelineDayAt(event);
  showTimelineDrop(target);
  if (!target) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
});
ids.timelineScroll.addEventListener('dragleave', event => { if (!ids.timelineScroll.contains(event.relatedTarget)) showTimelineDrop(null); });
ids.timelineScroll.addEventListener('drop', event => {
  if (!timelineDrag) return;
  const target = timelineDayAt(event);
  const action = findAction(timelineDrag.id);
  endTimelineDrag();
  if (!target) return;
  event.preventDefault();
  if (action && !closed(action) && action.due !== target.day.iso) updateDue(action, target.day.iso);
});
ids.timelineTray.addEventListener('dragover', event => {
  if (timelineDrag?.kind !== 'chip') return;
  event.preventDefault();
  ids.timelineTray.classList.add('is-drop');
});
ids.timelineTray.addEventListener('dragleave', event => { if (!ids.timelineTray.contains(event.relatedTarget)) ids.timelineTray.classList.remove('is-drop'); });
ids.timelineTray.addEventListener('drop', event => {
  if (timelineDrag?.kind !== 'chip') return;
  event.preventDefault();
  const action = findAction(timelineDrag.id);
  endTimelineDrag();
  if (action && !closed(action) && action.due) updateDue(action, '');
});
document.addEventListener('dragend', endTimelineDrag);
// An empty day of a project: a click starts a new action due that day, in that project.
function clearGhost() { ids.timelineScroll.querySelector('.tl-ghost')?.remove(); }
ids.timelineScroll.addEventListener('pointermove', event => {
  const body = event.target instanceof Element && event.target.classList.contains('tl-days') ? event.target : null;
  const target = body && !timelineDrag ? timelineDayAt(event) : null;
  if (!target) { clearGhost(); return; }
  let ghost = ids.timelineScroll.querySelector('.tl-ghost');
  if (!ghost) {
    ghost = element('div', 'tl-ghost');
    ghost.setAttribute('aria-hidden', 'true');
    ghost.append(svgIcon(ICONS.plus));
  }
  const sc = timelineModel.sc;
  ghost.style.left = `${sc.xs[target.index]}px`;
  ghost.style.width = `${sc.xs[target.index + 1] - sc.xs[target.index]}px`;
  body.title = `New action due ${dayText(target.day.iso, DAY_FORMAT)}`;
  body.append(ghost);
});
ids.timelineScroll.addEventListener('pointerleave', clearGhost);
ids.timelineScroll.addEventListener('click', event => {
  if (!(event.target instanceof Element) || !event.target.classList.contains('tl-days')) return;
  const target = timelineDayAt(event);
  if (target) openEditor(null, {register: event.target.closest('.tl-lane').dataset.register, due: target.day.iso});
});
// The axis follows the width of the page: drawn again when it changes (and between the frieze and the agenda under 700 px).
let timelineFrame = 0;
new ResizeObserver(() => {
  if (view !== 'timeline' || timelineFrame) return;
  const width = Math.floor(ids.timelineScroll.clientWidth);
  const narrow = ids.mainContent.getBoundingClientRect().width < TL.agenda;
  if (width === 0 || (Math.abs(width - timelineWidth) <= 1 && narrow === timelineNarrow)) return;
  timelineFrame = requestAnimationFrame(() => {
    timelineFrame = 0;
    if (narrow !== timelineNarrow) timelineAnchor = true;
    render();
  });
}).observe(ids.timelineScroll);

// ---------- Start ----------
applyAccent(brainFromUrl() || readStoredBrain());
if (!narrowQuery.matches && readSidebarCollapsed()) ids.app.classList.add('sidebar-collapsed');
updateSidebarToggle();
ids.searchInput.value = typeof savedUI.search === 'string' ? savedUI.search : '';
ids.ownerFilter.value = savedUI.owner === 'mine' ? 'mine' : '';
ids.scopeFilter.value = ['active', 'all', 'closed'].includes(savedUI.scope) ? savedUI.scope : 'active';
ids.toolSearch.value = typeof savedUI.toolSearch === 'string' ? savedUI.toolSearch : '';
ids.docQuery.value = typeof savedUI.docQuery === 'string' ? savedUI.docQuery : '';
ids.docProject.value = ['', INBOX_REGISTER, 'none'].includes(savedUI.docProject) ? savedUI.docProject : '';
// The brain is known before anything is requested, so that no view starts on the wrong one.
loadBrains({initial: true}).finally(() => {
  setView(view, false);
  refresh();
});
