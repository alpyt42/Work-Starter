'use strict';

// Logic of the Timeline view, apart from drawing it: the visible range, ISO weeks and weekends, the fit-to-width scale (and the day under
// a pointer), where each action lands, which ones are overdue, vague or undated, the lanes and their stacking, the summary counts, the
// "no deadline" tray and the keyboard neighbours of a chip. Days are ISO strings (YYYY-MM-DD) and all arithmetic is done in UTC, so a
// daylight-saving change never moves a day. No DOM and no clock ("today" always comes from the caller): the page draws the result, and
// the tests run this same file under node.
const TimelineView = (() => {
  const DAY = 86400000;
  const PLAIN = /^(\d{4})-(\d{2})-(\d{2})$/;
  const RANGE_WEEKS = {two: 2, six: 6, quarter: 13};
  // The narrowest a weekday gets (px) before the frieze scrolls sideways instead of shrinking, per range; a weekend day is END_RATIO of it.
  const MIN_DAY = {two: 30, six: 12, quarter: 6};
  const END_RATIO = 0.75;
  const STATE_RANK = {'/': 0, ' ': 1, w: 2};
  const PRIORITY_RANK = {'⏫': 0, '🔼': 1, '': 2, '🔽': 3};

  // UTC midnight of a real calendar date, NaN for anything else ("2026-02-30", "week of 05/10").
  function ms(day) {
    const match = typeof day === 'string' ? PLAIN.exec(day) : null;
    if (!match) return NaN;
    const [year, month, date] = [Number(match[1]), Number(match[2]), Number(match[3])];
    const time = Date.UTC(year, month - 1, date);
    const check = new Date(time);
    return check.getUTCFullYear() === year && check.getUTCMonth() === month - 1 && check.getUTCDate() === date ? time : NaN;
  }
  function iso(time) {
    const date = new Date(time);
    const pad = (number, size = 2) => String(number).padStart(size, '0');
    return `${pad(date.getUTCFullYear(), 4)}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
  }
  function isPlainDate(text) { return !Number.isNaN(ms(text)); }
  function addDays(day, count) { return iso(ms(day) + count * DAY); }
  function diffDays(from, to) { return Math.round((ms(to) - ms(from)) / DAY); }
  function weekday(day) { return (new Date(ms(day)).getUTCDay() + 6) % 7; } // 0 = Monday … 6 = Sunday
  function isWeekend(day) { return weekday(day) >= 5; }
  function mondayOf(day) { return addDays(day, -weekday(day)); }
  // ISO 8601: the week belongs to the year of its Thursday, and week 1 is the one that holds January 4th.
  function isoWeek(day) {
    const thursday = addDays(day, 3 - weekday(day));
    const year = Number(thursday.slice(0, 4));
    return {year, week: Math.floor(diffDays(`${year}-01-01`, thursday) / 7) + 1};
  }
  // The new due date when a deadline moves by `delta` days; null when the action has no plain date to move.
  function moveDue(due, delta) { return isPlainDate(due) ? addDays(due, delta) : null; }

  // Runs of consecutive days that share a key, as {…label, start, span}.
  function runs(days, keyOf, labelOf) {
    const found = [];
    for (const day of days) {
      const key = keyOf(day);
      const last = found.at(-1);
      if (last && last.key === key) last.span += 1;
      else found.push({key, ...labelOf(day), start: day.index, span: 1});
    }
    return found.map(({key, ...rest}) => rest);
  }

  // Monday of last week, over 2 weeks, 6 weeks (default) or 13 weeks (a quarter), so a range is always whole weeks.
  function range(today, key = 'six') {
    const weeks = RANGE_WEEKS[key] || RANGE_WEEKS.six;
    const start = mondayOf(addDays(today, -7));
    const days = [];
    for (let index = 0; index < weeks * 7; index += 1) {
      const day = addDays(start, index);
      const {year: weekYear, week} = isoWeek(day);
      days.push({
        iso: day, index, weekday: index % 7, weekend: index % 7 >= 5, today: day === today,
        year: Number(day.slice(0, 4)), month: Number(day.slice(5, 7)), day: Number(day.slice(8, 10)), week, weekYear
      });
    }
    return {
      key: RANGE_WEEKS[key] ? key : 'six', weeks, start, end: days.at(-1).iso, days,
      months: runs(days, day => `${day.year}-${day.month}`, day => ({year: day.year, month: day.month})),
      weekSpans: runs(days, day => `${day.weekYear}-${day.week}`, day => ({year: day.weekYear, week: day.week}))
    };
  }

  // The time axis: the days fill `width` (less the project labels and the overdue zone) with no sideways scroll, weekends narrower; a
  // range only scrolls when its days would drop under MIN_DAY. xs[i] is the left edge of day i (whole pixels), xs[days] the total.
  function scale({width, weeks, key = 'six', labelW = 150, lateW = 148, ratio = END_RATIO}) {
    const days = weeks * 7;
    const available = Math.max(0, Math.floor(width - labelW - lateW));
    const min = MIN_DAY[key] || MIN_DAY.six;
    const dayW = Math.max(min, available / (weeks * (5 + 2 * ratio)));
    const xs = [0];
    let edge = 0;
    for (let index = 0; index < days; index += 1) {
      edge += index % 7 >= 5 ? dayW * ratio : dayW;
      xs.push(Math.round(edge));
    }
    const fits = dayW * (weeks * (5 + 2 * ratio)) <= available + 0.5;
    if (fits) xs[days] = Math.max(available, xs[days - 1] + 1); // the last day takes the rounding
    return {dayW, endW: dayW * ratio, xs, days, total: xs[days], labelW, lateW, overflow: !fits, density: dayW >= 18 ? 'day' : 'week'};
  }
  // Index of the day under x (px from the left edge of the days), -1 outside them.
  function dayAt(sc, x) {
    if (!(x >= 0) || x >= sc.total) return -1;
    let low = 0;
    let high = sc.days - 1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (sc.xs[middle] <= x) low = middle; else high = middle - 1;
    }
    return low;
  }

  function finished(action) { return action.state === 'x' || action.state === '-'; }
  // Days past due for an unfinished action (0 when it is not late).
  function overdueDays(action, today) {
    return !finished(action) && isPlainDate(action.due) && action.due < today ? diffDays(action.due, today) : 0;
  }
  // A deadline that is not a date: a `due` that is text, or the `due:` wording of an action that has no 📅 date ("week of 05/10").
  function vagueText(action) {
    if (action.due) return isPlainDate(action.due) ? '' : String(action.due).trim();
    return String(action.due_note || '').trim();
  }
  // Open and with nothing to put on the frieze: no date (vague or not).
  function undated(action) { return !finished(action) && !isPlainDate(action.due); }

  // Owner initials for a chip: first and last word ("Jane Doe" → "JD"), the first two letters of a single name.
  function initials(owner) {
    const words = String(owner || '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return '';
    const letters = words.length === 1 ? Array.from(words[0]).slice(0, 2) : [Array.from(words[0])[0], Array.from(words.at(-1))[0]];
    return letters.join('').toLocaleUpperCase();
  }

  // The weeks the summary talks about: this one (today to Sunday), and the two after it.
  function windows(today) {
    const weekEnd = addDays(mondayOf(today), 6);
    return {today, weekEnd, nextStart: addDays(weekEnd, 1), nextEnd: addDays(weekEnd, 14)};
  }
  // Counts of the open actions for the strip under the toolbar: overdue, due this week, due in the next two weeks, vague, no deadline.
  function summary(actions, today) {
    const found = {...windows(today), overdue: 0, week: 0, next: 0, vague: 0, none: 0};
    for (const action of actions) {
      if (finished(action)) continue;
      if (vagueText(action)) found.vague += 1;
      else if (!isPlainDate(action.due)) found.none += 1;
      else if (action.due < today) found.overdue += 1;
      else if (action.due <= found.weekEnd) found.week += 1;
      else if (action.due >= found.nextStart && action.due <= found.nextEnd) found.next += 1;
    }
    return found;
  }
  // Whether an action belongs to one of the strip's spotlights ('overdue', 'week', 'next').
  function inSpot(action, kind, today) {
    if (finished(action) || !isPlainDate(action.due)) return false;
    const week = windows(today);
    if (kind === 'overdue') return action.due < today;
    if (kind === 'week') return action.due >= today && action.due <= week.weekEnd;
    if (kind === 'next') return action.due >= week.nextStart && action.due <= week.nextEnd;
    return false;
  }

  // The tray of open actions with no date, by project: those with a vague deadline first, then the others; `query` narrows by words
  // (ID, title, owner, project, wording). Projects keep the register order, actions are in progress, to do, then waiting.
  function tray(actions, {query = '', order = []} = {}) {
    const words = String(query).toLowerCase().split(/\s+/).filter(Boolean);
    const rank = new Map(order.map((register, index) => [register, index]));
    const laneRank = register => (rank.has(register) ? rank.get(register) : order.length);
    const sections = {vague: new Map(), none: new Map()};
    for (const action of actions) {
      if (!undated(action)) continue;
      const text = vagueText(action);
      const haystack = `${action.id} ${action.title} ${action.owner} ${action.project} ${text}`.toLowerCase();
      if (!words.every(word => haystack.includes(word))) continue;
      const groups = sections[text ? 'vague' : 'none'];
      if (!groups.has(action.register)) groups.set(action.register, {register: action.register, project: action.project, items: []});
      groups.get(action.register).items.push({action, text});
    }
    const sorted = groups => [...groups.values()]
      .sort((a, b) => laneRank(a.register) - laneRank(b.register) || a.register.localeCompare(b.register))
      .map(group => ({...group, items: group.items.sort((a, b) =>
        (STATE_RANK[a.action.state] ?? 1) - (STATE_RANK[b.action.state] ?? 1) ||
        (PRIORITY_RANK[a.action.priority] ?? 2) - (PRIORITY_RANK[b.action.priority] ?? 2) ||
        a.action.id.localeCompare(b.action.id, 'en', {numeric: true}))}));
    const vague = sorted(sections.vague);
    const none = sorted(sections.none);
    const count = groups => groups.reduce((sum, group) => sum + group.items.length, 0);
    return {vague, none, counts: {vague: count(vague), none: count(none)}};
  }

  // Where every action goes. Cancelled ones and those without a plain date are left out of the frieze; done ones only with showDone,
  // at their done date. Unfinished ones go to the Late zone when due before the range, to `later` when due after it. A scheduled date
  // inside the range, earlier than the due date, becomes a marker joined to the chip. Every project that has an open action gets a lane,
  // dated or not (`open`, `undated`: how many open, how many of them have no date).
  // With a `scale` the chips also get a position: x and w in px (a chip starts on its day and runs right, or ends on it and runs left
  // when it would leave the range), and a track, the row it stacks in so no two chips overlap.
  function layout(actions, {today, start, end, showDone = false, order = [], scale: sc = null, chipW = 132, gap = 6}) {
    const rank = new Map(order.map((register, index) => [register, index]));
    const laneRank = register => (rank.has(register) ? rank.get(register) : order.length);
    const byRegister = new Map();
    const lane = action => {
      if (!byRegister.has(action.register)) byRegister.set(action.register, {register: action.register, project: action.project, entries: [], open: 0, undated: 0});
      return byRegister.get(action.register);
    };
    const later = [];
    for (const action of actions) {
      if (!finished(action)) {
        const home = lane(action);
        home.open += 1;
        if (!isPlainDate(action.due)) home.undated += 1;
      }
      if (action.state === '-') continue;
      const done = action.state === 'x';
      let date = '';
      if (done) {
        if (!showDone) continue;
        date = isPlainDate(action.done) ? action.done : isPlainDate(action.due) ? action.due : '';
        if (!date || date < start || date > end) continue;
      } else {
        if (!isPlainDate(action.due)) continue;
        date = action.due;
        if (date > end) { later.push(action); continue; }
      }
      const column = date < start ? -1 : diffDays(start, date);
      const scheduled = !done && isPlainDate(action.scheduled) ? action.scheduled : '';
      const sched = !scheduled ? '' : scheduled < date ? 'before' : scheduled === date ? 'same' : 'after';
      let marker = null;
      if (sched === 'before' && scheduled >= start) marker = {column: diffDays(start, scheduled)};
      lane(action).entries.push({
        id: action.id, action, register: action.register, project: action.project, date, column, late: column === -1, done,
        overdue: done ? 0 : overdueDays(action, today), scheduled, sched, marker, track: 0, x: 0, w: 0, flip: false
      });
    }
    const by = (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id, 'en', {numeric: true});
    const lanes = [...byRegister.values()].filter(item => item.entries.length || item.open)
      .sort((a, b) => laneRank(a.register) - laneRank(b.register) || a.register.localeCompare(b.register)).map((item, index) => {
        item.index = index;
        item.entries.sort(by);
        for (const entry of item.entries) entry.lane = index;
        // The overdue zone stacks its chips one under another; the days stack the ones that would overlap.
        item.lateTracks = 0;
        for (const entry of item.entries) if (entry.late) entry.track = item.lateTracks++;
        const ends = [];
        const dated = item.entries.filter(entry => !entry.late);
        if (sc) {
          for (const entry of dated) {
            const right = sc.xs[entry.column + 1];
            entry.flip = sc.xs[entry.column] + chipW > sc.total;
            entry.w = Math.min(chipW, sc.total);
            entry.x = entry.flip ? Math.max(0, right - entry.w) : sc.xs[entry.column];
            if (entry.marker) {
              entry.marker.x = Math.round((sc.xs[entry.marker.column] + sc.xs[entry.marker.column + 1]) / 2);
              if (entry.marker.x > entry.x - 6) entry.marker = null; // it would sit under the chip: the chip carries the hourglass instead
            }
          }
        }
        const left = entry => (entry.marker && entry.marker.x !== undefined ? Math.min(entry.x, entry.marker.x - 9) : entry.x);
        for (const entry of [...dated].sort((a, b) => left(a) - left(b) || by(a, b))) {
          const from = sc ? left(entry) : entry.column;
          const to = sc ? entry.x + entry.w : entry.column;
          let track = ends.findIndex(last => last + (sc ? gap : 1) <= from);
          if (track === -1) { track = ends.length; ends.push(to); } else ends[track] = to;
          entry.track = track;
        }
        item.tracks = ends.length;
        return item;
      });
    const entries = lanes.flatMap(item => item.entries);
    later.sort((a, b) => a.due.localeCompare(b.due) || a.id.localeCompare(b.id, 'en', {numeric: true}));
    const late = entries.filter(entry => entry.late).sort((a, b) => by(a, b) || a.lane - b.lane);
    return {lanes, late, later, total: entries.length};
  }

  // The chip to reach with an arrow key from chip `id`: left and right walk the lane by date (then by ID), up and down go to the
  // previous or next lane that has chips, on the chip closest in date; home and end are the first and last chip of the lane. null:
  // nowhere to go.
  function neighbour(lanes, id, direction) {
    const lane = lanes.find(item => item.entries.some(entry => entry.id === id));
    if (!lane) return null;
    const at = lane.entries.findIndex(entry => entry.id === id);
    if (direction === 'left') return lane.entries[at - 1]?.id ?? null;
    if (direction === 'right') return lane.entries[at + 1]?.id ?? null;
    if (direction === 'home') return lane.entries[0].id;
    if (direction === 'end') return lane.entries.at(-1).id;
    const step = direction === 'down' ? 1 : direction === 'up' ? -1 : 0;
    if (!step) return null;
    let target = null;
    for (let index = lane.index + step; index >= 0 && index < lanes.length && !target; index += step) if (lanes[index].entries.length) target = lanes[index];
    if (!target) return null;
    const here = lane.entries[at].date;
    let best = null;
    for (const entry of target.entries) {
      const distance = Math.abs(diffDays(here, entry.date));
      if (best === null || distance < best.distance) best = {distance, id: entry.id};
    }
    return best.id;
  }

  // The same entries by day for the agenda layout: each day of the range with its chips (lane order, then stacking order) and its
  // scheduled markers; the late ones come separately.
  function agenda(result, days) {
    const flat = result.lanes.flatMap(lane => lane.entries);
    const order = (a, b) => a.lane - b.lane || a.track - b.track || a.id.localeCompare(b.id, 'en', {numeric: true});
    return days.map(day => ({
      day,
      entries: flat.filter(entry => entry.column === day.index).sort(order),
      markers: flat.filter(entry => entry.marker && entry.marker.column === day.index).sort(order)
    }));
  }

  return {
    ranges: Object.keys(RANGE_WEEKS), isPlainDate, addDays, diffDays, weekday, isWeekend, mondayOf, isoWeek, moveDue,
    range, scale, dayAt, overdueDays, vagueText, undated, initials, windows, summary, inSpot, tray, layout, neighbour, agenda
  };
})();
if (typeof module !== 'undefined') module.exports = TimelineView;
