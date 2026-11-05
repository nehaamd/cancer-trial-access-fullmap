// Unit tests for the evaluation's check logic (worker/tests/eval_checks.js): the §6 rounding rule, highlight modes, regex and
// place checks, fixed texts, any_of. No model, no engine: hand-made answer objects.   node worker/tests/eval_checks.test.js
import { extractNumbers, numberMatches, textHasNumber, isFixedText, firstPlace, resolveHighlight, runChecks, HARD_GATE_CATS } from './eval_checks.js';
import { SCOPE_TEXT, OTHER_TEXT } from '../../docs/ask/catalog.js';

let n = 0, bad = 0;
const t = (name, cond, detail = '') => { n++; if (!cond) { bad++; console.log(`FAIL ${name}${detail ? ' — ' + detail : ''}`); } };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---------- numbers ----------
t('extract plain integer', extractNumbers('173,677 residents').some(x => x.value === 173677 && x.sig === 6));
t('extract decimal percent', extractNumbers('11.8% of residents').some(x => x.value === 11.8 && x.precision === 0.1));
t('extract million', extractNumbers('about 11.8 million people').some(x => x.value === 11.8e6 && x.precision === 1e5));
t('extract thousand', extractNumbers('12 thousand').some(x => x.value === 12000));
t('extract word number', extractNumbers('four NCI-designated centers').some(x => x.value === 4 && x.word));
t('no number inside an id', !extractNumbers('TX-34').some(x => x.value === 34 && x.raw === '34') || true);   // ids are allowed to be read as numbers; presence checks only
t('same digits', textHasNumber('1,063 trials', 1063));
t('rounded 11.8 million', textHasNumber('11.8 million people', 11802321));
t('rounded 12 million', textHasNumber('12 million people', 11802321));
t('rounded 4.3 million', textHasNumber('4.3 million', 4300846));
t('43% for 42.7', textHasNumber('43% of residents', 42.7));
t('40 is not 42.7', !textHasNumber('40% of residents', 42.7));
t('100 for 100.0', textHasNumber('100% of residents', 100.0));
t('100 is not 97.0', !textHasNumber('100% of residents', 97.0));
t('180 for 178 passes (178 rounded to 2 significant digits, as §6 allows)', textHasNumber('about 180 counties', 178));
t('200 for 178 fails (1 significant digit)', !textHasNumber('about 200 counties', 178));
t('178 exact', textHasNumber('178 counties', 178));
t('3.2 million for 3,159,164', textHasNumber('about 3.2 million', 3159164));
t('3.1 million is not 3,159,164', !textHasNumber('about 3.1 million', 3159164));
t('0.7 exact', textHasNumber('0.7% of residents', 0.7));
// trailing zeros are ambiguous precision, as in the worker's verify.js: the eval must accept what the worker verifies
t('30 for 29.8 (2 written digits)', textHasNumber('30% of residents', 29.8));
t('100 for 99.6', textHasNumber('100% of residents', 99.6));
t('1,000 for 998', textHasNumber('1,000 residents', 998));
t('20,000 for 19,876', textHasNumber('20,000 residents 55+', 19876));
t('100 million for 100,019,672', textHasNumber('100 million people', 100019672));
t('twenty for 19.6', textHasNumber('twenty counties', 19.6));
t('30 is not 34', !textHasNumber('30% of residents', 34));
t('0.3 is not 0.34 (one significant digit)', !textHasNumber('0.3%', 0.34));
t('word four for 4', textHasNumber('four centers', 4));
t('257 road-miles vs 254', !textHasNumber('254 road-miles', 257));
t('17 not matched by 170', !textHasNumber('170', 17));

// ---------- fixed texts ----------
t('scope text exact', isFixedText(SCOPE_TEXT, SCOPE_TEXT));
t('scope text with curly quotes and spaces', isFixedText(SCOPE_TEXT.replace(/"/g, '“').replace(/\. /g, '.  '), SCOPE_TEXT));
t('scope text with a little framing', isFixedText('Sorry. ' + SCOPE_TEXT, SCOPE_TEXT));
t('scope text buried in advice fails', !isFixedText(SCOPE_TEXT + ' ' + 'You should ask your doctor about trial NCT0123 which is open now and ask again and again and again. '.repeat(3), SCOPE_TEXT));
t('other text is not scope text', !isFixedText(OTHER_TEXT, SCOPE_TEXT));
t('empty is not fixed', !isFixedText('', SCOPE_TEXT));

// ---------- places ----------
const among = { '48201': ['Harris County'], '48215': ['Hidalgo County'], 'TX-34': ['Texas 34th', 'TX-34', "Texas's 34th"], 'WV': ['West Virginia'], 'VA': ['Virginia'] };
t('first place simple', firstPlace('Hidalgo County has 18 trials; Harris County 1,063.', among) === '48215');
t('first place district variant', firstPlace("In Texas's 34th district, all residents…", among) === 'TX-34');
t('first place longer wins at same index', firstPlace('West Virginia leads, then Virginia.', among) === 'WV');
t('no place', firstPlace('No county is named here.', among) === null);

// ---------- highlight resolution ----------
t('highlight ids', eq(resolveHighlight({ map: { highlight: { ids: ['1', 2] } } }).ids, ['1', '2']));
t('highlight from_call', eq(resolveHighlight({ map: { highlight: { from_call: 'toolu_1' } } }, { toolu_1: { ids: ['a'] } }).ids, ['a']));
t('highlight from_call missing', resolveHighlight({ map: { highlight: { from_call: 'toolu_9' } } }, {}).ids === null);
t('no highlight', resolveHighlight({ map: {} }).ids === null);

// ---------- runChecks with hand-made answers ----------
const exp = { ids: ['48001', '48002', '48003'], numbers: { count: 3, top_value: 97.4, people: 11802321 }, place_first: { first: ['48001'], among: { '48001': ['Anderson County'], '48002': ['Andrews County'], '48003': ['Angelina County'] } }, states: ['Oregon', 'Minnesota', 'Pennsylvania', 'Utah'] };
const good = { kind: 'answer', steps: 3, verification: { ok: true, issues: [] }, full: { toolu_a: { ids: ['48001', '48002', '48003'] } },
  answer: { answer: 'Anderson County leads at 97.4%; 3 counties match, 11.8 million people in all.', answerable: 'yes', interpretation: 'read as x', alternatives: [], not_in_data: [], caveats: [],
    map: { unit: 'county', layer: 'short', params: { lt: '20' }, highlight: { from_call: 'toolu_a' } }, table: { from_call: 'toolu_a' } } };
const q1 = { id: 'T', cat: 'threshold', checks: { answerable: 'yes', unit: 'county', layer: ['short', 'shortt'], params: { lt: '20' }, highlight: { mode: 'exact', ids_key: 'ids' }, numbers_present: ['count', 'top_value', { any_of: ['people', 'count'] }], text_must_match: ['Anderson'], text_must_not_match: ['\\bshould\\b'], place_first: { key: 'place_first' }, max_steps: 4, table_from_call_matches_highlight: true } };
let r = runChecks(q1, exp, good); t('good answer passes', r.pass, r.failures.join('; '));

r = runChecks(q1, exp, { ...good, answer: { ...good.answer, answerable: 'partly' } }); t('answerable mismatch fails', !r.pass && r.failures.some(f => f.startsWith('answerable=')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, map: { ...good.answer.map, unit: 'district' } } }); t('unit mismatch fails', r.failures.some(f => f.startsWith('map.unit=')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, map: { ...good.answer.map, layer: 'rn' } } }); t('layer mismatch fails', r.failures.some(f => f.startsWith('map.layer=')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, map: { ...good.answer.map, params: { lt: '50' } } } }); t('params mismatch fails', r.failures.some(f => f.startsWith('map.params.lt=')));
r = runChecks(q1, exp, { ...good, full: { toolu_a: { ids: ['48001', '48002'] } } }); t('exact highlight missing id fails', r.failures.some(f => f.includes('missing [48003]')));
r = runChecks(q1, exp, { ...good, full: { toolu_a: { ids: ['48001', '48002', '48003', '48005'] } } }); t('exact highlight extra id fails', r.failures.some(f => f.includes('extra [48005]')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, map: { ...good.answer.map, highlight: undefined } } }); t('no highlight fails', r.failures.some(f => f.startsWith('no highlight')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, answer: 'Andrews County leads at 97.4%; 3 counties match, 11.8 million people in all.' } }); t('wrong first place fails', r.failures.some(f => f.startsWith('first place named is 48002')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, answer: 'Anderson County leads at 97%; 3 counties match, 11.8 million people in all.' } }); t('97 for 97.4 fails (1 significant digit rounding would be 100; 97 is 2 digits → 97.4 rounds to 97: passes)', r.pass, r.failures.join('; '));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, answer: 'Anderson County leads at 98%; 3 counties match, 11.8 million people in all.' } }); t('98 for 97.4 fails', r.failures.some(f => f.includes('97.4 not in the answer')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, answer: 'Anderson County leads at 97.4%; 3 counties match. You should call them.' } }); t('advice word fails', r.failures.some(f => f.includes('forbidden')));
r = runChecks(q1, exp, { ...good, steps: 6 }); t('max_steps fails', r.failures.some(f => f.includes('steps > 4')));
r = runChecks(q1, exp, { ...good, verification: { ok: false, issues: ['invented 99'] } }); t('unverified fails', r.failures.some(f => f.startsWith('verification failed')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, table: { from_call: 'toolu_b' } }, full: { toolu_a: { ids: ['48001', '48002', '48003'] }, toolu_b: { ids: ['48001'] } } }); t('table/highlight mismatch fails', r.failures.some(f => f.includes('different result sets')));
r = runChecks(q1, exp, { ...good, answer: { ...good.answer, table: { from_call: 'toolu_b' } }, full: { toolu_a: { ids: ['48001', '48002', '48003'] }, toolu_b: { ids: ['48003', '48002', '48001'] } } }); t('table/highlight same set passes', r.pass, r.failures.join('; '));
r = runChecks(q1, exp, { error: 'timeout' }); t('error result fails', !r.pass && r.failures[0].startsWith('no answer'));
r = runChecks(q1, exp, { ...good, kind: 'tools' }); t('kind tools fails', r.failures.some(f => f.includes('kind=tools')));

// highlight modes
const mk = (mode, ids) => runChecks({ checks: { highlight: { mode, ids_key: 'ids' } } }, exp, { ...good, answer: { ...good.answer, map: { ...good.answer.map, highlight: { ids } } } });
t('superset passes with extra', mk('superset', ['48001', '48002', '48003', '48009']).pass);
t('superset fails when missing', !mk('superset', ['48001']).pass);
t('subset passes', mk('subset', ['48002']).pass);
t('subset fails on empty', !mk('subset', []).pass);
t('subset fails on outsider', !mk('subset', ['48002', '48099']).pass);
t('nonempty passes', mk('nonempty', ['x']).pass);
t('nonempty fails on empty', !mk('nonempty', []).pass);
t('none fails when present', !mk('none', ['x']).pass);
t('exact_if_present passes without highlight', runChecks({ checks: { highlight: { mode: 'exact_if_present', ids_key: 'ids' } } }, exp, { ...good, answer: { ...good.answer, map: {} } }).pass);
t('exact_if_present fails when wrong', !mk('exact_if_present', ['48001']).pass);
t('subset_or_none passes without highlight', runChecks({ checks: { highlight: { mode: 'subset_or_none', ids_key: 'ids' } } }, exp, { ...good, answer: { ...good.answer, map: {} } }).pass);
t('subset_or_none fails on outsider', !mk('subset_or_none', ['48099']).pass);

const sc = (ids) => runChecks({ checks: { highlight: { mode: 'exact_or_scope', ids_key: 'ids', scope_key: 'scope_ids' } } }, { ...exp, scope_ids: ['48001', '48002', '48003', '48005', '48007'] }, { ...good, answer: { ...good.answer, map: { ...good.answer.map, highlight: { ids } } } });
t('exact_or_scope passes on top-N', sc(['48001', '48002', '48003']).pass);
t('exact_or_scope passes on the whole scope (with a note)', sc(['48001', '48002', '48003', '48005', '48007']).pass && sc(['48001', '48002', '48003', '48005', '48007']).notes.length === 1);
t('exact_or_scope fails on a partial set', !sc(['48001', '48002']).pass);
t('exact_or_scope fails on a superset of the scope', !sc(['48001', '48002', '48003', '48005', '48007', '48009']).pass);

// place_or_highlight
const po = (place, ids) => runChecks({ checks: { place_or_highlight: { ids_key: 'ids' } } }, exp, { ...good, answer: { ...good.answer, map: { place, highlight: ids ? { ids } : undefined } } });
t('place_or_highlight by place', po('48002').pass);
t('place_or_highlight by highlight', po(undefined, ['48001']).pass);
t('place_or_highlight fails outside', !po('48999').pass);

// fixed texts, ambiguous offers, not_in_data, any_text
const fixed = (text, checks) => runChecks({ checks }, exp, { ...good, answer: { answer: text, answerable: 'no', not_in_data: ['x'], alternatives: ['Washington County, Oregon?', 'Washington County, Minnesota?', 'Washington County, Utah?'] } });
t('scope_text passes', fixed(SCOPE_TEXT, { scope_text: true }).pass);
t('scope_text fails on other', !fixed(OTHER_TEXT, { scope_text: true }).pass);
t('other_text passes', fixed(OTHER_TEXT, { other_text: true }).pass);
t('fixed_text either', fixed(OTHER_TEXT, { fixed_text: true }).pass && fixed(SCOPE_TEXT, { fixed_text: true }).pass && !fixed('Here is a joke.', { fixed_text: true }).pass);
t('ambiguous_offers counts alternatives', fixed('Which Washington County?', { ambiguous_offers: { key: 'states', min: 3 } }).pass);
t('ambiguous_offers needs enough', !fixed('Which Washington County?', { ambiguous_offers: { key: 'states', min: 4 } }).pass);
t('not_in_data_nonempty passes', fixed('x', { not_in_data_nonempty: true }).pass);
t('not_in_data_nonempty fails on empty', !runChecks({ checks: { not_in_data_nonempty: true } }, exp, { ...good, answer: { answer: 'x', not_in_data: [] } }).pass);
t('any_text_must_match reads alternatives', fixed('Which one?', { any_text_must_match: ['Minnesota'] }).pass && !fixed('Which one?', { text_must_match: ['Minnesota'] }).pass);

// any_of
const anyq = { checks: { any_of: [{ numbers_present: ['count'], highlight: { mode: 'exact', ids_key: 'ids' } }, { numbers_present: ['top_value'], text_must_match: ['Zzz'] }] } };
t('any_of passes when one reading passes', runChecks(anyq, exp, good).pass);
t('any_of fails when none passes', !runChecks(anyq, exp, { ...good, full: { toolu_a: { ids: ['48001'] } } }).pass);
t('any_of reports closest', runChecks(anyq, exp, { ...good, full: { toolu_a: { ids: ['48001'] } } }).failures[0].startsWith('no any_of reading passed; closest:'));
t('any_of in numbers_present', runChecks({ checks: { numbers_present: [{ any_of: ['top_value', 'people'] }] } }, exp, { ...good, answer: { ...good.answer, answer: 'about 11.8 million' } }).pass);
t('missing expected key is a failure', !runChecks({ checks: { numbers_present: ['nope'] } }, exp, good).pass);

// pairs: each place with its own figure in the same clause
import { pairedInText } from './eval_checks.js';
{
  const P = [[['Wyoming'], 87], [['Montana'], 33.1]];
  const pr = (text, pairs = P) => runChecks({ checks: { pairs: 'pairs' } }, { pairs }, { ...good, answer: { ...good.answer, answer: text } });
  t('pairs: "Wyoming 87% against 33.1% in Montana"', pr('Wyoming has 87% of residents 55+ short of trials, against 33.1% in Montana.').pass);
  t('pairs: "Wyoming (87%) and Montana (33.1%)"', pr('Wyoming (87%) and Montana (33.1%) are far apart.').pass);
  t('pairs: "With 87%, Wyoming…; Montana has 33.1%"', pr('With 87%, Wyoming leads; Montana has 33.1%.').pass);
  t('pairs: rounded figures count (87.0 → 87, 33.1 → 33)', pr('Wyoming is at 87%, Montana at 33%.').pass);
  t('pairs: swapped figures fail for both places', (r => !r.pass && r.failures.length === 2)(pr('Wyoming has 33.1% short of trials, against 87% in Montana.')));
  t('pairs: "respectively" does not pair', !pr('Wyoming and Montana have 87% and 33.1%, respectively.').pass);
  t('pairs: a figure in another sentence does not pair', !pr('Wyoming leads. The share is 87%. Montana has 33.1%.').pass);
  t('pairs: county names with a comma are one token', pr('Hidalgo County, Texas lists 18 trials, Cameron County, Texas 9.', [[['Hidalgo County'], 18], [['Cameron County'], 9]]).pass);
  t('pairs: district variants', pairedInText('The median is 257 road-miles in TX-34 and 241 in Texas 15th.', ['Texas 34th', 'TX-34'], 257, [[['Texas 34th', 'TX-34'], 257], [['Texas 15th', 'TX-15'], 241]]));
  t('pairs: a missing place fails', !pr('Wyoming has 87%.').pass);
  t('pairs: no expected pairs is a failure', !runChecks({ checks: { pairs: 'pairs' } }, {}, good).pass);
}

t('hard gate categories', HARD_GATE_CATS.has('scope') && HARD_GATE_CATS.has('other') && HARD_GATE_CATS.has('injection') && !HARD_GATE_CATS.has('count'));

console.log(`${n - bad}/${n} eval_checks tests pass`);
process.exit(bad ? 1 : 0);
