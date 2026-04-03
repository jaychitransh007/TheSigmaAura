from html import escape


def get_catalog_admin_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet" />
  <title>Aura Catalog Admin</title>
  <style>
    :root {
      --bg: #f6f0ea;
      --surface: #fffaf5;
      --ink: #201915;
      --muted: #6e655f;
      --line: #dfd1c4;
      --accent: #6f2f45;
      --accent-soft: #f3e6ea;
      --warn: #b08a4e;
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(184, 139, 150, 0.22), transparent 28%),
        radial-gradient(circle at 85% 12%, rgba(176, 138, 78, 0.14), transparent 24%),
        linear-gradient(180deg, #fbf6f1 0%, var(--bg) 42%, #f1e6da 100%);
    }
    .wrap {
      max-width: 1240px;
      margin: 24px auto 40px;
      padding: 0 16px;
    }
    .hero, .panel, .step {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 8px 24px rgba(20, 20, 20, 0.05);
    }
    .hero {
      padding: 20px;
      margin-bottom: 16px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-family: "Cormorant Garamond", serif;
      font-size: 32px;
      font-weight: 600;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
      max-width: 760px;
      line-height: 1.5;
    }
    .layout {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 16px;
    }
    .panel {
      padding: 16px;
    }
    .panel h2, .step h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .field {
      margin-bottom: 12px;
    }
    .field label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }
    .field input {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      background: #fff;
      font-size: 14px;
    }
    .btns {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    button {
      border: 1px solid transparent;
      border-radius: 10px;
      padding: 9px 12px;
      font-weight: 700;
      cursor: pointer;
      background: var(--accent);
      color: #fff;
    }
    button.secondary {
      background: #fff;
      color: var(--ink);
      border-color: var(--line);
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #fff;
    }
    .metric .label {
      font-size: 12px;
      color: var(--muted);
    }
    .metric .value {
      margin-top: 6px;
      font-size: 24px;
      font-weight: 800;
    }
    .steps {
      display: grid;
      gap: 12px;
    }
    .step {
      padding: 16px;
    }
    .step-num {
      display: inline-block;
      margin-bottom: 8px;
      padding: 4px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
    }
    .step p {
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.5;
    }
    .uploads {
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }
    .upload-item {
      padding: 10px 0;
      border-bottom: 1px dashed #e8e1d7;
      font-size: 13px;
    }
    .upload-item:last-child {
      border-bottom: none;
    }
    .mono {
      font-family: "JetBrains Mono", monospace;
      font-size: 12px;
      color: var(--muted);
      word-break: break-all;
    }
    .status-box {
      margin-top: 12px;
      border: 1px dashed var(--line);
      border-radius: 12px;
      background: #fff;
      padding: 12px;
      min-height: 80px;
      white-space: pre-wrap;
      font-size: 12px;
    }
    .warn {
      color: var(--warn);
      font-size: 12px;
      margin-top: 8px;
    }
    .jobs-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .jobs-table th, .jobs-table td {
      padding: 6px 8px;
      text-align: left;
      border-bottom: 1px solid var(--line);
    }
    .jobs-table th {
      color: var(--muted);
      font-weight: 600;
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
    }
    .badge-running { background: #dbeafe; color: #1e40af; }
    .badge-completed { background: #d1fae5; color: #065f46; }
    .badge-failed { background: #fee2e2; color: #991b1b; }
    .badge-pending { background: #f3f4f6; color: #6b7280; }
    .badge-type {
      background: var(--accent-soft);
      color: var(--accent);
    }
    .error-cell {
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #991b1b;
    }
    @media (max-width: 980px) {
      .layout { grid-template-columns: 1fr; }
      .summary { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Catalog Admin</h1>
      <p>Run the async catalog pipeline in sequence. Upload a CSV, sync catalog rows into Supabase, and then generate embeddings either for a limited sample or the full eligible dataset.</p>
    </section>

    <div class="layout">
      <aside class="panel">
        <h2>Control Panel</h2>
        <div class="field">
          <label>Source CSV Path</label>
          <input id="inputPath" value="data/catalog/enriched_catalog_upload.csv" />
        </div>
        <div class="field">
          <label>Max Rows</label>
          <input id="maxRows" type="number" min="0" value="5" />
        </div>
        <div class="field">
          <label>Start Row</label>
          <input id="startRow" type="number" min="0" value="0" />
        </div>
        <div class="field">
          <label>End Row (0 = all)</label>
          <input id="endRow" type="number" min="0" value="0" />
        </div>
        <div class="field" style="flex-direction:row;align-items:center;gap:8px;">
          <input id="includeIncomplete" type="checkbox" style="width:auto;" />
          <label for="includeIncomplete" style="margin:0;">Include Incomplete Rows</label>
        </div>
        <div class="field">
          <label>Upload New CSV</label>
          <input id="fileInput" type="file" accept=".csv,text/csv" />
        </div>
        <div class="btns">
          <button id="refreshBtn" class="secondary">Refresh Status</button>
          <button id="syncAllBtn">Run Full Pipeline</button>
        </div>
        <div id="statusBox" class="status-box">Loading status...</div>
        <div class="warn">Use `Max Rows = 0` for the full dataset. Start with 5 rows to validate enrichment and embeddings before scaling.</div>
      </aside>

      <main>
        <section class="summary">
          <div class="metric">
            <div class="label">Source Rows</div>
            <div class="value" id="sourceRows">0</div>
          </div>
          <div class="metric">
            <div class="label">Catalog Enriched in Supabase</div>
            <div class="value" id="catalogItems">0</div>
          </div>
          <div class="metric">
            <div class="label">Embedding Rows in Supabase</div>
            <div class="value" id="embeddingRows">0</div>
          </div>
          <div class="metric">
            <div class="label">Running Jobs</div>
            <div class="value" id="runningJobs">0</div>
          </div>
          <div class="metric">
            <div class="label">Failed Jobs</div>
            <div class="value" id="failedJobs">0</div>
          </div>
        </section>

        <section class="steps">
          <div class="step">
            <div class="step-num">STEP 1</div>
            <h2>Upload CSV</h2>
            <p>Upload a new fixed-column CSV to the admin uploads directory. The uploaded file becomes the source path for the next steps.</p>
            <div class="btns">
              <button id="uploadBtn">Upload Selected CSV</button>
            </div>
          </div>

          <div class="step">
            <div class="step-num">STEP 2</div>
            <h2>Sync Catalog Enriched</h2>
            <p>Store enriched catalog rows in Supabase `catalog_enriched`. Existing `product_id` values are replaced by upsert.</p>
            <div class="btns">
              <button id="syncItemsBtn">Sync Catalog Enriched</button>
            </div>
          </div>

          <div class="step">
            <div class="step-num">STEP 3</div>
            <h2>Backfill Canonical URLs</h2>
            <p>Repair older `catalog_enriched` rows that are missing canonical absolute product URLs by rebuilding them from known `store + handle` mappings.</p>
            <div class="btns">
              <button id="backfillUrlsBtn" class="secondary">Backfill URLs</button>
            </div>
          </div>

          <div class="step">
            <div class="step-num">STEP 4</div>
            <h2>Generate Embeddings</h2>
            <p>Generate embeddings for eligible rows and upsert them into `catalog_item_embeddings`. Existing rows are replaced per `product_id + model + dimensions`.</p>
            <div class="btns">
              <button id="syncEmbeddingsBtn">Sync Embeddings</button>
            </div>
          </div>

          <div class="step">
            <h2>Job History</h2>
            <div id="jobsTable"></div>
          </div>

          <div class="step uploads">
            <h2>Latest Uploads</h2>
            <div id="uploadsList"></div>
          </div>
        </section>
      </main>
    </div>
  </div>

  <script>
    const inputPathEl = document.getElementById("inputPath");
    const maxRowsEl = document.getElementById("maxRows");
    const startRowEl = document.getElementById("startRow");
    const endRowEl = document.getElementById("endRow");
    const fileInputEl = document.getElementById("fileInput");
    const statusBox = document.getElementById("statusBox");
    const sourceRowsEl = document.getElementById("sourceRows");
    const catalogItemsEl = document.getElementById("catalogItems");
    const embeddingRowsEl = document.getElementById("embeddingRows");
    const runningJobsEl = document.getElementById("runningJobs");
    const failedJobsEl = document.getElementById("failedJobs");
    const uploadsListEl = document.getElementById("uploadsList");
    const jobsTableEl = document.getElementById("jobsTable");

    function setStatus(text) {
      statusBox.textContent = text;
    }

    async function parseResponse(res) {
      const raw = await res.text();
      let data = null;
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch (_error) {
        if (!res.ok) {
          throw new Error(raw || ('HTTP ' + res.status));
        }
        throw new Error('Expected JSON response but received: ' + raw.slice(0, 160));
      }
      if (!res.ok) {
        throw new Error(data.detail || raw || ('HTTP ' + res.status));
      }
      return data;
    }

    function payload() {
      return {
        input_csv_path: inputPathEl.value.trim(),
        max_rows: parseInt(maxRowsEl.value || "0", 10),
        start_row: parseInt(startRowEl.value || "0", 10),
        end_row: parseInt(endRowEl.value || "0", 10),
        include_incomplete: document.getElementById("includeIncomplete").checked
      };
    }

    function renderUploads(items) {
      uploadsListEl.innerHTML = "";
      if (!items || !items.length) {
        uploadsListEl.innerHTML = '<div class="upload-item">No uploaded CSVs yet.</div>';
        return;
      }
      for (const item of items) {
        const div = document.createElement("div");
        div.className = "upload-item";
        div.innerHTML =
          '<div><strong>' + escapeHtml(item.filename) + '</strong></div>' +
          '<div class="mono">' + escapeHtml(item.input_csv_path) + '</div>' +
          '<div class="mono">' + escapeHtml(item.modified_at) + '</div>';
        uploadsListEl.appendChild(div);
      }
    }

    function renderJobs(jobs) {
      if (!jobs || !jobs.length) {
        jobsTableEl.innerHTML = '<div style="color:var(--muted);font-size:13px;">No jobs recorded yet.</div>';
        return;
      }
      let html = '<table class="jobs-table"><thead><tr>' +
        '<th>Type</th><th>Status</th><th>Rows</th><th>Saved</th><th>Missing</th><th>Started</th><th>Error</th>' +
        '</tr></thead><tbody>';
      for (const j of jobs) {
        const statusClass = 'badge-' + (j.status || 'pending');
        const started = j.started_at ? new Date(j.started_at).toLocaleString() : '';
        const err = j.error_message ? escapeHtml(j.error_message.slice(0, 80)) : '';
        html += '<tr>' +
          '<td><span class="badge badge-type">' + escapeHtml(j.job_type) + '</span></td>' +
          '<td><span class="badge ' + statusClass + '">' + escapeHtml(j.status) + '</span></td>' +
          '<td>' + (j.processed_rows != null ? j.processed_rows : '-') + '</td>' +
          '<td>' + (j.saved_rows != null ? j.saved_rows : '-') + '</td>' +
          '<td>' + (j.missing_url_rows != null ? j.missing_url_rows : '-') + '</td>' +
          '<td class="mono">' + escapeHtml(started) + '</td>' +
          '<td class="error-cell" title="' + escapeHtml(j.error_message || '') + '">' + err + '</td>' +
          '</tr>';
      }
      html += '</tbody></table>';
      jobsTableEl.innerHTML = html;
    }

    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    async function refreshStatus() {
      const path = encodeURIComponent(inputPathEl.value.trim());
      const res = await fetch('/v1/admin/catalog/status?input_csv_path=' + path);
      const data = await parseResponse(res);
      sourceRowsEl.textContent = data.source.total_rows;
      catalogItemsEl.textContent = data.catalog_enriched_count;
      embeddingRowsEl.textContent = data.catalog_embeddings_count;
      runningJobsEl.textContent = data.running_jobs || 0;
      failedJobsEl.textContent = data.failed_jobs || 0;
      renderJobs(data.recent_jobs || []);
      renderUploads(data.latest_uploads || []);
      setStatus(
        'Source: ' + data.source.input_csv_path + '\\n' +
        'Eligible embedding rows: ' + data.source.eligible_embedding_rows + '\\n' +
        'Distinct embedded products: ' + data.embedded_product_count
      );
    }

    async function uploadCsv() {
      const file = fileInputEl.files && fileInputEl.files[0];
      if (!file) {
        setStatus('Select a CSV file first.');
        return;
      }
      setStatus('Uploading CSV...');
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/v1/admin/catalog/upload', { method: 'POST', body: form });
      const data = await parseResponse(res);
      inputPathEl.value = data.input_csv_path;
      setStatus('Uploaded ' + data.filename + ' to ' + data.input_csv_path);
      await refreshStatus();
    }

    async function syncItems() {
      setStatus('Syncing catalog enriched...');
      const res = await fetch('/v1/admin/catalog/items/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload())
      });
      const data = await parseResponse(res);
      setStatus('Catalog enriched synced. Processed ' + data.processed_rows + ' rows, saved ' + data.saved_rows + '.');
      await refreshStatus();
    }

    async function syncEmbeddings() {
      setStatus('Generating embeddings...');
      const res = await fetch('/v1/admin/catalog/embeddings/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload())
      });
      const data = await parseResponse(res);
      setStatus('Embeddings synced. Processed ' + data.processed_rows + ' rows, saved ' + data.saved_rows + '.');
      await refreshStatus();
    }

    async function backfillUrls() {
      setStatus('Backfilling canonical product URLs...');
      const res = await fetch('/v1/admin/catalog/items/backfill-urls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload())
      });
      const data = await parseResponse(res);
      setStatus(
        'URL backfill complete. Processed ' + data.processed_rows +
        ' rows, updated ' + data.saved_rows +
        ', still missing ' + data.missing_url_rows + '.'
      );
      await refreshStatus();
    }

    async function runFullPipeline() {
      try {
        await syncItems();
        await syncEmbeddings();
      } catch (error) {
        setStatus(error.message || String(error));
      }
    }

    document.getElementById('refreshBtn').addEventListener('click', async () => {
      try { await refreshStatus(); } catch (error) { setStatus(error.message || String(error)); }
    });
    document.getElementById('uploadBtn').addEventListener('click', async () => {
      try { await uploadCsv(); } catch (error) { setStatus(error.message || String(error)); }
    });
    document.getElementById('syncItemsBtn').addEventListener('click', async () => {
      try { await syncItems(); } catch (error) { setStatus(error.message || String(error)); }
    });
    document.getElementById('backfillUrlsBtn').addEventListener('click', async () => {
      try { await backfillUrls(); } catch (error) { setStatus(error.message || String(error)); }
    });
    document.getElementById('syncEmbeddingsBtn').addEventListener('click', async () => {
      try { await syncEmbeddings(); } catch (error) { setStatus(error.message || String(error)); }
    });
    document.getElementById('syncAllBtn').addEventListener('click', runFullPipeline);

    refreshStatus().catch((error) => setStatus(error.message || String(error)));
  </script>
</body>
</html>"""
