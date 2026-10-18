// Text extraction from downloaded bytes, in the service worker. No page access, no network. Everything returned is untrusted text.
// txt/html directly; docx and pptx by reading the zip (central directory + DecompressionStream); PDFs are uploaded as bytes instead.
var SOSFiles = (function () {
  var MAX_ENTRY = 20 * 1024 * 1024, MAX_TEXT = 100000;
  function u16(b, o) { return b[o] | (b[o + 1] << 8); }
  function u32(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }

  function listZip(bytes) {
    var i = bytes.length - 22;
    for (; i >= 0 && i > bytes.length - 65600; i--) if (u32(bytes, i) === 0x06054b50) break;
    if (i < 0 || u32(bytes, i) !== 0x06054b50) throw new Error('not a zip');
    var n = u16(bytes, i + 10), p = u32(bytes, i + 16), out = [], total = 0;
    if (n > 600) throw new Error('too many entries'); // zip-bomb guard
    for (var k = 0; k < n && k < 5000; k++) {
      if (u32(bytes, p) !== 0x02014b50) break;
      var nl = u16(bytes, p + 28), el = u16(bytes, p + 30), cl = u16(bytes, p + 32);
      var name = '';
      for (var q = 0; q < nl; q++) name += String.fromCharCode(bytes[p + 46 + q]);
      var cs = u32(bytes, p + 20), us = u32(bytes, p + 24);
      total += us;
      if (total > 25 * 1024 * 1024) throw new Error('archive too large'); // 25 MB total
      if (us > 2000000 && cs > 0 && us / cs > 200) throw new Error('suspicious compression ratio');
      out.push({ name: name, method: u16(bytes, p + 10), csize: cs, usize: us, lho: u32(bytes, p + 42) });
      p += 46 + nl + el + cl;
    }
    return out;
  }
  async function readEntry(bytes, e) {
    if (e.usize > MAX_ENTRY) throw new Error('entry too large');
    var p = e.lho, start = p + 30 + u16(bytes, p + 26) + u16(bytes, p + 28);
    var data = bytes.subarray(start, start + e.csize);
    if (e.method === 0) return data;
    var stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }
  function decodeEntities(s) { return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#(\d+);/g, function (m, d) { return String.fromCharCode(+d); }).replace(/&amp;/g, '&'); }
  function runsText(xml, tag, paraTag) { // <w:t>..</w:t> runs, a newline at each paragraph end
    var out = '', re = new RegExp('<' + tag + '(?:\\s[^>]*)?>([^<]*)</' + tag + '>|</' + paraTag + '>', 'g'), m;
    while ((m = re.exec(xml))) { if (m[1] !== undefined) out += decodeEntities(m[1]); else out += '\n'; if (out.length > MAX_TEXT * 2) break; }
    return out.replace(/\n{3,}/g, '\n\n').trim();
  }
  var dec = function (u8) { return new TextDecoder('utf-8').decode(u8); };

  async function extractDocx(bytes) {
    var e = listZip(bytes).filter(function (x) { return x.name === 'word/document.xml'; })[0];
    if (!e) throw new Error('no document.xml');
    return runsText(dec(await readEntry(bytes, e)), 'w:t', 'w:p').slice(0, MAX_TEXT);
  }

  // pptx: slides in order, each followed by its speaker notes when present
  async function extractPptx(bytes) {
    var list = listZip(bytes);
    var slides = list.filter(function (x) { return /^ppt\/slides\/slide\d+\.xml$/.test(x.name); })
      .sort(function (a, b) { return parseInt(a.name.replace(/\D/g, ''), 10) - parseInt(b.name.replace(/\D/g, ''), 10); });
    if (!slides.length) throw new Error('no slides');
    var out = [];
    for (var i = 0; i < slides.length && i < 200; i++) {
      var num = slides[i].name.replace(/\D/g, '');
      var part = 'Slide ' + (i + 1) + ':\n' + runsText(dec(await readEntry(bytes, slides[i])), 'a:t', 'a:p');
      var notes = list.filter(function (x) { return x.name === 'ppt/notesSlides/notesSlide' + num + '.xml'; })[0];
      if (notes) { var nt = runsText(dec(await readEntry(bytes, notes)), 'a:t', 'a:p').replace(/^\d+\s*$/gm, '').trim(); if (nt) part += '\nNotes: ' + nt; }
      out.push(part);
    }
    return out.join('\n\n').slice(0, MAX_TEXT);
  }
  // xlsx: shared strings + cell values per sheet, tab separated
  async function extractXlsx(bytes) {
    var list = listZip(bytes), strings = [];
    var ss = list.filter(function (x) { return x.name === 'xl/sharedStrings.xml'; })[0];
    if (ss) {
      var sx = dec(await readEntry(bytes, ss)), sre = /<si>([\s\S]*?)<\/si>/g, sm;
      while ((sm = sre.exec(sx)) && strings.length < 50000) { var tx = '', tre = /<t(?:\s[^>]*)?>([^<]*)<\/t>/g, tm; while ((tm = tre.exec(sm[1]))) tx += decodeEntities(tm[1]); strings.push(tx); }
    }
    var sheets = list.filter(function (x) { return /^xl\/worksheets\/sheet\d+\.xml$/.test(x.name); })
      .sort(function (a, b) { return parseInt(a.name.replace(/\D/g, ''), 10) - parseInt(b.name.replace(/\D/g, ''), 10); });
    if (!sheets.length) throw new Error('no sheets');
    var out = [];
    for (var i = 0; i < sheets.length && i < 20; i++) {
      var xml = dec(await readEntry(bytes, sheets[i])), rows = [], rre = /<row[^>]*>([\s\S]*?)<\/row>/g, rm;
      while ((rm = rre.exec(xml)) && rows.length < 3000) {
        var cells = [], cre = /<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g, cm;
        while ((cm = cre.exec(rm[1]))) {
          var attrs = cm[1], inner = cm[2] || '', val = '';
          var v = inner.match(/<v>([^<]*)<\/v>/), is = inner.match(/<is>([\s\S]*?)<\/is>/);
          if (/t="s"/.test(attrs) && v) val = strings[parseInt(v[1], 10)] || '';
          else if (is) { var tt = is[1].match(/<t(?:\s[^>]*)?>([^<]*)<\/t>/); val = tt ? decodeEntities(tt[1]) : ''; }
          else if (v) val = decodeEntities(v[1]);
          cells.push(val);
        }
        if (cells.some(Boolean)) rows.push(cells.join('\t'));
      }
      out.push('Sheet ' + (i + 1) + ':\n' + rows.join('\n'));
    }
    return out.join('\n\n').slice(0, MAX_TEXT);
  }
  // odt / odp / ods: content.xml
  async function extractOdf(bytes) {
    var e = listZip(bytes).filter(function (x) { return x.name === 'content.xml'; })[0];
    if (!e) throw new Error('no content.xml');
    var xml = dec(await readEntry(bytes, e));
    xml = xml.replace(/<text:tab\s*\/>/g, '\t').replace(/<text:s\b[^>]*\/>/g, ' ').replace(/<text:line-break\s*\/>/g, '\n')
      .replace(/<\/(text:p|text:h|table:table-row)>/g, '\n').replace(/<\/table:table-cell>/g, '\t').replace(/<[^>]+>/g, '');
    return decodeEntities(xml).replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim().slice(0, MAX_TEXT);
  }
  function rtfToText(s) {
    return String(s).replace(/\\par[d]?\b ?/g, '\n').replace(/\\tab\b ?/g, '\t').replace(/\\'([0-9a-f]{2})/gi, function (m, h) { return String.fromCharCode(parseInt(h, 16)); })
      .replace(/\{\\\*[^{}]*\}/g, '').replace(/\\[a-z]+-?\d* ?/gi, '').replace(/[{}]/g, '').replace(/\n{3,}/g, '\n\n').trim().slice(0, MAX_TEXT);
  }

  function htmlToText(html) {
    return decodeEntities(String(html).replace(/<(script|style)[\s\S]*?<\/\1>/gi, ' ').replace(/<br\s*\/?>|<\/(p|div|li|h\d|tr)>/gi, '\n').replace(/<[^>]+>/g, ' '))
      .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n\n').trim().slice(0, MAX_TEXT);
  }
  // kind from content-type and/or file name
  function kindOf(contentType, name) {
    var ct = String(contentType || '').toLowerCase(), n = String(name || '').toLowerCase().split('?')[0];
    if (ct.indexOf('pdf') >= 0 || /\.pdf$/.test(n)) return 'pdf';
    if (ct.indexOf('wordprocessingml') >= 0 || /\.docx$/.test(n)) return 'docx';
    if (ct.indexOf('presentationml') >= 0 || /\.pptx$/.test(n)) return 'pptx';
    if (ct.indexOf('spreadsheetml') >= 0 || /\.xlsx$/.test(n)) return 'xlsx';
    if (ct.indexOf('opendocument') >= 0 || /\.(odt|odp|ods)$/.test(n)) return 'odf';
    if (ct.indexOf('rtf') >= 0 || /\.rtf$/.test(n)) return 'rtf';
    if (/\.(doc|ppt|xls)$/.test(n) || ct.indexOf('msword') >= 0 || ct.indexOf('ms-powerpoint') >= 0 || ct.indexOf('ms-excel') >= 0) return 'legacy';
    if (ct.indexOf('text/html') >= 0 || /\.html?$/.test(n)) return 'html';
    if (ct.indexOf('text/') === 0 || ct.indexOf('json') >= 0 || /\.(txt|md|csv|json)$/.test(n)) return 'txt';
    return '';
  }
  // Returns {text} or {pdf:true}; throws on unsupported or broken files.
  async function toText(kind, bytes) {
    if (kind === 'txt') return { text: dec(bytes).slice(0, MAX_TEXT) };
    if (kind === 'html') return { text: htmlToText(dec(bytes)) };
    if (kind === 'docx') return { text: await extractDocx(bytes) };
    if (kind === 'pptx') return { text: await extractPptx(bytes) };
    if (kind === 'xlsx') return { text: await extractXlsx(bytes) };
    if (kind === 'odf') return { text: await extractOdf(bytes) };
    if (kind === 'rtf') return { text: rtfToText(dec(bytes)) };
    if (kind === 'legacy') throw new Error('legacy');
    if (kind === 'pdf') return { pdf: true };
    throw new Error('unsupported');
  }
  return { listZip: listZip, extractDocx: extractDocx, extractPptx: extractPptx, extractXlsx: extractXlsx, extractOdf: extractOdf, rtfToText: rtfToText, htmlToText: htmlToText, kindOf: kindOf, toText: toText };
})();
if (typeof module !== 'undefined') module.exports = SOSFiles;
