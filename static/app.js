const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const approveBtn = document.getElementById('approveBtn');
const rejectBtn = document.getElementById('rejectBtn');
const loadAuditBtn = document.getElementById('loadAuditBtn');
const decisionNote = document.getElementById('decisionNote');

const documentBox = document.getElementById('documentBox');
const extractionBox = document.getElementById('extractionBox');
const suggestionBox = document.getElementById('suggestionBox');
const candidatesBox = document.getElementById('candidatesBox');
const auditBox = document.getElementById('auditBox');
const globalStatus = document.getElementById('globalStatus');

let currentDocument = null;
let currentSuggestion = null;

function setStatus(text) {
  globalStatus.textContent = text;
}

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function renderDocument(document) {
  if (!document) {
    documentBox.textContent = 'No document uploaded.';
    return;
  }

  const isImage = document.mime_type.startsWith('image/');
  const isPdf = document.mime_type === 'application/pdf';

  documentBox.innerHTML = `
    <div><strong>ID:</strong> ${document.id}</div>
    <div><strong>Filename:</strong> ${document.original_filename}</div>
    <div><strong>Status:</strong> ${document.status}</div>
    <div><strong>Uploaded by:</strong> ${document.uploaded_by_user_id}</div>
    ${
      isImage
        ? `<img class="preview" src="${document.file_url}" alt="Uploaded document preview" />`
        : ''
    }
    <div>
      <a class="file-link" href="${document.file_url}" target="_blank" rel="noreferrer">
        ${isPdf ? 'Open PDF' : 'Open original file'}
      </a>
    </div>
  `;
}

function resetDecisionButtons() {
  approveBtn.disabled = true;
  rejectBtn.disabled = true;
  loadAuditBtn.disabled = true;
}

function enableDecisionButtons() {
  rejectBtn.disabled = false;
  loadAuditBtn.disabled = false;
  approveBtn.disabled = !(currentSuggestion && currentSuggestion.suggested_transaction_id);
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

  const response = await fetch('/api/documents/upload', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    setStatus('Upload failed');
    alert(error);
    return;
  }

  const data = await response.json();
  currentDocument = data.document;
  currentSuggestion = data.suggestion;

  renderDocument(data.document);
  extractionBox.textContent = pretty(data.extraction);
  if (data.suggestion.suggested_transaction_id) {
  suggestionBox.innerHTML = `
    <div><strong>Suggested transaction:</strong> ${data.suggestion.suggested_transaction_id}</div>
    <div><strong>Confidence:</strong> ${data.suggestion.confidence}</div>
    <div><strong>Reason:</strong> ${data.suggestion.primary_reason ?? 'No reason provided'}</div>
    <div><strong>Notes:</strong> ${data.suggestion.uncertainty_notes ?? ''}</div>
  `;
} else {
  suggestionBox.innerHTML = `
    <div><strong>No likely match suggested</strong></div>
    <div><strong>Confidence:</strong> ${data.suggestion.confidence}</div>
    <div><strong>Notes:</strong> ${data.suggestion.uncertainty_notes ?? 'Not enough confidence to suggest a match.'}</div>
  `;
}

if (data.candidates.length > 0) {
  candidatesBox.innerHTML = data.candidates
    .map(
      (tx) => `
        <div style="border:1px solid #ddd; padding:10px; margin-bottom:10px; background:#fff;">
          <div><strong>ID:</strong> ${tx.id}</div>
          <div><strong>Date:</strong> ${tx.transaction_date}</div>
          <div><strong>Amount:</strong> ${tx.amount}</div>
          <div><strong>Direction:</strong> ${tx.direction}</div>
          <div><strong>Description:</strong> ${tx.description ?? ''}</div>
          <div><strong>Merchant:</strong> ${tx.merchant_or_counterparty ?? ''}</div>
          <div><strong>Reference:</strong> ${tx.reference ?? ''}</div>
        </div>
      `
    )
    .join('');
} else {
  candidatesBox.innerHTML = `
    <div>No candidate transactions found.</div>
  `;
}

  enableDecisionButtons();
  setStatus('Document processed');
});

approveBtn.addEventListener('click', async () => {
  if (!currentDocument || !currentSuggestion || !currentSuggestion.suggested_transaction_id) {
    return;
  }

  setStatus('Recording approval...');

  const response = await fetch(`/api/documents/${currentDocument.id}/decision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      decision: 'approved',
      transaction_id: Number(currentSuggestion.suggested_transaction_id),
      decided_by_user_id: 'demo-user',
      decision_note: decisionNote.value || null,
    }),
  });

  const data = await response.json();

  currentDocument = data.document;
  renderDocument(currentDocument);

  suggestionBox.innerHTML = `
    <div><strong>Decision:</strong> approved</div>
    <div><strong>Matched transaction:</strong> ${data.decision.transaction_id}</div>
    <div><strong>Decided by:</strong> ${data.decision.decided_by_user_id}</div>
    <div><strong>Time:</strong> ${data.decision.decided_at}</div>
  `;

  setStatus('Approved');
});

rejectBtn.addEventListener('click', async () => {
  if (!currentDocument) {
    return;
  }

  setStatus('Recording rejection...');

  const response = await fetch(`/api/documents/${currentDocument.id}/decision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      decision: 'rejected',
      transaction_id: currentSuggestion?.suggested_transaction_id
        ? Number(currentSuggestion.suggested_transaction_id)
        : null,
      decided_by_user_id: 'demo-user',
      decision_note: decisionNote.value || null,
    }),
  });

  const data = await response.json();

  currentDocument = data.document;
  renderDocument(currentDocument);

  suggestionBox.innerHTML = `
    <div><strong>Decision:</strong> rejected</div>
    <div><strong>Matched transaction:</strong> none</div>
    <div><strong>Decided by:</strong> ${data.decision.decided_by_user_id}</div>
    <div><strong>Time:</strong> ${data.decision.decided_at}</div>
  `;

  setStatus('Rejected');
});

loadAuditBtn.addEventListener('click', async () => {
  if (!currentDocument) {
    return;
  }

  setStatus('Loading audit trail...');

  const response = await fetch(`/api/documents/${currentDocument.id}/audit`);
  const data = await response.json();

  auditBox.innerHTML = data
    .map((event) => {
      const payload = event.payload_json
        ? `<pre>${JSON.stringify(event.payload_json, null, 2)}</pre>`
        : '';

      return `
        <div style="border:1px solid #ddd; padding:10px; margin-bottom:10px; background:#fff;">
          <div><strong>${event.event_type}</strong></div>
          <div><strong>Actor:</strong> ${event.actor_user_id ?? 'system'}</div>
          <div><strong>Time:</strong> ${event.occurred_at}</div>
          ${payload}
        </div>
      `;
    })
    .join('');

  setStatus('Audit trail loaded');
});