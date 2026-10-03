'use strict';
let agent = '', admin = '', active = null, latestStatus = null;
let agentIdentity = null, managementIdentity = null, connectionEpoch = 0;
const $ = id => document.getElementById(id);
function el(tag, text, cls) { const node = document.createElement(tag); node.textContent = text; if (cls) node.className = cls; return node; }
const pageNames = {overview: 'Overview', policies: 'Policies', requests: 'Test requests', documents: 'Documents', activity: 'Activity', connection: 'Connection'};
function navigate(page, focus = true) {
  if (!Object.hasOwn(pageNames, page)) page = 'overview';
  document.querySelectorAll('[data-page]').forEach(node => { node.hidden = node.dataset.page !== page; });
  document.querySelectorAll('nav [data-nav]').forEach(node => {
    if (node.dataset.nav === page) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current');
  });
  $('pageTitle').textContent = pageNames[page];
  document.title = 'FastFence · ' + pageNames[page];
  if (location.hash !== '#' + page) history.replaceState(null, '', '#' + page);
  if (focus) $('mainContent').focus({preventScroll: true});
}
function showGlobal(message = '') { $('globalMessage').textContent = message; $('globalMessage').classList.toggle('hidden', !message); }
async function api(path, token, body, method) {
  const response = await fetch(path, {method: method || (body !== undefined ? 'POST' : 'GET'),
    headers: {Authorization: 'Bearer ' + token, ...(body !== undefined ? {'Content-Type': 'application/json'} : {})},
    ...(body !== undefined ? {body: JSON.stringify(body)} : {})});
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 401) throw Error('Credential rejected. Reconnect with a valid identity.');
    if (response.status === 403) throw Error('This identity does not have permission for this action.');
    throw Error(typeof error.detail === 'string' ? error.detail : 'Request failed (HTTP ' + response.status + '). Check the submitted values and retry.');
  }
  return response.json();
}
function connectionLabels() {
  $('managementIdentity').textContent = managementIdentity?.subject || 'Not connected';
  $('agentIdentity').textContent = agentIdentity ? agentIdentity.subject + ' · ' + agentIdentity.tenant : 'Not connected';
  $('actorLabel').textContent = agentIdentity ? agentIdentity.subject + ' · ' + agentIdentity.tenant : 'Agent not connected';
  $('connectionStatus').textContent = admin ? 'Workspace connected' : agent ? 'Agent connected' : 'Not connected';
  $('connectionDot').classList.toggle('connected', !!(admin || agent));
  $('connectBtn').textContent = admin || agent ? 'Manage connection' : 'Connect workspace';
  $('disconnectBtn').disabled = !(agent || admin);
  $('onboarding').classList.toggle('hidden', !!admin);
  $('policyAccessNote').classList.toggle('hidden', !!admin);
  $('requestAccessNote').classList.toggle('hidden', !!agent);
}
function openConnection() { $('connectError').textContent = ''; $('connectDialog').showModal(); }
function notifyIdentityChange() {
  document.querySelectorAll('dialog').forEach(dialog => { if (dialog.id !== 'connectDialog' && dialog.open) dialog.close(); });
  document.dispatchEvent(new CustomEvent('fastfence:identity'));
}
async function connect() {
  const epoch = connectionEpoch;
  const nextAgent = $('agentToken').value.trim() || agent;
  const nextAdmin = $('adminToken').value.trim() || admin;
  if (!nextAgent && !nextAdmin) { $('connectError').textContent = 'Enter at least one credential.'; return; }
  $('saveConnect').disabled = true;
  $('connectError').textContent = '';
  try {
    const nextAgentIdentity = nextAgent ? await api('/api/me', nextAgent) : null;
    if (nextAgentIdentity?.admin) throw Error('The agent field requires an agent credential, not a management credential.');
    const nextManagementIdentity = nextAdmin ? await api('/api/me', nextAdmin) : null;
    if (nextManagementIdentity && !nextManagementIdentity.admin) throw Error('The management field requires a management credential.');
    if (epoch !== connectionEpoch) throw Error('Connection changed. Try again.');
    const changed = agent !== nextAgent || admin !== nextAdmin;
    if (changed) {
      connectionEpoch += 1;
      agent = nextAgent; admin = nextAdmin;
      active = null; latestStatus = null;
      resetPlaygroundConversation();
      clearManagementView();
      notifyIdentityChange();
    }
    agentIdentity = nextAgentIdentity; managementIdentity = nextManagementIdentity;
    $('agentToken').value = ''; $('adminToken').value = '';
    connectionLabels();
    $('connectDialog').close();
    showGlobal();
    if (admin) await refresh();
  } catch (error) {
    if ($('connectDialog').open) $('connectError').textContent = error.message;
    else showGlobal('Connected, but the workspace could not be refreshed. ' + error.message);
  } finally { $('saveConnect').disabled = false; }
}
function clearManagementView() {
  for (const id of ['requests', 'blocked', 'redacted', 'latency', 'overviewSource', 'lastChecked']) $(id).textContent = '—';
  $('version').textContent = 'Policy —'; $('policyVersion').textContent = 'Not loaded'; $('headerVersion').textContent = 'Policy not loaded';
  $('policySource').textContent = 'Source not loaded'; $('policyUpdated').textContent = '';
  for (const id of ['privacyMode', 'feedMode', 'textRuleCount', 'semanticMode']) $(id).textContent = 'Not loaded';
  $('runtimeHealth').textContent = 'Connect a management identity to inspect configuration.';
  $('semanticNote').textContent = 'Content analysis status is unavailable.';
  $('budgets').replaceChildren(el('p', 'No resource usage loaded.', 'small'));
  $('policySummary').textContent = 'Connect a management identity to load the active policy.';
  $('policyInventory').replaceChildren(el('p', 'No policy loaded.', 'small'));
  if (typeof renderAudit === 'function') { auditLoaded = false; auditRows = []; expandedAudit.clear(); renderAuditRows(); }
  if (typeof syncPlaygroundModels === 'function') syncPlaygroundModels();
}
function renderBudgets(rows) {
  $('budgets').replaceChildren();
  if (!rows.length) { $('budgets').append(el('p', 'No resource consumption recorded in this instance yet.', 'small')); return; }
  for (const budget of rows) {
    const row = el('div', '', 'budgetrow');
    row.append(el('strong', budget.subject + ' · ' + budget.roles.join(', '), 'small'));
    for (const [label, value, maximum] of [['Calls', budget.calls, budget.limits?.calls], ['Token units', budget.tokens, budget.limits?.tokens], ['Estimated cost · µUSD', budget.cost_microusd, budget.limits?.cost_microusd], ['Compute · ms', budget.compute_ms, budget.limits?.compute_ms], ['Concurrent', budget.inflight, budget.limits?.concurrent]]) {
      row.append(el('div', label + ' · ' + value + ' / ' + (maximum ?? 'not configured'), 'small'));
      const bar = el('div', '', 'bar'), fill = el('span', '');
      fill.style.width = (maximum ? Math.min(100, value / maximum * 100) : 0) + '%';
      bar.append(fill); row.append(bar);
    }
    $('budgets').append(row);
  }
}
async function refresh() {
  if (!admin) return;
  const token = admin, epoch = connectionEpoch;
  try {
    const status = await api('/api/admin/status', token);
    if (token !== admin || epoch !== connectionEpoch) return;
    active = status.policy; latestStatus = status;
    syncPlaygroundModels();
    $('requests').textContent = status.metrics.requests;
    $('blocked').textContent = status.metrics.blocked;
    $('redacted').textContent = status.metrics.redacted;
    $('latency').textContent = status.metrics.p95_latency_ms + ' ms';
    $('version').textContent = 'Policy v' + active.version;
    $('headerVersion').textContent = 'Policy v' + active.version;
    $('policyVersion').textContent = 'Active · v' + active.version;
    const source = status.configuration.source_kind === 'http_bundle' ? 'Remote configuration' : 'Local configuration';
    $('policySource').textContent = source + (status.configuration.management_writable ? ' · editable' : ' · read-only');
    $('overviewSource').textContent = source;
    $('lastChecked').textContent = status.configuration.last_checked_at ? new Date(status.configuration.last_checked_at).toLocaleTimeString() : 'Not yet checked';
    $('policyUpdated').textContent = 'Loaded at ' + new Date().toLocaleTimeString();
    $('runtimeHealth').textContent = status.configuration.last_error ? 'Update rejected. The last valid configuration remains active: ' + status.configuration.last_error : 'The gateway is using the last validated configuration. Background updates are checked automatically.';
    $('privacyMode').textContent = active.privacy.enabled ? active.privacy.input + ' / ' + active.privacy.output : 'Disabled';
    $('feedMode').textContent = active.signatures_enabled ? 'v' + status.feed.version + ' · ' + status.feed.signatures.length + ' signatures' : 'Disabled';
    $('textRuleCount').textContent = (active.text_rules || []).length + ' content · ' + (active.anonymization?.rules || []).length + ' anonymization';
    $('semanticMode').textContent = active.semantic.provider === 'disabled' ? 'Off — patterns only' : active.semantic.provider + ' · ' + active.semantic.model;
    $('semanticMode').className = active.semantic.provider === 'disabled' ? 'amber' : '';
    $('semanticNote').textContent = active.semantic.provider === 'disabled' ? 'Semantic analysis is disabled. Unmatched wording may pass local pattern checks. Enable content analysis in policy settings for model-based assessment.' : status.semantic_status;
    renderAudit(status.audit); renderBudgets(status.budgets);
    document.dispatchEvent(new CustomEvent('fastfence:status', {detail: status}));
    showGlobal();
  } catch (error) {
    if (epoch === connectionEpoch && token === admin) showGlobal('Workspace refresh failed. Displayed data may be stale. ' + error.message);
    throw error;
  }
}
$('semanticPolicyBtn').onclick = async () => {
  await openPolicyManager();
  if ($('policyDialog').open && admin) {
    $('policySemanticProvider').scrollIntoView({block: 'center'});
    $('policySemanticProvider').focus({preventScroll: true});
  }
};
$('saveConnect').onclick = connect;
$('connectBtn').onclick = openConnection;
$('closeConnect').onclick = () => { $('connectDialog').close(); $('agentToken').value = ''; $('adminToken').value = ''; };
$('connectDialog').addEventListener('close', () => { $('agentToken').value = ''; $('adminToken').value = ''; });
$('disconnectBtn').onclick = () => {
  connectionEpoch += 1; agent = ''; admin = ''; active = null; latestStatus = null; agentIdentity = null; managementIdentity = null;
  resetPlaygroundConversation(); clearManagementView(); notifyIdentityChange(); connectionLabels(); showGlobal();
};
$('refreshBtn').onclick = () => { if (!admin) openConnection(); else refresh().catch(() => {}); };
$('exportBtn').onclick = async () => {
  if (!admin) { openConnection(); return; }
  const token = admin, epoch = connectionEpoch;
  try {
    const response = await fetch('/api/admin/audit.jsonl', {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) throw Error('Audit export failed (HTTP ' + response.status + '). Reconnect or retry.');
    const blob = await response.blob();
    if (epoch !== connectionEpoch || token !== admin) return;
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'fastfence-audit.jsonl'; link.click(); URL.revokeObjectURL(url);
  } catch (error) { showGlobal(error.message); }
};
document.querySelectorAll('[data-nav]').forEach(button => { button.onclick = () => navigate(button.dataset.nav); });
document.querySelectorAll('[data-connect]').forEach(button => { button.onclick = openConnection; });
for (const [id, path] of [['mcpEndpoint', '/mcp/'], ['openaiEndpoint', '/v1'], ['restEndpoint', '/api']]) $(id).textContent = location.origin + path;
document.querySelectorAll('[data-copy]').forEach(button => { button.onclick = async () => {
  try { await navigator.clipboard.writeText($(button.dataset.copy).textContent); $('copyMessage').textContent = 'Endpoint copied.'; }
  catch { $('copyMessage').textContent = 'Clipboard unavailable. Select and copy the endpoint above.'; }
}; });
window.addEventListener('hashchange', () => navigate(location.hash.slice(1), false));
navigate(location.hash.slice(1), false);
setInterval(() => { if (admin && !document.hidden) refresh().catch(() => {}); }, 5000);
