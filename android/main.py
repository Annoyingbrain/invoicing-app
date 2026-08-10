"""
Invoice App — Kivy/Android Version
MarLoN Creative Solutions (FZC)
"""
import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta

try:
    from android.storage import primary_external_storage_path
    from android.permissions import request_permissions, Permission
    ANDROID = True
except ImportError:
    ANDROID = False

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.core.window import Window

Window.minimum_width, Window.minimum_height = 360, 640

# ── Palette ────────────────────────────────────────────────────────────────
P  = [0.17, 0.24, 0.31, 1]   # #2c3e50  primary dark
A  = [0.20, 0.60, 0.86, 1]   # #3498db  accent blue
G  = [0.15, 0.68, 0.38, 1]   # #27ae60  success green
R  = [0.91, 0.30, 0.24, 1]   # #e74c3c  warning red
T  = [0.09, 0.63, 0.52, 1]   # #16a085  teal
O  = [0.90, 0.49, 0.13, 1]   # #e67e22  orange
V  = [0.56, 0.27, 0.68, 1]   # #8e44ad  purple
W  = [1, 1, 1, 1]             # white
BG = [0.94, 0.96, 0.97, 1]   # #f0f4f8  background

COMPANY = {
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
}


# ── Widget helpers ─────────────────────────────────────────────────────────

def set_bg(widget, color):
    with widget.canvas.before:
        clr = Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, v: setattr(rect, 'pos', v),
                size=lambda w, v: setattr(rect, 'size', v))


def mk_btn(text, color, height=dp(48), fn=None):
    btn = Button(text=text, size_hint_y=None, height=height, font_size=sp(14),
                 bold=True, background_normal='', background_color=color, color=W)
    if fn:
        btn.bind(on_press=lambda *_: fn())
    return btn


def mk_inp(hint='', multiline=False, height=dp(44)):
    return TextInput(hint_text=hint, multiline=multiline, size_hint_y=None,
                     height=height, font_size=sp(14), background_color=W,
                     foreground_color=P, padding=[dp(10), dp(10)])


def mk_lbl(text, size=13, bold=False, color=None, **kw):
    color = color or P
    return Label(text=text, font_size=sp(size), bold=bold, color=color, **kw)


def mk_header(title, color=None, back_fn=None):
    color = color or P
    bar = BoxLayout(size_hint_y=None, height=dp(56))
    set_bg(bar, color)
    if back_fn:
        bb = Button(text='<', size_hint=(None, 1), width=dp(52), font_size=sp(18),
                    background_normal='', background_color=color, color=W, bold=True)
        bb.bind(on_press=lambda *_: back_fn())
        bar.add_widget(bb)
    lbl = mk_lbl(title, 15, bold=True, color=W, halign='left', valign='middle')
    lbl.bind(size=lbl.setter('text_size'))
    bar.add_widget(lbl)
    return bar


def mk_sep(color=None, height=dp(1)):
    sep = Widget(size_hint_y=None, height=height)
    set_bg(sep, color or [0.85, 0.88, 0.91, 1])
    return sep


def popup_msg(title, msg, on_ok=None):
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
    set_bg(content, W)
    lbl = mk_lbl(msg, 13, color=P, halign='center', valign='middle')
    lbl.bind(size=lbl.setter('text_size'))
    content.add_widget(lbl)
    btn = mk_btn('OK', A)
    content.add_widget(btn)
    pop = Popup(title=title, content=content, size_hint=(0.88, None), height=dp(220))
    def _ok(*_):
        pop.dismiss()
        if on_ok:
            on_ok()
    btn.bind(on_press=_ok)
    pop.open()


def popup_confirm(title, msg, on_yes):
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
    set_bg(content, W)
    lbl = mk_lbl(msg, 13, color=P, halign='center', valign='middle')
    lbl.bind(size=lbl.setter('text_size'))
    content.add_widget(lbl)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    yes_btn = mk_btn('Yes', R)
    no_btn  = mk_btn('No',  P)
    row.add_widget(yes_btn)
    row.add_widget(no_btn)
    content.add_widget(row)
    pop = Popup(title=title, content=content, size_hint=(0.88, None), height=dp(250))
    yes_btn.bind(on_press=lambda *_: (on_yes(), pop.dismiss()))
    no_btn.bind(on_press=pop.dismiss)
    pop.open()


def popup_picker(title, options, on_select):
    """Scrollable picker popup."""
    content = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(4))
    set_bg(content, BG)

    sv = ScrollView(do_scroll_x=False, size_hint_y=1)
    grid = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
    grid.bind(minimum_height=grid.setter('height'))

    pop = Popup(title=title, content=content, size_hint=(0.9, 0.7))

    for opt in options:
        btn = mk_btn(opt, A, height=dp(52))
        opt_val = opt
        btn.bind(on_press=lambda *_, v=opt_val: (on_select(v), pop.dismiss()))
        grid.add_widget(btn)

    sv.add_widget(grid)
    content.add_widget(sv)
    content.add_widget(mk_btn('Cancel', P, height=dp(44), fn=pop.dismiss))
    pop.open()


def scroll_view():
    sv = ScrollView(do_scroll_x=False)
    grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None,
                      padding=[dp(12), dp(12), dp(12), dp(12)])
    grid.bind(minimum_height=grid.setter('height'))
    sv.add_widget(grid)
    return sv, grid


def lbl_field(grid, label_text, entry_widget):
    lbl = mk_lbl(label_text, 12, color=P, halign='left', valign='middle',
                 size_hint_y=None, height=dp(26))
    lbl.bind(size=lbl.setter('text_size'))
    grid.add_widget(lbl)
    grid.add_widget(entry_widget)


# ── Database ───────────────────────────────────────────────────────────────

class DB:
    def __init__(self, path):
        self.path = path
        self._init()

    def cx(self):
        return sqlite3.connect(self.path, timeout=10)

    def _init(self):
        c = self.cx()
        c.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT, phone TEXT, address TEXT, trade_license TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_number TEXT UNIQUE,
            customer_id INTEGER, items_data TEXT, notes TEXT, total_amount REAL,
            issued_date TEXT, due_date TEXT, created_at TEXT, pdf_path TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL,
            unit_price REAL DEFAULT 0, discount REAL DEFAULT 0, note TEXT)''')
        cols_inv = {r[1] for r in c.execute("PRAGMA table_info(invoices)").fetchall()}
        for col in ('issued_date', 'due_date', 'pdf_path'):
            if col not in cols_inv:
                c.execute(f'ALTER TABLE invoices ADD COLUMN {col} TEXT')
        cols_cust = {r[1] for r in c.execute("PRAGMA table_info(customers)").fetchall()}
        if 'trade_license' not in cols_cust:
            c.execute('ALTER TABLE customers ADD COLUMN trade_license TEXT')
        c.commit(); c.close()

    def customers(self):
        c = self.cx()
        rows = c.execute(
            "SELECT id,name,email,phone,address,trade_license FROM customers ORDER BY name"
        ).fetchall()
        c.close(); return rows

    def customer(self, cid):
        c = self.cx()
        row = c.execute(
            "SELECT name,email,phone,address,trade_license FROM customers WHERE id=?", (cid,)
        ).fetchone()
        c.close(); return row

    def add_customer(self, name, email, phone, address, lic):
        c = self.cx()
        c.execute(
            "INSERT INTO customers (name,email,phone,address,trade_license) VALUES (?,?,?,?,?)",
            (name, email, phone, address, lic))
        c.commit(); cid = c.lastrowid; c.close(); return cid

    def upd_customer(self, cid, name, email, phone, address, lic):
        c = self.cx()
        c.execute(
            "UPDATE customers SET name=?,email=?,phone=?,address=?,trade_license=? WHERE id=?",
            (name, email, phone, address, lic, cid))
        c.commit(); c.close()

    def del_customer(self, cid):
        c = self.cx()
        c.execute("DELETE FROM customers WHERE id=?", (cid,)); c.commit(); c.close()

    def items(self):
        c = self.cx()
        rows = c.execute(
            "SELECT id,description,unit_price,discount,note FROM items ORDER BY description"
        ).fetchall()
        c.close(); return rows

    def upsert_item(self, desc, price, discount, note):
        c = self.cx()
        ex = c.execute("SELECT id FROM items WHERE description=?", (desc,)).fetchone()
        if ex:
            c.execute("UPDATE items SET unit_price=?,discount=?,note=? WHERE id=?",
                      (price, discount, note, ex[0]))
        else:
            c.execute("INSERT INTO items (description,unit_price,discount,note) VALUES (?,?,?,?)",
                      (desc, price, discount, note))
        c.commit(); c.close()

    def upd_item(self, iid, desc, price, discount, note):
        c = self.cx()
        c.execute("UPDATE items SET description=?,unit_price=?,discount=?,note=? WHERE id=?",
                  (desc, price, discount, note, iid))
        c.commit(); c.close()

    def del_item(self, iid):
        c = self.cx()
        c.execute("DELETE FROM items WHERE id=?", (iid,)); c.commit(); c.close()

    def next_inv_no(self):
        c = self.cx()
        n = c.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(invoice_number,5) AS INTEGER)),0) FROM invoices"
        ).fetchone()[0]
        c.close(); return f"INV-{n+1:04d}"

    def save_invoice(self, inv_no, cid, items, notes, total, issued, due, pdf_path):
        c = self.cx()
        c.execute(
            '''INSERT INTO invoices
               (invoice_number,customer_id,items_data,notes,total_amount,
                issued_date,due_date,created_at,pdf_path)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (inv_no, cid, json.dumps(items), notes, total, issued, due,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pdf_path))
        c.commit(); c.close()

    def invoices(self):
        c = self.cx()
        rows = c.execute(
            '''SELECT i.id,i.invoice_number,cu.name,i.total_amount,i.created_at,i.pdf_path
               FROM invoices i JOIN customers cu ON i.customer_id=cu.id ORDER BY i.id DESC'''
        ).fetchall()
        c.close(); return rows

    def del_invoice(self, iid):
        c = self.cx()
        c.execute("DELETE FROM invoices WHERE id=?", (iid,)); c.commit(); c.close()


# ── PDF generator ──────────────────────────────────────────────────────────

def gen_pdf(customer_data, items, notes, project_name, issued, due, inv_no, out_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer)
    from reportlab.lib import colors as rc

    doc = SimpleDocTemplate(out_path, pagesize=letter,
                             topMargin=0.5*inch, bottomMargin=0.5*inch)
    sty = getSampleStyleSheet()
    story = []

    ts = ParagraphStyle('T', parent=sty['Heading1'], fontSize=24,
                         textColor=rc.HexColor('#1f4788'), spaceAfter=0, alignment=0)
    cs = ParagraphStyle('C', parent=sty['Normal'], fontSize=11,
                         textColor=rc.HexColor('#333333'), spaceAfter=2)
    ds = ParagraphStyle('D', parent=sty['Normal'], fontSize=9,
                         textColor=rc.HexColor('#666666'), spaceAfter=1)
    ls = ParagraphStyle('L', parent=sty['Normal'], fontSize=9,
                         textColor=rc.HexColor('#333333'), fontName='Helvetica-Bold', spaceAfter=2)

    # Header row
    ht = Table([[Paragraph("INVOICE", ts), Paragraph(COMPANY['name'], cs)]],
               colWidths=[3.5*inch, 3.5*inch])
    ht.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('VALIGN', (0,0), (-1,0), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,0), 0), ('RIGHTPADDING', (0,0), (-1,0), 0),
    ]))
    story += [
        ht, Spacer(1, 0.15*inch),
        Paragraph(
            f"{COMPANY['address']}<br/>{COMPANY['phone']}<br/>"
            f"{COMPANY['email']}<br/>TRN: {COMPANY['trade_license']}", ds),
        Spacer(1, 0.2*inch),
    ]

    # Bill-to block
    cname   = customer_data.get('name', '')
    caddr   = customer_data.get('address', '')
    cphone  = customer_data.get('phone', '')
    bt = Table([
        [Paragraph("<b>BILL TO</b>", ls), "",
         Paragraph("<b>INVOICE NUMBER</b>", ls), Paragraph(f"<b>{inv_no}</b>", cs)],
        [Paragraph(cname, cs),  "", Paragraph("<b>ISSUED</b>", ls), Paragraph(issued, ds)],
        [Paragraph(caddr, ds),  "", Paragraph("<b>DUE</b>", ls),    Paragraph(due,    ds)],
        [Paragraph(cphone, ds), "", "", ""],
    ], colWidths=[2.5*inch, 0.5*inch, 1.5*inch, 1.5*inch])
    bt.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,-1), 'LEFT'), ('ALIGN', (2,0), (3,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 3),  ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story += [bt, Spacer(1, 0.25*inch)]

    # Items table
    ids = ParagraphStyle('ID', parent=sty['Normal'], fontSize=9,
                          textColor=rc.HexColor('#333333'))
    td = [["SERVICES", "PRICE", "Days/OT", "AMOUNT"]]
    for it in items:
        dh = it['description']
        if it.get('discount', 0) > 0:
            dh += f"<br/><font size='7.5' color='#888888'>Discount: {it['discount']}%</font>"
        if it.get('note'):
            dh += f"<br/><font size='7.5' color='#888888'>{it['note']}</font>"
        td.append([
            Paragraph(dh, ids),
            f"AED {it['unit_price']:.2f}",
            f"{it['quantity']:.0f}",
            f"AED {it['amount']:.2f}",
        ])
    if len(td) == 1:
        td.append(["", "", "", ""])
    it_tbl = Table(td, colWidths=[2.5*inch, 1.5*inch, 1.75*inch, 1.25*inch])
    it_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), rc.HexColor('#e8e8e8')),
        ('TEXTCOLOR', (0,0), (-1,0), rc.HexColor('#333333')),
        ('ALIGN', (0,0), (0,-1), 'LEFT'), ('ALIGN', (1,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8), ('TOPPADDING', (0,0), (-1,0), 8),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [rc.white, rc.HexColor('#f9f9f9')]),
        ('GRID', (0,0), (-1,-1), 0.5, rc.HexColor('#e0e0e0')),
        ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,1), (-1,-1), 6),  ('BOTTOMPADDING', (0,1), (-1,-1), 6),
    ]))
    story.append(it_tbl)

    # Summary
    pre   = sum(i['quantity'] * i['unit_price'] for i in items)
    total = sum(i['amount'] for i in items)
    disc  = pre - total
    story.append(Spacer(1, 0.2*inch))
    sd = [[Paragraph("Subtotal", sty['Normal']),
           Paragraph(f"AED {pre:.2f}", sty['Normal'])]]
    if disc > 0:
        sd.append([Paragraph("Discount", sty['Normal']),
                   Paragraph(f"- AED {disc:.2f}", sty['Normal'])])
    sd.append([Paragraph("Total", sty['Normal']),
               Paragraph(f"AED {total:.2f}", sty['Normal'])])
    st = Table(sd, colWidths=[4.5*inch, 1.5*inch])
    st.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,-1), 'RIGHT'), ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.2*inch))

    al_sty = ParagraphStyle('AL', parent=sty['Normal'], fontSize=12, fontName='Helvetica-Bold')
    av_sty = ParagraphStyle('AV', parent=sty['Normal'], fontSize=14, fontName='Helvetica-Bold')
    ad = Table([[Paragraph("<b>Amount due</b>", al_sty),
                  Paragraph(f"<b>AED {total:.2f}</b>", av_sty)]],
               colWidths=[4.5*inch, 1.5*inch])
    ad.setStyle(TableStyle([('ALIGN',(0,0),(0,0),'RIGHT'), ('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(ad)
    story.append(Spacer(1, 0.3*inch))

    fl = ParagraphStyle('FL', parent=sty['Normal'], fontSize=9,
                         textColor=rc.HexColor('#333333'), fontName='Helvetica-Bold', spaceAfter=3)
    ft = ParagraphStyle('FT', parent=sty['Normal'], fontSize=8,
                         textColor=rc.HexColor('#666666'), spaceAfter=2)
    if project_name:
        story += [Spacer(1, 0.15*inch),
                  Paragraph(f"<b>Project Name:</b> {project_name}", ft)]
    story += [
        Spacer(1, 0.15*inch),
        Paragraph("Payment instruction", fl),
        Paragraph(
            f"IBAN: {COMPANY['iban']}<br/>"
            f"Account number: {COMPANY['account_number']}<br/>"
            f"Currency: {COMPANY['currency']}<br/>"
            f"Swift code: {COMPANY['swift_code']}<br/>"
            f"Routing number: {COMPANY['routing_code']}<br/>"
            f"Name: {COMPANY['beneficiary']}", ft),
    ]
    if notes:
        story += [Spacer(1, 0.15*inch), Paragraph("Notes", fl), Paragraph(notes, ft)]
    doc.build(story)


def open_file(path):
    if ANDROID:
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Uri    = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(Uri.parse('file://' + path), 'application/pdf')
            intent.addFlags(0x00000001)
            PythonActivity.mActivity.startActivity(intent)
        except Exception:
            popup_msg('PDF Saved', f'Saved to:\n{path}')
    elif sys.platform == 'win32':
        os.startfile(path)
    else:
        import subprocess
        subprocess.call(['xdg-open', path])


# ── Screens ────────────────────────────────────────────────────────────────

def get_app():
    return App.get_running_app()


class HomeScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Create Invoice  —  MarLoN', P))

        acc = Widget(size_hint_y=None, height=dp(3))
        set_bg(acc, A)
        root.add_widget(acc)

        sv, grid = scroll_view()

        # Status summary
        cname = app.customer_data['name'] if app.customer_data else '—'
        n_items = len(app.items_data_list)
        status_lbl = mk_lbl(
            f'Customer: {cname}   Items: {n_items}', 11, color=P,
            halign='center', valign='middle', size_hint_y=None, height=dp(32))
        status_lbl.bind(size=status_lbl.setter('text_size'))
        grid.add_widget(status_lbl)

        steps = [
            ("1. Customer",            A, 'customer'),
            ("2. Add Items",           G, 'item_add'),
            ("3. Project Name",        T, 'project'),
            ("4. Notes",               O, 'notes'),
            ("5. Preview Invoice PDF", V, '__preview'),
            ("6. Save & Generate PDF", P, '__save'),
        ]
        for label, color, target in steps:
            grid.add_widget(mk_btn(label, color, height=dp(56),
                                   fn=lambda t=target: self._handle(t)))
            grid.add_widget(mk_sep())

        grid.add_widget(Widget(size_hint_y=None, height=dp(12)))

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        row.add_widget(mk_btn('All Invoices',   P, fn=lambda: self.go('invoices')))
        row.add_widget(mk_btn('Customers',      A, fn=lambda: self.go('customers')))
        row.add_widget(mk_btn('Item Catalog',   G, fn=lambda: self.go('catalog')))
        grid.add_widget(row)

        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))
        grid.add_widget(mk_btn('New Invoice (Reset)', R, fn=self._new_invoice))

        root.add_widget(sv)
        self.add_widget(root)

    def go(self, screen):
        self.manager.current = screen

    def _handle(self, target):
        if   target == '__preview': self._preview()
        elif target == '__save':    self._save()
        else:                       self.go(target)

    def _preview(self):
        app = get_app()
        if not app.items_data_list:
            popup_msg('Preview', 'Add at least one item first (Step 2).'); return
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), 'invoice_preview.pdf')
        issued = app.issued_date or datetime.now().strftime("%d-%m-%Y")
        due    = app.due_date   or (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")
        cdata  = app.customer_data or {'name': '', 'address': '', 'phone': ''}
        try:
            gen_pdf(cdata, app.items_data_list, app.notes_data or '',
                    app.project_name or '', issued, due, 'PREVIEW', tmp)
            open_file(tmp)
        except Exception as e:
            popup_msg('Preview Error', str(e))

    def _save(self):
        app = get_app()
        if not app.customer_data:
            popup_msg('Error', 'Please complete Step 1: Customer first.'); return
        if not app.items_data_list:
            popup_msg('Error', 'Please complete Step 2: Add Items first.'); return
        if not app.issued_date:
            app.issued_date = datetime.now().strftime("%d-%m-%Y")
        if not app.due_date:
            self.go('due_date'); return
        self._do_save()

    def _do_save(self):
        app = get_app()
        inv_no = app.db.next_inv_no()
        os.makedirs(app.pdf_dir, exist_ok=True)
        pdf_path = os.path.join(app.pdf_dir, f"{inv_no}.pdf")
        total = sum(i['amount'] for i in app.items_data_list)
        try:
            gen_pdf(app.customer_data, app.items_data_list, app.notes_data or '',
                    app.project_name or '', app.issued_date, app.due_date, inv_no, pdf_path)
            app.db.save_invoice(inv_no, app.customer_data['id'], app.items_data_list,
                                 app.notes_data or '', total, app.issued_date,
                                 app.due_date, pdf_path)
            app.reset_invoice()
            popup_msg('Saved!', f'Invoice {inv_no} saved.\nPDF: {pdf_path}',
                      on_ok=lambda: self.on_enter())
        except Exception as e:
            popup_msg('Error', f'Failed to save:\n{str(e)}')

    def _new_invoice(self):
        popup_confirm('New Invoice', 'Clear all current invoice data?',
                      on_yes=lambda: (get_app().reset_invoice(),
                                      popup_msg('Ready', 'Invoice cleared. Start with Step 1.')))


# ── Customer screens ───────────────────────────────────────────────────────

class CustomerScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Customer', A, back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()

        # Pick from existing customers
        customers = app.db.customers()
        cust_names = [f"{c[0]}: {c[1]}" for c in customers]
        self._cust_map = {f"{c[0]}: {c[1]}": c for c in customers}

        grid.add_widget(mk_lbl('Select existing customer:', 12, color=P,
                                size_hint_y=None, height=dp(26),
                                halign='left', valign='middle'))
        pick_btn = mk_btn(
            'Pick Existing Customer' if customers else 'No customers yet — create one below',
            A, height=dp(48))
        grid.add_widget(pick_btn)

        if customers:
            def _pick():
                popup_picker('Select Customer', cust_names, self._load_customer)
            pick_btn.bind(on_press=lambda *_: _pick())

        grid.add_widget(mk_sep(height=dp(2)))
        grid.add_widget(mk_lbl('— or enter / edit details below —', 11, color=[0.5,0.5,0.5,1],
                                size_hint_y=None, height=dp(26), halign='center'))

        # Form
        self.e_name    = mk_inp('Customer Name *')
        self.e_license = mk_inp('TRN')
        self.e_email   = mk_inp('Email')
        self.e_phone   = mk_inp('Phone')
        self.e_address = mk_inp('Address')

        lbl_field(grid, 'Customer Name *', self.e_name)
        lbl_field(grid, 'TRN',             self.e_license)
        lbl_field(grid, 'Email',           self.e_email)
        lbl_field(grid, 'Phone',           self.e_phone)
        lbl_field(grid, 'Address',         self.e_address)

        # Pre-fill if customer already selected
        if app.customer_data:
            self._fill(app.customer_data)

        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))
        grid.add_widget(mk_btn('Save Customer', G, fn=self._save))

        root.add_widget(sv)
        self.add_widget(root)
        self._selected_id = app.customer_data['id'] if app.customer_data else None

    def _load_customer(self, val):
        c = self._cust_map.get(val)
        if c:
            self._selected_id = c[0]
            self._fill({'name': c[1], 'email': c[2] or '', 'phone': c[3] or '',
                        'address': c[4] or '', 'trade_license': c[5] or ''})

    def _fill(self, d):
        self.e_name.text    = d.get('name', '')
        self.e_license.text = d.get('trade_license', '')
        self.e_email.text   = d.get('email', '')
        self.e_phone.text   = d.get('phone', '')
        self.e_address.text = d.get('address', '')

    def _save(self):
        app = get_app()
        name = self.e_name.text.strip()
        if not name:
            popup_msg('Error', 'Customer name is required.'); return

        email   = self.e_email.text.strip()
        phone   = self.e_phone.text.strip()
        address = self.e_address.text.strip()
        lic     = self.e_license.text.strip()

        if self._selected_id:
            app.db.upd_customer(self._selected_id, name, email, phone, address, lic)
            cid = self._selected_id
        else:
            cid = app.db.add_customer(name, email, phone, address, lic)
            self._selected_id = cid

        app.customer_data = {'id': cid, 'name': name, 'email': email,
                              'phone': phone, 'address': address, 'trade_license': lic}
        popup_msg('Saved', f'Customer "{name}" saved.', on_ok=lambda: setattr(self.manager, 'current', 'home'))


class CustomerListScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Manage Customers', A,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()
        customers = get_app().db.customers()

        if not customers:
            grid.add_widget(mk_lbl('No customers yet.', 13, color=P,
                                    size_hint_y=None, height=dp(50),
                                    halign='center', valign='middle'))
        else:
            for c in customers:
                cid, name, email, phone = c[0], c[1], c[2], c[3]
                row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(6), padding=[0, dp(4)])
                set_bg(row, W)

                info = BoxLayout(orientation='vertical', padding=[dp(8), dp(4)])
                set_bg(info, W)
                t = mk_lbl(name, 13, bold=True, color=P, halign='left', valign='middle')
                t.bind(size=t.setter('text_size'))
                s = mk_lbl(f'{email or ""} {phone or ""}', 10, color=[0.5,0.5,0.5,1],
                            halign='left', valign='middle')
                s.bind(size=s.setter('text_size'))
                info.add_widget(t)
                info.add_widget(s)

                edit_btn = mk_btn('Edit', A, height=dp(40),
                                   fn=lambda _c=c: self._edit(_c))
                del_btn  = mk_btn('Del',  R, height=dp(40),
                                   fn=lambda _cid=cid, _n=name: self._delete(_cid, _n))
                edit_btn.size_hint_x = None; edit_btn.width = dp(64)
                del_btn.size_hint_x  = None; del_btn.width  = dp(48)

                row.add_widget(info)
                row.add_widget(edit_btn)
                row.add_widget(del_btn)
                grid.add_widget(row)
                grid.add_widget(mk_sep())

        root.add_widget(sv)
        self.add_widget(root)

    def _edit(self, c):
        app = get_app()
        app.edit_customer_data = {
            'id': c[0], 'name': c[1], 'email': c[2] or '', 'phone': c[3] or '',
            'address': c[4] or '', 'trade_license': c[5] or ''
        }
        self.manager.current = 'customer_edit'

    def _delete(self, cid, name):
        def _do():
            get_app().db.del_customer(cid)
            self.on_enter()
        popup_confirm('Delete', f'Delete customer "{name}"?', on_yes=_do)


class CustomerEditScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        d = getattr(app, 'edit_customer_data', {})
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Edit Customer', A,
                                   back_fn=lambda: setattr(self.manager, 'current', 'customers')))

        sv, grid = scroll_view()

        self.e_name    = mk_inp('Name *');         self.e_name.text    = d.get('name', '')
        self.e_license = mk_inp('TRN');              self.e_license.text = d.get('trade_license', '')
        self.e_email   = mk_inp('Email');           self.e_email.text   = d.get('email', '')
        self.e_phone   = mk_inp('Phone');           self.e_phone.text   = d.get('phone', '')
        self.e_address = mk_inp('Address');         self.e_address.text = d.get('address', '')

        lbl_field(grid, 'Name *',         self.e_name)
        lbl_field(grid, 'TRN',            self.e_license)
        lbl_field(grid, 'Email',          self.e_email)
        lbl_field(grid, 'Phone',          self.e_phone)
        lbl_field(grid, 'Address',        self.e_address)

        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))
        grid.add_widget(mk_btn('Update Customer', G, fn=self._save))

        root.add_widget(sv)
        self.add_widget(root)
        self._cid = d.get('id')

    def _save(self):
        name = self.e_name.text.strip()
        if not name:
            popup_msg('Error', 'Name is required.'); return
        get_app().db.upd_customer(
            self._cid, name, self.e_email.text.strip(),
            self.e_phone.text.strip(), self.e_address.text.strip(),
            self.e_license.text.strip())
        popup_msg('Updated', f'Customer "{name}" updated.',
                  on_ok=lambda: setattr(self.manager, 'current', 'customers'))


# ── Item screens ───────────────────────────────────────────────────────────

class ItemAddScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        n = len(app.items_data_list)
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header(f'Add Item  (invoice has {n})', G,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()

        # Catalog picker
        catalog = app.db.items()
        self._cat_map = {row[1]: row for row in catalog}
        cat_btn = mk_btn('Pick from Catalog' if catalog else 'No catalog items yet',
                         A, height=dp(48))
        if catalog:
            cat_btn.bind(on_press=lambda *_: popup_picker(
                'Pick Item', list(self._cat_map.keys()), self._fill_from_catalog))
        grid.add_widget(cat_btn)
        grid.add_widget(mk_sep(height=dp(2)))

        self.e_desc     = mk_inp('Description *')
        self.e_qty      = mk_inp('Quantity *')
        self.e_price    = mk_inp('Unit Price (AED) *')
        self.e_discount = mk_inp('Discount %');   self.e_discount.text = '0'
        self.e_note     = mk_inp('Note')

        lbl_field(grid, 'Description *',    self.e_desc)
        lbl_field(grid, 'Quantity *',       self.e_qty)
        lbl_field(grid, 'Unit Price (AED)', self.e_price)
        lbl_field(grid, 'Discount %',       self.e_discount)
        lbl_field(grid, 'Note',             self.e_note)

        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(mk_btn('Add to Invoice', G, fn=self._add))
        row.add_widget(mk_btn('Add Another',    A, fn=self._add_another))
        grid.add_widget(row)

        # Show current items
        if app.items_data_list:
            grid.add_widget(mk_sep(height=dp(2)))
            grid.add_widget(mk_lbl(f'Items in this invoice ({n}):', 12, color=P,
                                    size_hint_y=None, height=dp(28), halign='left'))
            for i, item in enumerate(app.items_data_list):
                lbl = mk_lbl(
                    f"  {i+1}. {item['description']}  x{item['quantity']:.0f}  AED {item['amount']:.2f}",
                    11, color=P, size_hint_y=None, height=dp(28),
                    halign='left', valign='middle')
                lbl.bind(size=lbl.setter('text_size'))
                grid.add_widget(lbl)
            grid.add_widget(mk_btn('Clear All Items', R, fn=self._clear_items))

        root.add_widget(sv)
        self.add_widget(root)

    def _fill_from_catalog(self, name):
        row = self._cat_map.get(name)
        if row:
            self.e_desc.text     = row[1]
            self.e_price.text    = str(row[2])
            self.e_discount.text = str(row[3])
            self.e_note.text     = row[4] or ''

    def _collect(self):
        desc = self.e_desc.text.strip()
        if not desc or not self.e_qty.text or not self.e_price.text:
            popup_msg('Error', 'Description, Quantity, and Price are required.')
            return None
        try:
            qty      = float(self.e_qty.text)
            price    = float(self.e_price.text)
            discount = float(self.e_discount.text or '0')
        except ValueError:
            popup_msg('Error', 'Quantity, Price, Discount must be numbers.')
            return None
        note = self.e_note.text.strip()
        get_app().db.upsert_item(desc, price, discount, note)
        return {
            'description': desc, 'quantity': qty, 'unit_price': price,
            'discount': discount, 'note': note,
            'amount': qty * price * (1 - discount / 100),
        }

    def _add(self):
        item = self._collect()
        if item:
            get_app().items_data_list.append(item)
            popup_msg('Added', f'"{item["description"]}" added.',
                      on_ok=lambda: setattr(self.manager, 'current', 'home'))

    def _add_another(self):
        item = self._collect()
        if item:
            get_app().items_data_list.append(item)
            self.on_enter()

    def _clear_items(self):
        popup_confirm('Clear Items', 'Remove all items from this invoice?',
                      on_yes=lambda: (get_app().items_data_list.clear(), self.on_enter()))


class ItemCatalogScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Item Catalog', G,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()
        items = get_app().db.items()

        if not items:
            grid.add_widget(mk_lbl('No catalog items yet.\nAdd items via Step 2.', 13,
                                    color=P, size_hint_y=None, height=dp(60),
                                    halign='center', valign='middle'))
        else:
            for it in items:
                iid, desc, price, discount, note = it
                row = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(6), padding=[0, dp(4)])
                set_bg(row, W)

                info = BoxLayout(orientation='vertical', padding=[dp(8), dp(4)])
                set_bg(info, W)
                t = mk_lbl(desc, 13, bold=True, color=P, halign='left', valign='middle')
                t.bind(size=t.setter('text_size'))
                s = mk_lbl(f'AED {price:.2f}  Disc: {discount}%  {note or ""}', 10,
                            color=[0.5,0.5,0.5,1], halign='left', valign='middle')
                s.bind(size=s.setter('text_size'))
                info.add_widget(t)
                info.add_widget(s)

                edit_btn = mk_btn('Edit', A, height=dp(40), fn=lambda _i=it: self._edit(_i))
                del_btn  = mk_btn('Del',  R, height=dp(40), fn=lambda _id=iid, _d=desc: self._del(_id, _d))
                edit_btn.size_hint_x = None; edit_btn.width = dp(64)
                del_btn.size_hint_x  = None; del_btn.width  = dp(48)

                row.add_widget(info)
                row.add_widget(edit_btn)
                row.add_widget(del_btn)
                grid.add_widget(row)
                grid.add_widget(mk_sep())

        root.add_widget(sv)
        self.add_widget(root)

    def _edit(self, it):
        app = get_app()
        app.edit_item_data = {
            'id': it[0], 'description': it[1], 'price': str(it[2]),
            'discount': str(it[3]), 'note': it[4] or ''
        }
        self.manager.current = 'item_edit'

    def _del(self, iid, desc):
        def _do():
            get_app().db.del_item(iid)
            self.on_enter()
        popup_confirm('Delete', f'Delete "{desc}" from catalog?', on_yes=_do)


class ItemEditScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        d = getattr(app, 'edit_item_data', {})
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Edit Item', G,
                                   back_fn=lambda: setattr(self.manager, 'current', 'catalog')))

        sv, grid = scroll_view()

        self.e_desc     = mk_inp('Description *');  self.e_desc.text     = d.get('description', '')
        self.e_price    = mk_inp('Price (AED)');     self.e_price.text    = d.get('price', '0')
        self.e_discount = mk_inp('Discount %');      self.e_discount.text = d.get('discount', '0')
        self.e_note     = mk_inp('Note');            self.e_note.text     = d.get('note', '')

        lbl_field(grid, 'Description *', self.e_desc)
        lbl_field(grid, 'Price (AED)',   self.e_price)
        lbl_field(grid, 'Discount %',    self.e_discount)
        lbl_field(grid, 'Note',          self.e_note)

        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))
        grid.add_widget(mk_btn('Update Item', G, fn=self._save))

        root.add_widget(sv)
        self.add_widget(root)
        self._iid = d.get('id')

    def _save(self):
        desc = self.e_desc.text.strip()
        if not desc:
            popup_msg('Error', 'Description is required.'); return
        try:
            price    = float(self.e_price.text or '0')
            discount = float(self.e_discount.text or '0')
        except ValueError:
            popup_msg('Error', 'Price and Discount must be numbers.'); return
        get_app().db.upd_item(self._iid, desc, price, discount, self.e_note.text.strip())
        popup_msg('Updated', f'"{desc}" updated.',
                  on_ok=lambda: setattr(self.manager, 'current', 'catalog'))


# ── Simple text input screens ──────────────────────────────────────────────

class ProjectScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Project Name', T,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()
        grid.add_widget(mk_lbl('Enter an optional project reference name:', 12, color=P,
                                size_hint_y=None, height=dp(32), halign='left'))
        self.e_project = mk_inp('Project Name (optional)')
        self.e_project.text = app.project_name or ''
        grid.add_widget(self.e_project)
        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))
        grid.add_widget(mk_btn('Save', T, fn=self._save))
        root.add_widget(sv)
        self.add_widget(root)

    def _save(self):
        val = self.e_project.text.strip() or None
        get_app().project_name = val
        popup_msg('Saved', f'Project: {val or "(none)"}',
                  on_ok=lambda: setattr(self.manager, 'current', 'home'))


class NotesScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Notes', O,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()
        grid.add_widget(mk_lbl('Additional notes or payment terms:', 12, color=P,
                                size_hint_y=None, height=dp(32), halign='left'))
        self.e_notes = mk_inp('Notes...', multiline=True, height=dp(180))
        self.e_notes.text = app.notes_data or ''
        grid.add_widget(self.e_notes)
        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))
        grid.add_widget(mk_btn('Save Notes', O, fn=self._save))
        root.add_widget(sv)
        self.add_widget(root)

    def _save(self):
        val = self.e_notes.text.strip() or None
        get_app().notes_data = val
        popup_msg('Saved', 'Notes saved.',
                  on_ok=lambda: setattr(self.manager, 'current', 'home'))


class DueDateScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        app = get_app()
        default_due = (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('Invoice Due Date', P,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()
        grid.add_widget(mk_lbl('Enter due date (DD-MM-YYYY):', 12, color=P,
                                size_hint_y=None, height=dp(32), halign='left'))
        self.e_due = mk_inp('DD-MM-YYYY')
        self.e_due.text = app.due_date or default_due
        grid.add_widget(self.e_due)

        grid.add_widget(mk_lbl(f'Default (30 days): {default_due}', 11,
                                color=[0.5,0.5,0.5,1], size_hint_y=None, height=dp(28),
                                halign='left'))
        grid.add_widget(Widget(size_hint_y=None, height=dp(8)))

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(mk_btn('Use 30 Days',  G, fn=lambda: self._set(default_due)))
        row.add_widget(mk_btn('Set Custom',   A, fn=self._set_custom))
        grid.add_widget(row)

        root.add_widget(sv)
        self.add_widget(root)
        self._default_due = default_due

    def _set(self, val):
        get_app().due_date = val
        popup_msg('Due Date Set', f'Due: {val}',
                  on_ok=lambda: self._proceed())

    def _set_custom(self):
        val = self.e_due.text.strip()
        try:
            datetime.strptime(val, "%d-%m-%Y")
        except ValueError:
            popup_msg('Error', 'Enter date as DD-MM-YYYY (e.g. 30-07-2026)'); return
        self._set(val)

    def _proceed(self):
        home = self.manager.get_screen('home')
        self.manager.current = 'home'
        home._do_save()


# ── Invoice list ───────────────────────────────────────────────────────────

class InvoiceListScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        self._build()

    def _build(self):
        root = BoxLayout(orientation='vertical')
        set_bg(root, BG)
        root.add_widget(mk_header('All Invoices', P,
                                   back_fn=lambda: setattr(self.manager, 'current', 'home')))

        sv, grid = scroll_view()
        invoices = get_app().db.invoices()

        if not invoices:
            grid.add_widget(mk_lbl('No invoices yet.', 13, color=P,
                                    size_hint_y=None, height=dp(60),
                                    halign='center', valign='middle'))
        else:
            for inv in invoices:
                iid, inv_no, cname, total, created_at, pdf_path = inv
                row = BoxLayout(size_hint_y=None, height=dp(72), spacing=dp(6), padding=[0, dp(4)])
                set_bg(row, W)

                info = BoxLayout(orientation='vertical', padding=[dp(8), dp(4)])
                set_bg(info, W)
                t = mk_lbl(f'{inv_no}  —  {cname}', 13, bold=True, color=P,
                            halign='left', valign='middle')
                t.bind(size=t.setter('text_size'))
                s = mk_lbl(f'AED {total:.2f}   {created_at[:10]}', 11,
                            color=[0.5,0.5,0.5,1], halign='left', valign='middle')
                s.bind(size=s.setter('text_size'))
                info.add_widget(t)
                info.add_widget(s)

                view_btn = mk_btn('PDF', A, height=dp(44),
                                   fn=lambda _p=pdf_path, _n=inv_no: self._view(_p, _n))
                del_btn  = mk_btn('Del', R, height=dp(44),
                                   fn=lambda _id=iid, _n=inv_no: self._delete(_id, _n))
                view_btn.size_hint_x = None; view_btn.width = dp(58)
                del_btn.size_hint_x  = None; del_btn.width  = dp(48)

                row.add_widget(info)
                row.add_widget(view_btn)
                row.add_widget(del_btn)
                grid.add_widget(row)
                grid.add_widget(mk_sep())

        root.add_widget(sv)
        self.add_widget(root)

    def _view(self, pdf_path, inv_no):
        if pdf_path and os.path.exists(pdf_path):
            open_file(pdf_path)
        else:
            popup_msg('Not Found', f'PDF for {inv_no} not found.\nPath: {pdf_path or "unknown"}')

    def _delete(self, iid, inv_no):
        def _do():
            get_app().db.del_invoice(iid)
            self.on_enter()
        popup_confirm('Delete', f'Delete invoice {inv_no}?', on_yes=_do)


# ── App ────────────────────────────────────────────────────────────────────

class InvoiceApp(App):
    title = 'Invoice — MarLoN'

    # Invoice state
    customer_data   = None
    items_data_list = None
    notes_data      = None
    project_name    = None
    issued_date     = None
    due_date        = None

    # Editing state
    edit_customer_data = None
    edit_item_data     = None

    db      = None
    pdf_dir = None

    def build(self):
        self.items_data_list = []

        # Paths
        if ANDROID:
            try:
                ext = primary_external_storage_path()
                self.pdf_dir = os.path.join(ext, 'Documents', 'MarLoN_Invoices')
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE,
                                     Permission.READ_EXTERNAL_STORAGE])
            except Exception:
                self.pdf_dir = os.path.join(self.user_data_dir, 'invoices')
        else:
            self.pdf_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'invoices')

        self.db = DB(os.path.join(self.user_data_dir, 'invoices.db'))

        sm = ScreenManager(transition=SlideTransition())
        for name, cls in [
            ('home',          HomeScreen),
            ('customer',      CustomerScreen),
            ('customers',     CustomerListScreen),
            ('customer_edit', CustomerEditScreen),
            ('item_add',      ItemAddScreen),
            ('catalog',       ItemCatalogScreen),
            ('item_edit',     ItemEditScreen),
            ('project',       ProjectScreen),
            ('notes',         NotesScreen),
            ('due_date',      DueDateScreen),
            ('invoices',      InvoiceListScreen),
        ]:
            sm.add_widget(cls(name=name))
        return sm

    def reset_invoice(self):
        self.customer_data   = None
        self.items_data_list = []
        self.notes_data      = None
        self.project_name    = None
        self.issued_date     = None
        self.due_date        = None


if __name__ == '__main__':
    InvoiceApp().run()
