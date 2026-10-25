'use strict';

// Text edits behind the Markdown toolbar. Each one takes the value and the selection of a text field and returns an edit
// {from, to, text, select: [start, end]}: replace value[from, to) with text, then select [start, end) of the new value.
// No DOM here: the page applies the edit, and the tests run this same file under node.
const MarkdownEdit = (() => {
  // Quote markers and indentation before a list marker: lists keep both when a line changes.
  const LEAD = /^((?:>[ \t]?)*[ \t]*)/;
  const MARKER = /^(?:[-*+]|\d+[.)])[ \t]+(?:\[.\][ \t]+)?/;
  const LIST = {
    bullets: /^((?:>[ \t]?)*[ \t]*)[-*+](?![ \t]+\[.\][ \t])[ \t]+/,
    numbers: /^((?:>[ \t]?)*[ \t]*)\d+[.)][ \t]+/,
    tasks: /^((?:>[ \t]?)*[ \t]*)[-*+][ \t]+\[.\][ \t]+/
  };
  const NUMBERED = /^((?:>[ \t]?)*[ \t]*)(\d+)[.)][ \t]+/;

  function lineStart(value, index) { return index <= 0 ? 0 : value.lastIndexOf('\n', index - 1) + 1; }

  // Spaces at the edges of a selection stay outside the markers: `** word **` would not render as bold.
  function trimmed(value, start, end) {
    const text = value.slice(start, end);
    const a = start + text.length - text.trimStart().length;
    const b = end - (text.length - text.trimEnd().length);
    return a < b ? [a, b] : [end, end];
  }

  // Markers already around the selection, or at both ends of it: {around, inside} are the [opening, closing] lengths to strip (null: none).
  // `*` is shared by italic (one) and bold (two): `***x***` is both, so the run of asterisks decides which one is present.
  function wrapped(value, a, b, open, close) {
    const inner = value.slice(a, b);
    if (open === '*' || open === '**') {
      const run = (text, index, step) => { let count = 0; while (text[index + step * count] === '*') count += 1; return count; };
      const has = count => (open === '*' ? count % 2 === 1 : count >= 2);
      const full = inner.length > 0 && run(inner, 0, 1) === inner.length;
      return {
        around: has(Math.min(run(value, a - 1, -1), run(value, b, 1))) ? [open.length, open.length] : null,
        inside: !full && has(Math.min(run(inner, 0, 1), run(inner, inner.length - 1, -1))) ? [open.length, open.length] : null
      };
    }
    return {
      around: value.slice(a - open.length, a) === open && value.slice(b, b + close.length) === close ? [open.length, close.length] : null,
      inside: inner.length >= open.length + close.length && inner.startsWith(open) && inner.endsWith(close) ? [open.length, close.length] : null
    };
  }

  // Bold, italic, underline, strikethrough, code: wrap the selection, or unwrap it when it is already wrapped.
  function inline(value, start, end, open, close) {
    const [a, b] = trimmed(value, start, end);
    const {around, inside} = wrapped(value, a, b, open, close);
    if (around) return {from: a - around[0], to: b + around[1], text: value.slice(a, b), select: [a - around[0], b - around[0]]};
    if (inside) {
      const text = value.slice(a + inside[0], b - inside[1]);
      return {from: a, to: b, text, select: [a, a + text.length]};
    }
    return {from: a, to: b, text: open + value.slice(a, b) + close, select: [a + open.length, b + open.length]};
  }

  // Lists and quote apply to every selected line, and come off again when all of them already have it.
  function lines(value, start, end, kind) {
    const from = lineStart(value, start);
    const last = end > start && value[end - 1] === '\n' ? end - 1 : end;
    const lineEnd = value.indexOf('\n', last);
    const to = lineEnd < 0 ? value.length : lineEnd;
    const old = value.slice(from, to).split('\n');
    const blank = old.map(line => line.trim() === '');
    const allBlank = blank.every(Boolean);
    const quote = kind === 'quote';
    const has = quote ? line => line.startsWith('>') : line => LIST[kind].test(line);
    const off = old.filter((_, index) => allBlank || !blank[index]).every(has);
    // A numbered list continues the one just above, at the same indentation.
    let number = 1;
    if (kind === 'numbers' && !off && from > 0) {
      const above = NUMBERED.exec(value.slice(lineStart(value, from - 1), from - 1));
      const first = old.find((_, index) => !blank[index]) || '';
      if (above && above[1] === LEAD.exec(first)[1]) number = Number(above[2]) + 1;
    }
    const out = old.map((line, index) => {
      if (quote) {
        if (off) return line.replace(/^> ?/, '');
        return has(line) ? line : blank[index] && old.length > 1 ? '>' : `> ${line}`;
      }
      if (blank[index] && !allBlank) return line;
      if (off) return line.replace(LIST[kind], '$1');
      if (kind !== 'numbers' && has(line)) return line;
      const lead = LEAD.exec(line)[1];
      const marker = kind === 'numbers' ? `${number++}. ` : kind === 'tasks' ? '- [ ] ' : '- ';
      return lead + marker + line.slice(lead.length).replace(MARKER, '');
    });
    const text = out.join('\n');
    const caret = Math.min(Math.max(start + text.length - (to - from), from), from + text.length);
    return {from, to, text, select: start === end ? [caret, caret] : [from, from + text.length]};
  }

  // [selection](url) with the url selected, ready to be typed or pasted; a selected address becomes [text](address) instead.
  function link(value, start, end) {
    const [a, b] = trimmed(value, start, end);
    const text = value.slice(a, b);
    const whole = /^\[([^\]\n]*)\]\([^)\n]*\)$/.exec(text);
    if (whole) return {from: a, to: b, text: whole[1], select: [a, a + whole[1].length]};
    if (/^(?:https?:\/\/|mailto:)\S+$/i.test(text)) return {from: a, to: b, text: `[text](${text})`, select: [a + 1, a + 5]};
    const label = text || 'text';
    const at = a + label.length + 3;
    return {from: a, to: b, text: `[${label}](url)`, select: [at, at + 3]};
  }

  // A symbol (an arrow) replaces the selection, like typed text.
  function insert(value, start, end, text) { return {from: start, to: end, text, select: [start + text.length, start + text.length]}; }

  const TOOLS = {
    bold: (value, start, end) => inline(value, start, end, '**', '**'),
    italic: (value, start, end) => inline(value, start, end, '*', '*'),
    underline: (value, start, end) => inline(value, start, end, '<u>', '</u>'),
    strike: (value, start, end) => inline(value, start, end, '~~', '~~'),
    code: (value, start, end) => inline(value, start, end, '`', '`'),
    bullets: (value, start, end) => lines(value, start, end, 'bullets'),
    numbers: (value, start, end) => lines(value, start, end, 'numbers'),
    tasks: (value, start, end) => lines(value, start, end, 'tasks'),
    quote: (value, start, end) => lines(value, start, end, 'quote'),
    link,
    arrow: (value, start, end, symbol = '→') => insert(value, start, end, symbol)
  };

  function edit(tool, value, start, end, argument) { return TOOLS[tool](value, start, end, argument); }
  function apply(value, change) {
    return {value: value.slice(0, change.from) + change.text + value.slice(change.to), start: change.select[0], end: change.select[1]};
  }
  return {tools: Object.keys(TOOLS), edit, apply};
})();
if (typeof module !== 'undefined') module.exports = MarkdownEdit;
