// Pure tests for the content-index helpers in parse.js. Run: node extension/tests/test_index.js
const assert = require('assert');
const P = require('../parse.js');
assert.strictEqual(P.itemType('/ultra/courses/_1_1/file/_2_1'), 'file');
assert.strictEqual(P.itemType('/ultra/courses/_1_1/assessment/_2_1/overview'), 'assessment');
assert.strictEqual(P.itemType('/ultra/courses/_1_1/discussion/_2_1'), 'discussion');
assert.strictEqual(P.itemType('/ultra/courses/_1_1/outline/edit/document/_3_1'), 'document');
const items = [
  { path: 'Schedule & Syllabus', title: 'Syllabus', type: 'file', href: '/ultra/courses/_1_1/file/_2_1?courseId=_1_1' },
  { path: 'Homework > Week 1', title: 'Quiz 1', type: 'assessment', href: '/ultra/courses/_1_1/assessment/_5_1/overview' },
  { path: '', title: 'Welcome', type: 'document', href: '/ultra/courses/_1_1/outline/edit/document/_3_1' }
];
const txt = P.buildIndexText('EN 210', items, 'https://ualearn.blackboard.com', 60000);
const lines = txt.split('\n');
assert.strictEqual(lines.length, 4);
assert.strictEqual(lines[1], 'Schedule & Syllabus > Syllabus [file] <https://ualearn.blackboard.com/ultra/courses/_1_1/file/_2_1?courseId=_1_1>');
assert.strictEqual(lines[3], 'Welcome [document] <https://ualearn.blackboard.com/ultra/courses/_1_1/outline/edit/document/_3_1>');
// cap: never more than the byte budget
const many = Array.from({ length: 2000 }, (_, i) => ({ path: 'Folder > Sub', title: 'Item number ' + i, type: 'file', href: '/ultra/courses/_1_1/file/_' + i + '_1' }));
const big = P.buildIndexText('EN 210', many, 'https://ualearn.blackboard.com', 60000);
assert.ok(big.length <= 60000 && big.split('\n').length > 100, 'capped to ~60 KB, length ' + big.length);
// fingerprint: same index same hash, any change differs
assert.strictEqual(P.indexFingerprint(items), P.indexFingerprint(items.slice()));
const changed = items.map(i => Object.assign({}, i)); changed[1].title = 'Quiz 2';
assert.notStrictEqual(P.indexFingerprint(items), P.indexFingerprint(changed));
console.log('ok index helpers: format, 60 KB cap, fingerprint');
// syllabus candidate: title first, files/documents and shallow "Schedule & Syllabus" folders preferred
const cand = P.pickSyllabus([
  { path: 'Homework', title: 'Quiz 1', type: 'assessment', href: '/a' },
  { path: 'Week 1 > Readings', title: 'Course Schedule', type: 'document', href: '/b' },
  { path: 'Schedule & Syllabus', title: 'MIS 430 Syllabus Fall', type: 'file', href: '/c' },
  { path: '', title: 'Syllabus (old)', type: 'link', href: '/d' }
]);
assert.strictEqual(cand.href, '/c', 'best syllabus candidate');
assert.strictEqual(P.pickSyllabus([{ path: '', title: 'Slides week 1', type: 'file', href: '/x' }]), null, 'no candidate when nothing looks like a syllabus');
console.log('ok syllabus candidate picker');
// junk detection: the SPA shell, loading screens, menu-only text and short text are never uploaded
assert.ok(P.looksJunk('JavaScript is required to use this application. '.repeat(10)), 'noscript shell');
assert.ok(P.looksJunk('Loading ' + 'x'.repeat(400)), 'loading screen');
assert.ok(P.looksJunk('short'), 'too short');
assert.ok(P.looksJunk(['Course Content', 'Calendar', 'Discussions', 'Gradebook', 'Messages', 'Roster', 'Attendance', 'Books & Tools', 'Skip to main content'].join('\n') + '\n' + ' '.repeat(10)), 'menu labels only');
assert.ok(!P.looksJunk('Lab 3 instructions. Install the Kleopatra tool, create a key pair, and sign the provided file. '.repeat(6)), 'real content passes');
console.log('ok junk detection');

// ranking: an Ultra document beats a file beats a link when the titles are equally good
const rk = P.rankSyllabus([
  { path: '', title: 'Syllabus', type: 'link', href: 'https://docs.google.com/document/d/A/edit' },
  { path: '', title: 'Syllabus', type: 'file', href: '/f' },
  { path: '', title: 'Syllabus', type: 'document', href: '/d' }
], 3);
assert.deepStrictEqual(rk.map(x => x.type), ['document', 'file', 'link'], 'document, then file, then link');
console.log('ok syllabus ranking: document, file, link');
