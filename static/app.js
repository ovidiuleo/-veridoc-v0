const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const approveBtn = document.getElementById('approveBtn');
const rejectBtn = document.getElementById('rejectBtn');
const loadAuditBtn = document.getElementById('loadAuditBtn');
const refreshDocumentsBtn = document.getElementById('refreshDocumentsBtn');
const decisionNote = document.getElementById('decisionNote');

const documentBox = document.getElementById('documentBox');
const extractionBox = document.getElementById('extractionBox');
const suggestionBox = document.getElementById('suggestionBox');
const candidatesBox = document.getElementById('candidatesBox');
const auditBox = document.getElementById('auditBox');
const documentsBox = document.getElementById('documentsBox');
const globalStatus = document.getElementById('globalStatus');

let currentDocument = null;
let currentSuggestion = null;
let currentCandidates = [];
let selectedTransactionId = null;

function setStatus(text) {
  globalStatus.textContent = text;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function formatMoney(amount, currency = 'GBP') {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
  }).format(Number(amount));
}

function formatDateTime(value) {
  if (!value) {
    return '';
  }

  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function resetDecisionButtons() {
  approveBtn.disabled = true;
  rejectBtn.disabled = true;
  loadAuditBtn.disabled = true;
}

function updateDecisionButtons() {
  rejectBtn.disabled = !currentDocument;
  loadAuditBtn.disabled = !currentDocument;
  approveBtn.disabled = !(currentDocument && selectedTransactionId);
}

function renderDocument(document) {
  if (!document) {
    documentBox.textContent = 'No document uploaded.';
    return;
  }

  const isImage = document.mime_type.startsWith('image/');
  const isPdf = document.mime_type === 'application/pdf';
  const fileUrl = escapeHtml(document.file_url);

  documentBox.innerHTML = `
    <dl class="detail-list">
      <div><dt>ID</dt><dd>${document.id}</dd></div>
      <div><dt>Filename</dt><dd>${escapeHtml(document.original_filename)}</dd></div>
      <div><dt>Status</dt><dd><span class="status-pill status-${escapeHtml(document.status)}">${escapeHtml(document.status)}</span></dd></div>
      <div><dt>Uploaded by</dt><dd>${escapeHtml(document.uploaded_by_user_id)}</dd></div>
      <div><dt>Uploaded</dt><dd>${formatDateTime(document.uploaded_at)}</dd></div>
    </dl>
    ${
      isImage
        ? `<img class="preview" src="${fileUrl}" alt="Uploaded document preview" />`
        : ''
    }
    <a class="file-link" href="${fileUrl}" target="_blank" rel="noreferrer">
      ${isPdf ? 'Open PDF' : 'Open original file'}
    </a>
  `;
}

function renderSuggestion(suggestion) {
  currentSuggestion = suggestion;
  selectedTransactionId = suggestion?.suggested_transaction_id
    ? Number(suggestion.suggested_transaction_id)
    : null;

  if (!suggestion) {
    suggestionBox.innerHTML = '<div>No suggestion yet.</div>';
    return;
  }

  if (suggestion.suggested_transaction_id) {
    suggestionBox.innerHTML = `
      <dl class="detail-list">
        <div><dt>Suggested transaction</dt><dd>${suggestion.suggested_transaction_id}</dd></div>
        <div><dt>Confidence</dt><dd>${escapeHtml(suggestion.confidence)}</dd></div>
        <div><dt>Score</dt><dd>${suggestion.suggested_score ?? '-'}</dd></div>
        <div><dt>Reason</dt><dd>${escapeHtml(suggestion.primary_reason ?? 'No reason provided')}</dd></div>
        <div><dt>Notes</dt><dd>${escapeHtml(suggestion.uncertainty_notes ?? '')}</dd></div>
      </dl>
    `;
  } else {
    suggestionBox.innerHTML = `
      <div><strong>No likely match suggested</strong></div>
      <div><strong>Confidence:</strong> ${escapeHtml(suggestion.confidence)}</div>
      <div><strong>Notes:</strong> ${escapeHtml(suggestion.uncertainty_notes ?? 'Not enough confidence to suggest a match.')}</div>
    `;
  }
}

function renderCandidates(candidates) {
  currentCandidates = candidates || [];

  if (currentCandidates.length === 0) {
    candidatesBox.innerHTML = '<div>No candidate transactions found.</div>';
    updateDecisionButtons();
    return;
  }

  candidatesBox.innerHTML = currentCandidates
    .map((tx) => {
      const selected = selectedTransactionId === tx.id;

      return `
        <article class="transaction-row ${selected ? 'transaction-row-selected' : ''}">
          <div>
            <div class="transaction-title">${escapeHtml(tx.merchant_or_counterparty ?? tx.description ?? `Transaction ${tx.id}`)}</div>
            <div class="muted">${escapeHtml(tx.transaction_date)} · ${escapeHtml(tx.reference ?? 'No reference')}</div>
            <div class="muted">${escapeHtml(tx.description ?? '')}</div>
          </div>
          <div class="transaction-actions">
            <strong>${formatMoney(tx.amount, tx.currency)}</strong>
            <button type="button" class="select-transaction-btn" data-transaction-id="${tx.id}">
              ${selected ? 'Selected' : 'Select'}
            </button>
          </div>
        </article>
      `;
    })
    .join('');

  updateDecisionButtons();
}

function renderDecision(decision) {
  if (!decision) {
    return;
  }

  suggestionBox.innerHTML = `
    <dl class="detail-list">
      <div><dt>Decision</dt><dd>${escapeHtml(decision.decision)}</dd></div>
      <div><dt>Matched transaction</dt><dd>${decision.transaction_id ?? 'none'}</dd></div>
      <div><dt>Decided by</dt><dd>${escapeHtml(decision.decided_by_user_id)}</dd></div>
      <div><dt>Time</dt><dd>${formatDateTime(decision.decided_at)}</dd></div>
      <div><dt>Note</dt><dd>${escapeHtml(decision.decision_note ?? '')}</dd></div>
    </dl>
  `;
}

function renderDocumentList(rows) {
  if (!rows.length) {
    documentsBox.innerHTML = '<div class="muted">No documents yet.</div>';
    return;
  }

  documentsBox.innerHTML = rows
    .map(({ document, extraction, suggestion, decision }) => {
      const amount = extraction?.total_amount
        ? formatMoney(extraction.total_amount, extraction.currency || 'GBP')
        : '-';
      const status = decision?.decision ?? document.status;
      const supplier = extraction?.supplier_name ?? document.original_filename;
      const suggestionText = suggestion?.suggested_transaction_id
        ? `Suggested #${suggestion.suggested_transaction_id}`
        : 'No suggestion';

      return `
        <button type="button" class="document-row" data-document-id="${document.id}">
          <span>
            <strong>${escapeHtml(supplier)}</strong>
            <small>${escapeHtml(document.original_filename)} · ${formatDateTime(document.uploaded_at)}</small>
          </span>
          <span>
            <strong>${amount}</strong>
            <small>${escapeHtml(status)} · ${escapeHtml(suggestionText)}</small>
          </span>
        </button>
      `;
    })
    .join('');
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return response.json();
}

async function loadDocuments() {
  const rows = await fetchJson('/api/documents');
  renderDocumentList(rows);
}

async function loadDocument(documentId) {
  setStatus('Loading document...');
  const data = await fetchJson(`/api/documents/${documentId}`);

  currentDocument = data.document;
  currentCandidates = [];
  renderDocument(data.document);
  extractionBox.textContent = data.extraction ? pretty(data.extraction) : 'No extraction data.';
  renderSuggestion(data.suggestion);
  renderDecision(data.decision);
  candidatesBox.innerHTML = '<div class="muted">Candidate transactions are shown immediately after upload.</div>';
  auditBox.textContent = 'No audit data yet.';
  updateDecisionButtons();
  setStatus('Document loaded');
}

uploadBtn.addEventListener('click', async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert('Choose a file first.');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('uploaded_by_user_id', 'demo-user');

  setStatus('Uploading and processing...');
  resetDecisionButtons();

  try {
    const data = await fetchJson('/api/documents/upload', {
      method: 'POST',
      body: formData,
    });

    currentDocument = data.document;
    renderDocument(data.document);
    extractionBox.textContent = pretty(data.extraction);
    renderSuggestion(data.suggestion);
    renderCandidates(data.candidates);
    auditBox.textContent = 'No audit data yet.';
    await loadDocuments();
    updateDecisionButtons();
    setStatus('Document processed');
  } catch (error) {
    setStatus('Upload failed');
    alert(error.message);
  }
});

candidatesBox.addEventListener('click', (event) => {
  const button = event.target.closest('.select-transaction-btn');
  if (!button) {
    return;
  }

  selectedTransactionId = Number(button.dataset.transactionId);
  renderCandidates(currentCandidates);
});

approveBtn.addEventListener('click', async () => {
  if (!currentDocument || !selectedTransactionId) {
    return;
  }

  setStatus('Recording approval...');

  const data = await fetchJson(`/api/documents/${currentDocument.id}/decision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      decision: 'approved',
      transaction_id: selectedTransactionId,
      decided_by_user_id: 'demo-user',
      decision_note: decisionNote.value || null,
    }),
  });

  currentDocument = data.document;
  renderDocument(currentDocument);
  renderDecision(data.decision);
  await loadDocuments();
  setStatus('Approved');
});

rejectBtn.addEventListener('click', async () => {
  if (!currentDocument) {
    return;
  }

  setStatus('Recording rejection...');

  const data = await fetchJson(`/api/documents/${currentDocument.id}/decision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      decision: 'rejected',
      transaction_id: selectedTransactionId,
      decided_by_user_id: 'demo-user',
      decision_note: decisionNote.value || null,
    }),
  });

  currentDocument = data.document;
  selectedTransactionId = null;
  renderDocument(currentDocument);
  renderDecision(data.decision);
  renderCandidates(currentCandidates);
  await loadDocuments();
  setStatus('Rejected');
});

loadAuditBtn.addEventListener('click', async () => {
  if (!currentDocument) {
    return;
  }

  setStatus('Loading audit trail...');

  const data = await fetchJson(`/api/documents/${currentDocument.id}/audit`);

  auditBox.innerHTML = data
    .map((event) => {
      const payload = event.payload_json
        ? `<pre>${escapeHtml(JSON.stringify(event.payload_json, null, 2))}</pre>`
        : '';

      return `
        <article class="audit-row">
          <div><strong>${escapeHtml(event.event_type)}</strong></div>
          <div class="muted">Actor: ${escapeHtml(event.actor_user_id ?? 'system')}</div>
          <div class="muted">Time: ${formatDateTime(event.occurred_at)}</div>
          ${payload}
        </article>
      `;
    })
    .join('');

  setStatus('Audit trail loaded');
});

refreshDocumentsBtn.addEventListener('click', async () => {
  setStatus('Refreshing documents...');
  await loadDocuments();
  setStatus('Ready');
});

documentsBox.addEventListener('click', (event) => {
  const row = event.target.closest('.document-row');
  if (!row) {
    return;
  }

  loadDocument(row.dataset.documentId);
});

loadDocuments().catch((error) => {
  setStatus('Could not load documents');
  console.error(error);
});
