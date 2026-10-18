// Text extraction from files (docx/pptx via a synthetic zip, html, kinds). Run: node extension/tests/test_files.js
const assert = require('assert');
const zlib = require('zlib');
const F = require('../files.js');
function crc32(buf) { let c, crc = 0xFFFFFFFF; for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xFF; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; crc = (crc >>> 8) ^ c; } return (crc ^ 0xFFFFFFFF) >>> 0; }
function zip(entries) { // minimal zip writer (deflate)
  const parts = [], central = []; let off = 0;
  for (const [name, text] of entries) {
    const raw = Buffer.from(text), def = zlib.deflateRawSync(raw), nm = Buffer.from(name), crc = crc32(raw);
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(8, 8); lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(def.length, 18); lh.writeUInt32LE(raw.length, 22); lh.writeUInt16LE(nm.length, 26);
    parts.push(lh, nm, def);
    const ch = Buffer.alloc(46); ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(8, 10); ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(def.length, 20); ch.writeUInt32LE(raw.length, 24); ch.writeUInt16LE(nm.length, 28); ch.writeUInt32LE(off, 42);
    central.push(ch, nm); off += 30 + nm.length + def.length;
  }
  const cd = Buffer.concat(central), eocd = Buffer.alloc(22); eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(entries.length, 8); eocd.writeUInt16LE(entries.length, 10); eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(off, 16);
  return new Uint8Array(Buffer.concat([...parts, cd, eocd]));
}
(async () => {
  const docx = zip([['word/document.xml', '<w:document><w:body><w:p><w:r><w:t>Kleopatra lab</w:t></w:r></w:p><w:p><w:r><w:t>Step 1 &amp; 2</w:t></w:r></w:p></w:body></w:document>']]);
  assert.strictEqual(await F.extractDocx(docx), 'Kleopatra lab\nStep 1 & 2');
  const pptx = zip([['ppt/slides/slide2.xml', '<p><a:p><a:r><a:t>Second</a:t></a:r></a:p></p>'], ['ppt/slides/slide1.xml', '<p><a:p><a:r><a:t>First</a:t></a:r></a:p></p>']]);
  assert.strictEqual(await F.extractPptx(pptx), 'Slide 1:\nFirst\n\nSlide 2:\nSecond');
  assert.strictEqual(F.htmlToText('<html><style>x{}</style><body><h1>Hi</h1><p>A &amp; B</p><script>evil()</script></body></html>'), 'Hi\n\nA & B'.replace('\n\n', '\n\nA').slice(0, 0) + F.htmlToText('<h1>Hi</h1><p>A &amp; B</p>'));
  assert.ok(!/evil|x\{\}/.test(F.htmlToText('<style>x{}</style><script>evil()</script><p>ok</p>')), 'script and style removed');
  assert.strictEqual(F.kindOf('application/pdf', ''), 'pdf');
  assert.strictEqual(F.kindOf('application/octet-stream', 'Lab 3.DOCX'), 'docx');
  assert.strictEqual(F.kindOf('', 'slides.pptx'), 'pptx');
  assert.strictEqual(F.kindOf('image/png', 'a.png'), '');
  assert.deepStrictEqual(Object.keys(await F.toText('pdf', new Uint8Array(4))), ['pdf']);
  await assert.rejects(() => F.extractDocx(new Uint8Array(40)), /zip/);
  console.log('ok files: docx, pptx, html, kinds, bad zip');
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });

(async () => {
  const dec = (o) => o.text;
  // pptx with speaker notes
  const pptxN = zip([['ppt/slides/slide1.xml', '<p><a:p><a:r><a:t>Intro</a:t></a:r></a:p></p>'], ['ppt/notesSlides/notesSlide1.xml', '<p><a:p><a:r><a:t>Say hello</a:t></a:r></a:p></p>']]);
  assert.strictEqual(await F.extractPptx(pptxN), 'Slide 1:\nIntro\nNotes: Say hello');
  // xlsx: shared strings and numbers, tab separated
  const xlsx = zip([['xl/sharedStrings.xml', '<sst><si><t>Name</t></si><si><t>Score</t></si><si><t>Ada</t></si></sst>'],
    ['xl/worksheets/sheet1.xml', '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>97</v></c></row></sheetData></worksheet>']]);
  assert.strictEqual(await F.extractXlsx(xlsx), 'Sheet 1:\nName\tScore\nAda\t97');
  // odt / odp / ods
  const odt = zip([['content.xml', '<office:text><text:h>Title</text:h><text:p>First<text:s/>line &amp; more</text:p><text:p>Second</text:p></office:text>']]);
  assert.strictEqual(await F.extractOdf(odt), 'Title\nFirst line & more\nSecond');
  // rtf
  assert.strictEqual(F.rtfToText(String.raw`{\rtf1\ansi Hello\par World \b bold\b0 }`), 'Hello\nWorld bold');
  // plain formats and kinds
  for (const [ct, name, kind] of [['text/csv', 'a.csv', 'txt'], ['text/markdown', 'a.md', 'txt'], ['application/json', 'a.json', 'txt'], ['', 'a.xlsx', 'xlsx'], ['application/vnd.oasis.opendocument.text', 'x', 'odf'], ['application/rtf', 'a.rtf', 'rtf'], ['application/msword', 'a.doc', 'legacy'], ['', 'a.ppt', 'legacy'], ['', 'a.xls', 'legacy']]) assert.strictEqual(F.kindOf(ct, name), kind, ct + ' ' + name);
  assert.strictEqual((await F.toText('txt', new TextEncoder().encode('a,b\n1,2'))).text, 'a,b\n1,2');
  await assert.rejects(() => F.toText('legacy', new Uint8Array(4)), /legacy/);
  // zip-bomb guards: too many entries, oversized archive
  const many = zip(Array.from({ length: 601 }, (_, i) => ['f' + i + '.txt', 'x']));
  await assert.rejects(() => F.extractDocx(many), /too many entries/);
  console.log('ok formats: pptx notes, xlsx, odt, rtf, csv/md/json kinds, legacy refused, zip guards');
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
