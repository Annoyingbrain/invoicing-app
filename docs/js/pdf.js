/* Invoice PDF rendering with jsPDF, mirroring the layout of the desktop app's generate_pdf(). */

const InvoicePDF = (() => {
  const PAGE_W = 612, PAGE_H = 792; // US Letter in points
  const MARGIN = 36; // 0.5in
  const CONTENT_W = PAGE_W - MARGIN * 2;

  function calcTotals(items, vatEnabled) {
    const preDiscount = items.reduce((s, i) => s + i.quantity * i.unit_price, 0);
    const subtotal = items.reduce((s, i) => s + i.amount, 0);
    const vat = vatEnabled ? Math.round(subtotal * 0.05 * 100) / 100 : 0;
    return {
      preDiscount,
      discount: preDiscount - subtotal,
      subtotal,
      vat,
      total: subtotal + vat,
    };
  }

  function build({ company, customer, invoiceNumber, issuedDate, dueDate, items, notes, projectName, vatEnabled }) {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: 'pt', format: 'letter' });
    const cy = company.currency || 'AED';
    let y = MARGIN;

    // ── Header: logo/title left, company info right ──
    const leftX = MARGIN;
    const rightX = PAGE_W - MARGIN;

    if (company.logo_path) {
      try {
        const props = doc.getImageProperties(company.logo_path);
        const w = Math.min(115, props.width);
        const h = w * (props.height / props.width);
        doc.addImage(company.logo_path, leftX, y, w, h);
        y += h + 6;
      } catch (e) { /* ignore bad image data */ }
    }
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(24);
    doc.setTextColor('#1f4788');
    doc.text('INVOICE', leftX, y + 18);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor('#555555');
    const companyLines = [
      { text: company.name || '', bold: true },
      { text: company.address || '' },
      { text: [company.phone, company.email].filter(Boolean).join('   |   ') },
      { text: company.trade_license ? `TRN: ${company.trade_license}` : '' },
    ].filter(l => l.text);
    let ry = MARGIN + 2;
    for (const line of companyLines) {
      doc.setFont('helvetica', line.bold ? 'bold' : 'normal');
      doc.setFontSize(line.bold ? 11 : 9);
      doc.text(line.text, rightX, ry, { align: 'right' });
      ry += line.bold ? 15 : 13;
    }

    y = Math.max(y + 24, ry) + 10;

    // separator
    doc.setDrawColor('#dddddd');
    doc.setLineWidth(1.5);
    doc.line(leftX, y, rightX, y);
    y += 22;

    // ── Bill To + Invoice details ──
    const billToTop = y;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8);
    doc.setTextColor('#888888');
    doc.text('BILL TO', leftX, y);
    y += 14;

    const billLines = [];
    if (customer?.name) billLines.push({ text: customer.name, bold: true, size: 10 });
    if (customer?.trade_license) billLines.push({ text: `TRN: ${customer.trade_license}`, size: 9 });
    if (customer?.address) billLines.push({ text: customer.address, size: 9 });
    if (customer?.phone) billLines.push({ text: customer.phone, size: 9 });
    if (customer?.email) billLines.push({ text: customer.email, size: 9 });
    doc.setTextColor('#444444');
    for (const l of billLines) {
      doc.setFont('helvetica', l.bold ? 'bold' : 'normal');
      doc.setFontSize(l.size);
      doc.text(l.text, leftX, y);
      y += 14;
    }

    // Invoice details box (right column)
    const boxX = PAGE_W - MARGIN - 190;
    const boxW = 190;
    let by = billToTop;
    const rowsInfo = [
      ['INVOICE NUMBER', invoiceNumber, '#1f4788', 11, true],
      ['ISSUED', issuedDate, '#222222', 9, false],
      ['DUE DATE', dueDate, '#222222', 9, false],
    ];
    const rowH = 24;
    doc.setFillColor('#f7f9fc');
    doc.setDrawColor('#dce4ee');
    doc.setLineWidth(0.7);
    doc.rect(boxX, by, boxW, rowH * rowsInfo.length, 'FD');
    for (let i = 0; i < rowsInfo.length; i++) {
      const rowY = by + rowH * i;
      if (i > 0) doc.line(boxX, rowY, boxX + boxW, rowY);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8);
      doc.setTextColor('#888888');
      doc.text(rowsInfo[i][0], boxX + 8, rowY + 15);
      doc.setFont('helvetica', rowsInfo[i][4] ? 'bold' : 'normal');
      doc.setFontSize(rowsInfo[i][3]);
      doc.setTextColor(rowsInfo[i][2]);
      doc.text(String(rowsInfo[i][1] || ''), boxX + 85, rowY + 15);
    }

    y = Math.max(y, by + rowH * rowsInfo.length) + 20;

    // ── Items table ──
    const cols = [
      { label: 'SERVICES', x: leftX, w: 220 },
      { label: 'PRICE', x: leftX + 220, w: 100 },
      { label: 'QTY', x: leftX + 320, w: 70 },
      { label: 'AMOUNT', x: leftX + 390, w: CONTENT_W - 390 },
    ];
    doc.setFillColor('#e8e8e8');
    doc.rect(leftX, y, CONTENT_W, 22, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor('#333333');
    for (const c of cols) doc.text(c.label, c.x + 6, y + 15);
    y += 22;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    const displayItems = items.length ? items : [{ description: '', quantity: 0, unit_price: 0, amount: 0 }];
    for (let idx = 0; idx < displayItems.length; idx++) {
      const item = displayItems[idx];
      const subLines = [];
      if (item.discount) subLines.push(`Discount: ${item.discount}%`);
      if (item.note) subLines.push(item.note);
      const descLines = doc.splitTextToSize(item.description || '', cols[0].w - 12);
      const rowLineCount = descLines.length + subLines.length;
      const rowH = Math.max(24, rowLineCount * 11 + 12);

      if (idx % 2 === 1) {
        doc.setFillColor('#f9f9f9');
        doc.rect(leftX, y, CONTENT_W, rowH, 'F');
      }

      let ty = y + 15;
      doc.setTextColor('#333333');
      doc.setFontSize(9);
      for (const dl of descLines) { doc.text(dl, cols[0].x + 6, ty); ty += 11; }
      doc.setTextColor('#888888');
      doc.setFontSize(7.5);
      for (const sl of subLines) { doc.text(sl, cols[0].x + 6, ty); ty += 10; }

      doc.setTextColor('#333333');
      doc.setFontSize(9);
      doc.text(`${cy} ${item.unit_price.toFixed(2)}`, cols[1].x + 6, y + 15);
      doc.text(String(item.quantity), cols[2].x + 6, y + 15);
      doc.text(`${cy} ${item.amount.toFixed(2)}`, cols[3].x + 6, y + 15);

      doc.setDrawColor('#e0e0e0');
      doc.setLineWidth(0.5);
      doc.line(leftX, y + rowH, leftX + CONTENT_W, y + rowH);

      y += rowH;
      if (y > PAGE_H - 220) { doc.addPage(); y = MARGIN; }
    }
    y += 20;

    // ── Summary ──
    const totals = calcTotals(items, vatEnabled);
    const summaryRows = [['Subtotal', `${cy} ${totals.preDiscount.toFixed(2)}`]];
    if (totals.discount > 0.004) summaryRows.push(['Discount', `- ${cy} ${totals.discount.toFixed(2)}`]);
    if (totals.vat > 0) summaryRows.push(['VAT (5%)', `${cy} ${totals.vat.toFixed(2)}`]);
    summaryRows.push(['Total', `${cy} ${totals.total.toFixed(2)}`]);

    const summaryLabelX = rightX - 140; // fixed right edge for labels, well clear of the value column
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor('#000000');
    for (const [label, value] of summaryRows) {
      doc.text(label, summaryLabelX, y, { align: 'right' });
      doc.text(value, rightX, y, { align: 'right' });
      y += 16;
    }

    y += 8;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.text('Amount due', summaryLabelX, y, { align: 'right' });
    doc.setFontSize(14);
    doc.text(`${cy} ${totals.total.toFixed(2)}`, rightX, y, { align: 'right' });
    y += 30;

    if (y > PAGE_H - 160) { doc.addPage(); y = MARGIN; }

    // ── Footer: project name, payment instructions, notes ──
    doc.setFont('helvetica', 'normal');
    if (projectName) {
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor('#333333');
      doc.text('Project Name:', leftX, y);
      const labelW = doc.getTextWidth('Project Name: ');
      doc.setFont('helvetica', 'normal');
      doc.setTextColor('#666666');
      doc.text(projectName, leftX + labelW, y);
      y += 18;
    }

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor('#333333');
    doc.text('Payment instruction', leftX, y);
    y += 13;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor('#666666');
    const paymentLines = [
      `IBAN: ${company.iban || ''}`,
      `Account number: ${company.account_number || ''}`,
      `Currency: ${company.currency || ''}`,
      `Swift code: ${company.swift_code || ''}`,
      `Routing number: ${company.routing_code || ''}`,
      `Name: ${company.beneficiary || ''}`,
    ];
    for (const l of paymentLines) { doc.text(l, leftX, y); y += 11; }

    if (notes) {
      y += 10;
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor('#333333');
      doc.text('Notes', leftX, y);
      y += 13;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor('#666666');
      const noteLines = doc.splitTextToSize(notes, CONTENT_W);
      for (const l of noteLines) { doc.text(l, leftX, y); y += 11; }
    }

    return doc;
  }

  function preview(args) {
    const doc = build(args);
    const url = doc.output('bloburl');
    window.open(url, '_blank');
  }

  function download(args, filename) {
    const doc = build(args);
    doc.save(filename);
  }

  return { build, preview, download, calcTotals };
})();

/* Earnings report PDF, mirroring the desktop app's generate_earnings_pdf() at a lighter level of detail. */
const EarningsPDF = (() => {
  const PAGE_W = 612, PAGE_H = 792;
  const MARGIN = 72; // 1in, matching the desktop report's wider margins
  const CONTENT_W = PAGE_W - MARGIN * 2;

  function fmtDate(d) {
    return `${String(d.getDate()).padStart(2, '0')}-${String(d.getMonth() + 1).padStart(2, '0')}-${d.getFullYear()}`;
  }

  function build({ company, fromDt, toDt, data }) {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: 'pt', format: 'letter' });
    const cy = company.currency || 'AED';
    let y = MARGIN;

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(20);
    doc.setTextColor('#1f4788');
    doc.text('Earnings Report', MARGIN, y);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor('#555555');
    doc.text(company.name || '', PAGE_W - MARGIN, y - 4, { align: 'right' });
    doc.setFontSize(8);
    doc.setTextColor('#888888');
    doc.text(`Period: ${fmtDate(fromDt)} to ${fmtDate(toDt)}`, PAGE_W - MARGIN, y + 10, { align: 'right' });
    y += 26;

    doc.setDrawColor('#dddddd');
    doc.setLineWidth(1);
    doc.line(MARGIN, y, PAGE_W - MARGIN, y);
    y += 24;

    // Summary tiles
    const tiles = [
      ['Invoices in range', String(data.invoices.length), '#1f4788'],
      ['Total invoiced', `${cy} ${data.totalAmt.toFixed(2)}`, '#1f4788'],
      ['Paid', `${cy} ${data.paidAmt.toFixed(2)}`, '#1a6e1a'],
      ['Unpaid', `${cy} ${data.unpaidAmt.toFixed(2)}`, '#a84000'],
    ];
    const tileW = CONTENT_W / tiles.length;
    tiles.forEach(([label, value, color], i) => {
      const x = MARGIN + i * tileW;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor('#888888');
      doc.text(label, x, y);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(12);
      doc.setTextColor(color);
      doc.text(value, x, y + 18);
    });
    y += 42;
    doc.setDrawColor('#eeeeee');
    doc.line(MARGIN, y, PAGE_W - MARGIN, y);
    y += 22;

    // Detail table — widths sum to exactly CONTENT_W so STATUS isn't squeezed
    // past the header's colored background (was invisible: white text on white).
    const cols = [
      { label: 'INVOICE', x: MARGIN, w: 70 },
      { label: 'CUSTOMER', x: MARGIN + 70, w: 170 },
      { label: 'ISSUED', x: MARGIN + 240, w: 70 },
      { label: 'AMOUNT', x: MARGIN + 310, w: 90 },
      { label: 'STATUS', x: MARGIN + 400, w: CONTENT_W - 400 },
    ];
    doc.setFillColor('#8e44ad');
    doc.rect(MARGIN, y, CONTENT_W, 20, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8);
    doc.setTextColor('#ffffff');
    for (const c of cols) doc.text(c.label, c.x + 6, y + 13);
    y += 20;

    doc.setFont('helvetica', 'normal');
    for (let idx = 0; idx < data.invoices.length; idx++) {
      const inv = data.invoices[idx];
      const rowH = 18;
      if (y + rowH > PAGE_H - 80) {
        doc.addPage();
        y = MARGIN;
      }
      if (idx % 2 === 1) { doc.setFillColor('#f9f6fb'); doc.rect(MARGIN, y, CONTENT_W, rowH, 'F'); }
      doc.setFontSize(8.5);
      doc.setTextColor('#333333');
      doc.text(inv.invoice_number, cols[0].x + 6, y + 12);
      doc.text(inv.customer_name, cols[1].x + 6, y + 12, { maxWidth: cols[1].w - 10 });
      doc.text(inv.issued_date || '', cols[2].x + 6, y + 12);
      doc.text(`${cy} ${inv.total_amount.toFixed(2)}`, cols[3].x + 6, y + 12);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(inv.paid ? '#1a6e1a' : '#a84000');
      doc.text(inv.paid ? 'Paid' : 'Unpaid', cols[4].x + 6, y + 12);
      doc.setFont('helvetica', 'normal');
      y += rowH;
    }
    if (!data.invoices.length) {
      doc.setFontSize(9);
      doc.setTextColor('#999999');
      doc.text('No invoices in this date range.', MARGIN + 6, y + 14);
      y += 24;
    }

    y += 10;
    doc.setDrawColor('#eeeeee');
    doc.line(MARGIN, y, PAGE_W - MARGIN, y);
    y += 18;
    doc.setFontSize(7.5);
    doc.setTextColor('#aaaaaa');
    doc.text(`Generated ${fmtDate(new Date())}`, PAGE_W - MARGIN, y, { align: 'right' });

    return doc;
  }

  function download(args, filename) {
    build(args).save(filename);
  }

  return { build, download };
})();
