// Run from the repository root: node tools/arb_inspect/tests/test_ui.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
const webroot = path.join(root, 'targets/magisk_module/module/webroot');
const nodes = new Map();
function node(id) {
  if (!nodes.has(id)) nodes.set(id, {
    textContent: '', innerHTML: '', value: '', dataset: {}, classList: {add() {}, remove() {}},
    addEventListener() {}, setAttribute() {}, replaceChildren() { this.innerHTML = ''; }
  });
  return nodes.get(id);
}
const context = vm.createContext({
  document: {getElementById: node, querySelector: node, querySelectorAll: () => [], documentElement: {}},
  window: {}, setTimeout: () => 0, clearTimeout() {}, Date, console
});
const run = script => vm.runInContext(script, context);
run(fs.readFileSync(path.join(webroot, 'app.js'), 'utf8'));
run(fs.readFileSync(path.join(webroot, 'arb.js'), 'utf8'));
run(`var base = {STATUS:'ok', SW_ID:'28', SECONDARY_SW_ID:'0', OEM_ARB:'1', QTI_ARB:'absent'};`);
for (const [override, expected] of [
  [{}, 'same'], [{OEM_ARB:'0'}, 'lower'], [{OEM_ARB:'4294967295'}, 'higher'],
  [{SW_ID:'29'}, 'domain'], [{QTI_ARB:'0'}, 'authorities'],
  [{STATUS:'error'}, 'unknown'], [{OEM_ARB:undefined}, 'unknown']
]) {
  context.override = override;
  assert.equal(run('compareArb(base, {...base, ...override})'), expected);
}
assert.equal(run("compareArb({...base, QTI_ARB:'3'}, {...base, OEM_ARB:'2', QTI_ARB:'2'})"), 'mixed');
run(String.raw`state.moduleDir = "/data/adb/modules/test's module";
  refreshStatus = () => ({RUNNING:'0'});
  var commandSeen = '';
  exec = cmd => { commandSeen = cmd; return 'CURRENT_SLOT=_a\nA_STATUS=ok\nA_SW_ID=28\nA_SECONDARY_SW_ID=0\nA_OEM_ARB=0\nA_QTI_ARB=absent\nB_STATUS=ok\nB_SW_ID=28\nB_SECONDARY_SW_ID=0\nB_OEM_ARB=1\nB_QTI_ARB=absent'; };`);
node('arbPartition').value = 'abl';
run("checkArb('slots')");
assert.match(node('arbResults').innerHTML, /较高/);
assert.match(run('commandSeen'), /arb_check\.sh/);
run("state.lang = 'en'; refreshArbLanguage()");
assert.match(node('arbResults').innerHTML, /Higher/);
run('updateArbRunning(true)');
assert.equal(node('arbResults').innerHTML, '');
assert.equal(node('arbSlotsButton').disabled, true);
node('arbPartition').value = '../abl';
run("checkArb('slots')");
assert.match(node('arbMessage').textContent, /without a slot suffix/);
node('arbPartition').value = 'abl';
node('arbImagePath').value = "/sdcard/photo's $(id) <img>.img";
run(String.raw`exec = cmd => { commandSeen = cmd; return 'CURRENT_SLOT=unknown\nCURRENT_STATUS=error\nCURRENT_ERROR=UNKNOWN_SLOT\nFILE_STATUS=error\nFILE_ERROR=UNSUPPORTED_FORMAT'; };
  checkArb('image');`);
assert.match(node('arbMessage').textContent, /unknown/);
assert.match(node('arbResults').innerHTML, /&lt;img&gt;/);
assert.doesNotMatch(node('arbResults').innerHTML, /<img>/);
assert.match(run('commandSeen'), /'\\''/);
run("exec = () => ''; checkArb('image')");
assert.match(node('arbMessage').textContent, /NO_RESULT/);
assert.equal(node('arbResults').innerHTML, '');
console.log('UI checks passed: comparisons, language, stale results, errors, escaping.');
