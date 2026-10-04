let layaRuleSavedCases = null;
let semanticReplayOwner = '';
let semanticReplaySuite = null;
let semanticReplayBusy = false;
let semanticReplayRevision = 0;
function resetSavedSemanticCases() {
  layaRuleSavedCases = null;
  $('layaRuleSavedCases').replaceChildren(); $('layaRuleSavedCases').hidden = true;
  $('layaRuleNewCases').hidden = false;
}
async function loadSavedSemanticCases(rule, owner) {
  const saved = await api('/api/admin/semantic/tests',owner);
  if (owner !== admin) return;
  const suite = saved.suites.find(item => item.rule.id === rule.id);
  if (!suite) return;
  layaRuleSavedCases = suite.cases.map(item => ({id:item.id,text:item.text,direction:item.direction,target:item.target,expected:item.expected}));
  const container = $('layaRuleSavedCases');
  container.hidden = false; $('layaRuleNewCases').hidden = true;
  container.append(el('p','Saved expectations loaded with their exact scopes. Status: ' + suite.status + '. They will be re-evaluated against this proposed rule; no old result is reused.'));
  const details = el('details'); details.append(el('summary',layaRuleSavedCases.length + ' saved scoped cases'));
  container.append(details);
  for (const item of layaRuleSavedCases) {
    const row = el('div','', 'rule-card');
    row.append(el('strong',item.id + ' · ' + item.target + ' ' + item.direction + ' · ' + (item.expected === 'blocked' ? 'Block' : 'No semantic block')),el('p',item.text));
    details.append(row);
  }
  const replace = el('button','Replace saved examples','btn');
  replace.type = 'button'; replace.onclick = () => { if (!layaRuleBusy) { resetSavedSemanticCases(); invalidateLayaRuleTest(); } };
  container.append(replace);
}
function renderSemanticReplay(result) {
  const container = $('semanticReplayResults'); container.replaceChildren();
  for (const item of result.results) {
    const row = el('div','', 'rule-card');
    row.append(el('strong',item.rule_id + ' / ' + item.id + ' · ' + item.target + ' ' + item.direction),
      el('p','Expected: ' + (item.expected === 'blocked' ? 'Block' : 'No semantic block') + ' · actual: ' + assessmentLabel(item) + ' · ' + (item.passed ? 'PASS' : 'FAIL')));
    container.append(row);
  }
  for (const item of result.skipped || []) container.append(el('p','Skipped ' + item.rule_id + ': ' + item.reason,'amber'));
  for (const warning of result.warnings || []) container.append(el('p',warning,'amber'));
}
async function openSemanticReplay() {
  if (!admin) { openConnection(); return; }
  if (semanticReplayBusy) return;
  const owner = admin, revision = ++semanticReplayRevision;
  semanticReplayOwner = owner; semanticReplaySuite = null;
  $('semanticReplayResults').replaceChildren(); $('runSemanticReplay').disabled = true;
  $('semanticReplayMessage').textContent = 'Loading saved cases…'; $('semanticReplayDialog').showModal();
  try {
    const saved = await api('/api/admin/semantic/tests',owner);
    if (owner !== admin || revision !== semanticReplayRevision) return;
    semanticReplaySuite = saved;
    const count = saved.suites.reduce((total,suite) => total + suite.cases.length,0);
    $('semanticReplayMessage').textContent = count ? count + ' saved scoped cases. Running them calls actual Laya for applicable cases; inactive scopes are reported as skipped.' : 'No saved semantic cases yet. Add a reviewed Laya rule first.';
    $('runSemanticReplay').disabled = !count;
  } catch (error) { if (owner === admin && revision === semanticReplayRevision) $('semanticReplayMessage').textContent = error.message; }
}
$('replaySemanticTestsBtn').onclick = openSemanticReplay;
$('runSemanticReplay').onclick = async () => {
  if (semanticReplayBusy || !semanticReplaySuite || semanticReplayOwner !== admin) return;
  const owner = admin, suite = semanticReplaySuite, revision = semanticReplayRevision;
  semanticReplayBusy = true; $('runSemanticReplay').disabled = true;
  $('semanticReplayMessage').textContent = 'Replaying saved expectations with actual Laya…';
  try {
    const result = await api('/api/admin/semantic/tests/replay',owner,{base_version:suite.policy_version,suite_digest:suite.suite_digest});
    if (owner !== admin || revision !== semanticReplayRevision) return;
    if (result.policy_version !== suite.policy_version || result.suite_digest !== suite.suite_digest) throw Error('Replay results refer to a different configuration.');
    renderSemanticReplay(result);
    const passed = result.tests_passed === true && result.results.length > 0 && result.results.every(item => item.passed === true && item.status === 'evaluated' && item.decision === item.expected);
    $('semanticReplayMessage').textContent = passed ? 'All evaluated expectations passed. No policy was changed. Skipped cases, if any, are listed below.' : 'Some expectations failed, were unavailable, or no active cases could be evaluated. No policy was changed.';
  } catch (error) { if (owner === admin && revision === semanticReplayRevision) $('semanticReplayMessage').textContent = error.message + ' Close and reopen to load the current suite.'; }
  finally { semanticReplayBusy = false; $('runSemanticReplay').disabled = !semanticReplaySuite; }
};
$('closeSemanticReplay').onclick = () => { semanticReplayRevision += 1; semanticReplaySuite = null; $('semanticReplayDialog').close(); };
$('semanticReplayDialog').addEventListener('cancel', () => { semanticReplayRevision += 1; semanticReplaySuite = null; });
document.addEventListener('fastfence:status', event => {
  if (semanticReplaySuite && event.detail.policy.version !== semanticReplaySuite.policy_version) {
    semanticReplayRevision += 1; semanticReplaySuite = null; $('runSemanticReplay').disabled = true;
    $('semanticReplayMessage').textContent = 'Policy changed. Close and reopen to load the current test suite.';
  }
});
document.addEventListener('fastfence:identity', () => {
  semanticReplayRevision += 1; semanticReplaySuite = null; semanticReplayOwner = '';
  $('semanticReplayResults').replaceChildren(); $('semanticReplayDialog').close();
});
