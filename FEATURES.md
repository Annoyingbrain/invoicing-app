# Enhanced Features Added

## 1. Database Storage ✓
- **SQLite database** (`invoices.db`) stores all invoice data persistently
- **Customers table**: Stores customer details (name, email, phone, address)
- **Invoices table**: Stores invoice records with items, notes, totals, and timestamps
- Auto-generated invoice numbers (INV-0001, INV-0002, etc.)

## 2. PDF Generation ✓
- **Professional PDF output** using reportlab library
- PDFs stored in `invoices/` folder
- Each PDF includes:
  - Invoice number and creation date
  - Customer information
  - Itemized table with descriptions, quantities, prices, taxes
  - Subtotal, tax total, and grand total
  - Optional notes section
- Beautiful formatting with headers, tables, and styled text

## 3. Invoice Preview ✓
- **Preview Invoice** button shows formatted invoice before saving
- Displays all calculations and formatting
- Text-based preview in new window
- Allows verification before committing to database

## 4. Edit/Delete Functionality ✓
- **View All Invoices** menu option shows all saved invoices
- Displays invoice number, customer name, total amount, and date
- **View PDF** button opens the saved PDF file
- **Delete** button removes invoice from database
- Tree view table for easy browsing

## 5. Multiple Items Support ✓
- Add multiple line items to a single invoice
- Each item supports:
  - Description
  - Quantity (decimal support)
  - Unit Price
  - Tax percentage (individual per item)
- Items are accumulated in a list

## 6. Automatic Calculations ✓
- Calculate item amounts: Quantity × Unit Price
- Calculate per-item tax: Item Amount × Tax %
- Calculate totals: Sum of all items + Sum of all taxes
- All calculations done with proper decimal precision

## 7. Enhanced UI ✓
- Menu bar with File menu
- New Invoice action to reset form
- Five buttons on main window:
  - Customer (light blue)
  - Items (light green)
  - Note (light yellow)
  - Preview Invoice (light coral)
  - Save & Generate PDF (light sky blue)
- Professional dialog windows for data entry
- Treeview widget for invoice list display

## 8. Input Validation ✓
- Required field validation (customer name, items)
- Numeric validation for quantity, price, and tax
- Error messages for invalid inputs
- User-friendly feedback messages

## Database Initialization ✓
- Automatic database and table creation on first run
- Folder creation for PDF storage
- No manual setup required

## Menu Options ✓
- File → New Invoice
- File → View All Invoices
- File → Exit

All features are fully implemented and integrated into the application!
