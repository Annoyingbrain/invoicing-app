import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog, ttk
import sqlite3
import os
import sys
import json
import csv
import tempfile
import webbrowser
import urllib.parse
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image as RLImage
from reportlab.lib import colors

class InvoicingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Invoicing App — MarLoN Creative Solutions")
        self.root.geometry("820x860")
        self.root.configure(bg='#f0f4f8')

        if getattr(sys, 'frozen', False):
            _app_dir = os.path.dirname(sys.executable)
        else:
            _app_dir = os.path.dirname(os.path.abspath(__file__))

        self.db_file       = os.path.join(_app_dir, "invoices.db")
        self.invoices_folder = os.path.join(_app_dir, "invoices")
        self.draft_file    = os.path.join(_app_dir, "draft.json")

        # defaults — overwritten by load_company_settings after DB init
        self.company_info = {
            "name":           "MarLoN Creative Solutions (FZC)",
            "address":        "Hub Canal 1, apt 706, Sport City, Dubai, AE",
            "phone":          "+971 58 553 7339",
            "email":          "k.marko86@gmail.com",
            "trade_license":  "104949492300001",
            "bank_name":      "Emirates NBD",
            "beneficiary":    "Lorino Nosova",
            "account_number": "0214396942502",
            "iban":           "AE610260000214396942502",
            "routing_code":   "302620122",
            "swift_code":     "EBILAEAD",
            "currency":       "AED",
            "logo_path":      "",
        }

        self.primary_color = '#2c3e50'
        self.accent_color  = '#3498db'
        self.success_color = '#27ae60'
        self.warning_color = '#e74c3c'

        # invoice build state
        self.vat_enabled        = False
        self.dashboard_labels   = {}
        self._vat_subtitle_lbl  = None
        self._header_title_lbl  = None
        self._edit_banner_lbl   = None
        self._reset_invoice_state()

        self.init_database()
        self.load_company_settings()
        self.create_invoices_folder()
        self.create_menu()
        self.create_buttons()
        self.update_dashboard()
        self.check_draft()

    def _reset_invoice_state(self):
        self.customer_data     = None
        self.items_data_list   = []
        self.notes_data        = None
        self.project_name      = None
        self.current_invoice_id = None
        self.issued_date       = None
        self.due_date          = None
        self.vat_enabled       = False
    
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                address TEXT,
                trade_license TEXT
            )
        ''')

        cursor.execute('''
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
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                unit_price REAL DEFAULT 0,
                discount REAL DEFAULT 0,
                note TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cursor.execute("PRAGMA table_info(invoices)")
        columns = [col[1] for col in cursor.fetchall()]
        for col, defn in [
            ('issued_date',  'TEXT'),
            ('due_date',     'TEXT'),
            ('pdf_path',     'TEXT'),
            ('paid',         'INTEGER DEFAULT 0'),
            ('paid_amount',  'REAL DEFAULT 0'),
            ('vat_enabled',  'INTEGER DEFAULT 0'),
            ('project_name', 'TEXT'),
        ]:
            if col not in columns:
                cursor.execute(f'ALTER TABLE invoices ADD COLUMN {col} {defn}')

        cursor.execute("PRAGMA table_info(customers)")
        cust_columns = [col[1] for col in cursor.fetchall()]
        if 'trade_license' not in cust_columns:
            cursor.execute('ALTER TABLE customers ADD COLUMN trade_license TEXT')

        cursor.execute("PRAGMA table_info(items)")
        item_cols = [col[1] for col in cursor.fetchall()]
        if 'tax' in item_cols and 'discount' not in item_cols:
            try:
                cursor.execute('ALTER TABLE items RENAME COLUMN tax TO discount')
            except Exception:
                cursor.execute('ALTER TABLE items ADD COLUMN discount REAL DEFAULT 0')
                cursor.execute('UPDATE items SET discount = tax')

        # seed settings from hardcoded defaults if table is empty
        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            for k, v in self.company_info.items():
                cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        conn.commit()
        conn.close()

    def load_company_settings(self):
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        conn.close()
        for k, v in rows:
            self.company_info[k] = v or ''

    def save_company_settings_to_db(self, d):
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        for k, v in d.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
        conn.close()
        self.company_info.update(d)
    
    # ── Draft save / restore ────────────────────────────────────────
    def save_draft(self):
        try:
            d = {
                'customer_data':   self.customer_data,
                'items_data_list': self.items_data_list,
                'notes_data':      self.notes_data,
                'project_name':    self.project_name,
                'issued_date':     self.issued_date,
                'due_date':        self.due_date,
                'vat_enabled':     self.vat_enabled,
            }
            with open(self.draft_file, 'w', encoding='utf-8') as f:
                json.dump(d, f)
        except Exception:
            pass

    def clear_draft(self):
        try:
            if os.path.exists(self.draft_file):
                os.remove(self.draft_file)
        except Exception:
            pass

    def check_draft(self):
        if not os.path.exists(self.draft_file):
            return
        try:
            with open(self.draft_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if not d.get('customer_data') and not d.get('items_data_list'):
                return
            cust = d.get('customer_data', {})
            cname = cust.get('name', '?') if cust else '?'
            nitems = len(d.get('items_data_list', []))
            if messagebox.askyesno(
                "Restore Draft",
                f"An unsaved draft was found:\n  Customer: {cname}\n  Items: {nitems}\n\nRestore it?"
            ):
                self.customer_data   = d.get('customer_data')
                self.items_data_list = d.get('items_data_list', [])
                self.notes_data      = d.get('notes_data')
                self.project_name    = d.get('project_name')
                self.issued_date     = d.get('issued_date')
                self.due_date        = d.get('due_date')
                self.vat_enabled     = d.get('vat_enabled', False)
                self._refresh_vat_subtitle()
        except Exception:
            pass

    def _refresh_vat_subtitle(self):
        if self._vat_subtitle_lbl:
            state = "ON (5%)" if self.vat_enabled else "OFF"
            self._vat_subtitle_lbl.config(text=f"VAT 5% is currently: {state}")

    # ── Company settings dialog ──────────────────────────────────────
    def settings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Company Settings")
        dlg.geometry("560x620")
        dlg.resizable(False, False)
        dlg.configure(bg='#f5f5f5')

        tk.Frame(dlg, bg=self.primary_color).pack(fill=tk.X)
        tk.Label(dlg.winfo_children()[-1], text="⚙️ Company Settings",
                 font=("Segoe UI", 14, "bold"), bg=self.primary_color,
                 fg='white', pady=14).pack()

        nb = ttk.Notebook(dlg)
        nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        def make_tab(label):
            f = tk.Frame(nb, bg='#f5f5f5')
            nb.add(f, text=label)
            return f

        def field_row(parent, label, key, row, secret=False):
            tk.Label(parent, text=label, font=("Segoe UI", 9),
                     bg='#f5f5f5', fg=self.primary_color).grid(
                row=row, column=0, sticky='w', pady=(8, 2), padx=(8, 4))
            e = tk.Entry(parent, width=38, font=("Segoe UI", 10),
                         relief=tk.FLAT, bg='white', bd=1,
                         show='*' if secret else '')
            e.grid(row=row, column=1, sticky='ew', pady=(8, 2), padx=(0, 8), ipady=6)
            e.insert(0, self.company_info.get(key, ''))
            return e

        # Tab 1 — Company
        t1 = make_tab("Company")
        t1.columnconfigure(1, weight=1)
        fields_t1 = [
            ("Company Name:",    "name"),
            ("Address:",         "address"),
            ("Phone:",           "phone"),
            ("Email:",           "email"),
            ("TRN:",   "trade_license"),
        ]
        entries_t1 = {k: field_row(t1, lbl, k, i) for i, (lbl, k) in enumerate(fields_t1)}

        # Tab 2 — Banking
        t2 = make_tab("Banking")
        t2.columnconfigure(1, weight=1)
        fields_t2 = [
            ("Bank Name:",       "bank_name"),
            ("Beneficiary:",     "beneficiary"),
            ("Account Number:",  "account_number"),
            ("IBAN:",            "iban"),
            ("Routing Code:",    "routing_code"),
            ("Swift Code:",      "swift_code"),
            ("Currency:",        "currency"),
        ]
        entries_t2 = {k: field_row(t2, lbl, k, i) for i, (lbl, k) in enumerate(fields_t2)}

        # Tab 3 — Appearance (logo)
        t3 = make_tab("Appearance")
        t3.columnconfigure(1, weight=1)
        tk.Label(t3, text="Logo file (PNG/JPG):", font=("Segoe UI", 9),
                 bg='#f5f5f5', fg=self.primary_color).grid(
            row=0, column=0, sticky='w', pady=(14, 2), padx=(8, 4))
        logo_var = tk.StringVar(value=self.company_info.get('logo_path', ''))
        logo_entry = tk.Entry(t3, textvariable=logo_var, width=30, font=("Segoe UI", 9),
                              relief=tk.FLAT, bg='white', bd=1)
        logo_entry.grid(row=0, column=1, sticky='ew', pady=(14, 2), padx=(0, 4), ipady=6)

        def browse_logo():
            path = filedialog.askopenfilename(
                filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
                parent=dlg)
            if path:
                logo_var.set(path)

        self.create_styled_button(t3, text="Browse…", command=browse_logo,
                                  bg=self.accent_color, width=9, height=1).grid(
            row=0, column=2, padx=4, pady=(14, 2))

        tk.Label(t3, text="Shown in the top-left corner of generated PDFs.",
                 font=("Segoe UI", 8), bg='#f5f5f5', fg='#999').grid(
            row=1, column=0, columnspan=3, sticky='w', padx=8, pady=(2, 0))

        def save_all():
            new_vals = {}
            new_vals.update({k: e.get().strip() for k, e in entries_t1.items()})
            new_vals.update({k: e.get().strip() for k, e in entries_t2.items()})
            new_vals['logo_path'] = logo_var.get().strip()
            if not new_vals.get('name'):
                messagebox.showerror("Error", "Company name is required!", parent=dlg)
                return
            self.save_company_settings_to_db(new_vals)
            # update window title
            self.root.title(f"Invoicing App — {self.company_info['name']}")
            messagebox.showinfo("Saved", "Settings saved!", parent=dlg)
            dlg.destroy()

        bf = tk.Frame(dlg, bg='#f5f5f5')
        bf.pack(fill=tk.X, padx=16, pady=(4, 14))
        self.create_styled_button(bf, text="✓ Save Settings", command=save_all,
                                  bg=self.success_color, width=16, height=1).pack(side=tk.LEFT)
        self.create_styled_button(bf, text="Cancel", command=dlg.destroy,
                                  bg='#95a5a6', width=10, height=1).pack(side=tk.LEFT, padx=8)

        dlg.transient(self.root)
        dlg.grab_set()

    def create_invoices_folder(self):
        """Create invoices folder if it doesn't exist"""
        if not os.path.exists(self.invoices_folder):
            os.makedirs(self.invoices_folder)
    
    def create_menu(self):
        """Create menu bar"""
        drop_style = dict(
            tearoff=0,
            bg='white',
            fg=self.primary_color,
            activebackground=self.accent_color,
            activeforeground='white',
            font=('Segoe UI', 9),
            relief=tk.FLAT,
            bd=1,
        )
        menubar = tk.Menu(self.root, bg='white', fg=self.primary_color, relief=tk.FLAT)
        self.root.config(menu=menubar)

        self.root.bind_all('<Control-n>', lambda _e: self.new_invoice())
        self.root.bind_all('<Control-q>', lambda _e: self.root.quit())

        file_menu = tk.Menu(menubar, **drop_style)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Invoice",      command=self.new_invoice,       accelerator="Ctrl+N")
        file_menu.add_command(label="View All Invoices",command=self.view_all_invoices)
        file_menu.add_command(label="Earnings Report",  command=self.earnings_report)
        file_menu.add_separator()
        file_menu.add_command(label="Settings",         command=self.settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",             command=self.root.quit,         accelerator="Ctrl+Q")

        customers_menu = tk.Menu(menubar, **drop_style)
        menubar.add_cascade(label="Customers", menu=customers_menu)
        customers_menu.add_command(label="Manage Customers", command=self.manage_customers)

        items_menu = tk.Menu(menubar, **drop_style)
        menubar.add_cascade(label="Items", menu=items_menu)
        items_menu.add_command(label="Manage Item Catalog", command=self.manage_items)
        items_menu.add_separator()
        items_menu.add_command(label="Add New Item", command=self.items_prompt)
        items_menu.add_command(label="Clear Invoice Items", command=self.clear_all_items)
    
    def new_invoice(self):
        self._reset_invoice_state()
        self.clear_draft()
        if self._header_title_lbl:
            self._header_title_lbl.config(text="Create Invoice")
        if self._edit_banner_lbl:
            self._edit_banner_lbl.config(text="")
        self._refresh_vat_subtitle()
        self.update_dashboard()
        messagebox.showinfo("New Invoice", "Ready for a new invoice. Start by clicking Customer.")
    
    def create_buttons(self):
        BG = '#f0f4f8'
        self.root.configure(bg=BG)

        # ── Header ──────────────────────────────────────────────
        header = tk.Frame(self.root, bg=self.primary_color)
        header.pack(fill=tk.X)

        self._header_title_lbl = tk.Label(
            header, text="Create Invoice",
            font=("Segoe UI", 20, "bold"),
            bg=self.primary_color, fg='white',
            padx=32, pady=20
        )
        self._header_title_lbl.pack(side=tk.LEFT)

        tk.Label(
            header, text=self.company_info['name'],
            font=("Segoe UI", 9),
            bg=self.primary_color, fg='#7f9fb5', pady=22
        ).pack(side=tk.LEFT)

        tk.Frame(self.root, bg=self.accent_color, height=3).pack(fill=tk.X)

        # edit-mode banner
        self._edit_banner_lbl = tk.Label(
            self.root, text="", font=("Segoe UI", 9, "italic"),
            bg='#fff3cd', fg='#856404', pady=4
        )
        self._edit_banner_lbl.pack(fill=tk.X)

        # ── Step cards ──────────────────────────────────────────
        steps_frame = tk.Frame(self.root, bg=BG)
        steps_frame.pack(fill=tk.X, padx=44, pady=(14, 4))

        steps = [
            ("1", "Customer",            "Select or create a customer",        self.customer_prompt,    self.accent_color),
            ("2", "Items",               "Add services or products",            self.items_prompt,       self.success_color),
            ("3", "Project Name",        "Optional project reference",          self.project_name_prompt,'#16a085'),
            ("4", "Notes",               "Payment terms and additional notes",  self.note_prompt,        '#e67e22'),
            ("5", "VAT",                 "VAT 5% is currently: OFF",            self.vat_toggle,         '#c0392b'),
            ("6", "Preview Invoice",     "Review before generating",            self.preview_invoice,    '#8e44ad'),
            ("7", "Save & Generate PDF", "Save to database and export PDF",     self.save_invoice,       self.primary_color),
        ]

        for step_num, title, subtitle, command, color in steps:
            _, sub_lbl = self._make_step_card(steps_frame, step_num, title, subtitle, command, color)
            if title == "VAT":
                self._vat_subtitle_lbl = sub_lbl

        # ── Dashboard ────────────────────────────────────────────
        dash_outer = tk.Frame(self.root, bg='#dce4ee')
        dash_outer.pack(fill=tk.X, padx=44, pady=(10, 20))
        dash = tk.Frame(dash_outer, bg='white')
        dash.pack(fill=tk.X, padx=1, pady=1)

        stat_defs = [
            ('this_month', "This Month",  self.accent_color),
            ('outstanding','Outstanding', '#e67e22'),
            ('overdue',    'Overdue',     self.warning_color),
            ('all_time',   'All Time',    self.success_color),
        ]
        for col, (key, label, color) in enumerate(stat_defs):
            cell = tk.Frame(dash, bg='white', padx=18, pady=12)
            cell.grid(row=0, column=col, sticky='nsew')
            dash.columnconfigure(col, weight=1)
            tk.Label(cell, text=label, font=("Segoe UI", 8),
                     bg='white', fg='#888888').pack(anchor='w')
            val_lbl = tk.Label(cell, text="—", font=("Segoe UI", 13, "bold"),
                               bg='white', fg=color)
            val_lbl.pack(anchor='w')
            self.dashboard_labels[key] = val_lbl
            if col < len(stat_defs) - 1:
                tk.Frame(dash, bg='#eeeeee', width=1).grid(
                    row=0, column=col, sticky='nse')

    def update_dashboard(self):
        if not self.dashboard_labels:
            return
        try:
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT total_amount, issued_date, COALESCE(paid_amount,0), due_date FROM invoices"
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return

        today     = datetime.now().date()
        cur_month = (today.year, today.month)

        this_month_total = 0.0
        outstanding      = 0.0
        overdue_total    = 0.0
        all_time_total   = 0.0

        for total, issued, paid_amt, due_date_str in rows:
            all_time_total += total
            remaining = max(0.0, total - paid_amt)
            if remaining > 0:
                outstanding += remaining
                if due_date_str:
                    try:
                        due_dt = datetime.strptime(due_date_str, "%d-%m-%Y").date()
                        if due_dt < today:
                            overdue_total += remaining
                    except ValueError:
                        pass
            if issued:
                try:
                    idt = datetime.strptime(issued, "%d-%m-%Y").date()
                    if (idt.year, idt.month) == cur_month:
                        this_month_total += total
                except ValueError:
                    pass

        cy = self.company_info.get('currency', 'AED')
        self.dashboard_labels['this_month'].config( text=f"{cy} {this_month_total:,.2f}")
        self.dashboard_labels['outstanding'].config( text=f"{cy} {outstanding:,.2f}")
        self.dashboard_labels['overdue'].config(     text=f"{cy} {overdue_total:,.2f}")
        self.dashboard_labels['all_time'].config(    text=f"{cy} {all_time_total:,.2f}")

    def vat_toggle(self):
        self.vat_enabled = not self.vat_enabled
        state = "ON (5%)" if self.vat_enabled else "OFF"
        self._refresh_vat_subtitle()
        self.save_draft()
        messagebox.showinfo("VAT Updated", f"VAT is now {state}.")

    def create_styled_button(self, parent, text, command, bg, width=20, height=3):
        """Create a styled button with hover effects"""
        btn = tk.Button(
            parent, text=text,
            command=command,
            width=width, height=height,
            font=("Segoe UI", 11, "bold"),
            bg=bg,
            fg='white',
            relief=tk.FLAT,
            cursor='hand2',
            activebackground=self.lighten_color(bg, 20),
            activeforeground='white',
            bd=0,
            padx=20, pady=15
        )
        return btn

    def _make_step_card(self, parent, step_num, title, subtitle, command, color):
        """Create a clickable step card for the main window"""
        BG_CARD = 'white'
        BG_HOVER = '#f4f8fd'

        outer = tk.Frame(parent, bg='#dce4ee')
        outer.pack(fill=tk.X, pady=5)

        card = tk.Frame(outer, bg=BG_CARD, cursor='hand2')
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        tk.Frame(card, bg=color, width=5).pack(side=tk.LEFT, fill=tk.Y)

        badge_wrap = tk.Frame(card, bg=BG_CARD, padx=16, pady=14, cursor='hand2')
        badge_wrap.pack(side=tk.LEFT)

        badge = tk.Frame(badge_wrap, bg=color, width=34, height=34, cursor='hand2')
        badge.pack()
        badge.pack_propagate(False)
        badge_num = tk.Label(badge, text=step_num, font=("Segoe UI", 11, "bold"),
                             bg=color, fg='white', cursor='hand2')
        badge_num.place(relx=0.5, rely=0.5, anchor='center')

        text_wrap = tk.Frame(card, bg=BG_CARD, cursor='hand2')
        text_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=14)

        title_lbl = tk.Label(text_wrap, text=title, font=("Segoe UI", 12, "bold"),
                             bg=BG_CARD, fg=self.primary_color, anchor='w', cursor='hand2')
        title_lbl.pack(fill=tk.X)

        sub_lbl = tk.Label(text_wrap, text=subtitle, font=("Segoe UI", 9),
                           bg=BG_CARD, fg='#8899aa', anchor='w', cursor='hand2')
        sub_lbl.pack(fill=tk.X)

        arrow = tk.Label(card, text="›", font=("Segoe UI", 22),
                         bg=BG_CARD, fg='#b0bed0', padx=22, cursor='hand2')
        arrow.pack(side=tk.RIGHT, fill=tk.Y)

        hover_targets = [card, badge_wrap, text_wrap, title_lbl, sub_lbl, arrow]
        all_widgets = hover_targets + [outer]

        def on_enter(_e):
            for w in hover_targets:
                try:
                    w.configure(bg=BG_HOVER)
                except tk.TclError:
                    pass
            outer.configure(bg=color)

        def on_leave(e):
            px, py = e.widget.winfo_pointerxy()
            cx, cy = card.winfo_rootx(), card.winfo_rooty()
            if cx <= px <= cx + card.winfo_width() and cy <= py <= cy + card.winfo_height():
                return
            for w in hover_targets:
                try:
                    w.configure(bg=BG_CARD)
                except tk.TclError:
                    pass
            outer.configure(bg='#dce4ee')

        for w in all_widgets:
            w.bind('<Button-1>', lambda _e, cmd=command: cmd())
            w.bind('<Enter>', on_enter)
            w.bind('<Leave>', on_leave)

        return outer, sub_lbl

    def lighten_color(self, color, percent):
        """Lighten a hex color by blending toward white"""
        c = int(color.lstrip('#'), 16)
        r = (c >> 16) & 0xFF
        g = (c >> 8) & 0xFF
        b = c & 0xFF
        factor = percent / 100
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def due_date_prompt(self):
        """Due date selection dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Set Due Date")
        dialog.geometry("450x350")
        dialog.configure(bg='#f5f5f5')

        title_frame = tk.Frame(dialog, bg=self.primary_color)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="📅 Invoice Due Date",
            font=("Segoe UI", 14, "bold"),
            bg=self.primary_color, fg='white', pady=15
        ).pack()

        content_frame = tk.Frame(dialog, bg='#f5f5f5')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text="Enter due date (DD-MM-YYYY):", font=("Segoe UI", 10), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(0, 5))

        date_entry = tk.Entry(content_frame, width=40, font=("Segoe UI", 11), relief=tk.FLAT, bg='white', bd=1)
        default_due = (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")
        date_entry.insert(0, default_due)
        date_entry.pack(fill=tk.X, ipady=8, pady=(0, 15))

        tk.Label(
            content_frame, text=f"Default: 30 days from now ({default_due})",
            font=("Segoe UI", 9), bg='#f5f5f5', fg='#7f8c8d'
        ).pack(anchor='w', pady=(0, 20))

        def save_due_date():
            try:
                due_date_str = date_entry.get().strip()
                if due_date_str:
                    datetime.strptime(due_date_str, "%d-%m-%Y")
                    self.due_date = due_date_str
                else:
                    self.due_date = default_due
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Please enter date in DD-MM-YYYY format (e.g., 26-06-2026)")

        def set_default():
            self.due_date = default_due
            dialog.destroy()

        button_frame = tk.Frame(dialog, bg='#f5f5f5')
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        custom_btn = self.create_styled_button(
            button_frame, text="✓ Set Custom",
            command=save_due_date,
            bg=self.accent_color,
            width=15, height=1
        )
        custom_btn.pack(side=tk.LEFT, padx=5)

        default_btn = self.create_styled_button(
            button_frame, text="✓ Use 30 Days",
            command=set_default,
            bg=self.success_color,
            width=15, height=1
        )
        default_btn.pack(side=tk.LEFT, padx=5)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)
    
    def customer_prompt(self):
        """Customer selection/creation dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Customer Information")
        dialog.geometry("600x720")
        dialog.resizable(False, False)
        dialog.configure(bg='#f5f5f5')

        title_frame = tk.Frame(dialog, bg=self.accent_color)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="👤 Customer Information",
            font=("Segoe UI", 14, "bold"),
            bg=self.accent_color, fg='white', pady=15
        ).pack()

        content_frame = tk.Frame(dialog, bg='#f5f5f5')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text="Search or select customer:", font=("Segoe UI", 10, "bold"), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(0, 8))

        search_frame = tk.Frame(content_frame, bg='#f5f5f5')
        search_frame.pack(fill=tk.X, pady=(0, 15))

        search_entry = tk.Entry(search_frame, width=50, font=("Segoe UI", 10), relief=tk.FLAT, bg='white', bd=1)
        search_entry.pack(fill=tk.X, ipady=6)

        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM customers ORDER BY name")
        all_customers = cursor.fetchall()
        conn.close()

        customer_dict = {name: cid for cid, name in all_customers}
        customer_names = [name for cid, name in all_customers]
        customer_names.insert(0, "➕ Create New Customer")

        tk.Label(content_frame, text="Customer:", font=("Segoe UI", 10), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(0, 5))

        customer_combo = ttk.Combobox(content_frame, values=customer_names, font=("Segoe UI", 10), state="readonly", width=50)
        customer_combo.pack(fill=tk.X, ipady=6)

        def filter_customers(*args):
            search_text = search_entry.get().lower()
            if search_text:
                filtered = [name for name in customer_names[1:] if search_text in name.lower()]
                filtered.insert(0, "➕ Create New Customer")
            else:
                filtered = customer_names
            customer_combo['values'] = filtered
            if filtered:
                customer_combo.current(0)

        search_entry.bind('<KeyRelease>', filter_customers)

        tk.Label(content_frame, text="Customer Details:", font=("Segoe UI", 10, "bold"), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(15, 10))

        fields = [
            ("Customer Name:", "name"),
            ("TRN:", "license"),
            ("Email:", "email"),
            ("Phone:", "phone"),
            ("Address:", "address")
        ]

        entries = {}
        for label_text, key in fields:
            tk.Label(content_frame, text=label_text, font=("Segoe UI", 10), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(8, 2))
            entry = tk.Entry(content_frame, width=50, font=("Segoe UI", 10), relief=tk.FLAT, bg='white', bd=1)
            entry.pack(fill=tk.X, ipady=8)
            entries[key] = entry

        def load_customer(cid):
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT name, email, phone, address, trade_license FROM customers WHERE id = ?", (cid,))
            result = cursor.fetchone()
            conn.close()

            if result:
                entries['name'].config(state=tk.NORMAL)
                entries['name'].delete(0, tk.END)
                entries['name'].insert(0, result[0])
                entries['name'].config(state=tk.DISABLED)
                entries['email'].delete(0, tk.END)
                entries['email'].insert(0, result[1] or '')
                entries['phone'].delete(0, tk.END)
                entries['phone'].insert(0, result[2] or '')
                entries['address'].delete(0, tk.END)
                entries['address'].insert(0, result[3] or '')
                entries['license'].delete(0, tk.END)
                entries['license'].insert(0, result[4] or '')

        def on_customer_change(*args):
            selection = customer_combo.get()
            if selection == "➕ Create New Customer":
                for entry in entries.values():
                    entry.config(state=tk.NORMAL)
                    entry.delete(0, tk.END)
                entries['name'].config(state=tk.NORMAL)
            elif selection in customer_dict:
                for entry in entries.values():
                    entry.config(state=tk.NORMAL)
                load_customer(customer_dict[selection])
                entries['name'].config(state=tk.DISABLED)

        customer_combo.bind('<<ComboboxSelected>>', on_customer_change)

        def save_customer():
            if not entries['name'].get():
                messagebox.showerror("Error", "Customer name is required!")
                return

            selection = customer_combo.get()
            customer_id = None

            if selection == "➕ Create New Customer" or not selection:
                conn = sqlite3.connect(self.db_file, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO customers (name, email, phone, address, trade_license)
                    VALUES (?, ?, ?, ?, ?)
                ''', (entries['name'].get(), entries['email'].get(), entries['phone'].get(), entries['address'].get(), entries['license'].get()))
                conn.commit()
                customer_id = cursor.lastrowid
                conn.close()
            else:
                customer_id = customer_dict[selection]
                conn = sqlite3.connect(self.db_file, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE customers SET email = ?, phone = ?, address = ?, trade_license = ?
                    WHERE id = ?
                ''', (entries['email'].get(), entries['phone'].get(), entries['address'].get(), entries['license'].get(), customer_id))
                conn.commit()
                conn.close()

            self.customer_data = {
                "id": customer_id,
                "name": entries['name'].get(),
                "trade_license": entries['license'].get(),
                "email": entries['email'].get(),
                "phone": entries['phone'].get(),
                "address": entries['address'].get()
            }
            messagebox.showinfo("Success", "Customer information saved!")
            self.save_draft()
            dialog.destroy()

        button_frame = tk.Frame(dialog, bg='#f5f5f5')
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        save_btn = self.create_styled_button(
            button_frame, text="✓ Save",
            command=save_customer,
            bg=self.success_color,
            width=15, height=1
        )
        save_btn.pack(side=tk.LEFT, padx=5)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    def manage_customers(self):
        """Manage customers window - view, edit, delete"""
        manage_window = tk.Toplevel(self.root)
        manage_window.title("Manage Customers")
        manage_window.geometry("700x500")
        manage_window.configure(bg='#f5f5f5')

        title_frame = tk.Frame(manage_window, bg=self.accent_color)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="👥 Manage Customers",
            font=("Segoe UI", 14, "bold"),
            bg=self.accent_color, fg='white', pady=15
        ).pack()

        tree_frame = tk.Frame(manage_window, bg='#f5f5f5')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, phone, address FROM customers ORDER BY name")
        customers = cursor.fetchall()
        conn.close()

        tree = ttk.Treeview(tree_frame, columns=("Name", "Email", "Phone", "Address"), height=15)
        tree.column("#0", width=0, stretch=tk.NO)
        tree.column("Name", anchor=tk.W, width=150)
        tree.column("Email", anchor=tk.W, width=150)
        tree.column("Phone", anchor=tk.W, width=100)
        tree.column("Address", anchor=tk.W, width=200)

        tree.heading("#0", text="", anchor=tk.W)
        tree.heading("Name", text="Name", anchor=tk.W)
        tree.heading("Email", text="Email", anchor=tk.W)
        tree.heading("Phone", text="Phone", anchor=tk.W)
        tree.heading("Address", text="Address", anchor=tk.W)

        for customer in customers:
            tree.insert("", tk.END, text="", values=(customer[1], customer[2], customer[3], customer[4]), tags=(customer[0],))

        tree.pack(fill=tk.BOTH, expand=True)

        button_frame = tk.Frame(manage_window, bg='#f5f5f5')
        button_frame.pack(pady=15)

        def edit_customer():
            selected = tree.selection()
            if not selected:
                messagebox.showerror("Error", "Please select a customer!")
                return

            customer_id = tree.item(selected)['tags'][0]
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT name, email, phone, address, trade_license FROM customers WHERE id = ?", (customer_id,))
            result = cursor.fetchone()
            conn.close()

            edit_dialog = tk.Toplevel(manage_window)
            edit_dialog.title("Edit Customer")
            edit_dialog.geometry("500x540")
            edit_dialog.resizable(False, False)
            edit_dialog.configure(bg='#f5f5f5')

            title_frame_edit = tk.Frame(edit_dialog, bg=self.accent_color)
            title_frame_edit.pack(fill=tk.X)

            tk.Label(
                title_frame_edit, text="✏️ Edit Customer",
                font=("Segoe UI", 14, "bold"),
                bg=self.accent_color, fg='white', pady=15
            ).pack()

            content_frame_edit = tk.Frame(edit_dialog, bg='#f5f5f5')
            content_frame_edit.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            fields_edit = [
                ("Customer Name:", "name"),
                ("TRN:", "license"),
                ("Email:", "email"),
                ("Phone:", "phone"),
                ("Address:", "address")
            ]

            entries_edit = {}
            for label_text, key in fields_edit:
                tk.Label(content_frame_edit, text=label_text, font=("Segoe UI", 10), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(8, 2))
                entry = tk.Entry(content_frame_edit, width=50, font=("Segoe UI", 10), relief=tk.FLAT, bg='white', bd=1)
                entry.pack(fill=tk.X, ipady=8)
                entries_edit[key] = entry

            if result:
                entries_edit['name'].insert(0, result[0] or '')
                entries_edit['license'].insert(0, result[4] or '')
                entries_edit['email'].insert(0, result[1] or '')
                entries_edit['phone'].insert(0, result[2] or '')
                entries_edit['address'].insert(0, result[3] or '')

            def save_edit():
                if not entries_edit['name'].get():
                    messagebox.showerror("Error", "Customer name is required!")
                    return

                conn = sqlite3.connect(self.db_file, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE customers SET name = ?, email = ?, phone = ?, address = ?, trade_license = ?
                    WHERE id = ?
                ''', (entries_edit['name'].get(), entries_edit['email'].get(), entries_edit['phone'].get(), entries_edit['address'].get(), entries_edit['license'].get(), customer_id))
                conn.commit()
                conn.close()

                messagebox.showinfo("Success", "Customer updated!")
                edit_dialog.destroy()
                self.manage_customers()
                manage_window.destroy()

            button_frame_edit = tk.Frame(edit_dialog, bg='#f5f5f5')
            button_frame_edit.pack(fill=tk.X, padx=20, pady=(0, 20))

            save_btn_edit = self.create_styled_button(
                button_frame_edit, text="✓ Update",
                command=save_edit,
                bg=self.success_color,
                width=15, height=1
            )
            save_btn_edit.pack(side=tk.LEFT, padx=5)

            edit_dialog.transient(manage_window)
            edit_dialog.grab_set()

        def delete_customer():
            selected = tree.selection()
            if not selected:
                messagebox.showerror("Error", "Please select a customer!")
                return

            if messagebox.askyesno("Confirm", "Delete this customer?"):
                customer_id = tree.item(selected)['tags'][0]
                conn = sqlite3.connect(self.db_file, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
                conn.commit()
                conn.close()

                messagebox.showinfo("Success", "Customer deleted!")
                self.manage_customers()
                manage_window.destroy()

        btn_edit = self.create_styled_button(
            button_frame, text="✏️ Edit",
            command=edit_customer,
            bg=self.accent_color,
            width=15, height=1
        )
        btn_edit.pack(side=tk.LEFT, padx=5)

        btn_delete = self.create_styled_button(
            button_frame, text="🗑️ Delete",
            command=delete_customer,
            bg=self.warning_color,
            width=15, height=1
        )
        btn_delete.pack(side=tk.LEFT, padx=5)

        manage_window.transient(self.root)
        manage_window.grab_set()

    def manage_items(self):
        """Item catalog window - view, edit, delete saved items"""
        manage_window = tk.Toplevel(self.root)
        manage_window.title("Item Catalog")
        manage_window.geometry("820x520")
        manage_window.configure(bg='#f5f5f5')

        title_frame = tk.Frame(manage_window, bg=self.success_color)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="📦 Item Catalog",
            font=("Segoe UI", 14, "bold"),
            bg=self.success_color, fg='white', pady=15
        ).pack()

        tree_frame = tk.Frame(manage_window, bg='#f5f5f5')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT id, description, unit_price, discount, note FROM items ORDER BY description")
        catalog_items = cursor.fetchall()
        conn.close()

        if not catalog_items:
            tk.Label(
                tree_frame,
                text="No items in catalog yet. Add items via the Items button or 'Add New Item'.",
                font=("Segoe UI", 11), bg='#f5f5f5', fg='#7f8c8d'
            ).pack(pady=50)
        else:
            tree = ttk.Treeview(
                tree_frame,
                columns=("Description", "Unit Price", "Discount %", "Note"),
                height=15
            )
            tree.column("#0", width=0, stretch=tk.NO)
            tree.column("Description", anchor=tk.W, width=210)
            tree.column("Unit Price",  anchor=tk.W, width=110)
            tree.column("Discount %",  anchor=tk.CENTER, width=80)
            tree.column("Note",        anchor=tk.W, width=310)

            tree.heading("Description", text="Description", anchor=tk.W)
            tree.heading("Unit Price",  text="Unit Price",  anchor=tk.W)
            tree.heading("Discount %",  text="Discount %",  anchor=tk.CENTER)
            tree.heading("Note",        text="Note",        anchor=tk.W)

            scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)

            for item in catalog_items:
                tree.insert("", tk.END, values=(
                    item[1],
                    f"AED {item[2]:.2f}",
                    f"{item[3]}%",
                    item[4] or ''
                ), tags=(item[0],))

            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            button_frame = tk.Frame(manage_window, bg='#f5f5f5')
            button_frame.pack(pady=15)

            def edit_item():
                selected = tree.selection()
                if not selected:
                    messagebox.showerror("Error", "Please select an item!")
                    return

                item_id = tree.item(selected)['tags'][0]
                conn = sqlite3.connect(self.db_file, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT description, unit_price, discount, note FROM items WHERE id = ?",
                    (item_id,))
                result = cursor.fetchone()
                conn.close()

                edit_dialog = tk.Toplevel(manage_window)
                edit_dialog.title("Edit Item")
                edit_dialog.geometry("500x460")
                edit_dialog.resizable(False, False)
                edit_dialog.configure(bg='#f5f5f5')

                tk.Frame(edit_dialog, bg=self.success_color).pack(fill=tk.X)
                tk.Label(
                    edit_dialog.winfo_children()[-1], text="✏️ Edit Catalog Item",
                    font=("Segoe UI", 14, "bold"),
                    bg=self.success_color, fg='white', pady=15
                ).pack()

                cf = tk.Frame(edit_dialog, bg='#f5f5f5')
                cf.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

                edit_fields = [
                    ("Description:", "desc"),
                    ("Unit Price (AED):", "price"),
                    ("Discount (%):", "discount"),
                    ("Note:", "note"),
                ]
                ed = {}
                for lbl, key in edit_fields:
                    tk.Label(cf, text=lbl, font=("Segoe UI", 10),
                             bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(8, 2))
                    e = tk.Entry(cf, width=50, font=("Segoe UI", 10),
                                 relief=tk.FLAT, bg='white', bd=1)
                    e.pack(fill=tk.X, ipady=8)
                    ed[key] = e

                if result:
                    ed['desc'].insert(0,     result[0] or '')
                    ed['price'].insert(0,    str(result[1]))
                    ed['discount'].insert(0, str(result[2]))
                    ed['note'].insert(0,     result[3] or '')

                def save_edit():
                    if not ed['desc'].get():
                        messagebox.showerror("Error", "Description is required!")
                        return
                    try:
                        price    = float(ed['price'].get()    or '0')
                        discount = float(ed['discount'].get() or '0')
                    except ValueError:
                        messagebox.showerror("Error", "Price and Discount must be numbers!")
                        return

                    conn = sqlite3.connect(self.db_file, timeout=10.0)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE items SET description=?, unit_price=?, discount=?, note=? WHERE id=?",
                        (ed['desc'].get(), price, discount, ed['note'].get(), item_id))
                    conn.commit()
                    conn.close()

                    edit_dialog.destroy()
                    manage_window.destroy()
                    self.manage_items()

                bf = tk.Frame(edit_dialog, bg='#f5f5f5')
                bf.pack(fill=tk.X, padx=20, pady=(0, 20))
                self.create_styled_button(bf, text="✓ Update",
                                          command=save_edit,
                                          bg=self.success_color,
                                          width=15, height=1).pack(side=tk.LEFT, padx=5)

                edit_dialog.transient(manage_window)
                edit_dialog.grab_set()

            def delete_item():
                selected = tree.selection()
                if not selected:
                    messagebox.showerror("Error", "Please select an item!")
                    return

                if messagebox.askyesno("Confirm", "Remove this item from the catalog?"):
                    item_id = tree.item(selected)['tags'][0]
                    conn = sqlite3.connect(self.db_file, timeout=10.0)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
                    conn.commit()
                    conn.close()

                    manage_window.destroy()
                    self.manage_items()

            self.create_styled_button(button_frame, text="✏️ Edit",
                                      command=edit_item,
                                      bg=self.accent_color,
                                      width=15, height=1).pack(side=tk.LEFT, padx=5)
            self.create_styled_button(button_frame, text="🗑️ Delete",
                                      command=delete_item,
                                      bg=self.warning_color,
                                      width=15, height=1).pack(side=tk.LEFT, padx=5)

        manage_window.transient(self.root)
        manage_window.grab_set()

    def clear_all_items(self):
        """Clear all items from the list"""
        if not self.items_data_list:
            messagebox.showinfo("Info", "No items to clear!")
            return

        if messagebox.askyesno("Confirm", f"Delete all {len(self.items_data_list)} items?"):
            self.items_data_list = []
            messagebox.showinfo("Success", "All items cleared!")

    def items_prompt(self):
        """Manage invoice items: view/edit/remove existing and add new"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Items")
        dialog.geometry("560x860")
        dialog.resizable(True, True)
        dialog.configure(bg='#f5f5f5')

        # ── Header ────────────────────────────────────────────────
        title_frame = tk.Frame(dialog, bg=self.success_color)
        title_frame.pack(fill=tk.X)
        header_lbl = tk.Label(
            title_frame, text="",
            font=("Segoe UI", 14, "bold"),
            bg=self.success_color, fg='white', pady=15
        )
        header_lbl.pack()

        content_frame = tk.Frame(dialog, bg='#f5f5f5')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        editing_idx = [None]

        # ── Current items treeview ────────────────────────────────
        items_lbl = tk.Label(content_frame, font=("Segoe UI", 10, "bold"),
                             bg='#f5f5f5', fg=self.primary_color)
        items_lbl.pack(anchor='w', pady=(0, 5))

        tree_outer = tk.Frame(content_frame, bg='#f5f5f5')
        tree_outer.pack(fill=tk.X)

        cols = ("desc", "qty", "price", "disc", "amount")
        tree = ttk.Treeview(tree_outer, columns=cols, show='headings', height=5)
        tree.heading("desc",   text="Description")
        tree.heading("qty",    text="Qty")
        tree.heading("price",  text="Price")
        tree.heading("disc",   text="Disc%")
        tree.heading("amount", text="Amount")
        tree.column("desc",   width=200, minwidth=120)
        tree.column("qty",    width=50,  anchor='center')
        tree.column("price",  width=80,  anchor='e')
        tree.column("disc",   width=55,  anchor='center')
        tree.column("amount", width=90,  anchor='e')
        vsb = ttk.Scrollbar(tree_outer, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.X)

        item_btn_row = tk.Frame(content_frame, bg='#f5f5f5')
        item_btn_row.pack(anchor='w', pady=(4, 8))

        ttk.Separator(content_frame, orient='horizontal').pack(fill=tk.X, pady=(0, 10))

        # ── Catalog dropdown ──────────────────────────────────────
        tk.Label(content_frame, text="Select from saved catalog:", font=("Segoe UI", 10),
                 bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(0, 5))

        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT id, description, unit_price, discount, note FROM items ORDER BY description")
        catalog_rows = cursor.fetchall()
        conn.close()

        catalog_dict = {row[1]: row for row in catalog_rows}
        catalog_names = ["— New Item —"] + [row[1] for row in catalog_rows]

        catalog_combo = ttk.Combobox(content_frame, values=catalog_names,
                                     font=("Segoe UI", 10), state="readonly", width=50)
        catalog_combo.current(0)
        catalog_combo.pack(fill=tk.X, ipady=6, pady=(0, 12))

        # ── Form fields ───────────────────────────────────────────
        fields = [
            ("Description:", "desc"),
            ("Quantity:", "qty"),
            ("Unit Price (AED):", "price"),
            ("Discount (%):", "discount"),
            ("Note:", "note"),
        ]
        entries = {}
        for label_text, key in fields:
            tk.Label(content_frame, text=label_text, font=("Segoe UI", 10),
                     bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(6, 2))
            entry = tk.Entry(content_frame, width=40, font=("Segoe UI", 10),
                             relief=tk.FLAT, bg='white', bd=1)
            entry.pack(fill=tk.X, ipady=7)
            entries[key] = entry
        entries['discount'].insert(0, "0")

        # ── Helpers ───────────────────────────────────────────────
        def clear_form():
            for e in entries.values():
                e.delete(0, tk.END)
            entries['discount'].insert(0, "0")
            editing_idx[0] = None
            save_btn.config(text="✓ Add to Invoice")
            catalog_combo.set("— New Item —")

        def load_for_edit():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Select Item", "Please select an item to edit.")
                return
            idx = int(sel[0])
            item = self.items_data_list[idx]
            for e in entries.values():
                e.delete(0, tk.END)
            entries['desc'].insert(0, item['description'])
            entries['qty'].insert(0, str(item['quantity']))
            entries['price'].insert(0, str(item['unit_price']))
            entries['discount'].insert(0, str(item.get('discount', 0)))
            entries['note'].insert(0, item.get('note', ''))
            catalog_combo.set("— New Item —")
            editing_idx[0] = idx
            save_btn.config(text="✓ Update Item")

        def remove_item():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Select Item", "Please select an item to remove.")
                return
            idx = int(sel[0])
            item = self.items_data_list[idx]
            if messagebox.askyesno("Remove Item", f"Remove '{item['description']}' from invoice?"):
                self.items_data_list.pop(idx)
                self.save_draft()
                if editing_idx[0] == idx:
                    clear_form()
                elif editing_idx[0] is not None and editing_idx[0] > idx:
                    editing_idx[0] -= 1
                refresh_tree()

        def refresh_tree():
            for row in tree.get_children():
                tree.delete(row)
            cy = self.company_info.get('currency', 'AED')
            for i, item in enumerate(self.items_data_list):
                tree.insert('', 'end', iid=str(i), values=(
                    item['description'],
                    item['quantity'],
                    f"{item['unit_price']:.2f}",
                    f"{item.get('discount', 0):.0f}%",
                    f"{cy} {item['amount']:.2f}",
                ))
            n = len(self.items_data_list)
            header_lbl.config(text=f"📦 Items  —  Invoice items: {n}")
            items_lbl.config(text=f"Current invoice items ({n}):" if n else "No items added yet.")
            for w in item_btn_row.winfo_children():
                w.destroy()
            if n:
                tk.Button(item_btn_row, text="✏ Edit", font=("Segoe UI", 9),
                          bg='#3498db', fg='white', relief=tk.FLAT, cursor='hand2',
                          padx=10, pady=4, command=load_for_edit).pack(side=tk.LEFT, padx=(0, 6))
                tk.Button(item_btn_row, text="✕ Remove", font=("Segoe UI", 9),
                          bg='#e74c3c', fg='white', relief=tk.FLAT, cursor='hand2',
                          padx=10, pady=4, command=remove_item).pack(side=tk.LEFT)

        def on_catalog_select(*_args):
            selection = catalog_combo.get()
            for entry in entries.values():
                entry.delete(0, tk.END)
            entries['discount'].insert(0, "0")
            editing_idx[0] = None
            save_btn.config(text="✓ Add to Invoice")
            if selection in catalog_dict:
                row = catalog_dict[selection]
                entries['desc'].insert(0, row[1])
                entries['price'].insert(0, str(row[2]))
                entries['discount'].delete(0, tk.END)
                entries['discount'].insert(0, str(row[3]))
                entries['note'].insert(0, row[4] or '')

        catalog_combo.bind('<<ComboboxSelected>>', on_catalog_select)

        def save_items():
            desc = entries['desc'].get().strip()
            if not desc or not entries['qty'].get() or not entries['price'].get():
                messagebox.showerror("Error", "Description, Quantity and Price are required!")
                return
            try:
                qty      = float(entries['qty'].get())
                price    = float(entries['price'].get())
                discount = float(entries['discount'].get() or '0')
                note     = entries['note'].get().strip()
            except ValueError:
                messagebox.showerror("Error", "Quantity, Price, and Discount must be numbers!")
                return

            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            existing = cursor.execute(
                "SELECT id FROM items WHERE description = ?", (desc,)).fetchone()
            if existing:
                cursor.execute(
                    "UPDATE items SET unit_price=?, discount=?, note=? WHERE id=?",
                    (price, discount, note, existing[0]))
            else:
                cursor.execute(
                    "INSERT INTO items (description, unit_price, discount, note) VALUES (?, ?, ?, ?)",
                    (desc, price, discount, note))
            conn.commit()
            conn.close()

            item_data = {
                "description": desc,
                "quantity":    qty,
                "unit_price":  price,
                "discount":    discount,
                "amount":      qty * price * (1 - discount / 100),
                "note":        note,
            }
            if editing_idx[0] is not None:
                self.items_data_list[editing_idx[0]] = item_data
            else:
                self.items_data_list.append(item_data)

            self.save_draft()
            clear_form()
            refresh_tree()

        # ── Bottom buttons ────────────────────────────────────────
        button_frame = tk.Frame(dialog, bg='#f5f5f5')
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        save_btn = self.create_styled_button(
            button_frame, text="✓ Add to Invoice",
            command=save_items,
            bg=self.success_color,
            width=18, height=1
        )
        save_btn.pack(side=tk.LEFT, padx=5)

        self.create_styled_button(
            button_frame, text="Close",
            command=dialog.destroy,
            bg='#7f8c8d',
            width=10, height=1
        ).pack(side=tk.LEFT, padx=5)

        refresh_tree()

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    def project_name_prompt(self):
        """Project name dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Name")
        dialog.geometry("450x250")
        dialog.configure(bg='#f5f5f5')

        title_frame = tk.Frame(dialog, bg='#16a085')
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="🏢 Project Name",
            font=("Segoe UI", 14, "bold"),
            bg='#16a085', fg='white', pady=15
        ).pack()

        content_frame = tk.Frame(dialog, bg='#f5f5f5')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text="Enter project name:", font=("Segoe UI", 10), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(0, 10))

        project_entry = tk.Entry(content_frame, width=50, font=("Segoe UI", 11), relief=tk.FLAT, bg='white', bd=1)
        if self.project_name:
            project_entry.insert(0, self.project_name)
        project_entry.pack(fill=tk.X, ipady=8)

        def save_project():
            self.project_name = project_entry.get().strip() or None
            self.save_draft()
            if self.project_name:
                messagebox.showinfo("Success", f"Project name set to: {self.project_name}")
            else:
                messagebox.showinfo("Success", "Project name cleared!")
            dialog.destroy()

        button_frame = tk.Frame(dialog, bg='#f5f5f5')
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        save_btn = self.create_styled_button(
            button_frame, text="✓ Save",
            command=save_project,
            bg='#16a085',
            width=15, height=1
        )
        save_btn.pack(side=tk.LEFT, padx=5)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    def note_prompt(self):
        """Notes dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Additional Notes")
        dialog.geometry("550x450")
        dialog.configure(bg='#f5f5f5')

        title_frame = tk.Frame(dialog, bg='#f39c12')
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="📝 Additional Notes",
            font=("Segoe UI", 14, "bold"),
            bg='#f39c12', fg='white', pady=15
        ).pack()

        content_frame = tk.Frame(dialog, bg='#f5f5f5')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text="Add any additional notes or terms:", font=("Segoe UI", 10), bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(0, 10))

        note_text = tk.Text(content_frame, height=12, width=50, font=("Segoe UI", 10), relief=tk.FLAT, bg='white', bd=1, wrap=tk.WORD)
        note_text.pack(fill=tk.BOTH, expand=True, ipady=5)
        if self.notes_data:
            note_text.insert("1.0", self.notes_data)

        def save_note():
            self.notes_data = note_text.get("1.0", tk.END).strip()
            self.save_draft()
            messagebox.showinfo("Success", "Notes saved!")
            dialog.destroy()

        button_frame = tk.Frame(dialog, bg='#f5f5f5')
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        save_btn = self.create_styled_button(
            button_frame, text="✓ Save Notes",
            command=save_note,
            bg='#f39c12',
            width=15, height=1
        )
        save_btn.pack(side=tk.LEFT, padx=5)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    def calculate_total(self):
        """Return (pre_discount, discount_amount, subtotal, vat_amount, grand_total)"""
        pre_discount = sum(item["quantity"] * item["unit_price"] for item in self.items_data_list)
        subtotal     = sum(item["amount"] for item in self.items_data_list)
        vat_amount   = round(subtotal * 0.05, 2) if self.vat_enabled else 0.0
        return pre_discount, pre_discount - subtotal, subtotal, vat_amount, subtotal + vat_amount
    
    def preview_invoice(self):
        """Generate a temporary PDF and open it in the system viewer"""
        tmp_path = os.path.join(tempfile.gettempdir(), "invoice_preview.pdf")
        try:
            self.generate_pdf("PREVIEW", tmp_path)
            os.startfile(tmp_path)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Could not generate preview:\n{str(e)}")
    
    def generate_invoice_text(self):
        """Generate formatted invoice text"""
        issued_date = self.issued_date or datetime.now().strftime("%d-%m-%Y")
        due_date = self.due_date or (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")
        
        text = "=" * 60 + "\n"
        text += "INVOICE\n"
        text += "=" * 60 + "\n\n"
        
        text += f"Issued: {issued_date}\n"
        text += f"Due: {due_date}\n\n"
        
        text += "CUSTOMER INFORMATION\n"
        if self.customer_data:
            text += f"Name: {self.customer_data.get('name', '')}\n"
            text += f"TRN: {self.customer_data.get('trade_license', '')}\n"
            text += f"Email: {self.customer_data.get('email', '')}\n"
            text += f"Phone: {self.customer_data.get('phone', '')}\n"
            text += f"Address: {self.customer_data.get('address', '')}\n\n"
        else:
            text += "Name: \n"
            text += "TRN:\n"
            text += "Email: \n"
            text += "Phone: \n"
            text += "Address: \n\n"
        
        text += "ITEMS\n"
        text += "-" * 60 + "\n"
        text += f"{'Description':<25} {'Qty':>8} {'Price':>10} {'Amount':>10}\n"
        text += "-" * 60 + "\n"
        
        if self.items_data_list:
            for item in self.items_data_list:
                text += f"{item['description']:<25} {item['quantity']:>8.2f} AED {item['unit_price']:>9.2f} AED {item['amount']:>9.2f}\n"
                if item.get('discount', 0) > 0:
                    text += f"  Discount: {item['discount']}%\n"
                if item.get('note'):
                    text += f"  Note: {item['note']}\n"
        else:
            text += "\n"
        
        text += "-" * 60 + "\n"
        
        if self.items_data_list:
            pre_discount, discount_amount, _, vat_amount, grand_total = self.calculate_total()
            text += f"{'SUBTOTAL':<45} AED {pre_discount:>12.2f}\n"
            if discount_amount > 0:
                text += f"{'DISCOUNT':<45} AED -{discount_amount:>11.2f}\n"
            if vat_amount > 0:
                text += f"{'VAT (5%)':<45} AED {vat_amount:>12.2f}\n"
            text += f"{'TOTAL':<45} AED {grand_total:>12.2f}\n"
        else:
            text += f"{'SUBTOTAL':<45} AED {'0.00':>12}\n"
            text += f"{'TOTAL':<45} AED {'0.00':>12}\n"
        
        text += "=" * 60 + "\n\n"

        if self.project_name:
            text += "PROJECT NAME\n"
            text += f"{self.project_name}\n\n"

        if self.notes_data:
            text += "NOTES\n"
            text += "-" * 60 + "\n"
            text += self.notes_data + "\n"
        
        return text
    
    def get_next_invoice_number(self):
        """Get next invoice number"""
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(CAST(SUBSTR(invoice_number, 5) AS INTEGER)), 0) FROM invoices")
        max_num = cursor.fetchone()[0]
        conn.close()
        return f"INV-{max_num + 1:04d}"
    
    def save_invoice(self):
        if not self.customer_data or not self.customer_data.get('id'):
            messagebox.showerror("Error", "Please select or create a customer first!")
            return
        if not self.items_data_list:
            messagebox.showerror("Error", "Please add at least one item!")
            return
        if not self.issued_date:
            self.issued_date = datetime.now().strftime("%d-%m-%Y")
        if not self.due_date:
            self.due_date_prompt()
            if not self.due_date:
                return

        editing = self.current_invoice_id is not None

        if editing:
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT invoice_number, pdf_path FROM invoices WHERE id=?",
                           (self.current_invoice_id,))
            row = cursor.fetchone()
            conn.close()
            invoice_number    = row[0]
            existing_pdf_path = row[1] or ''

            if existing_pdf_path and os.path.exists(existing_pdf_path):
                if messagebox.askyesno("Overwrite PDF?",
                                       f"Overwrite existing PDF?\n{existing_pdf_path}"):
                    pdf_path = existing_pdf_path
                else:
                    pdf_path = filedialog.asksaveasfilename(
                        defaultextension=".pdf",
                        filetypes=[("PDF files", "*.pdf")],
                        initialfile=f"{invoice_number}.pdf")
            else:
                pdf_path = filedialog.asksaveasfilename(
                    defaultextension=".pdf",
                    filetypes=[("PDF files", "*.pdf")],
                    initialfile=f"{invoice_number}.pdf")
            if not pdf_path:
                return
        else:
            invoice_number = self.get_next_invoice_number()
            pdf_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile=f"{invoice_number}.pdf")
            if not pdf_path:
                return

        try:
            *_, grand_total = self.calculate_total()
            items_json = json.dumps(self.items_data_list)
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()

            if editing:
                cursor.execute('''
                    UPDATE invoices SET customer_id=?, items_data=?, notes=?,
                        total_amount=?, issued_date=?, due_date=?, pdf_path=?,
                        vat_enabled=?, project_name=?
                    WHERE id=?
                ''', (self.customer_data['id'], items_json, self.notes_data or "",
                      grand_total, self.issued_date, self.due_date, pdf_path,
                      1 if self.vat_enabled else 0,
                      self.project_name or "",
                      self.current_invoice_id))
            else:
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute('''
                    INSERT INTO invoices
                        (invoice_number, customer_id, items_data, notes, total_amount,
                         issued_date, due_date, created_at, pdf_path,
                         vat_enabled, project_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (invoice_number, self.customer_data['id'], items_json,
                      self.notes_data or "", grand_total,
                      self.issued_date, self.due_date, created_at, pdf_path,
                      1 if self.vat_enabled else 0,
                      self.project_name or ""))

            conn.commit()
            conn.close()

            self.generate_pdf(invoice_number, pdf_path)
            action = "updated" if editing else "saved"
            messagebox.showinfo("Success", f"Invoice {invoice_number} {action} and PDF generated!")
            self.new_invoice()
            self.update_dashboard()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save invoice: {str(e)}")
    
    def generate_pdf(self, invoice_number, pdf_path):

        issued_date = self.issued_date or datetime.now().strftime("%d-%m-%Y")
        due_date = self.due_date or (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")

        doc = SimpleDocTemplate(pdf_path, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=0,
            alignment=0
        )

        # ── Top header: INVOICE title (left) + company details (right) ──
        company_right_style = ParagraphStyle(
            'CompanyRight',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#555555'),
            alignment=2,
            leading=14,
        )

        company_header_html = (
            f"<font size='11'><b>{self.company_info['name']}</b></font><br/>"
            f"{self.company_info['address']}<br/>"
            f"{self.company_info['phone']}   |   {self.company_info['email']}<br/>"
            f"TRN: {self.company_info['trade_license']}"
        )

        # logo + INVOICE title in left cell
        logo_path = self.company_info.get('logo_path', '').strip()
        if logo_path and os.path.exists(logo_path):
            try:
                logo_img = RLImage(logo_path)
                aspect   = logo_img.imageWidth / max(logo_img.imageHeight, 1)
                logo_w   = min(1.6*inch, logo_img.imageWidth)
                logo_img = RLImage(logo_path, width=logo_w, height=logo_w / aspect)
                left_cell = Table([[logo_img], [Paragraph("INVOICE", title_style)]],
                                  colWidths=[3.25*inch])
                left_cell.setStyle(TableStyle([
                    ('LEFTPADDING',   (0,0),(-1,-1), 0),
                    ('RIGHTPADDING',  (0,0),(-1,-1), 0),
                    ('TOPPADDING',    (0,0),(-1,-1), 0),
                    ('BOTTOMPADDING', (0,0),(0,0),   4),
                    ('BOTTOMPADDING', (0,1),(-1,-1), 0),
                ]))
            except Exception:
                left_cell = Paragraph("INVOICE", title_style)
        else:
            left_cell = Paragraph("INVOICE", title_style)

        top_table = Table(
            [[left_cell, Paragraph(company_header_html, company_right_style)]],
            colWidths=[3.25*inch, 3.25*inch]
        )
        top_table.setStyle(TableStyle([
            ('ALIGN',         (0, 0), (0, 0), 'LEFT'),
            ('ALIGN',         (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(top_table)
        story.append(Spacer(1, 0.15*inch))

        # Thin separator line
        sep_table = Table([[""]], colWidths=[6.5*inch], rowHeights=[2])
        sep_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#dddddd')),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(sep_table)
        story.append(Spacer(1, 0.18*inch))

        # ── Bill To + Invoice details ────────────────────────────────────
        customer_name      = self.customer_data.get('name',          '') if self.customer_data else ''
        customer_trade_lic = self.customer_data.get('trade_license', '') if self.customer_data else ''
        customer_address   = self.customer_data.get('address',       '') if self.customer_data else ''
        customer_phone     = self.customer_data.get('phone',         '') if self.customer_data else ''
        customer_email     = self.customer_data.get('email',         '') if self.customer_data else ''

        bill_to_info_style = ParagraphStyle(
            'BillToInfo',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#444444'),
            leading=15,
        )

        bill_to_lines = ["<b><font size='8' color='#888888'>BILL TO</font></b>"]
        if customer_name:
            bill_to_lines.append(f"<font size='10'><b>{customer_name}</b></font>")
        if customer_trade_lic:
            bill_to_lines.append(f"TRN: {customer_trade_lic}")
        if customer_address:
            bill_to_lines.append(customer_address)
        if customer_phone:
            bill_to_lines.append(customer_phone)
        if customer_email:
            bill_to_lines.append(customer_email)

        bill_to_para = Paragraph("<br/>".join(bill_to_lines), bill_to_info_style)

        inv_label_style = ParagraphStyle(
            'InvLabel',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#888888'),
            fontName='Helvetica-Bold',
        )
        inv_value_style = ParagraphStyle(
            'InvValue',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#222222'),
        )
        inv_num_style = ParagraphStyle(
            'InvNum',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#1f4788'),
            fontName='Helvetica-Bold',
        )

        inv_detail_data = [
            [Paragraph("INVOICE NUMBER", inv_label_style), Paragraph(invoice_number, inv_num_style)],
            [Paragraph("ISSUED",         inv_label_style), Paragraph(issued_date, inv_value_style)],
            [Paragraph("DUE DATE",       inv_label_style), Paragraph(due_date, inv_value_style)],
        ]
        inv_detail_table = Table(inv_detail_data, colWidths=[1.3*inch, 1.7*inch])
        inv_detail_table.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f7f9fc')),
            ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#dce4ee')),
            ('LINEBELOW',     (0, 0), (-1, -2), 0.5, colors.HexColor('#dce4ee')),
        ]))

        bill_to_section = Table(
            [[bill_to_para, inv_detail_table]],
            colWidths=[3.5*inch, 3.0*inch]
        )
        bill_to_section.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',   (0, 0), (0, 0), 0),
            ('RIGHTPADDING',  (0, 0), (0, 0), 12),
            ('LEFTPADDING',   (1, 0), (1, 0), 0),
            ('RIGHTPADDING',  (1, 0), (1, 0), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(bill_to_section)
        story.append(Spacer(1, 0.25*inch))

        item_desc_style = ParagraphStyle(
            'ItemDesc', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#333333')
        )

        table_data = [["SERVICES", "PRICE", "Days/OT", "AMOUNT"]]
        for item in self.items_data_list:
            desc_html = item['description']
            if item.get('discount', 0) > 0:
                desc_html += (
                    f"<br/><font size='7.5' color='#888888'>Discount: {item['discount']}%</font>"
                )
            if item.get('note'):
                desc_html += (
                    f"<br/><font size='7.5' color='#888888'>{item['note']}</font>"
                )
            table_data.append([
                Paragraph(desc_html, item_desc_style),
                f"AED {item['unit_price']:.2f}",
                f"{item['quantity']:.0f}",
                f"AED {item['amount']:.2f}"
            ])

        if len(table_data) == 1:
            table_data.append(["", "", "", ""])

        table = Table(table_data, colWidths=[2.8*inch, 1.5*inch, 1.0*inch, 1.2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('ALIGN',         (0, 0), (0, -1), 'LEFT'),
            ('ALIGN',         (1, 0), (-1, -1), 'LEFT'),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING',    (0, 0), (-1, 0), 8),
            ('FONTSIZE',      (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
            ('GRID',          (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('TOPPADDING',    (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        story.append(table)

        pre_discount, discount_amount, _, vat_amount, grand_total = self.calculate_total()
        story.append(Spacer(1, 0.2*inch))

        cy = self.company_info.get('currency', 'AED')
        summary_data = [
            [Paragraph("Subtotal", styles['Normal']),
             Paragraph(f"{cy} {pre_discount:.2f}", styles['Normal'])],
        ]
        if discount_amount > 0:
            summary_data.append([
                Paragraph("Discount", styles['Normal']),
                Paragraph(f"- {cy} {discount_amount:.2f}", styles['Normal'])
            ])
        if vat_amount > 0:
            summary_data.append([
                Paragraph("VAT (5%)", styles['Normal']),
                Paragraph(f"{cy} {vat_amount:.2f}", styles['Normal'])
            ])
        summary_data.append([
            Paragraph("Total", styles['Normal']),
            Paragraph(f"{cy} {grand_total:.2f}", styles['Normal'])
        ])

        summary_table = Table(summary_data, colWidths=[5.0*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN',         (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME',      (0, 0), (0, -1), 'Helvetica'),
            ('FONTSIZE',      (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.2*inch))

        amount_due_data = [[
            Paragraph("<b>Amount due</b>",
                      ParagraphStyle('ADL', parent=styles['Normal'], fontSize=12, fontName='Helvetica-Bold')),
            Paragraph(f"<b>{cy} {grand_total:.2f}</b>",
                      ParagraphStyle('ADV', parent=styles['Normal'], fontSize=14, fontName='Helvetica-Bold'))
        ]]
        amount_due_table = Table(amount_due_data, colWidths=[5.0*inch, 1.5*inch])
        amount_due_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(amount_due_table)

        story.append(Spacer(1, 0.3*inch))

        footer_style = ParagraphStyle(
            'FooterLabel',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
            fontName='Helvetica-Bold',
            spaceAfter=3
        )

        footer_text_style = ParagraphStyle(
            'FooterText',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#666666'),
            spaceAfter=2
        )

        if self.project_name:
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph(f"<b>Project Name:</b> {self.project_name}", footer_text_style))

        story.append(Spacer(1, 0.15*inch))
        story.append(Paragraph("Payment instruction", footer_style))
        payment_details = (
            f"IBAN: {self.company_info['iban']}<br/>"
            f"Account number: {self.company_info['account_number']}<br/>"
            f"Currency: {self.company_info['currency']}<br/>"
            f"Swift code: {self.company_info['swift_code']}<br/>"
            f"Routing number: {self.company_info['routing_code']}<br/>"
            f"Name: {self.company_info['beneficiary']}"
        )
        story.append(Paragraph(payment_details, footer_text_style))

        if self.notes_data:
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph("Notes", footer_style))
            story.append(Paragraph(self.notes_data, footer_text_style))

        doc.build(story)
    
    def view_all_invoices(self):
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT i.id, i.invoice_number, c.name, c.email,
                   i.total_amount, i.issued_date, i.pdf_path,
                   i.due_date, COALESCE(i.paid_amount, 0),
                   i.customer_id, COALESCE(i.vat_enabled,0),
                   i.notes, i.items_data, COALESCE(i.project_name,'')
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
        ''')
        invoices = cursor.fetchall()
        conn.close()

        if not invoices:
            messagebox.showinfo("No Invoices", "No invoices found.")
            return

        today = datetime.now().date()
        cy    = self.company_info.get('currency', 'AED')

        def classify(inv):
            total      = inv[4]
            paid_amt   = inv[8]
            due_str    = inv[7]
            if paid_amt >= total:
                return 'paid'
            past_due = False
            if due_str:
                try:
                    past_due = datetime.strptime(due_str, "%d-%m-%Y").date() < today
                except ValueError:
                    pass
            if past_due:
                return 'overdue'
            if paid_amt > 0:
                return 'partial'
            return 'unpaid'

        status_order = {'overdue': 0, 'unpaid': 1, 'partial': 2, 'paid': 3}
        invoices_sorted = sorted(invoices, key=lambda x: (status_order[classify(x)], -x[0]))

        list_window = tk.Toplevel(self.root)
        list_window.title("All Invoices")
        list_window.geometry("1020x640")
        list_window.configure(bg='#f5f5f5')

        # ── Header ──────────────────────────────────────────────────
        hdr = tk.Frame(list_window, bg=self.primary_color)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="📋 All Invoices", font=("Segoe UI", 14, "bold"),
                 bg=self.primary_color, fg='white', pady=14, padx=20).pack(side=tk.LEFT)

        outstanding = sum(max(0, inv[4] - inv[8]) for inv in invoices)
        overdue_amt = sum(max(0, inv[4] - inv[8]) for inv in invoices if classify(inv) == 'overdue')
        tk.Label(hdr,
                 text=f"Outstanding: {cy} {outstanding:.2f}   |   Overdue: {cy} {overdue_amt:.2f}",
                 font=("Segoe UI", 9), bg=self.primary_color, fg='#7f9fb5', pady=18
                 ).pack(side=tk.LEFT)

        # ── Tree ────────────────────────────────────────────────────
        tree_frame = tk.Frame(list_window, bg='#f5f5f5')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        cols = ("Invoice", "Customer", "Amount", "Paid", "Issued", "Due", "Status")
        tree = ttk.Treeview(tree_frame, columns=cols, height=18, show='headings')
        widths = [110, 190, 110, 110, 100, 100, 90]
        anchors = [tk.W, tk.W, tk.E, tk.E, tk.W, tk.W, tk.CENTER]
        for col, w, a in zip(cols, widths, anchors):
            tree.column(col, anchor=a, width=w)
            tree.heading(col, text=col, anchor=a)

        tree.tag_configure('overdue', background='#fde8e8', foreground='#7b0000')
        tree.tag_configure('unpaid',  background='#fffbf0', foreground='#7a5500')
        tree.tag_configure('partial', background='#eaf4ff', foreground='#1a4a8a')
        tree.tag_configure('paid',    background='#edfaed', foreground='#1a6e1a')
        tree.tag_configure('group_header', background='#dde4ed',
                           foreground=self.primary_color, font=('Segoe UI', 9, 'bold'))

        invoice_map = {}

        def insert_group(label, rows, tag):
            if not rows:
                return
            hdr_iid = f"hdr_{tag}"
            tree.insert("", tk.END, iid=hdr_iid,
                        values=(f"  {label} ({len(rows)})", "", "", "", "", "", ""),
                        tags=('group_header',))
            for inv in rows:
                iid        = f"inv_{inv[0]}"
                total      = inv[4]
                paid_amt   = inv[8]
                remaining  = max(0.0, total - paid_amt)
                status_lbl = {'overdue':'Overdue','unpaid':'Unpaid',
                              'partial':'Partial','paid':'Paid'}[tag]
                tree.insert("", tk.END, iid=iid,
                            values=(inv[1], inv[2],
                                    f"{cy} {total:.2f}",
                                    f"{cy} {paid_amt:.2f}" if paid_amt > 0 else "—",
                                    inv[5] or "—", inv[7] or "—", status_lbl),
                            tags=(tag,))
                invoice_map[iid] = {
                    'id': inv[0], 'invoice_number': inv[1],
                    'customer_name': inv[2], 'customer_email': inv[3],
                    'total_amount': total, 'paid_amount': paid_amt,
                    'remaining': remaining,
                    'issued_date': inv[5], 'pdf_path': inv[6] or '',
                    'due_date': inv[7], 'customer_id': inv[9],
                    'vat_enabled': inv[10], 'notes': inv[11],
                    'items_data': inv[12], 'project_name': inv[13],
                    'status': tag,
                }

        for tag in ('overdue', 'unpaid', 'partial', 'paid'):
            insert_group(tag.upper(), [i for i in invoices_sorted if classify(i) == tag], tag)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Button rows ─────────────────────────────────────────────
        bf1 = tk.Frame(list_window, bg='#f5f5f5')
        bf1.pack(pady=(4, 2))
        bf2 = tk.Frame(list_window, bg='#f5f5f5')
        bf2.pack(pady=(2, 10))

        def get_sel():
            sel = tree.selection()
            if not sel:
                messagebox.showerror("Error", "Please select an invoice!")
                return None
            iid = sel[0]
            if iid not in invoice_map:
                messagebox.showerror("Error", "Select an invoice row, not a group header.")
                return None
            return iid

        def view_pdf():
            iid = get_sel()
            if not iid:
                return
            p = invoice_map[iid]['pdf_path']
            if p and os.path.exists(p):
                os.startfile(p)
            else:
                messagebox.showerror("Error", "PDF not found. It may have been moved or deleted.")

        def edit_invoice():
            iid = get_sel()
            if not iid:
                return
            self.load_invoice_for_edit(invoice_map[iid], list_window)

        def duplicate_invoice():
            iid = get_sel()
            if not iid:
                return
            self.duplicate_invoice_action(invoice_map[iid], list_window)

        def record_payment():
            iid = get_sel()
            if not iid:
                return
            d = invoice_map[iid]
            self.record_payment_dialog(d['id'], d['invoice_number'],
                                       d['total_amount'], d['paid_amount'],
                                       list_window)

        def email_invoice():
            iid = get_sel()
            if not iid:
                return
            d = invoice_map[iid]
            self.email_invoice_action(d['invoice_number'], d['pdf_path'],
                                      d['customer_email'], d['total_amount'],
                                      list_window)

        def export_csv():
            self.export_invoices_csv(list(invoice_map.values()))

        def delete_invoice():
            iid = get_sel()
            if not iid:
                return
            if messagebox.askyesno("Confirm", "Delete this invoice? This cannot be undone."):
                conn = sqlite3.connect(self.db_file, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM invoices WHERE id=?", (invoice_map[iid]['id'],))
                conn.commit()
                conn.close()
                self.update_dashboard()
                list_window.destroy()
                self.view_all_invoices()

        row1_btns = [
            ("👁️ View PDF",   view_pdf,       self.accent_color,  12),
            ("✏️ Edit",        edit_invoice,   '#16a085',          9),
            ("📋 Duplicate",   duplicate_invoice,'#8e44ad',        12),
            ("💰 Payment",     record_payment, self.success_color, 11),
        ]
        row2_btns = [
            ("✉️ Email",       email_invoice,  '#2980b9',          9),
            ("📥 Export CSV",  export_csv,     '#e67e22',          12),
            ("📊 Earnings",    lambda: self.earnings_report(list_window), '#8e44ad', 11),
            ("🗑️ Delete",      delete_invoice, self.warning_color, 9),
        ]
        for text, cmd, bg, w in row1_btns:
            self.create_styled_button(bf1, text=text, command=cmd,
                                      bg=bg, width=w, height=1).pack(side=tk.LEFT, padx=4)
        for text, cmd, bg, w in row2_btns:
            self.create_styled_button(bf2, text=text, command=cmd,
                                      bg=bg, width=w, height=1).pack(side=tk.LEFT, padx=4)

        list_window.transient(self.root)
        list_window.grab_set()

    def load_invoice_for_edit(self, inv_data, list_window):
        try:
            items = json.loads(inv_data['items_data'] or '[]')
        except Exception:
            items = []
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, email, phone, address, trade_license FROM customers WHERE id=?",
            (inv_data['customer_id'],))
        crow = cursor.fetchone()
        conn.close()

        self._reset_invoice_state()
        self.current_invoice_id = inv_data['id']
        self.items_data_list    = items
        self.notes_data         = inv_data['notes']
        self.project_name       = inv_data['project_name'] or None
        self.vat_enabled        = bool(inv_data['vat_enabled'])
        self._refresh_vat_subtitle()

        if crow:
            self.customer_data = {
                'id': inv_data['customer_id'],
                'name': crow[0], 'email': crow[1] or '',
                'phone': crow[2] or '', 'address': crow[3] or '',
                'trade_license': crow[4] or '',
            }

        if self._header_title_lbl:
            self._header_title_lbl.config(text=f"Editing  {inv_data['invoice_number']}")
        if self._edit_banner_lbl:
            self._edit_banner_lbl.config(
                text=f"  Editing invoice {inv_data['invoice_number']} — "
                     "make changes then click Save & Generate PDF")

        list_window.destroy()
        messagebox.showinfo("Edit Mode",
                            f"Invoice {inv_data['invoice_number']} loaded.\n"
                            "Update any fields, then click Save & Generate PDF.")

    def duplicate_invoice_action(self, inv_data, list_window):
        try:
            items = json.loads(inv_data['items_data'] or '[]')
        except Exception:
            items = []
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, email, phone, address, trade_license FROM customers WHERE id=?",
            (inv_data['customer_id'],))
        crow = cursor.fetchone()
        conn.close()

        self._reset_invoice_state()
        self.items_data_list = items
        self.notes_data      = inv_data['notes']
        self.project_name    = inv_data['project_name'] or None
        self.vat_enabled     = bool(inv_data['vat_enabled'])
        self._refresh_vat_subtitle()

        if crow:
            self.customer_data = {
                'id': inv_data['customer_id'],
                'name': crow[0], 'email': crow[1] or '',
                'phone': crow[2] or '', 'address': crow[3] or '',
                'trade_license': crow[4] or '',
            }

        self.save_draft()
        list_window.destroy()
        messagebox.showinfo("Duplicated",
                            f"Invoice {inv_data['invoice_number']} duplicated as a new invoice.\n"
                            "Review the fields and click Save & Generate PDF.")

    def record_payment_dialog(self, invoice_id, invoice_number, total_amount, paid_amount, parent):
        cy        = self.company_info.get('currency', 'AED')
        remaining = max(0.0, total_amount - paid_amount)

        dlg = tk.Toplevel(parent)
        dlg.title(f"Record Payment — {invoice_number}")
        dlg.geometry("400x320")
        dlg.resizable(False, False)
        dlg.configure(bg='#f5f5f5')
        tk.Frame(dlg, bg=self.success_color).pack(fill=tk.X)
        tk.Label(dlg.winfo_children()[-1], text=f"💰 Record Payment — {invoice_number}",
                 font=("Segoe UI", 12, "bold"), bg=self.success_color,
                 fg='white', pady=12).pack()

        cf = tk.Frame(dlg, bg='#f5f5f5')
        cf.pack(fill=tk.BOTH, expand=True, padx=22, pady=16)

        for lbl, val in [("Invoice total:", f"{cy} {total_amount:.2f}"),
                         ("Already paid:",  f"{cy} {paid_amount:.2f}"),
                         ("Remaining:",     f"{cy} {remaining:.2f}")]:
            row = tk.Frame(cf, bg='#f5f5f5')
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=lbl, font=("Segoe UI", 10), bg='#f5f5f5',
                     fg='#555', width=16, anchor='w').pack(side=tk.LEFT)
            tk.Label(row, text=val, font=("Segoe UI", 10, "bold"), bg='#f5f5f5',
                     fg=self.primary_color).pack(side=tk.LEFT)

        tk.Label(cf, text="Payment amount:", font=("Segoe UI", 10),
                 bg='#f5f5f5', fg=self.primary_color).pack(anchor='w', pady=(12, 2))
        amt_entry = tk.Entry(cf, width=20, font=("Segoe UI", 11),
                             relief=tk.FLAT, bg='white', bd=1)
        amt_entry.insert(0, f"{remaining:.2f}")
        amt_entry.pack(anchor='w', ipady=7)

        def do_record():
            try:
                payment = float(amt_entry.get().strip())
            except ValueError:
                messagebox.showerror("Error", "Enter a valid number.", parent=dlg)
                return
            if payment <= 0:
                messagebox.showerror("Error", "Amount must be positive.", parent=dlg)
                return
            new_paid = min(total_amount, paid_amount + payment)
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE invoices SET paid_amount=?, paid=? WHERE id=?",
                (new_paid, 1 if new_paid >= total_amount else 0, invoice_id))
            conn.commit()
            conn.close()
            self.update_dashboard()
            dlg.destroy()
            parent.destroy()
            self.view_all_invoices()

        def mark_full():
            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("UPDATE invoices SET paid_amount=?, paid=1 WHERE id=?",
                           (total_amount, invoice_id))
            conn.commit()
            conn.close()
            self.update_dashboard()
            dlg.destroy()
            parent.destroy()
            self.view_all_invoices()

        bf = tk.Frame(dlg, bg='#f5f5f5')
        bf.pack(fill=tk.X, padx=22, pady=(0, 16))
        self.create_styled_button(bf, text="✓ Record", command=do_record,
                                  bg=self.success_color, width=11, height=1).pack(side=tk.LEFT, padx=(0,6))
        self.create_styled_button(bf, text="✓ Mark Fully Paid", command=mark_full,
                                  bg='#16a085', width=16, height=1).pack(side=tk.LEFT)

        dlg.transient(parent)
        dlg.grab_set()

    def email_invoice_action(self, invoice_number, pdf_path, customer_email,
                             total_amount, parent):
        cy      = self.company_info.get('currency', 'AED')
        subject = f"Invoice {invoice_number} from {self.company_info['name']}"
        body    = (
            f"Dear Customer,\n\n"
            f"Please find attached invoice {invoice_number}.\n\n"
            f"Total Amount: {cy} {total_amount:.2f}\n\n"
            f"Payment details:\n"
            f"IBAN: {self.company_info.get('iban','')}\n"
            f"Account: {self.company_info.get('account_number','')}\n"
            f"Swift: {self.company_info.get('swift_code','')}\n\n"
            f"Thank you for your business!\n\n"
            f"{self.company_info['name']}\n"
            f"{self.company_info.get('phone','')}\n"
            f"{self.company_info.get('email','')}"
        )
        to  = customer_email or ''
        url = (f"mailto:{to}?subject={urllib.parse.quote(subject)}"
               f"&body={urllib.parse.quote(body)}")
        webbrowser.open(url)
        msg = "Your email client has been opened with a pre-filled message."
        if pdf_path and os.path.exists(pdf_path):
            msg += f"\n\nPlease attach the PDF manually:\n{pdf_path}"
        messagebox.showinfo("Email Prepared", msg, parent=parent)

    def export_invoices_csv(self, inv_list):
        cy   = self.company_info.get('currency', 'AED')
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="invoices_export.csv")
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Invoice #", "Customer", f"Total ({cy})",
                                 f"Paid ({cy})", f"Remaining ({cy})",
                                 "Issued", "Due", "Status"])
                for d in inv_list:
                    writer.writerow([
                        d['invoice_number'], d['customer_name'],
                        f"{d['total_amount']:.2f}",
                        f"{d['paid_amount']:.2f}",
                        f"{d['remaining']:.2f}",
                        d['issued_date'] or '', d['due_date'] or '',
                        d['status'].capitalize()])
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed:\n{e}")

    def earnings_report(self, parent=None):
        """Earnings report dialog with date range filter and PDF export"""
        parent = parent or self.root

        dialog = tk.Toplevel(parent)
        dialog.title("Earnings Report")
        dialog.geometry("480x490")
        dialog.resizable(False, False)
        dialog.configure(bg='#f5f5f5')

        title_frame = tk.Frame(dialog, bg='#8e44ad')
        title_frame.pack(fill=tk.X)
        tk.Label(
            title_frame, text="📊 Earnings Report",
            font=("Segoe UI", 14, "bold"),
            bg='#8e44ad', fg='white', pady=15
        ).pack()

        content = tk.Frame(dialog, bg='#f5f5f5')
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        tk.Label(content, text="Date range — based on invoice issue date:",
                 font=("Segoe UI", 10, "bold"), bg='#f5f5f5', fg=self.primary_color
                 ).pack(anchor='w', pady=(0, 10))

        range_frame = tk.Frame(content, bg='#f5f5f5')
        range_frame.pack(fill=tk.X, pady=(0, 4))

        tk.Label(range_frame, text="From:", font=("Segoe UI", 10),
                 bg='#f5f5f5', fg=self.primary_color).grid(row=0, column=0, padx=(0, 6), sticky='w')
        from_entry = tk.Entry(range_frame, width=13, font=("Segoe UI", 10),
                              relief=tk.FLAT, bg='white', bd=1)
        from_entry.grid(row=0, column=1, ipady=7, padx=(0, 20))
        from_entry.insert(0, "01-01-" + datetime.now().strftime("%Y"))

        tk.Label(range_frame, text="To:", font=("Segoe UI", 10),
                 bg='#f5f5f5', fg=self.primary_color).grid(row=0, column=2, padx=(0, 6), sticky='w')
        to_entry = tk.Entry(range_frame, width=13, font=("Segoe UI", 10),
                            relief=tk.FLAT, bg='white', bd=1)
        to_entry.grid(row=0, column=3, ipady=7)
        to_entry.insert(0, datetime.now().strftime("%d-%m-%Y"))

        tk.Label(content, text="Format: DD-MM-YYYY",
                 font=("Segoe UI", 8), bg='#f5f5f5', fg='#aaaaaa').pack(anchor='w', pady=(2, 16))

        # ── Results card ─────────────────────────────────────────
        card = tk.Frame(content, bg='white', relief=tk.FLAT, bd=1)
        card.pack(fill=tk.BOTH, expand=True)

        result_rows_def = [
            ('count',   "Invoices in range:",  self.primary_color),
            ('total',   "Total invoiced:",     self.primary_color),
            ('paid',    "Paid:",               self.success_color),
            ('unpaid',  "Unpaid:",             '#e67e22'),
        ]
        result_labels = {}
        for i, (key, label_text, color) in enumerate(result_rows_def):
            row = tk.Frame(card, bg='white')
            row.pack(fill=tk.X, padx=18, pady=10)
            tk.Label(row, text=label_text, font=("Segoe UI", 10),
                     bg='white', fg='#555555', width=22, anchor='w').pack(side=tk.LEFT)
            lbl = tk.Label(row, text="—", font=("Segoe UI", 11, "bold"),
                           bg='white', fg=color, anchor='e')
            lbl.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            result_labels[key] = lbl
            if i < len(result_rows_def) - 1:
                tk.Frame(card, bg='#f0f0f0', height=1).pack(fill=tk.X, padx=18)

        last_result = {'data': None}

        def get_data():
            try:
                from_dt = datetime.strptime(from_entry.get().strip(), "%d-%m-%Y")
                to_dt   = datetime.strptime(to_entry.get().strip(),   "%d-%m-%Y")
            except ValueError:
                messagebox.showerror("Error", "Please enter dates in DD-MM-YYYY format.", parent=dialog)
                return None
            if from_dt > to_dt:
                messagebox.showerror("Error", "From date must be before To date.", parent=dialog)
                return None

            conn = sqlite3.connect(self.db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT i.invoice_number, c.name, i.issued_date, i.total_amount, COALESCE(i.paid, 0)
                FROM invoices i
                JOIN customers c ON i.customer_id = c.id
            ''')
            rows = cursor.fetchall()
            conn.close()

            in_range = []
            for inv_num, cust_name, issued, amount, paid in rows:
                if not issued:
                    continue
                try:
                    inv_dt = datetime.strptime(issued, "%d-%m-%Y")
                except ValueError:
                    continue
                if from_dt <= inv_dt <= to_dt:
                    in_range.append((inv_num, cust_name, issued, amount, paid))

            in_range.sort(key=lambda x: (x[4], x[2]))  # unpaid first, then date

            total_amt  = sum(r[3] for r in in_range)
            paid_amt   = sum(r[3] for r in in_range if r[4] == 1)
            unpaid_amt = sum(r[3] for r in in_range if r[4] == 0)

            return {
                'from_dt':     from_dt,
                'to_dt':       to_dt,
                'invoices':    in_range,
                'total_amt':   total_amt,
                'paid_amt':    paid_amt,
                'unpaid_amt':  unpaid_amt,
                'paid_count':  sum(1 for r in in_range if r[4] == 1),
                'unpaid_count':sum(1 for r in in_range if r[4] == 0),
            }

        def calculate():
            data = get_data()
            if not data:
                return
            last_result['data'] = data
            result_labels['count'].config(text=str(len(data['invoices'])))
            result_labels['total'].config(text=f"AED {data['total_amt']:.2f}")
            result_labels['paid'].config(text=f"AED {data['paid_amt']:.2f}")
            result_labels['unpaid'].config(text=f"AED {data['unpaid_amt']:.2f}")

        def export_pdf():
            data = last_result['data']
            if not data:
                data = get_data()
                if not data:
                    return
                last_result['data'] = data

            default_name = (
                f"Earnings_{data['from_dt'].strftime('%Y%m%d')}"
                f"_{data['to_dt'].strftime('%Y%m%d')}.pdf"
            )
            pdf_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile=default_name,
                parent=dialog
            )
            if not pdf_path:
                return
            try:
                self.generate_earnings_pdf(data, pdf_path)
                messagebox.showinfo("Success", f"Earnings report saved!\n{pdf_path}", parent=dialog)
                os.startfile(pdf_path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export PDF:\n{str(e)}", parent=dialog)

        btn_row = tk.Frame(content, bg='#f5f5f5')
        btn_row.pack(anchor='w', pady=(14, 0))

        def export_csv():
            data = last_result['data']
            if not data:
                data = get_data()
                if not data:
                    return
                last_result['data'] = data
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile=f"Earnings_{data['from_dt'].strftime('%Y%m%d')}"
                            f"_{data['to_dt'].strftime('%Y%m%d')}.csv",
                parent=dialog)
            if not path:
                return
            cy = self.company_info.get('currency', 'AED')
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Invoice #", "Customer", "Issued",
                                     f"Amount ({cy})", "Status"])
                    for inv_num, cust, issued, amount, paid in data['invoices']:
                        writer.writerow([inv_num, cust, issued or '',
                                         f"{amount:.2f}",
                                         "Paid" if paid else "Unpaid"])
                    writer.writerow([])
                    writer.writerow(["", "", "Total", f"{data['total_amt']:.2f}", ""])
                    writer.writerow(["", "", "Paid",  f"{data['paid_amt']:.2f}",  ""])
                    writer.writerow(["", "", "Unpaid",f"{data['unpaid_amt']:.2f}",""])
                messagebox.showinfo("Exported", f"Saved to:\n{path}", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", f"Export failed:\n{e}", parent=dialog)

        self.create_styled_button(
            btn_row, text="Calculate",
            command=calculate, bg='#8e44ad', width=11, height=1
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.create_styled_button(
            btn_row, text="Export PDF",
            command=export_pdf, bg=self.primary_color, width=11, height=1
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.create_styled_button(
            btn_row, text="Export CSV",
            command=export_csv, bg='#e67e22', width=11, height=1
        ).pack(side=tk.LEFT)

        dialog.transient(parent)
        dialog.grab_set()

    def generate_earnings_pdf(self, data, pdf_path):
        """Generate a styled earnings report PDF"""
        doc = SimpleDocTemplate(
            pdf_path, pagesize=letter,
            topMargin=0.5*inch, bottomMargin=0.6*inch,
            leftMargin=1.0*inch, rightMargin=1.0*inch
        )
        styles = getSampleStyleSheet()
        story  = []

        # ── Styles ───────────────────────────────────────────────
        er_title_style = ParagraphStyle(
            'ERTitle', parent=styles['Heading1'],
            fontSize=22, textColor=colors.HexColor('#1f4788'),
            spaceAfter=0, alignment=0
        )
        company_right_style = ParagraphStyle(
            'ERCompanyRight', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#555555'),
            alignment=2, leading=14
        )
        period_style = ParagraphStyle(
            'ERPeriod', parent=styles['Normal'],
            fontSize=10, textColor=colors.white, fontName='Helvetica-Bold'
        )
        generated_style = ParagraphStyle(
            'ERGenerated', parent=styles['Normal'],
            fontSize=8, textColor=colors.HexColor('#aaccee'), alignment=2
        )
        section_hdr_style = ParagraphStyle(
            'ERSectionHdr', parent=styles['Normal'],
            fontSize=8.5, textColor=colors.HexColor('#888888'),
            fontName='Helvetica-Bold', spaceBefore=0, spaceAfter=0
        )
        cell_style = ParagraphStyle(
            'ERCell', parent=styles['Normal'],
            fontSize=8.5, textColor=colors.HexColor('#333333'), leading=12
        )
        cell_paid_style = ParagraphStyle(
            'ERCellPaid', parent=styles['Normal'],
            fontSize=8.5, textColor=colors.HexColor('#1a6e1a'),
            fontName='Helvetica-Bold', leading=12
        )
        cell_unpaid_style = ParagraphStyle(
            'ERCellUnpaid', parent=styles['Normal'],
            fontSize=8.5, textColor=colors.HexColor('#a84000'),
            fontName='Helvetica-Bold', leading=12
        )
        detail_hdr_style = ParagraphStyle(
            'ERDetailHdr', parent=styles['Normal'],
            fontSize=8, textColor=colors.white, fontName='Helvetica-Bold'
        )
        summary_lbl_style = ParagraphStyle(
            'ERSumLbl', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#555555')
        )
        summary_blue_style = ParagraphStyle(
            'ERSumBlue', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#1f4788'), fontName='Helvetica-Bold'
        )
        summary_green_style = ParagraphStyle(
            'ERSumGreen', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#1a6e1a'), fontName='Helvetica-Bold'
        )
        summary_orange_style = ParagraphStyle(
            'ERSumOrange', parent=styles['Normal'],
            fontSize=9, textColor=colors.HexColor('#a84000'), fontName='Helvetica-Bold'
        )
        footer_style = ParagraphStyle(
            'ERFooter', parent=styles['Normal'],
            fontSize=7.5, textColor=colors.HexColor('#aaaaaa'), alignment=2
        )

        def make_sep(height=2, color='#dddddd'):
            t = Table([[""]], colWidths=[6.5*inch], rowHeights=[height])
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(-1,-1), colors.HexColor(color)),
                ('LEFTPADDING',   (0,0),(-1,-1), 0),
                ('RIGHTPADDING',  (0,0),(-1,-1), 0),
                ('TOPPADDING',    (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 0),
            ]))
            return t

        def stat_cell(label, value, val_color):
            return Paragraph(
                f"<font size='7' color='#888888'><b>{label}</b></font><br/>"
                f"<font size='12' color='{val_color}'><b>{value}</b></font>",
                ParagraphStyle('sc', parent=styles['Normal'], leading=20)
            )

        # ── Header ───────────────────────────────────────────────
        company_html = (
            f"<font size='11'><b>{self.company_info['name']}</b></font><br/>"
            f"{self.company_info['address']}<br/>"
            f"{self.company_info['phone']}   |   {self.company_info['email']}<br/>"
            f"TRN: {self.company_info['trade_license']}"
        )
        logo_path = self.company_info.get('logo_path', '').strip()
        if logo_path and os.path.exists(logo_path):
            try:
                _li   = RLImage(logo_path)
                _asp  = _li.imageWidth / max(_li.imageHeight, 1)
                _lw   = min(1.6*inch, _li.imageWidth)
                _li   = RLImage(logo_path, width=_lw, height=_lw / _asp)
                _left = Table([[_li], [Paragraph("EARNINGS REPORT", er_title_style)]],
                              colWidths=[3.25*inch])
                _left.setStyle(TableStyle([
                    ('LEFTPADDING',  (0,0),(-1,-1), 0), ('RIGHTPADDING', (0,0),(-1,-1), 0),
                    ('TOPPADDING',   (0,0),(-1,-1), 0), ('BOTTOMPADDING',(0,0),(0,0),   4),
                    ('BOTTOMPADDING',(0,1),(-1,-1), 0),
                ]))
            except Exception:
                _left = Paragraph("EARNINGS REPORT", er_title_style)
        else:
            _left = Paragraph("EARNINGS REPORT", er_title_style)

        top_table = Table(
            [[_left, Paragraph(company_html, company_right_style)]],
            colWidths=[3.25*inch, 3.25*inch]
        )
        top_table.setStyle(TableStyle([
            ('ALIGN',         (0,0),(0,0), 'LEFT'),
            ('ALIGN',         (1,0),(1,0), 'RIGHT'),
            ('VALIGN',        (0,0),(-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0),(-1,-1), 0),
            ('RIGHTPADDING',  (0,0),(-1,-1), 0),
            ('TOPPADDING',    (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ]))
        story.append(top_table)
        story.append(Spacer(1, 0.15*inch))
        story.append(make_sep())
        story.append(Spacer(1, 0.18*inch))

        # ── Period bar ───────────────────────────────────────────
        from_str      = data['from_dt'].strftime("%d %b %Y")
        to_str        = data['to_dt'].strftime("%d %b %Y")
        generated_str = datetime.now().strftime("%d %b %Y, %H:%M")

        period_table = Table(
            [[Paragraph(f"Period:   {from_str}  →  {to_str}", period_style),
              Paragraph(f"Generated: {generated_str}", generated_style)]],
            colWidths=[4.0*inch, 2.5*inch]
        )
        period_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,-1), colors.HexColor('#1f4788')),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('LEFTPADDING',   (0,0),(-1,-1), 14),
            ('RIGHTPADDING',  (0,0),(-1,-1), 14),
            ('TOPPADDING',    (0,0),(-1,-1), 10),
            ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ]))
        story.append(period_table)
        story.append(Spacer(1, 0.22*inch))

        # ── 4 stat boxes ─────────────────────────────────────────
        n_total  = len(data['invoices'])
        n_paid   = data['paid_count']
        n_unpaid = data['unpaid_count']

        stats_data = [[
            stat_cell("INVOICES",           str(n_total),                    '#1f4788'),
            stat_cell("TOTAL INVOICED",     f"AED {data['total_amt']:.2f}",  '#1f4788'),
            stat_cell(f"PAID  ({n_paid})",  f"AED {data['paid_amt']:.2f}",   '#1a6e1a'),
            stat_cell(f"UNPAID  ({n_unpaid})", f"AED {data['unpaid_amt']:.2f}", '#a84000'),
        ]]
        stats_table = Table(stats_data, colWidths=[1.625*inch]*4)
        stats_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(0,0), colors.HexColor('#eef3fb')),
            ('BACKGROUND',    (1,0),(1,0), colors.HexColor('#eef3fb')),
            ('BACKGROUND',    (2,0),(2,0), colors.HexColor('#edfaed')),
            ('BACKGROUND',    (3,0),(3,0), colors.HexColor('#fff8ef')),
            ('BOX',           (0,0),(0,0), 0.5, colors.HexColor('#c8d8f0')),
            ('BOX',           (1,0),(1,0), 0.5, colors.HexColor('#c8d8f0')),
            ('BOX',           (2,0),(2,0), 0.5, colors.HexColor('#b8e8b8')),
            ('BOX',           (3,0),(3,0), 0.5, colors.HexColor('#f5d9b0')),
            ('LEFTPADDING',   (0,0),(-1,-1), 14),
            ('RIGHTPADDING',  (0,0),(-1,-1), 14),
            ('TOPPADDING',    (0,0),(-1,-1), 12),
            ('BOTTOMPADDING', (0,0),(-1,-1), 12),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))

        # ── Invoice detail table ─────────────────────────────────
        story.append(Paragraph("INVOICE DETAILS", section_hdr_style))
        story.append(Spacer(1, 0.07*inch))
        story.append(make_sep(1, '#1f4788'))
        story.append(Spacer(1, 0.1*inch))

        if not data['invoices']:
            story.append(Paragraph(
                "No invoices found in this period.",
                ParagraphStyle('EREmpty', parent=styles['Normal'],
                               fontSize=9, textColor=colors.HexColor('#888888'),
                               alignment=1)
            ))
        else:
            detail_data = [[
                Paragraph("INVOICE #",  detail_hdr_style),
                Paragraph("CUSTOMER",   detail_hdr_style),
                Paragraph("ISSUED",     detail_hdr_style),
                Paragraph("AMOUNT",     detail_hdr_style),
                Paragraph("STATUS",     detail_hdr_style),
            ]]
            row_tags = []
            for inv_num, cust_name, issued, amount, paid in data['invoices']:
                status_style = cell_paid_style if paid else cell_unpaid_style
                detail_data.append([
                    Paragraph(inv_num or "—",      cell_style),
                    Paragraph(cust_name or "—",    cell_style),
                    Paragraph(issued or "—",        cell_style),
                    Paragraph(f"AED {amount:.2f}", cell_style),
                    Paragraph("Paid" if paid else "Unpaid", status_style),
                ])
                row_tags.append(paid)

            style_cmds = [
                ('BACKGROUND',    (0,0),(-1,0),  colors.HexColor('#1f4788')),
                ('GRID',          (0,0),(-1,-1),  0.4, colors.HexColor('#e0e0e0')),
                ('TOPPADDING',    (0,0),(-1,-1),  6),
                ('BOTTOMPADDING', (0,0),(-1,-1),  6),
                ('LEFTPADDING',   (0,0),(-1,-1),  8),
                ('RIGHTPADDING',  (0,0),(-1,-1),  8),
                ('VALIGN',        (0,0),(-1,-1),  'MIDDLE'),
                ('ALIGN',         (3,0),(3,-1),   'RIGHT'),
                ('ALIGN',         (4,0),(4,-1),   'CENTER'),
            ]
            for i, paid in enumerate(row_tags):
                bg = colors.HexColor('#f0faf0') if paid else colors.HexColor('#fff9f0')
                style_cmds.append(('BACKGROUND', (0, i+1), (-1, i+1), bg))

            detail_table = Table(
                detail_data,
                colWidths=[1.1*inch, 2.1*inch, 1.0*inch, 1.3*inch, 1.0*inch]
            )
            detail_table.setStyle(TableStyle(style_cmds))
            story.append(detail_table)

        # ── Summary totals ───────────────────────────────────────
        story.append(Spacer(1, 0.25*inch))
        summary_data = [
            [Paragraph("Total invoiced:", summary_lbl_style),
             Paragraph(f"AED {data['total_amt']:.2f}", summary_blue_style)],
            [Paragraph(f"Paid  ({n_paid})", summary_lbl_style),
             Paragraph(f"AED {data['paid_amt']:.2f}", summary_green_style)],
            [Paragraph(f"Unpaid  ({n_unpaid})", summary_lbl_style),
             Paragraph(f"AED {data['unpaid_amt']:.2f}", summary_orange_style)],
        ]
        summary_table = Table(summary_data, colWidths=[5.0*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN',         (0,0),(0,-1), 'RIGHT'),
            ('ALIGN',         (1,0),(1,-1), 'RIGHT'),
            ('TOPPADDING',    (0,0),(-1,-1), 3),
            ('BOTTOMPADDING', (0,0),(-1,-1), 3),
            ('LINEABOVE',     (0,0),(-1,0),  0.5, colors.HexColor('#cccccc')),
        ]))
        story.append(summary_table)

        # ── Footer ───────────────────────────────────────────────
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(
            f"{self.company_info['name']}  —  Earnings Report  —  Generated {generated_str}",
            footer_style
        ))

        doc.build(story)

if __name__ == "__main__":
    root = tk.Tk()
    app = InvoicingApp(root)
    root.mainloop()
