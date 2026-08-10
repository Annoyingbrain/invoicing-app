/* SQLite (sql.js) wrapper: schema, load/save, CRUD helpers, IndexedDB autosave. */

const DB = (() => {
  let SQL = null;
  let db = null;
  let currentFileName = 'invoices.db';
  let dirty = false;

  const DEFAULT_SETTINGS = {
    name: "My Company",
    address: "",
    phone: "",
    email: "",
    trade_license: "",
    bank_name: "",
    beneficiary: "",
    account_number: "",
    iban: "",
    routing_code: "",
    swift_code: "",
    currency: "AED",
    logo_path: "", // base64 data URL in the browser build
  };

  const SCHEMA = `
    CREATE TABLE IF NOT EXISTS customers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT,
      phone TEXT,
      address TEXT,
      trade_license TEXT
    );
    CREATE TABLE IF NOT EXISTS invoices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      invoice_number TEXT UNIQUE,
      customer_id INTEGER,
      items_data TEXT,
      notes TEXT,
      total_amount REAL,
      issued_date TEXT,
      due_date TEXT,
      created_at TEXT,
      pdf_path TEXT,
      paid INTEGER DEFAULT 0,
      paid_amount REAL DEFAULT 0,
      vat_enabled INTEGER DEFAULT 0,
      project_name TEXT,
      FOREIGN KEY (customer_id) REFERENCES customers(id)
    );
    CREATE TABLE IF NOT EXISTS items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      description TEXT NOT NULL,
      unit_price REAL DEFAULT 0,
      discount REAL DEFAULT 0,
      note TEXT
    );
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    );
  `;

  async function init() {
    SQL = await initSqlJs({ locateFile: (f) => `lib/${f}` });
  }

  function markDirty() {
    dirty = true;
    document.dispatchEvent(new CustomEvent('db:dirty'));
    autosaveToIndexedDB();
  }

  function markClean() {
    dirty = false;
    document.dispatchEvent(new CustomEvent('db:clean'));
  }

  function isDirty() { return dirty; }
  function getFileName() { return currentFileName; }

  function ensureSchema() {
    db.exec(SCHEMA);
    const count = db.exec("SELECT COUNT(*) FROM settings")[0].values[0][0];
    if (count === 0) {
      const stmt = db.prepare("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)");
      for (const [k, v] of Object.entries(DEFAULT_SETTINGS)) {
        stmt.run([k, v]);
      }
      stmt.free();
    }
  }

  // The handle of the file currently loaded/saved, when the File System Access
  // API is available. Kept so "Save Database" can write straight back to the
  // same file with no dialog, the way a desktop app would.
  let fileHandle = null;
  function canUseFsAccess() { return !!window.showOpenFilePicker; }
  function hasFileHandle() { return !!fileHandle; }

  function newDatabase() {
    db = new SQL.Database();
    ensureSchema();
    currentFileName = 'invoices.db';
    fileHandle = null;
    markClean();
  }

  function loadDatabase(arrayBuffer, fileName) {
    db = new SQL.Database(new Uint8Array(arrayBuffer));
    ensureSchema();
    currentFileName = fileName || 'invoices.db';
    fileHandle = null; // plain <input type=file> path: no handle to write back to
    markClean();
  }

  async function loadDatabaseFromPicker() {
    const [handle] = await window.showOpenFilePicker({
      types: [{ description: 'SQLite Database', accept: { 'application/x-sqlite3': ['.db', '.sqlite', '.sqlite3'] } }],
    });
    const file = await handle.getFile();
    const buf = await file.arrayBuffer();
    db = new SQL.Database(new Uint8Array(buf));
    ensureSchema();
    currentFileName = handle.name;
    fileHandle = handle;
    // Ask for write access up front so a later "Save Database" doesn't need a dialog.
    try { await handle.requestPermission({ mode: 'readwrite' }); } catch (e) { /* keep read-only handle */ }
    markClean();
  }

  function exportBytes() {
    return db.export();
  }

  async function writeBytesToHandle(handle, bytes) {
    const perm = await handle.requestPermission({ mode: 'readwrite' });
    if (perm !== 'granted') throw new Error('Write permission denied');
    const writable = await handle.createWritable();
    await writable.write(bytes);
    await writable.close();
  }

  function downloadBytes(bytes, fileName) {
    const blob = new Blob([bytes], { type: 'application/x-sqlite3' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName || 'invoices.db';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // Save Database: overwrite the file we loaded/last saved to, silently if possible.
  async function saveDatabase() {
    const bytes = exportBytes();
    if (fileHandle) {
      try {
        await writeBytesToHandle(fileHandle, bytes);
        markClean();
        return;
      } catch (e) {
        if (e.name === 'AbortError') return;
        // permission revoked or handle stale — fall through to a fresh save-as prompt
      }
    }
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: currentFileName,
          types: [{ description: 'SQLite Database', accept: { 'application/x-sqlite3': ['.db'] } }],
        });
        await writeBytesToHandle(handle, bytes);
        currentFileName = handle.name;
        fileHandle = handle;
        markClean();
        return;
      } catch (e) {
        if (e.name === 'AbortError') return;
      }
    }
    downloadBytes(bytes, currentFileName);
    markClean();
  }

  // Save As: write a copy to a new file without changing what "Save Database" targets.
  async function saveDatabaseAs() {
    const bytes = exportBytes();
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: currentFileName,
          types: [{ description: 'SQLite Database', accept: { 'application/x-sqlite3': ['.db'] } }],
        });
        await writeBytesToHandle(handle, bytes);
        return true;
      } catch (e) {
        if (e.name === 'AbortError') return false;
        throw e;
      }
    }
    downloadBytes(bytes, currentFileName);
    return true;
  }

  // ---- IndexedDB autosave (crash-recovery net) ----
  const IDB_NAME = 'invoicing-app-autosave';
  const IDB_STORE = 'db';
  let idbTimer = null;

  function openIdb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function autosaveToIndexedDB() {
    clearTimeout(idbTimer);
    idbTimer = setTimeout(async () => {
      try {
        const idb = await openIdb();
        const tx = idb.transaction(IDB_STORE, 'readwrite');
        tx.objectStore(IDB_STORE).put({ bytes: exportBytes(), fileName: currentFileName, savedAt: Date.now() }, 'current');
        idb.close();
      } catch (e) {
        console.warn('Autosave failed', e);
      }
    }, 600);
  }

  async function loadAutosave() {
    try {
      const idb = await openIdb();
      const tx = idb.transaction(IDB_STORE, 'readonly');
      const req = tx.objectStore(IDB_STORE).get('current');
      const result = await new Promise((resolve, reject) => {
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      idb.close();
      return result || null;
    } catch (e) {
      return null;
    }
  }

  // ---- Query helpers ----
  function all(sql, params = []) {
    const stmt = db.prepare(sql);
    stmt.bind(params);
    const rows = [];
    while (stmt.step()) rows.push(stmt.getAsObject());
    stmt.free();
    return rows;
  }

  function run(sql, params = []) {
    db.run(sql, params);
    markDirty();
  }

  function lastInsertId() {
    return db.exec("SELECT last_insert_rowid()")[0].values[0][0];
  }

  // ---- Settings ----
  function getSettings() {
    const rows = all("SELECT key, value FROM settings");
    const out = { ...DEFAULT_SETTINGS };
    for (const r of rows) out[r.key] = r.value;
    return out;
  }

  function saveSettings(obj) {
    const stmt = db.prepare("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value");
    for (const [k, v] of Object.entries(obj)) stmt.run([k, v ?? '']);
    stmt.free();
    markDirty();
  }

  // ---- Customers ----
  function listCustomers(search = '') {
    if (search) {
      return all("SELECT * FROM customers WHERE name LIKE ? ORDER BY name", [`%${search}%`]);
    }
    return all("SELECT * FROM customers ORDER BY name");
  }

  function getCustomer(id) {
    const rows = all("SELECT * FROM customers WHERE id=?", [id]);
    return rows[0] || null;
  }

  function upsertCustomer(c) {
    if (c.id) {
      run("UPDATE customers SET name=?, email=?, phone=?, address=?, trade_license=? WHERE id=?",
        [c.name, c.email || '', c.phone || '', c.address || '', c.trade_license || '', c.id]);
      return c.id;
    } else {
      run("INSERT INTO customers (name, email, phone, address, trade_license) VALUES (?, ?, ?, ?, ?)",
        [c.name, c.email || '', c.phone || '', c.address || '', c.trade_license || '']);
      return lastInsertId();
    }
  }

  function deleteCustomer(id) {
    run("DELETE FROM customers WHERE id=?", [id]);
  }

  // ---- Item catalog ----
  function listCatalogItems() {
    return all("SELECT * FROM items ORDER BY description");
  }

  function upsertCatalogItem(item) {
    const existing = all("SELECT id FROM items WHERE description=?", [item.description]);
    if (existing.length) {
      run("UPDATE items SET unit_price=?, discount=?, note=? WHERE id=?",
        [item.unit_price, item.discount || 0, item.note || '', existing[0].id]);
      return existing[0].id;
    } else {
      run("INSERT INTO items (description, unit_price, discount, note) VALUES (?, ?, ?, ?)",
        [item.description, item.unit_price, item.discount || 0, item.note || '']);
      return lastInsertId();
    }
  }

  function deleteCatalogItem(id) {
    run("DELETE FROM items WHERE id=?", [id]);
  }

  // ---- Invoices ----
  function getNextInvoiceNumber() {
    const rows = all("SELECT COALESCE(MAX(CAST(SUBSTR(invoice_number, 5) AS INTEGER)), 0) AS m FROM invoices");
    return `INV-${String(rows[0].m + 1).padStart(4, '0')}`;
  }

  function saveInvoice(inv) {
    const itemsJson = JSON.stringify(inv.items);
    if (inv.id) {
      run(`UPDATE invoices SET customer_id=?, items_data=?, notes=?, total_amount=?,
             issued_date=?, due_date=?, vat_enabled=?, project_name=? WHERE id=?`,
        [inv.customer_id, itemsJson, inv.notes || '', inv.total_amount,
         inv.issued_date, inv.due_date, inv.vat_enabled ? 1 : 0, inv.project_name || '', inv.id]);
      return { id: inv.id, invoice_number: inv.invoice_number };
    } else {
      const invoice_number = getNextInvoiceNumber();
      const created_at = new Date().toISOString().slice(0, 19).replace('T', ' ');
      run(`INSERT INTO invoices
            (invoice_number, customer_id, items_data, notes, total_amount,
             issued_date, due_date, created_at, paid, paid_amount, vat_enabled, project_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)`,
        [invoice_number, inv.customer_id, itemsJson, inv.notes || '', inv.total_amount,
         inv.issued_date, inv.due_date, created_at, inv.vat_enabled ? 1 : 0, inv.project_name || '']);
      return { id: lastInsertId(), invoice_number };
    }
  }

  function recordPayment(invoiceId, amount) {
    const inv = all("SELECT total_amount, COALESCE(paid_amount,0) AS paid_amount FROM invoices WHERE id=?", [invoiceId])[0];
    const newPaid = Math.min(inv.total_amount, inv.paid_amount + amount);
    run("UPDATE invoices SET paid_amount=?, paid=? WHERE id=?",
      [newPaid, newPaid >= inv.total_amount ? 1 : 0, invoiceId]);
  }

  function markFullyPaid(invoiceId) {
    run("UPDATE invoices SET paid_amount=total_amount, paid=1 WHERE id=?", [invoiceId]);
  }

  function listInvoices() {
    return all(`
      SELECT i.id, i.invoice_number, c.name AS customer_name, c.email AS customer_email,
             i.total_amount, i.issued_date, i.due_date, COALESCE(i.paid_amount,0) AS paid_amount,
             i.customer_id, COALESCE(i.vat_enabled,0) AS vat_enabled, i.notes, i.items_data,
             COALESCE(i.project_name,'') AS project_name
      FROM invoices i JOIN customers c ON i.customer_id = c.id
      ORDER BY i.id DESC
    `);
  }

  function getInvoice(id) {
    const rows = all(`
      SELECT i.*, c.name AS customer_name, c.email AS customer_email,
             c.phone AS customer_phone, c.address AS customer_address,
             c.trade_license AS customer_trade_license
      FROM invoices i JOIN customers c ON i.customer_id = c.id
      WHERE i.id=?`, [id]);
    return rows[0] || null;
  }

  function deleteInvoice(id) {
    run("DELETE FROM invoices WHERE id=?", [id]);
  }

  function parseDMY(str) {
    if (!str) return null;
    const [d, m, y] = str.split('-').map(Number);
    if (!d || !m || !y) return null;
    return new Date(y, m - 1, d);
  }

  function classifyInvoice(inv, today = new Date()) {
    const total = inv.total_amount, paidAmt = inv.paid_amount || 0;
    if (paidAmt >= total) return 'paid';
    let pastDue = false;
    const due = parseDMY(inv.due_date);
    if (due) pastDue = due < new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (pastDue) return 'overdue';
    if (paidAmt > 0) return 'partial';
    return 'unpaid';
  }

  function getDashboardStats() {
    const rows = all("SELECT total_amount, issued_date, COALESCE(paid_amount,0) AS paid_amount, due_date FROM invoices");
    const today = new Date();
    const curYear = today.getFullYear(), curMonth = today.getMonth();
    let thisMonthTotal = 0, outstanding = 0, overdueTotal = 0, allTimeTotal = 0;
    for (const r of rows) {
      allTimeTotal += r.total_amount;
      const remaining = Math.max(0, r.total_amount - r.paid_amount);
      if (remaining > 0) {
        outstanding += remaining;
        const due = parseDMY(r.due_date);
        if (due && due < new Date(curYear, curMonth, today.getDate())) overdueTotal += remaining;
      }
      const issued = parseDMY(r.issued_date);
      if (issued && issued.getFullYear() === curYear && issued.getMonth() === curMonth) thisMonthTotal += r.total_amount;
    }
    return { thisMonthTotal, outstanding, overdueTotal, allTimeTotal, invoiceCount: rows.length };
  }

  function getInvoicesInRange(fromDMY, toDMY) {
    const fromDt = parseDMY(fromDMY), toDt = parseDMY(toDMY);
    const rows = all(`
      SELECT i.invoice_number, c.name AS customer_name, i.issued_date, i.total_amount,
             COALESCE(i.paid_amount,0) AS paid_amount, COALESCE(i.paid,0) AS paid
      FROM invoices i JOIN customers c ON i.customer_id = c.id
    `);
    const inRange = rows.filter((r) => {
      const d = parseDMY(r.issued_date);
      return d && fromDt && toDt && d >= fromDt && d <= toDt;
    });
    inRange.sort((a, b) => (a.paid - b.paid) || (parseDMY(a.issued_date) - parseDMY(b.issued_date)));
    const totalAmt = inRange.reduce((s, r) => s + r.total_amount, 0);
    const paidAmt = inRange.reduce((s, r) => s + (r.paid ? r.total_amount : 0), 0);
    const unpaidAmt = totalAmt - paidAmt;
    return { invoices: inRange, totalAmt, paidAmt, unpaidAmt };
  }

  return {
    init, newDatabase, loadDatabase, loadDatabaseFromPicker,
    saveDatabase, saveDatabaseAs, exportBytes,
    canUseFsAccess, hasFileHandle,
    isDirty, markDirty, markClean, getFileName,
    loadAutosave,
    getSettings, saveSettings,
    listCustomers, getCustomer, upsertCustomer, deleteCustomer,
    listCatalogItems, upsertCatalogItem, deleteCatalogItem,
    getNextInvoiceNumber, saveInvoice, listInvoices, getInvoice, deleteInvoice,
    recordPayment, markFullyPaid,
    classifyInvoice, getDashboardStats, getInvoicesInRange, parseDMY,
  };
})();
