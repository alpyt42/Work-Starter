'use strict';

// Date logic of the Timeline view: the visible range, ISO weeks and weekends, where each action lands, which ones are late or vague,
// the lanes and their stacking, and the keyboard neighbours of a chip. Days are ISO strings (YYYY-MM-DD) and all arithmetic is done in
// UTC, so a daylight-saving change never moves a day. No DOM and no clock ("today" always comes from the caller): the page draws the
// result, and the tests run this same file under node.
const TimelineView = (() => {
  const DAY = 86400000;
  const PLAIN = /^(\d{4})-(\d{2})-(\d{2})$/;
  const RANGE_WEEKS = {two: 2, six: 6, quarter: 13};

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

  // Where every action goes. Cancelled ones and those without any deadline are left out; done ones only with showDone, at their done
  // date. Unfinished ones go to the Late column when due before the range, to `later` when due after it, to `vague` when the deadline
  // is not a date. A scheduled date inside the range becomes a marker joined to the chip.
  function layout(actions, {today, start, end, showDone = false, order = []}) {
    const rank = new Map(order.map((register, index) => [register, index]));
    const laneRank = register => (rank.has(register) ? rank.get(register) : order.length);
    const byRegister = new Map();
    const vague = [];
    const later = [];
    for (const action of actions) {
      if (action.state === '-') continue;
      const done = action.state === 'x';
      let date = '';
      if (done) {
        if (!showDone) continue;
        date = isPlainDate(action.done) ? action.done : isPlainDate(action.due) ? action.due : '';
        if (!date || date < start || date > end) continue;
      } else {
        const text = vagueText(action);
        if (text) { vague.push({action, text}); continue; }
        if (!isPlainDate(action.due)) continue;
        date = action.due;
        if (date > end) { later.push(action); continue; }
      }
      const column = date < start ? -1 : diffDays(start, date);
      const scheduled = !done && isPlainDate(action.scheduled) ? action.scheduled : '';
      let marker = null;
      if (scheduled && scheduled >= start && scheduled <= end && diffDays(start, scheduled) !== column) {
        const at = diffDays(start, scheduled);
        marker = {column: at, from: Math.min(at, column) + 1, to: Math.max(at, column) - 1};
      }
      const entry = {
        id: action.id, action, register: action.register, project: action.project, date, column, late: column === -1, done,
        overdue: done ? 0 : overdueDays(action, today), scheduled, sameDay: Boolean(scheduled) && scheduled === date, marker, track: 0
      };
      if (!byRegister.has(action.register)) byRegister.set(action.register, []);
      byRegister.get(action.register).push(entry);
    }
    const by = (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id, 'en', {numeric: true});
    const lanes = [...byRegister.entries()].sort((a, b) => laneRank(a[0]) - laneRank(b[0]) || a[0].localeCompare(b[0])).map(([register, entries], index) => {
      entries.sort(by);
      // Stacking: an entry takes the first track whose last entry ends before it starts (a marker and its join count as part of it).
      const ends = [];
      const span = entry => [Math.min(entry.column, entry.marker ? entry.marker.column : entry.column), Math.max(entry.column, entry.marker ? entry.marker.column : entry.column)];
      for (const entry of [...entries].sort((a, b) => span(a)[0] - span(b)[0] || span(a)[1] - span(b)[1] || by(a, b))) {
        const [from, to] = span(entry);
        let track = ends.findIndex(last => last < from);
        if (track === -1) { track = ends.length; ends.push(to); } else ends[track] = to;
        entry.track = track;
      }
      return {index, register, project: entries[0].project, tracks: ends.length, entries};
    });
    for (const lane of lanes) for (const entry of lane.entries) entry.lane = lane.index;
    const entries = lanes.flatMap(lane => lane.entries);
    vague.sort((a, b) => laneRank(a.action.register) - laneRank(b.action.register) || a.action.id.localeCompare(b.action.id, 'en', {numeric: true}));
    later.sort((a, b) => a.due.localeCompare(b.due) || a.id.localeCompare(b.id, 'en', {numeric: true}));
    const late = entries.filter(entry => entry.late).sort((a, b) => by(a, b) || a.lane - b.lane);
    return {lanes, late, vague, later, total: entries.length};
  }

  // The chip to reach with an arrow key from chip `id`: left and right walk the lane by date (then by ID), up and down go to the
  // previous or next lane, on the chip closest in date; home and end are the first and last chip of the lane. null: nowhere to go.
  function neighbour(lanes, id, direction) {
    const lane = lanes.find(item => item.entries.some(entry => entry.id === id));
    if (!lane) return null;
    const at = lane.entries.findIndex(entry => entry.id === id);
    if (direction === 'left') return lane.entries[at - 1]?.id ?? null;
    if (direction === 'right') return lane.entries[at + 1]?.id ?? null;
    if (direction === 'home') return lane.entries[0].id;
    if (direction === 'end') return lane.entries.at(-1).id;
    const target = lanes[lane.index + (direction === 'down' ? 1 : direction === 'up' ? -1 : 0)];
    if (!target || target === lane) return null;
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
    ranges: Object.keys(RANGE_WEEKS), isPlainDate, addDays, diffDays, weekday, isWeekend, mondayOf, isoWeek,
    range, overdueDays, vagueText, layout, neighbour, agenda
  };
})();
if (typeof module !== 'undefined') module.exports = TimelineView;
