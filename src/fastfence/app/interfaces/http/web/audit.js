let auditRows = [];
let auditLoaded = false;
const expandedAudit = new Set();

function auditSearchText(record) {
  return [record.request_id, record.subject, record.tenant, record.target,
    record.reason, record.event_kind, record.policy_version, record.feed_version,
    ...(record.findings || [])].join(' ').toLocaleLowerCase();
}
function auditDetails(record) {
  const container = el('div', '', 'body');
  const fields = [
    ['Request ID', record.request_id],
    ['Queue wait', Number.isSafeInteger(record.queue_wait_ms) && record.queue_wait_ms >= 0 ? record.queue_wait_ms + ' ms (included in total latency)' : 'Not recorded by this version'],
    ['Matched controls', (record.findings || []).join(', ') || 'None'],
    ['Upstream', record.upstream_executed ? 'Executed' : 'Not executed'],
    ['Policy / feed', 'v' + record.policy_version + ' / v' + record.feed_version],
    ['Identity / tenant', record.subject + ' / ' + record.tenant],
    ['Instance', record.instance_id],
    ['Event kind', record.event_kind],
    ['Input text analysis', record.semantic_input_status || 'Not recorded by this version'],
    ['Output text analysis', record.semantic_output_status || 'Not recorded by this version'],
    ['Semantic severity', record.semantic_score == null ? 'Not evaluated' : record.semantic_score + ' (ordinal, not probability)'],
    ['Accounted token units', record.tokens],
  ];
  for (const [label, value] of fields) {
    const line = el('p', '', 'small');
    line.style.wordBreak = 'break-word';
    line.append(el('strong', label + ': '), document.createTextNode(String(value ?? 'Unavailable')));
    container.append(line);
  }
  return container;
}
function renderAuditRows() {
  const query = $('auditSearch').value.trim().toLocaleLowerCase();
  const decision = $('auditDecision').value;
  const rows = auditRows.filter((record) =>
    (!decision || record.decision === decision) && (!query || auditSearchText(record).includes(query)));
  $('auditWindow').textContent = auditLoaded ? 'Showing ' + rows.length + ' of ' + auditRows.length +
    ' loaded recent events. Export audit for the retained history.' : 'Connect a management identity to inspect recent events.';
  $('events').replaceChildren();
  rows.forEach((record, index) => {
    const row = document.createElement('tr');
    [new Date(record.time).toLocaleTimeString(), record.subject, record.target, record.decision,
      record.reason, 'v' + record.policy_version, record.latency_ms + ' ms'].forEach((value, column) => {
      const color = record.decision === 'blocked' || record.decision === 'error' ? 'red' : record.decision === 'redacted' ? 'amber' : 'green';
      row.append(el('td', value, column === 3 ? 'tag ' + color : ''));
    });
    const cell = document.createElement('td');
    const button = el('button', 'Details', 'btn');
    const detailRow = document.createElement('tr');
    detailRow.id = 'audit-detail-' + index;
    const detailCell = document.createElement('td');
    detailCell.colSpan = 8;
    detailCell.append(auditDetails(record));
    detailRow.append(detailCell);
    const updateExpanded = () => {
      const open = expandedAudit.has(record.request_id);
      detailRow.hidden = !open;
      button.textContent = open ? 'Hide' : 'Details';
      button.setAttribute('aria-expanded', String(open));
    };
    button.setAttribute('aria-controls', detailRow.id);
    button.setAttribute('aria-label', 'Inspect request ' + record.request_id);
    button.onclick = () => {
      if (expandedAudit.has(record.request_id)) expandedAudit.delete(record.request_id);
      else expandedAudit.add(record.request_id);
      updateExpanded();
    };
    updateExpanded();
    cell.append(button);
    row.append(cell);
    $('events').append(row, detailRow);
  });
  if (!rows.length) {
    const row = document.createElement('tr');
    const message = !auditLoaded ? 'Connect a management token to view audit events.' :
      auditRows.length ? 'No loaded events match these filters. Clear filters or export the retained history.' : 'No decisions yet. Run a protected call.';
    const cell = el('td', message, 'small');
    cell.colSpan = 8;
    row.append(cell);
    $('events').append(row);
  }
}
function renderAudit(rows) {
  auditRows = rows.slice(0, 200);
  auditLoaded = true;
  const retained = new Set(auditRows.map((row) => row.request_id));
  for (const id of expandedAudit) if (!retained.has(id)) expandedAudit.delete(id);
  renderAuditRows();
}
function focusAudit(requestId) {
  navigate('activity');
  $('auditSearch').value = requestId;
  $('auditDecision').value = '';
  if (auditRows.some((row) => row.request_id === requestId)) expandedAudit.add(requestId);
  renderAuditRows();
  $('auditPanel').scrollIntoView({behavior: 'smooth', block: 'start'});
  $('auditSearch').focus({preventScroll: true});
}
$('auditSearch').oninput = renderAuditRows;
$('auditDecision').onchange = renderAuditRows;
$('clearAuditFilters').onclick = () => {
  $('auditSearch').value = '';
  $('auditDecision').value = '';
  renderAuditRows();
};
