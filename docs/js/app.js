/* UI wiring for the Invoicing App (browser edition). */

(() => {
  const $ = (id) => document.getElementById(id);

  // ── Invoice-in-progress state ──
  let currentInvoiceId = null;
  let selectedCustomer = null; // {id, name, email, phone, address, trade_license}
  let itemsList = []; // [{description, quantity, unit_price, discount, amount, note}]
  let editingItemIdx = null;

  function toast(msg, isError = false) {
    const t = $('toast');
    t.textContent = msg;
    t.hidden = false;
    t.className = 'toast' + (isError ? ' error' : '');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { t.hidden = true; }, 3200);
  }

  // ── Generic modal ──
  function openModal(title, bodyNode) {
    $('modalTitle').textContent = title;
    const body = $('modalBody');
    body.innerHTML = '';
    body.appendChild(bodyNode);
    $('modalOverlay').hidden = false;
  }
  function closeModal() {
    $('modalOverlay').hidden = true;
    $('modalBody').innerHTML = '';
  }
  function setupModal() {
    $('modalClose').addEventListener('click', closeModal);
    $('modalOverlay').addEventListener('click', (e) => { if (e.target.id === 'modalOverlay') closeModal(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('modalOverlay').hidden) closeModal(); });
  }

  function openRecordPaymentModal(invId) {
    const inv = DB.getInvoice(invId);
    const cy = DB.getSettings().currency || 'AED';
    const paidAmount = inv.paid_amount || 0;
    const remaining = Math.max(0, inv.total_amount - paidAmount);

    const body = document.createElement('div');
    body.innerHTML = `
      <div class="modal-stat-row"><span>Invoice total</span><b>${cy} ${inv.total_amount.toFixed(2)}</b></div>
      <div class="modal-stat-row"><span>Already paid</span><b>${cy} ${paidAmount.toFixed(2)}</b></div>
      <div class="modal-stat-row"><span>Remaining</span><b>${cy} ${remaining.toFixed(2)}</b></div>
      <label>Payment amount</label>
      <input type="number" id="paymentAmountInput" step="any" value="${remaining.toFixed(2)}">
      <div class="row modal-actions">
        <button id="btnRecordPayment" class="btn btn-primary">Record Payment</button>
        <button id="btnMarkFullyPaid" class="btn btn-secondary">Mark Fully Paid</button>
      </div>`;
    openModal(`Record Payment — ${inv.invoice_number}`, body);

    body.querySelector('#btnRecordPayment').addEventListener('click', () => {
      const amt = parseFloat(body.querySelector('#paymentAmountInput').value);
      if (isNaN(amt) || amt <= 0) { toast('Enter a valid payment amount', true); return; }
      DB.recordPayment(invId, amt);
      closeModal();
      renderInvoicesTab();
      toast('Payment recorded');
    });
    body.querySelector('#btnMarkFullyPaid').addEventListener('click', () => {
      DB.markFullyPaid(invId);
      closeModal();
      renderInvoicesTab();
      toast('Marked as fully paid');
    });
  }

  function todayISO() { return new Date().toISOString().slice(0, 10); }
  function isoToDMY(iso) { if (!iso) return ''; const [y, m, d] = iso.split('-'); return `${d}-${m}-${y}`; }
  function dmyToISO(dmy) { if (!dmy) return ''; const [d, m, y] = dmy.split('-'); return `${y}-${m}-${d}`; }

  // ────────────────────────────────────────────────────────────
  // In-progress invoice draft (separate from the whole-database
  // IndexedDB autosave — this is just the unsaved form you're filling in)
  // ────────────────────────────────────────────────────────────
  const DRAFT_KEY = 'invoicing-app-draft';

  function saveDraftToStorage() {
    try {
      const draft = {
        customer: selectedCustomer,
        items: itemsList,
        notes: $('notesField').value,
        projectName: $('projectName').value,
        issuedDate: $('issuedDate').value,
        dueDate: $('dueDate').value,
        vatEnabled: $('vatToggle').checked,
      };
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch (e) { /* storage unavailable — draft just won't persist */ }
  }

  function clearDraftFromStorage() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ }
  }

  function checkDraftOnBoot() {
    let draft;
    try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch (e) { return; }
    if (!draft || (!draft.customer && !(draft.items || []).length)) return;
    const custName = draft.customer?.name || '?';
    const nItems = (draft.items || []).length;
    if (!confirm(`An unsaved invoice draft was found:\n  Customer: ${custName}\n  Items: ${nItems}\n\nRestore it?`)) return;
    selectedCustomer = draft.customer || null;
    itemsList = draft.items || [];
    $('notesField').value = draft.notes || '';
    $('projectName').value = draft.projectName || '';
    if (draft.issuedDate) $('issuedDate').value = draft.issuedDate;
    if (draft.dueDate) $('dueDate').value = draft.dueDate;
    $('vatToggle').checked = !!draft.vatEnabled;
    renderSelectedCustomer();
    renderItemsTable();
  }

  // ────────────────────────────────────────────────────────────
  // Tabs
  // ────────────────────────────────────────────────────────────
  function switchToTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === tabName));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    $(`tab-${tabName}`).classList.add('active');
    if (tabName === 'dashboard') renderDashboardTab();
    if (tabName === 'invoices') renderInvoicesTab();
    if (tabName === 'customers') renderCustomersTab();
    if (tabName === 'catalog') renderCatalogTab();
    if (tabName === 'settings') renderSettingsTab();
  }

  function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => switchToTab(btn.dataset.tab));
    });
    document.querySelectorAll('[data-goto-tab]').forEach((btn) => {
      btn.addEventListener('click', () => switchToTab(btn.dataset.gotoTab));
    });
  }

  function renderDashboardTab() {
    const s = DB.getDashboardStats();
    const cy = DB.getSettings().currency || 'AED';
    $('statThisMonth').textContent = `${cy} ${s.thisMonthTotal.toFixed(2)}`;
    $('statOutstanding').textContent = `${cy} ${s.outstanding.toFixed(2)}`;
    $('statOverdue').textContent = `${cy} ${s.overdueTotal.toFixed(2)}`;
    $('statAllTime').textContent = `${cy} ${s.allTimeTotal.toFixed(2)}`;
  }

  // ────────────────────────────────────────────────────────────
  // Top bar: DB status + load/save/new
  // ────────────────────────────────────────────────────────────
  function refreshDbStatus() {
    $('dbFileLabel').textContent = DB.getFileName();
    $('dbDirtyDot').hidden = !DB.isDirty();
    const settings = DB.getSettings();
    $('companyNameLabel').textContent = settings.name || 'Invoicing App';
    document.title = `Invoicing App — ${settings.name || ''}`;
  }

  function setupTopbar() {
    document.addEventListener('db:dirty', refreshDbStatus);
    document.addEventListener('db:clean', refreshDbStatus);

    $('btnNewDb').addEventListener('click', () => {
      if (DB.isDirty() && !confirm('Start a new database? Unsaved changes will be lost unless you save first.')) return;
      DB.newDatabase();
      refreshAll();
      toast('New database created');
    });

    $('btnLoadDb').addEventListener('click', async () => {
      if (DB.isDirty() && !confirm('Loading a database will discard unsaved changes. Continue?')) return;
      if (DB.canUseFsAccess()) {
        try {
          await DB.loadDatabaseFromPicker();
          refreshAll();
          toast(`Loaded ${DB.getFileName()} — Save Database will now write straight back to it`);
        } catch (err) {
          if (err.name !== 'AbortError') toast(`Failed to load database: ${err.message}`, true);
        }
      } else {
        $('fileInput').click();
      }
    });

    $('fileInput').addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const buf = await file.arrayBuffer();
      try {
        DB.loadDatabase(buf, file.name);
        refreshAll();
        toast(`Loaded ${file.name}`);
      } catch (err) {
        toast(`Failed to load database: ${err.message}`, true);
      }
      e.target.value = '';
    });

    $('btnSaveDb').addEventListener('click', async () => {
      await DB.saveDatabase();
      refreshDbStatus();
      toast(DB.hasFileHandle() ? `Saved to ${DB.getFileName()}` : 'Database saved');
    });

    $('btnSaveDbAs').addEventListener('click', async () => {
      const saved = await DB.saveDatabaseAs();
      if (saved) toast('Saved a copy — your currently loaded database is unchanged');
    });

    window.addEventListener('beforeunload', (e) => {
      if (DB.isDirty()) { e.preventDefault(); e.returnValue = ''; }
    });
  }

  function refreshAll() {
    refreshDbStatus();
    resetInvoiceForm();
    populateCustomerList();
    populateCatalogSelect();
    renderDashboardTab();
    renderInvoicesTab();
    renderCustomersTab();
    renderCatalogTab();
    renderSettingsTab();
  }

  // ────────────────────────────────────────────────────────────
  // New Invoice tab
  // ────────────────────────────────────────────────────────────
  function populateCustomerList(filter = '') {
    const list = DB.listCustomers(filter);
    const sel = $('customerSelect');
    sel.innerHTML = '';
    for (const c of list) {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      sel.appendChild(opt);
    }
  }

  function renderSelectedCustomer() {
    const box = $('selectedCustomerBox');
    if (!selectedCustomer) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<b>${escapeHtml(selectedCustomer.name)}</b><br>
      ${selectedCustomer.trade_license ? 'TRN: ' + escapeHtml(selectedCustomer.trade_license) + '<br>' : ''}
      ${selectedCustomer.email ? escapeHtml(selectedCustomer.email) + '<br>' : ''}
      ${selectedCustomer.phone ? escapeHtml(selectedCustomer.phone) + '<br>' : ''}
      ${selectedCustomer.address ? escapeHtml(selectedCustomer.address) : ''}`;
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // Some invoices saved by older builds of the desktop app stored items_data as a
  // Python str(list-of-dicts) (single-quoted, e.g. [{'description': 'x', 'tax': 0.0}])
  // instead of real JSON. JSON.parse rejects that outright, so fall back to a small
  // literal parser restricted to the shapes Python's repr() actually produces
  // (strings/numbers/booleans/None, nested lists/dicts) — never eval().
  function parsePythonLiteral(src) {
    let i = 0;
    const skipWs = () => { while (i < src.length && /\s/.test(src[i])) i++; };
    function parseValue() {
      skipWs();
      const c = src[i];
      if (c === '[') return parseArray();
      if (c === '{') return parseObject();
      if (c === "'" || c === '"') return parseString();
      if (src.startsWith('True', i)) { i += 4; return true; }
      if (src.startsWith('False', i)) { i += 5; return false; }
      if (src.startsWith('None', i)) { i += 4; return null; }
      return parseNumber();
    }
    function parseArray() {
      i++; skipWs();
      const arr = [];
      if (src[i] === ']') { i++; return arr; }
      while (true) {
        arr.push(parseValue());
        skipWs();
        if (src[i] === ',') { i++; skipWs(); continue; }
        if (src[i] === ']') { i++; break; }
        throw new Error(`Expected , or ] at position ${i}`);
      }
      return arr;
    }
    function parseObject() {
      i++; skipWs();
      const obj = {};
      if (src[i] === '}') { i++; return obj; }
      while (true) {
        skipWs();
        const key = parseString();
        skipWs();
        if (src[i] !== ':') throw new Error(`Expected : at position ${i}`);
        i++;
        obj[key] = parseValue();
        skipWs();
        if (src[i] === ',') { i++; continue; }
        if (src[i] === '}') { i++; break; }
        throw new Error(`Expected , or } at position ${i}`);
      }
      return obj;
    }
    function parseString() {
      const quote = src[i];
      if (quote !== "'" && quote !== '"') throw new Error(`Expected string at position ${i}`);
      i++;
      let out = '';
      while (i < src.length && src[i] !== quote) {
        if (src[i] === '\\' && i + 1 < src.length) {
          const esc = { n: '\n', t: '\t', r: '\r' }[src[i + 1]];
          out += esc !== undefined ? esc : src[i + 1];
          i += 2;
          continue;
        }
        out += src[i]; i++;
      }
      i++; // closing quote
      return out;
    }
    function parseNumber() {
      const start = i;
      if (src[i] === '-') i++;
      while (i < src.length && /[0-9.]/.test(src[i])) i++;
      if (i === start) throw new Error(`Unexpected character at position ${i}`);
      return Number(src.slice(start, i));
    }
    const result = parseValue();
    skipWs();
    return result;
  }

  function parseItemsData(raw) {
    if (!raw) return [];
    try {
      return JSON.parse(raw);
    } catch (jsonErr) {
      try {
        const items = parsePythonLiteral(raw);
        // legacy rows used the pre-rename "tax" key where current code expects "discount"
        return items.map((it) => ('discount' in it ? it : { ...it, discount: it.tax || 0 }));
      } catch (legacyErr) {
        console.warn('Could not parse items_data, treating as no items:', raw, legacyErr);
        return [];
      }
    }
  }

  function setupCustomerPanel() {
    $('customerSearch').addEventListener('input', (e) => populateCustomerList(e.target.value));

    $('btnUseCustomer').addEventListener('click', () => {
      const sel = $('customerSelect');
      if (!sel.value) { toast('Select a customer first', true); return; }
      selectedCustomer = DB.getCustomer(Number(sel.value));
      renderSelectedCustomer();
      saveDraftToStorage();
    });

    $('btnNewCustomerToggle').addEventListener('click', () => {
      $('newCustomerForm').hidden = !$('newCustomerForm').hidden;
    });

    $('btnSaveNewCustomer').addEventListener('click', () => {
      const name = $('ncName').value.trim();
      if (!name) { toast('Customer name is required', true); return; }
      const c = {
        name,
        trade_license: $('ncTrn').value.trim(),
        email: $('ncEmail').value.trim(),
        phone: $('ncPhone').value.trim(),
        address: $('ncAddress').value.trim(),
      };
      const id = DB.upsertCustomer(c);
      selectedCustomer = DB.getCustomer(id);
      renderSelectedCustomer();
      populateCustomerList();
      ['ncName', 'ncTrn', 'ncEmail', 'ncPhone', 'ncAddress'].forEach((id2) => $(id2).value = '');
      $('newCustomerForm').hidden = true;
      toast('Customer saved');
      saveDraftToStorage();
    });
  }

  // ── Items ──
  function populateCatalogSelect() {
    const items = DB.listCatalogItems();
    const sel = $('catalogSelect');
    sel.innerHTML = '<option value="">— New item —</option>';
    for (const it of items) {
      const opt = document.createElement('option');
      opt.value = it.id;
      opt.textContent = it.description;
      opt.dataset.price = it.unit_price;
      opt.dataset.discount = it.discount;
      opt.dataset.note = it.note || '';
      sel.appendChild(opt);
    }
  }

  function clearItemForm() {
    $('itDesc').value = '';
    $('itQty').value = '1';
    $('itPrice').value = '';
    $('itDiscount').value = '0';
    $('itNote').value = '';
    $('catalogSelect').value = '';
    editingItemIdx = null;
    $('btnAddItem').textContent = '+ Add to Invoice';
  }

  function renderItemsTable() {
    const tbody = document.querySelector('#itemsTable tbody');
    tbody.innerHTML = '';
    const cy = DB.getSettings().currency || 'AED';
    itemsList.forEach((item, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(item.description)}${item.note ? `<br><small style="color:#999">${escapeHtml(item.note)}</small>` : ''}</td>
        <td>${item.quantity}</td>
        <td class="num">${cy} ${item.unit_price.toFixed(2)}</td>
        <td class="num">${item.discount || 0}%</td>
        <td class="num">${cy} ${item.amount.toFixed(2)}</td>
        <td>
          <button class="btn btn-secondary btn-small" data-act="edit" data-idx="${idx}">Edit</button>
          <button class="btn btn-danger btn-small" data-act="remove" data-idx="${idx}">✕</button>
        </td>`;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll('button[data-act=edit]').forEach((b) => b.addEventListener('click', () => editItem(Number(b.dataset.idx))));
    tbody.querySelectorAll('button[data-act=remove]').forEach((b) => b.addEventListener('click', () => removeItem(Number(b.dataset.idx))));
    renderTotals();
  }

  function editItem(idx) {
    const item = itemsList[idx];
    $('itDesc').value = item.description;
    $('itQty').value = item.quantity;
    $('itPrice').value = item.unit_price;
    $('itDiscount').value = item.discount || 0;
    $('itNote').value = item.note || '';
    editingItemIdx = idx;
    $('btnAddItem').textContent = '✓ Update Item';
  }

  function removeItem(idx) {
    itemsList.splice(idx, 1);
    if (editingItemIdx === idx) clearItemForm();
    renderItemsTable();
    saveDraftToStorage();
  }

  function renderTotals() {
    const vatEnabled = $('vatToggle').checked;
    const t = InvoicePDF.calcTotals(itemsList, vatEnabled);
    $('totSubtotal').textContent = t.preDiscount.toFixed(2);
    $('rowDiscount').hidden = !(t.discount > 0.004);
    $('totDiscount').textContent = t.discount.toFixed(2);
    $('rowVat').hidden = !(t.vat > 0);
    $('totVat').textContent = t.vat.toFixed(2);
    $('totTotal').textContent = t.total.toFixed(2);
  }

  function setupItemsPanel() {
    $('catalogSelect').addEventListener('change', (e) => {
      const opt = e.target.selectedOptions[0];
      if (!opt || !opt.value) return;
      $('itDesc').value = opt.textContent;
      $('itPrice').value = opt.dataset.price;
      $('itDiscount').value = opt.dataset.discount;
      $('itNote').value = opt.dataset.note;
      editingItemIdx = null;
      $('btnAddItem').textContent = '+ Add to Invoice';
    });

    $('vatToggle').addEventListener('change', () => { renderTotals(); saveDraftToStorage(); });

    $('btnAddItem').addEventListener('click', () => {
      const description = $('itDesc').value.trim();
      const quantity = parseFloat($('itQty').value);
      const unit_price = parseFloat($('itPrice').value);
      const discount = parseFloat($('itDiscount').value || '0');
      const note = $('itNote').value.trim();
      if (!description || isNaN(quantity) || isNaN(unit_price)) {
        toast('Description, quantity and price are required', true);
        return;
      }
      DB.upsertCatalogItem({ description, unit_price, discount, note });
      populateCatalogSelect();

      const item = { description, quantity, unit_price, discount, note, amount: quantity * unit_price * (1 - discount / 100) };
      if (editingItemIdx !== null) itemsList[editingItemIdx] = item;
      else itemsList.push(item);

      clearItemForm();
      renderItemsTable();
      saveDraftToStorage();
    });
  }

  function collectInvoiceData() {
    return {
      company: DB.getSettings(),
      customer: selectedCustomer,
      invoiceNumber: currentInvoiceId ? DB.getInvoice(currentInvoiceId).invoice_number : DB.getNextInvoiceNumber(),
      issuedDate: isoToDMY($('issuedDate').value) || new Date().toLocaleDateString('en-GB').replace(/\//g, '-'),
      dueDate: isoToDMY($('dueDate').value),
      items: itemsList,
      notes: $('notesField').value.trim(),
      projectName: $('projectName').value.trim(),
      vatEnabled: $('vatToggle').checked,
    };
  }

  function setupInvoiceActions() {
    ['notesField', 'projectName', 'issuedDate', 'dueDate'].forEach((id) => {
      $(id).addEventListener('change', saveDraftToStorage);
    });

    $('btnPreviewPdf').addEventListener('click', () => {
      if (!itemsList.length) { toast('Add at least one item first', true); return; }
      InvoicePDF.preview(collectInvoiceData());
    });

    $('btnSaveInvoice').addEventListener('click', () => {
      if (!selectedCustomer) { toast('Please select or create a customer first', true); return; }
      if (!itemsList.length) { toast('Please add at least one item', true); return; }
      if (!$('dueDate').value) { toast('Please set a due date', true); return; }

      const vatEnabled = $('vatToggle').checked;
      const totals = InvoicePDF.calcTotals(itemsList, vatEnabled);
      const issuedIso = $('issuedDate').value || todayISO();

      const result = DB.saveInvoice({
        id: currentInvoiceId,
        customer_id: selectedCustomer.id,
        items: itemsList,
        notes: $('notesField').value.trim(),
        total_amount: totals.total,
        issued_date: isoToDMY(issuedIso),
        due_date: isoToDMY($('dueDate').value),
        vat_enabled: vatEnabled,
        project_name: $('projectName').value.trim(),
      });

      const data = collectInvoiceData();
      data.invoiceNumber = result.invoice_number;
      InvoicePDF.download(data, `${result.invoice_number}.pdf`);

      toast(`Invoice ${result.invoice_number} saved`);
      resetInvoiceForm(true);
      renderInvoicesTab();
    });

    $('btnResetInvoice').addEventListener('click', () => resetInvoiceForm(true));
  }

  // alsoClearStoredDraft=false is used at boot, where we want the visible form
  // blanked before we've had a chance to ask whether to restore a saved draft.
  function resetInvoiceForm(alsoClearStoredDraft = false) {
    currentInvoiceId = null;
    selectedCustomer = null;
    itemsList = [];
    editingItemIdx = null;
    $('projectName').value = '';
    $('issuedDate').value = todayISO();
    const due = new Date(); due.setDate(due.getDate() + 30);
    $('dueDate').value = due.toISOString().slice(0, 10);
    $('vatToggle').checked = false;
    $('notesField').value = '';
    $('newCustomerForm').hidden = true;
    clearItemForm();
    renderSelectedCustomer();
    renderItemsTable();
    if (alsoClearStoredDraft) clearDraftFromStorage();
  }

  // ────────────────────────────────────────────────────────────
  // Invoices tab
  // ────────────────────────────────────────────────────────────
  function renderInvoicesTab() {
    const list = DB.listInvoices();
    const cy = DB.getSettings().currency || 'AED';
    const tbody = document.querySelector('#invoicesTable tbody');
    tbody.innerHTML = '';
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="color:#999">No invoices yet.</td></tr>';
      return;
    }
    for (const inv of list) {
      const status = DB.classifyInvoice(inv);
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(inv.invoice_number)}</td>
        <td>${escapeHtml(inv.customer_name)}</td>
        <td class="num">${cy} ${inv.total_amount.toFixed(2)}</td>
        <td class="num">${inv.paid_amount > 0 ? cy + ' ' + inv.paid_amount.toFixed(2) : '—'}</td>
        <td>${inv.issued_date || '—'}</td>
        <td>${inv.due_date || '—'}</td>
        <td><span class="status-badge status-${status}">${status}</span></td>
        <td class="actions-cell">
          ${status !== 'paid' ? `<button class="btn btn-secondary btn-small" data-act="pay" data-id="${inv.id}">Record Payment</button>` : ''}
          <button class="btn btn-secondary btn-small" data-act="pdf" data-id="${inv.id}">PDF</button>
          ${inv.customer_email ? `<button class="btn btn-secondary btn-small" data-act="email" data-id="${inv.id}">Email</button>` : ''}
          <button class="btn btn-secondary btn-small" data-act="dup" data-id="${inv.id}">Duplicate</button>
          <button class="btn btn-secondary btn-small" data-act="edit" data-id="${inv.id}">Edit</button>
          <button class="btn btn-danger btn-small" data-act="del" data-id="${inv.id}">Delete</button>
        </td>`;
      tbody.appendChild(tr);
    }
    tbody.querySelectorAll('button[data-act=pay]').forEach((b) => b.addEventListener('click', () => openRecordPaymentModal(Number(b.dataset.id))));
    tbody.querySelectorAll('button[data-act=pdf]').forEach((b) => b.addEventListener('click', () => regeneratePdf(Number(b.dataset.id))));
    tbody.querySelectorAll('button[data-act=email]').forEach((b) => b.addEventListener('click', () => emailInvoice(Number(b.dataset.id))));
    tbody.querySelectorAll('button[data-act=dup]').forEach((b) => b.addEventListener('click', () => duplicateInvoice(Number(b.dataset.id))));
    tbody.querySelectorAll('button[data-act=edit]').forEach((b) => b.addEventListener('click', () => loadInvoiceForEdit(Number(b.dataset.id))));
    tbody.querySelectorAll('button[data-act=del]').forEach((b) => b.addEventListener('click', () => deleteInvoiceRow(Number(b.dataset.id))));
  }

  function pdfDataFromStoredInvoice(inv) {
    return {
      company: DB.getSettings(),
      customer: { name: inv.customer_name, email: inv.customer_email, phone: inv.customer_phone, address: inv.customer_address, trade_license: inv.customer_trade_license },
      invoiceNumber: inv.invoice_number,
      issuedDate: inv.issued_date,
      dueDate: inv.due_date,
      items: parseItemsData(inv.items_data),
      notes: inv.notes,
      projectName: inv.project_name,
      vatEnabled: !!inv.vat_enabled,
    };
  }

  function regeneratePdf(id) {
    const inv = DB.getInvoice(id);
    InvoicePDF.download(pdfDataFromStoredInvoice(inv), `${inv.invoice_number}.pdf`);
  }

  function emailInvoice(id) {
    const inv = DB.getInvoice(id);
    const company = DB.getSettings();
    const cy = company.currency || 'AED';
    const subject = `Invoice ${inv.invoice_number} from ${company.name}`;
    const body =
      `Dear Customer,\n\n` +
      `Please find attached invoice ${inv.invoice_number}.\n\n` +
      `Total Amount: ${cy} ${inv.total_amount.toFixed(2)}\n\n` +
      `Payment details:\n` +
      `IBAN: ${company.iban || ''}\n` +
      `Account: ${company.account_number || ''}\n` +
      `Swift: ${company.swift_code || ''}\n\n` +
      `Thank you for your business!\n\n` +
      `${company.name}\n${company.phone || ''}\n${company.email || ''}`;
    const url = `mailto:${inv.customer_email || ''}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    InvoicePDF.download(pdfDataFromStoredInvoice(inv), `${inv.invoice_number}.pdf`);
    window.open(url, '_blank');
    toast('Email client opened — the PDF was downloaded so you can attach it manually');
  }

  function duplicateInvoice(id) {
    const inv = DB.getInvoice(id);
    currentInvoiceId = null; // duplicating always creates a NEW invoice, unlike Edit
    selectedCustomer = { id: inv.customer_id, name: inv.customer_name, email: inv.customer_email, phone: inv.customer_phone, address: inv.customer_address, trade_license: inv.customer_trade_license };
    itemsList = parseItemsData(inv.items_data);
    $('projectName').value = inv.project_name || '';
    $('issuedDate').value = todayISO();
    const due = new Date(); due.setDate(due.getDate() + 30);
    $('dueDate').value = due.toISOString().slice(0, 10);
    $('vatToggle').checked = !!inv.vat_enabled;
    $('notesField').value = inv.notes || '';
    renderSelectedCustomer();
    renderItemsTable();
    saveDraftToStorage();
    switchToTab('invoice');
    toast(`Duplicated ${inv.invoice_number} — review and Save as a new invoice`);
  }

  function loadInvoiceForEdit(id) {
    const inv = DB.getInvoice(id);
    currentInvoiceId = id;
    selectedCustomer = { id: inv.customer_id, name: inv.customer_name, email: inv.customer_email, phone: inv.customer_phone, address: inv.customer_address, trade_license: inv.customer_trade_license };
    itemsList = parseItemsData(inv.items_data);
    $('projectName').value = inv.project_name || '';
    $('issuedDate').value = dmyToISO(inv.issued_date);
    $('dueDate').value = dmyToISO(inv.due_date);
    $('vatToggle').checked = !!inv.vat_enabled;
    $('notesField').value = inv.notes || '';
    renderSelectedCustomer();
    renderItemsTable();
    switchToTab('invoice');
    toast(`Editing ${inv.invoice_number}`);
  }

  function deleteInvoiceRow(id) {
    const inv = DB.getInvoice(id);
    if (!confirm(`Delete invoice ${inv.invoice_number}? This cannot be undone.`)) return;
    DB.deleteInvoice(id);
    renderInvoicesTab();
    toast('Invoice deleted');
  }

  function csvCell(v) {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }

  function downloadCsv(rows, filename) {
    const csv = rows.map((r) => r.map(csvCell).join(',')).join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportInvoicesCsv() {
    const list = DB.listInvoices();
    const cy = DB.getSettings().currency || 'AED';
    const rows = [['Invoice #', 'Customer', `Total (${cy})`, `Paid (${cy})`, `Remaining (${cy})`, 'Issued', 'Due', 'Status']];
    for (const inv of list) {
      const remaining = Math.max(0, inv.total_amount - inv.paid_amount);
      const status = DB.classifyInvoice(inv);
      rows.push([inv.invoice_number, inv.customer_name, inv.total_amount.toFixed(2), inv.paid_amount.toFixed(2),
        remaining.toFixed(2), inv.issued_date || '', inv.due_date || '', status.charAt(0).toUpperCase() + status.slice(1)]);
    }
    downloadCsv(rows, 'invoices_export.csv');
    toast('Invoices exported to CSV');
  }

  // ────────────────────────────────────────────────────────────
  // Customers tab
  // ────────────────────────────────────────────────────────────
  let editingCustomerId = null;

  function renderCustomersTab() {
    const list = DB.listCustomers();
    const tbody = document.querySelector('#customersTable tbody');
    tbody.innerHTML = '';
    for (const c of list) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(c.name)}</td>
        <td>${escapeHtml(c.email)}</td>
        <td>${escapeHtml(c.phone)}</td>
        <td>${escapeHtml(c.address)}</td>
        <td>${escapeHtml(c.trade_license)}</td>
        <td>
          <button class="btn btn-secondary btn-small" data-act="edit" data-id="${c.id}">Edit</button>
          <button class="btn btn-danger btn-small" data-act="del" data-id="${c.id}">Delete</button>
        </td>`;
      tbody.appendChild(tr);
    }
    tbody.querySelectorAll('button[data-act=edit]').forEach((b) => b.addEventListener('click', () => {
      const c = DB.getCustomer(Number(b.dataset.id));
      editingCustomerId = c.id;
      $('cName').value = c.name; $('cTrn').value = c.trade_license || '';
      $('cEmail').value = c.email || ''; $('cPhone').value = c.phone || ''; $('cAddress').value = c.address || '';
    }));
    tbody.querySelectorAll('button[data-act=del]').forEach((b) => b.addEventListener('click', () => {
      if (!confirm('Delete this customer? Existing invoices referencing them will keep their name but lose the link.')) return;
      DB.deleteCustomer(Number(b.dataset.id));
      renderCustomersTab();
      populateCustomerList();
    }));
  }

  function setupCustomersTab() {
    $('btnSaveCustomer').addEventListener('click', () => {
      const name = $('cName').value.trim();
      if (!name) { toast('Name is required', true); return; }
      DB.upsertCustomer({
        id: editingCustomerId,
        name,
        trade_license: $('cTrn').value.trim(),
        email: $('cEmail').value.trim(),
        phone: $('cPhone').value.trim(),
        address: $('cAddress').value.trim(),
      });
      editingCustomerId = null;
      ['cName', 'cTrn', 'cEmail', 'cPhone', 'cAddress'].forEach((id) => $(id).value = '');
      renderCustomersTab();
      populateCustomerList();
      toast('Customer saved');
    });
  }

  // ────────────────────────────────────────────────────────────
  // Item Catalog tab
  // ────────────────────────────────────────────────────────────
  let editingCatalogId = null;

  function renderCatalogTab() {
    const list = DB.listCatalogItems();
    const tbody = document.querySelector('#catalogTable tbody');
    tbody.innerHTML = '';
    for (const it of list) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(it.description)}</td>
        <td class="num">${it.unit_price.toFixed(2)}</td>
        <td class="num">${it.discount || 0}%</td>
        <td>${escapeHtml(it.note)}</td>
        <td>
          <button class="btn btn-secondary btn-small" data-act="edit" data-id="${it.id}">Edit</button>
          <button class="btn btn-danger btn-small" data-act="del" data-id="${it.id}">Delete</button>
        </td>`;
      tbody.appendChild(tr);
    }
    tbody.querySelectorAll('button[data-act=edit]').forEach((b) => b.addEventListener('click', () => {
      const it = list.find((i) => i.id === Number(b.dataset.id));
      editingCatalogId = it.id;
      $('catDesc').value = it.description; $('catPrice').value = it.unit_price;
      $('catDiscount').value = it.discount || 0; $('catNote').value = it.note || '';
    }));
    tbody.querySelectorAll('button[data-act=del]').forEach((b) => b.addEventListener('click', () => {
      if (!confirm('Delete this catalog item?')) return;
      DB.deleteCatalogItem(Number(b.dataset.id));
      renderCatalogTab();
      populateCatalogSelect();
    }));
  }

  function setupCatalogTab() {
    $('btnSaveCatalogItem').addEventListener('click', () => {
      const description = $('catDesc').value.trim();
      const unit_price = parseFloat($('catPrice').value);
      if (!description || isNaN(unit_price)) { toast('Description and price are required', true); return; }
      if (editingCatalogId) {
        DB.upsertCatalogItem({ description, unit_price, discount: parseFloat($('catDiscount').value || '0'), note: $('catNote').value.trim() });
      } else {
        DB.upsertCatalogItem({ description, unit_price, discount: parseFloat($('catDiscount').value || '0'), note: $('catNote').value.trim() });
      }
      editingCatalogId = null;
      ['catDesc', 'catPrice', 'catDiscount', 'catNote'].forEach((id) => $(id).value = id === 'catDiscount' ? '0' : '');
      renderCatalogTab();
      populateCatalogSelect();
      toast('Catalog item saved');
    });
  }

  function setupInvoicesTab() {
    $('btnExportInvoicesCsv').addEventListener('click', exportInvoicesCsv);
  }

  // ────────────────────────────────────────────────────────────
  // Earnings tab
  // ────────────────────────────────────────────────────────────
  let lastEarningsData = null;
  let lastEarningsRange = null;

  function calculateEarnings() {
    const fromIso = $('earningsFrom').value, toIso = $('earningsTo').value;
    if (!fromIso || !toIso) { toast('Pick both a from and to date', true); return; }
    const fromDMY = isoToDMY(fromIso), toDMY = isoToDMY(toIso);
    if (fromIso > toIso) { toast('From date must be before To date', true); return; }

    const data = DB.getInvoicesInRange(fromDMY, toDMY);
    lastEarningsData = data;
    lastEarningsRange = { fromDt: DB.parseDMY(fromDMY), toDt: DB.parseDMY(toDMY) };

    const cy = DB.getSettings().currency || 'AED';
    $('earnCount').textContent = String(data.invoices.length);
    $('earnTotal').textContent = `${cy} ${data.totalAmt.toFixed(2)}`;
    $('earnPaid').textContent = `${cy} ${data.paidAmt.toFixed(2)}`;
    $('earnUnpaid').textContent = `${cy} ${data.unpaidAmt.toFixed(2)}`;
    $('earningsSummary').hidden = false;

    const tbody = document.querySelector('#earningsTable tbody');
    tbody.innerHTML = '';
    if (!data.invoices.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="color:#999">No invoices in this date range.</td></tr>';
    } else {
      for (const inv of data.invoices) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(inv.invoice_number)}</td>
          <td>${escapeHtml(inv.customer_name)}</td>
          <td>${inv.issued_date || ''}</td>
          <td class="num">${cy} ${inv.total_amount.toFixed(2)}</td>
          <td><span class="status-badge ${inv.paid ? 'status-paid' : 'status-unpaid'}">${inv.paid ? 'Paid' : 'Unpaid'}</span></td>`;
        tbody.appendChild(tr);
      }
    }
    $('earningsTable').hidden = false;
    $('earningsExportRow').hidden = false;
  }

  function setupEarningsTab() {
    const now = new Date();
    $('earningsFrom').value = `${now.getFullYear()}-01-01`;
    $('earningsTo').value = todayISO();

    $('btnCalculateEarnings').addEventListener('click', calculateEarnings);

    $('btnExportEarningsPdf').addEventListener('click', () => {
      if (!lastEarningsData) calculateEarnings();
      if (!lastEarningsData) return;
      const { fromDt, toDt } = lastEarningsRange;
      const filename = `Earnings_${fromDt.toISOString().slice(0, 10).replace(/-/g, '')}_${toDt.toISOString().slice(0, 10).replace(/-/g, '')}.pdf`;
      EarningsPDF.download({ company: DB.getSettings(), fromDt, toDt, data: lastEarningsData }, filename);
    });

    $('btnExportEarningsCsv').addEventListener('click', () => {
      if (!lastEarningsData) calculateEarnings();
      if (!lastEarningsData) return;
      const cy = DB.getSettings().currency || 'AED';
      const rows = [['Invoice #', 'Customer', 'Issued', `Amount (${cy})`, 'Status']];
      for (const inv of lastEarningsData.invoices) {
        rows.push([inv.invoice_number, inv.customer_name, inv.issued_date || '', inv.total_amount.toFixed(2), inv.paid ? 'Paid' : 'Unpaid']);
      }
      rows.push([]);
      rows.push(['', '', 'Total', lastEarningsData.totalAmt.toFixed(2), '']);
      rows.push(['', '', 'Paid', lastEarningsData.paidAmt.toFixed(2), '']);
      rows.push(['', '', 'Unpaid', lastEarningsData.unpaidAmt.toFixed(2), '']);
      const { fromDt, toDt } = lastEarningsRange;
      downloadCsv(rows, `Earnings_${fromDt.toISOString().slice(0, 10).replace(/-/g, '')}_${toDt.toISOString().slice(0, 10).replace(/-/g, '')}.csv`);
    });
  }

  // ────────────────────────────────────────────────────────────
  // Settings tab
  // ────────────────────────────────────────────────────────────
  const SETTINGS_FIELD_MAP = {
    sName: 'name', sAddress: 'address', sPhone: 'phone', sEmail: 'email', sTrn: 'trade_license',
    sBankName: 'bank_name', sBeneficiary: 'beneficiary', sAccountNumber: 'account_number',
    sIban: 'iban', sRoutingCode: 'routing_code', sSwiftCode: 'swift_code', sCurrency: 'currency',
  };
  let pendingLogoDataUrl = undefined; // undefined = unchanged, null = cleared, string = new

  function renderSettingsTab() {
    const s = DB.getSettings();
    for (const [elId, key] of Object.entries(SETTINGS_FIELD_MAP)) $(elId).value = s[key] || '';
    pendingLogoDataUrl = undefined;
    if (s.logo_path) {
      $('sLogoPreview').src = s.logo_path;
      $('sLogoPreview').hidden = false;
    } else {
      $('sLogoPreview').hidden = true;
    }
  }

  function setupSettingsTab() {
    $('sLogoFile').addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        pendingLogoDataUrl = reader.result;
        $('sLogoPreview').src = reader.result;
        $('sLogoPreview').hidden = false;
      };
      reader.readAsDataURL(file);
    });

    $('btnClearLogo').addEventListener('click', () => {
      pendingLogoDataUrl = null;
      $('sLogoPreview').hidden = true;
      $('sLogoFile').value = '';
    });

    $('btnSaveSettings').addEventListener('click', () => {
      const name = $('sName').value.trim();
      if (!name) { toast('Company name is required', true); return; }
      const obj = {};
      for (const [elId, key] of Object.entries(SETTINGS_FIELD_MAP)) obj[key] = $(elId).value.trim();
      if (pendingLogoDataUrl === null) obj.logo_path = '';
      else if (typeof pendingLogoDataUrl === 'string') obj.logo_path = pendingLogoDataUrl;
      // else unchanged: don't touch logo_path
      if (obj.logo_path === undefined) {
        const current = DB.getSettings();
        obj.logo_path = current.logo_path || '';
      }
      DB.saveSettings(obj);
      refreshDbStatus();
      toast('Settings saved');
    });
  }

  // ────────────────────────────────────────────────────────────
  // Boot
  // ────────────────────────────────────────────────────────────
  async function boot() {
    setupTabs();
    setupTopbar();
    setupModal();
    setupCustomerPanel();
    setupItemsPanel();
    setupInvoiceActions();
    setupCustomersTab();
    setupCatalogTab();
    setupInvoicesTab();
    setupEarningsTab();
    setupSettingsTab();

    await DB.init();

    const auto = await DB.loadAutosave();
    if (auto && auto.bytes && confirm('An unsaved session was found from your last visit. Restore it?')) {
      DB.loadDatabase(auto.bytes.buffer ? auto.bytes.buffer : auto.bytes, auto.fileName);
      DB.markDirty();
    } else {
      DB.newDatabase();
    }

    refreshAll();
    checkDraftOnBoot();
  }

  boot();
})();
