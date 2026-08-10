# Invoicing App - Enhanced Version

## Browser Version

A fully client-side browser edition now lives in [`docs/`](docs/) — no install, no server, no account. It runs entirely in your browser using [sql.js](https://sql.js.org) (SQLite compiled to WebAssembly), so your database stays a local `.db` file on your computer that you explicitly load and save; nothing is ever uploaded anywhere.

- **Try it locally:** `cd docs && python3 -m http.server 8000`, then open `http://localhost:8000`.
- **Load your existing data:** click **Load Database** and pick your `invoices.db` — the schema is fully compatible with the desktop app's database.
- **Save Database** writes straight back to the same file (in Chrome/Edge/Brave); **Save As…** exports a separate copy without touching the file you have open.

See [`docs/`](docs/) for the full feature set (dashboard, invoices, customers, item catalog, earnings report, payment tracking, PDF export).

## Features

✅ **Database Storage** - SQLite database to store all invoices
✅ **PDF Generation** - Generate professional PDF invoices
✅ **Invoice Preview** - Preview formatted invoices before saving
✅ **Edit/Delete** - View, manage, and delete saved invoices
✅ **Automatic Calculations** - Quantity, tax, and totals computed automatically
✅ **Auto-numbering** - Invoices numbered as INV-0001, INV-0002, etc.

## Installation

### 1. Install Required Dependencies

```bash
pip install reportlab
```

`tkinter` and `sqlite3` are included with Python by default.

### 2. Run the Application

```bash
cd d:\CODE\INVOICE
python invoicing_app.py
```

## How to Use

1. **New Invoice**: Click "File" → "New Invoice" to reset for a new invoice
2. **Enter Customer**: Click "Customer" button to enter customer details
3. **Add Items**: Click "Items" button to add line items (can add multiple)
4. **Add Notes**: Click "Note" button to add any additional notes
5. **Preview**: Click "Preview Invoice" to see formatted invoice
6. **Save & Generate PDF**: Click "Save & Generate PDF" to save and create PDF file
7. **View Invoices**: Click "File" → "View All Invoices" to see all saved invoices
8. **Delete/View PDF**: Select an invoice and click "View PDF" or "Delete"

## Files Generated

- **invoices.db** - SQLite database containing all invoice data
- **invoices/** - Folder containing generated PDF files (INV-XXXX.pdf)

## Database Schema

### customers table
- id (Primary Key)
- name
- email
- phone
- address

### invoices table
- id (Primary Key)
- invoice_number (Unique)
- customer_id (Foreign Key)
- items_data (JSON string)
- notes
- total_amount
- created_at (Timestamp)

## Features in Detail

### Multiple Items Support
Add multiple line items to a single invoice. Each item can have:
- Description
- Quantity
- Unit Price
- Tax Percentage

### Automatic Calculations
- Item amounts calculated as: Quantity × Unit Price
- Tax calculated per item: Item Amount × Tax %
- Total = Sum of all items + Sum of all taxes

### PDF Export
Professional PDF invoices include:
- Invoice number and date
- Customer information
- Itemized table with quantities, prices, and taxes
- Subtotal, tax total, and grand total
- Additional notes (if any)

### Invoice Management
- View all invoices with customer names and amounts
- Open saved PDFs directly from the application
- Delete invoices (removes from database)
- Sort by date (newest first)

## Notes

- The app creates an `invoices` folder automatically if it doesn't exist
- Each invoice is assigned a unique invoice number
- Customer information is stored separately for potential future use/reuse
- PDFs are saved with the invoice number as filename (e.g., INV-0001.pdf)

