from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.base import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.report import Report, ReportType
from app.models.company import Company
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.audit_log import AuditAction
from app.models.tally_masters import TallyLedger
from app.services.audit_service import audit_service
from app.core.config import settings
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import os

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    report_type: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    title: Optional[str] = None
    party_id: Optional[str] = None           # customer/vendor UUID for statement reports
    enable_ai_summary: Optional[bool] = False        # standalone AI summary of current period
    enable_ai_comparison: Optional[bool] = False
    comparison_basis: Optional[str] = None   # "prev_month"|"prev_year"|"prev_quarter"|"custom"
    comparison_period_start: Optional[datetime] = None
    comparison_period_end: Optional[datetime] = None


# ─── Font registration ────────────────────────────────────────────────────────

def _register_unicode_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        ("C:/Windows/Fonts/arial.ttf",    "C:/Windows/Fonts/arialbd.ttf",    "Arial",    "Arial-Bold"),
        ("C:/Windows/Fonts/calibri.ttf",  "C:/Windows/Fonts/calibrib.ttf",   "Calibri",  "Calibri-Bold"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "DejaVu",   "DejaVu-Bold"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "Liberation", "Liberation-Bold"),
        ("/Library/Fonts/Arial.ttf",      "/Library/Fonts/Arial Bold.ttf",   "Arial",    "Arial-Bold"),
    ]
    already_registered = set(pdfmetrics.getRegisteredFontNames())
    for reg_path, bold_path, reg_name, bold_name in candidates:
        if os.path.exists(reg_path) and os.path.exists(bold_path):
            try:
                if reg_name not in already_registered:
                    pdfmetrics.registerFont(TTFont(reg_name, reg_path))
                if bold_name not in already_registered:
                    pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                return reg_name, bold_name
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


# ─── PDF generation ───────────────────────────────────────────────────────────

def generate_pdf_report(
    report_type: str, company: Company, data: dict,
    period_start: datetime, period_end: datetime, title: str,
    ai_insight: Optional[str] = None,
) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
    from reportlab.lib.units import cm

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"{settings.UPLOAD_DIR}/report_{uuid.uuid4()}.pdf"

    FONT, FONT_BOLD = _register_unicode_fonts()

    def style(name, size, bold=False, color=None, align="LEFT"):
        return ParagraphStyle(
            name,
            fontName=FONT_BOLD if bold else FONT,
            fontSize=size,
            leading=size * 1.4,
            textColor=color or colors.HexColor("#1E293B"),
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0),
        )

    doc = SimpleDocTemplate(filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    story = []

    # ── Header
    story.append(Paragraph("FinPilot AI", style("brand", 22, bold=True, color=colors.HexColor("#4F46E5"))))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(company.name, style("company", 14, bold=True)))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#4F46E5")))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(title, style("title", 16, bold=True)))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Period: {period_start.strftime('%d %b %Y')} – {period_end.strftime('%d %b %Y')}",
        style("meta", 10, color=colors.HexColor("#64748B")),
    ))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}",
        style("meta2", 10, color=colors.HexColor("#64748B")),
    ))
    story.append(Spacer(1, 1*cm))

    def fmt(amount: float) -> str:
        return f"₹{float(amount):,.0f}"

    def make_table(table_data: list, col_widths: list, bold_last=False) -> Table:
        head_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE",   (0, 0), (-1, 0), 10),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("FONTNAME",   (0, 1), (-1, -1), FONT),
            ("FONTSIZE",   (0, 1), (-1, -1), 9),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F7FF")]),
        ]
        if bold_last:
            head_style += [
                ("FONTNAME",   (0, -1), (-1, -1), FONT_BOLD),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF2FF")),
            ]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle(head_style))
        return t

    # ── Report body
    if report_type == ReportType.PROFIT_LOSS:
        summary = data.get("summary", {})
        revenue  = summary.get("revenue",    0)
        expenses = summary.get("expenses",   0)
        profit   = summary.get("net_profit", 0)
        margin   = summary.get("profit_margin", 0)
        table_data = [
            ["Particulars",    "Amount"],
            ["Total Revenue",  fmt(revenue)],
            ["Total Expenses", fmt(expenses)],
            ["Net Profit",     fmt(profit)],
            ["Profit Margin",  f"{float(margin):.1f}%"],
        ]
        story.append(make_table(table_data, [12*cm, 5*cm], bold_last=True))

    elif report_type == ReportType.REVENUE:
        story.append(Paragraph("Revenue Summary", style("h2", 13, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        items = data.get("items", [])
        if items:
            table_data = [["Invoice #", "Customer", "Date", "Amount", "Status"]] + [
                [i.get("invoice_number",""), i.get("customer",""), i.get("date",""),
                 fmt(i.get("amount", 0)), i.get("status","")]
                for i in items[:50]
            ]
            story.append(make_table(table_data, [3*cm, 5*cm, 3*cm, 4*cm, 3*cm]))

    elif report_type == ReportType.EXPENSE:
        story.append(Paragraph("Expense Breakdown", style("h2", 13, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        items = data.get("categories", [])
        if items:
            total = sum(i.get("amount", 0) for i in items)
            table_data = [["Category", "Amount", "% of Total"]] + [
                [i.get("category","Other"), fmt(i.get("amount",0)),
                 f"{i.get('amount',0)/total*100:.1f}%" if total else "0%"]
                for i in items
            ]
            table_data.append(["TOTAL", fmt(total), "100%"])
            story.append(make_table(table_data, [8*cm, 5*cm, 4*cm], bold_last=True))

    elif report_type in (ReportType.MONTHLY_SUMMARY, ReportType.GST_SUMMARY):
        months = data.get("months", [])
        if report_type == ReportType.GST_SUMMARY:
            story.append(Paragraph("GST Summary", style("h2", 13, bold=True)))
            story.append(Spacer(1, 0.3*cm))
            gst_rows = data.get("gst_rows", [])
            if gst_rows:
                tdata = [["Month", "Taxable Sales", "GST Collected", "Taxable Purchases", "GST Paid", "Net GST"]] + [
                    [r["month"], fmt(r["taxable_sales"]), fmt(r["gst_collected"]),
                     fmt(r["taxable_purchases"]), fmt(r["gst_paid"]),
                     fmt(r["gst_collected"] - r["gst_paid"])]
                    for r in gst_rows
                ]
                story.append(make_table(tdata, [2.5*cm, 3*cm, 3*cm, 3.5*cm, 3*cm, 2.5*cm]))
        else:
            story.append(Paragraph("Monthly Financial Summary", style("h2", 13, bold=True)))
            story.append(Spacer(1, 0.3*cm))
            if months:
                table_data = [["Month", "Revenue", "Expenses", "Net Profit", "Margin"]] + [
                    [m["month"], fmt(m["revenue"]), fmt(m["expenses"]),
                     fmt(m["net_profit"]), f"{m.get('margin', 0):.1f}%"]
                    for m in months
                ]
                story.append(make_table(table_data, [3*cm, 3.5*cm, 3.5*cm, 3.5*cm, 3*cm]))

    elif report_type == ReportType.TRIAL_BALANCE:
        story.append(Paragraph("Trial Balance", style("h2", 13, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        ledgers = data.get("ledgers", [])
        total_dr = data.get("total_debit", 0)
        total_cr = data.get("total_credit", 0)
        if ledgers:
            table_data = [["Ledger Name", "Group", "Debit", "Credit"]] + [
                [l["name"], l["group"], fmt(l["debit"]) if l["debit"] else "", fmt(l["credit"]) if l["credit"] else ""]
                for l in ledgers
            ]
            table_data.append(["TOTAL", "", fmt(total_dr), fmt(total_cr)])
            story.append(make_table(table_data, [6*cm, 5*cm, 3*cm, 3*cm], bold_last=True))

    elif report_type in (ReportType.AGED_RECEIVABLES, ReportType.AGED_PAYABLES):
        label = "Aged Receivables" if report_type == ReportType.AGED_RECEIVABLES else "Aged Payables"
        story.append(Paragraph(label, style("h2", 13, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        parties = data.get("parties", [])
        totals = data.get("totals", {})
        if parties:
            table_data = [["Party", "Total Outstanding", "0-30 Days", "31-60 Days", "61-90 Days", "90+ Days"]] + [
                [
                    p["party_name"],
                    fmt(p["total"]),
                    fmt(p["bucket_0_30"]),
                    fmt(p["bucket_31_60"]),
                    fmt(p["bucket_61_90"]),
                    fmt(p["bucket_90_plus"]),
                ]
                for p in parties
            ]
            table_data.append([
                "TOTAL",
                fmt(totals.get("total", 0)),
                fmt(totals.get("bucket_0_30", 0)),
                fmt(totals.get("bucket_31_60", 0)),
                fmt(totals.get("bucket_61_90", 0)),
                fmt(totals.get("bucket_90_plus", 0)),
            ])
            story.append(make_table(table_data, [4*cm, 3*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm], bold_last=True))

    elif report_type in (ReportType.CUSTOMER_STATEMENT, ReportType.VENDOR_STATEMENT):
        party_name = data.get("party_name", "")
        party_gstin = data.get("party_gstin", "")
        opening_balance = data.get("opening_balance", 0)
        closing_balance = data.get("closing_balance", 0)
        transactions = data.get("transactions", [])

        story.append(Paragraph(f"Statement of Account: {party_name}", style("h2", 13, bold=True)))
        if party_gstin:
            story.append(Paragraph(f"GSTIN: {party_gstin}", style("gstin", 9, color=colors.HexColor("#64748B"))))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"Opening Balance: {fmt(opening_balance)}", style("ob", 10, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        if transactions:
            table_data = [["Date", "Voucher #", "Type", "Debit", "Credit", "Running Balance"]] + [
                [
                    t.get("date",""), t.get("voucher_number",""), t.get("type",""),
                    fmt(t["debit"]) if t.get("debit") else "",
                    fmt(t["credit"]) if t.get("credit") else "",
                    fmt(t.get("running_balance", 0)),
                ]
                for t in transactions
            ]
            story.append(make_table(table_data, [2.5*cm, 3*cm, 3*cm, 2.5*cm, 2.5*cm, 3*cm]))
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph(f"Closing Balance: {fmt(closing_balance)}", style("cb", 11, bold=True)))

    else:
        story.append(Paragraph(f"Report type: {report_type}", style("body", 11)))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(str(data)[:500], style("body2", 10)))

    # ── AI Insight box (if provided)
    if ai_insight:
        story.append(Spacer(1, 1*cm))
        ai_table = Table(
            [[Paragraph("\U0001f4a1 AI Insight", style("ai_hdr", 11, bold=True, color=colors.HexColor("#4338CA"))),
              ""],
             [Paragraph(ai_insight, style("ai_body", 10, color=colors.HexColor("#1E293B"))), ""]],
            colWidths=[16.5*cm, 0.5*cm],
        )
        ai_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#4F46E5")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("SPAN", (0, 1), (1, 1)),
        ]))
        story.append(KeepTogether(ai_table))

    story.append(Spacer(1, 2*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Generated by FinPilot AI  •  {company.name}  •  Confidential",
        style("footer", 8, color=colors.HexColor("#94A3B8")),
    ))

    report_subject = (
        report_type.value.replace("_", " ").title() + " Report"
        if hasattr(report_type, "value") else str(report_type)
    )

    def _set_metadata(canvas, _doc):
        canvas.setTitle(title)
        canvas.setAuthor(company.name)
        canvas.setSubject(report_subject)
        canvas.setCreator("FinPilot AI")

    doc.build(story, onFirstPage=_set_metadata, onLaterPages=_set_metadata)
    return filename


# ─── AI Comparative helper ────────────────────────────────────────────────────

def _call_ai_comparison(
    provider: str,
    primary_data: dict,
    comparison_data: dict,
    report_type: str,
    primary_label: str,
    comparison_label: str,
) -> Optional[str]:
    """Call Groq or OpenRouter to generate a comparative analysis paragraph.
    Returns the AI text or None on any failure (graceful degradation)."""
    import httpx

    def _delta_pct(new_val, old_val):
        if not old_val:
            return None
        return round((new_val - old_val) / abs(old_val) * 100, 1)

    # Build a concise numeric summary — never send raw PII to LLM
    summary_lines = [f"Report type: {report_type.replace('_', ' ').title()}",
                     f"Primary period: {primary_label}",
                     f"Comparison period: {comparison_label}", ""]

    def _add_metric(label, pkey, ckey=None):
        pv = primary_data.get(pkey, 0) or 0
        cv = comparison_data.get(ckey or pkey, 0) or 0
        delta = _delta_pct(pv, cv)
        summary_lines.append(
            f"{label}: {pv:,.0f} (was {cv:,.0f})"
            + (f", {'+' if delta >= 0 else ''}{delta}% change" if delta is not None else "")
        )

    s_pri = primary_data.get("summary", {})
    s_cmp = comparison_data.get("summary", {})
    for key in ("revenue", "expenses", "net_profit"):
        label = key.replace("_", " ").title()
        delta = _delta_pct(s_pri.get(key, 0), s_cmp.get(key, 0))
        pv = s_pri.get(key, 0) or 0
        cv = s_cmp.get(key, 0) or 0
        summary_lines.append(
            f"{label}: {pv:,.0f} (was {cv:,.0f})"
            + (f", {'+' if (delta or 0) >= 0 else ''}{delta}% change" if delta is not None else "")
        )

    prompt = (
        "You are a financial analyst assistant. Based on the following key metric comparison, "
        "write a concise 3-5 sentence commentary explaining what changed between the two periods "
        "and what it might mean for the business. Be specific about the numbers. "
        "Do not add headings, bullet points, or markdown formatting — plain paragraph only.\n\n"
        + "\n".join(summary_lines)
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        if provider == "groq" and settings.GROQ_API_KEY:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": settings.GROQ_MODEL, "messages": messages, "max_tokens": 300},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()

        elif settings.OPENROUTER_API_KEY:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": settings.AI_MODEL, "messages": messages, "max_tokens": 300},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


# ─── Data builders ────────────────────────────────────────────────────────────

def _build_pl_data(company_id, period_start, period_end, db) -> dict:
    revenue = float(db.query(func.sum(Invoice.total_amount)).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID]),
        Invoice.invoice_date.between(period_start, period_end),
    ).scalar() or 0)
    expenses = float(db.query(func.sum(Expense.total_amount)).filter(
        Expense.company_id == company_id,
        Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
        Expense.expense_date.between(period_start, period_end),
    ).scalar() or 0)
    return {
        "summary": {
            "revenue": revenue, "expenses": expenses,
            "net_profit": revenue - expenses,
            "profit_margin": round((revenue - expenses) / revenue * 100, 1) if revenue > 0 else 0,
        }
    }


def _build_monthly_data(company_id, period_start, period_end, db) -> dict:
    from collections import defaultdict
    months_data: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "expenses": 0.0})

    invoices = db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID]),
        Invoice.invoice_date.between(period_start, period_end),
    ).all()
    for inv in invoices:
        key = inv.invoice_date.strftime("%b %Y")
        months_data[key]["revenue"] += float(inv.total_amount or 0)

    exps = db.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
        Expense.expense_date.between(period_start, period_end),
    ).all()
    for exp in exps:
        key = exp.expense_date.strftime("%b %Y")
        months_data[key]["expenses"] += float(exp.total_amount or 0)

    months_list = []
    for month_key in sorted(months_data.keys(), key=lambda x: datetime.strptime(x, "%b %Y")):
        r = months_data[month_key]["revenue"]
        e = months_data[month_key]["expenses"]
        months_list.append({
            "month": month_key, "revenue": r, "expenses": e,
            "net_profit": r - e,
            "margin": round((r - e) / r * 100, 1) if r > 0 else 0,
        })
    return {"months": months_list, "summary": {"revenue": sum(m["revenue"] for m in months_list),
                                                 "expenses": sum(m["expenses"] for m in months_list)}}


def _build_gst_data(company_id, period_start, period_end, db) -> dict:
    from collections import defaultdict
    gst: dict[str, dict] = defaultdict(lambda: {
        "taxable_sales": 0.0, "gst_collected": 0.0,
        "taxable_purchases": 0.0, "gst_paid": 0.0,
    })
    sales_invs = db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.invoice_date.between(period_start, period_end),
    ).all()
    for inv in sales_invs:
        key = inv.invoice_date.strftime("%b %Y")
        amt = float(inv.total_amount or 0)
        gst_amt = float(getattr(inv, "gst_amount", None) or amt * 0.18)
        gst[key]["taxable_sales"] += amt - gst_amt
        gst[key]["gst_collected"] += gst_amt

    purchase_invs = db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.PURCHASE,
        Invoice.invoice_date.between(period_start, period_end),
    ).all()
    for inv in purchase_invs:
        key = inv.invoice_date.strftime("%b %Y")
        amt = float(inv.total_amount or 0)
        gst_amt = float(getattr(inv, "gst_amount", None) or amt * 0.18)
        gst[key]["taxable_purchases"] += amt - gst_amt
        gst[key]["gst_paid"] += gst_amt

    gst_rows = []
    for month_key in sorted(gst.keys(), key=lambda x: datetime.strptime(x, "%b %Y")):
        d = gst[month_key]
        gst_rows.append({"month": month_key, **d})
    return {"gst_rows": gst_rows}


def _build_trial_balance_data(company_id, period_end, db) -> dict:
    ledgers = db.query(TallyLedger).filter(
        TallyLedger.company_id == company_id,
        TallyLedger.is_active == True,
    ).order_by(TallyLedger.name).all()

    rows = []
    total_dr = 0.0
    total_cr = 0.0
    for l in ledgers:
        bal = float(l.closing_balance or 0)
        dr = max(bal, 0)
        cr = abs(min(bal, 0))
        total_dr += dr
        total_cr += cr
        rows.append({
            "name": l.name,
            "group": l.parent_group or "",
            "debit": dr if dr else None,
            "credit": cr if cr else None,
        })
    return {"ledgers": rows, "total_debit": total_dr, "total_credit": total_cr,
            "summary": {"revenue": 0, "expenses": 0}}


def _build_aged_data(company_id, period_end, invoice_type: str, db) -> dict:
    from collections import defaultdict
    now = period_end.date() if hasattr(period_end, "date") else period_end

    inv_type = InvoiceType.SALES if invoice_type == "receivables" else InvoiceType.PURCHASE
    invoices = db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == inv_type,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                             InvoiceStatus.OVERDUE, InvoiceStatus.DRAFT]),
    ).all()

    party_data: dict[str, dict] = defaultdict(lambda: {
        "party_name": "", "total": 0.0,
        "bucket_0_30": 0.0, "bucket_31_60": 0.0,
        "bucket_61_90": 0.0, "bucket_90_plus": 0.0,
    })

    for inv in invoices:
        outstanding = float(inv.total_amount or 0) - float(inv.paid_amount or 0)
        if outstanding <= 0:
            continue
        party_name = (inv.customer.name if inv.customer else None) or "Unknown"
        pid = str(inv.customer_id or inv.vendor_id or party_name)
        party_data[pid]["party_name"] = party_name
        party_data[pid]["total"] += outstanding

        due_date = getattr(inv, "due_date", None) or (inv.invoice_date + timedelta(days=30) if inv.invoice_date else None)
        if due_date:
            due = due_date.date() if hasattr(due_date, "date") else due_date
            days_over = (now - due).days
        else:
            days_over = 0

        if days_over <= 30:
            party_data[pid]["bucket_0_30"] += outstanding
        elif days_over <= 60:
            party_data[pid]["bucket_31_60"] += outstanding
        elif days_over <= 90:
            party_data[pid]["bucket_61_90"] += outstanding
        else:
            party_data[pid]["bucket_90_plus"] += outstanding

    parties = sorted(party_data.values(), key=lambda x: x["total"], reverse=True)
    totals = {
        "total": sum(p["total"] for p in parties),
        "bucket_0_30": sum(p["bucket_0_30"] for p in parties),
        "bucket_31_60": sum(p["bucket_31_60"] for p in parties),
        "bucket_61_90": sum(p["bucket_61_90"] for p in parties),
        "bucket_90_plus": sum(p["bucket_90_plus"] for p in parties),
    }
    return {"parties": parties, "totals": totals, "summary": {"revenue": 0, "expenses": 0}}


def _build_statement_data(company_id, party_id: str, is_customer: bool,
                          period_start, period_end, db) -> dict:
    try:
        pid = uuid.UUID(party_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="Invalid party_id")

    if is_customer:
        party = db.query(Customer).filter(Customer.id == pid, Customer.company_id == company_id).first()
        if not party:
            raise HTTPException(status_code=404, detail="Customer not found")
        party_name = party.name
        party_gstin = getattr(party, "gst_number", None) or ""
        invoices = db.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.customer_id == pid,
            Invoice.invoice_date.between(period_start, period_end),
        ).order_by(Invoice.invoice_date).all()
    else:
        party = db.query(Vendor).filter(Vendor.id == pid, Vendor.company_id == company_id).first()
        if not party:
            raise HTTPException(status_code=404, detail="Vendor not found")
        party_name = party.name
        party_gstin = getattr(party, "gst_number", None) or ""
        invoices = db.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.vendor_id == pid,
            Invoice.invoice_date.between(period_start, period_end),
        ).order_by(Invoice.invoice_date).all()

    opening_balance = 0.0
    running_balance = opening_balance
    transactions = []
    for inv in invoices:
        amt = float(inv.total_amount or 0)
        if is_customer:
            dr_amt = amt
            cr_amt = float(inv.paid_amount or 0) if inv.paid_amount else 0
        else:
            cr_amt = amt
            dr_amt = float(inv.paid_amount or 0) if inv.paid_amount else 0
        running_balance += dr_amt - cr_amt
        transactions.append({
            "date": inv.invoice_date.strftime("%d %b %Y") if inv.invoice_date else "",
            "voucher_number": inv.invoice_number or "",
            "type": inv.invoice_type.value if inv.invoice_type else "",
            "debit": dr_amt if dr_amt else None,
            "credit": cr_amt if cr_amt else None,
            "running_balance": running_balance,
        })

    return {
        "party_name": party_name,
        "party_gstin": party_gstin,
        "opening_balance": opening_balance,
        "closing_balance": running_balance,
        "transactions": transactions,
        "summary": {"revenue": 0, "expenses": 0},
    }


# ─── AI Summary helper ───────────────────────────────────────────────────────

def _call_ai_summary(
    provider: str,
    report_data: dict,
    report_type: str,
    period_label: str,
) -> Optional[str]:
    """Generate a concise AI narrative summary of the current period report data.
    Returns None on any failure (graceful degradation)."""
    import httpx

    s = report_data.get("summary", {})
    revenue = s.get("revenue", 0) or 0
    expenses = s.get("expenses", 0) or 0
    net_profit = s.get("net_profit", revenue - expenses) or 0
    margin = s.get("profit_margin", round((net_profit / revenue * 100), 1) if revenue else 0)

    extra_lines = []
    # Trial balance: add debit/credit totals
    if "total_debit" in report_data:
        extra_lines.append(f"Total Debit: {report_data['total_debit']:,.0f}")
        extra_lines.append(f"Total Credit: {report_data['total_credit']:,.0f}")
    # Aged report: add bucket breakdown
    if "totals" in report_data:
        t = report_data["totals"]
        extra_lines.append(f"Total Outstanding: {t.get('total', 0):,.0f}")
        extra_lines.append(f"0-30 days: {t.get('bucket_0_30', 0):,.0f}")
        extra_lines.append(f"31-60 days: {t.get('bucket_31_60', 0):,.0f}")
        extra_lines.append(f"61-90 days: {t.get('bucket_61_90', 0):,.0f}")
        extra_lines.append(f"90+ days: {t.get('bucket_90_plus', 0):,.0f}")

    prompt_lines = [
        f"Report type: {report_type.replace('_', ' ').title()}",
        f"Period: {period_label}",
        f"Revenue: {revenue:,.0f}",
        f"Expenses: {expenses:,.0f}",
        f"Net Profit: {net_profit:,.0f}",
        f"Profit Margin: {margin:.1f}%",
    ] + extra_lines

    prompt = (
        "You are a financial analyst assistant. Based on the following financial report data, "
        "write a concise 3-5 sentence executive summary highlighting key figures, trends, "
        "and any noteworthy observations. Be specific with numbers. "
        "Do not use bullet points, headings, or markdown — plain paragraph only.\n\n"
        + "\n".join(prompt_lines)
    )

    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "groq" and settings.GROQ_API_KEY:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": settings.GROQ_MODEL, "messages": messages, "max_tokens": 250},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        elif settings.OPENROUTER_API_KEY:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": settings.AI_MODEL, "messages": messages, "max_tokens": 250},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


# ─── Comparison period calculator ────────────────────────────────────────────

def _get_comparison_period(basis: str, primary_start: datetime, primary_end: datetime,
                            custom_start: Optional[datetime], custom_end: Optional[datetime]):
    if basis == "custom" and custom_start and custom_end:
        return custom_start, custom_end, "Custom Period"
    delta = primary_end - primary_start
    if basis == "prev_month":
        cmp_end = primary_start - timedelta(days=1)
        cmp_start = cmp_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = cmp_start.strftime("%b %Y")
    elif basis == "prev_year":
        cmp_start = primary_start.replace(year=primary_start.year - 1)
        cmp_end = primary_end.replace(year=primary_end.year - 1)
        label = f"{cmp_start.strftime('%b %Y')} – {cmp_end.strftime('%b %Y')}"
    elif basis == "prev_quarter":
        cmp_end = primary_start - timedelta(days=1)
        cmp_start = cmp_end - timedelta(days=89)
        label = f"{cmp_start.strftime('%b %Y')} – {cmp_end.strftime('%b %Y')}"
    else:  # default: prev period of same length
        cmp_end = primary_start - timedelta(days=1)
        cmp_start = cmp_end - delta
        label = f"{cmp_start.strftime('%d %b %Y')} – {cmp_end.strftime('%d %b %Y')}"
    return cmp_start, cmp_end, label


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/generate")
def generate_report(
    data: ReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    now = datetime.now(timezone.utc)
    period_start = data.period_start or now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = data.period_end or now

    valid_types = [e.value for e in ReportType]
    report_type_enum = (
        ReportType(data.report_type)
        if data.report_type in valid_types
        else ReportType.PROFIT_LOSS
    )
    cid = current_user.company_id

    # ── Build report data
    report_data: dict = {}

    if report_type_enum == ReportType.PROFIT_LOSS:
        report_data = _build_pl_data(cid, period_start, period_end, db)

    elif report_type_enum == ReportType.REVENUE:
        invoices = db.query(Invoice).filter(
            Invoice.company_id == cid,
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.invoice_date.between(period_start, period_end),
        ).order_by(Invoice.invoice_date.desc()).limit(50).all()
        report_data = {
            "items": [
                {
                    "invoice_number": inv.invoice_number,
                    "customer": inv.customer.name if inv.customer else "",
                    "date": inv.invoice_date.strftime("%d %b %Y"),
                    "amount": float(inv.total_amount),
                    "status": inv.status.value,
                }
                for inv in invoices
            ],
            "summary": {"revenue": sum(float(i.total_amount) for i in invoices), "expenses": 0},
        }

    elif report_type_enum == ReportType.EXPENSE:
        categories = db.query(
            Expense.category, func.sum(Expense.total_amount).label("total")
        ).filter(
            Expense.company_id == cid,
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.expense_date.between(period_start, period_end),
        ).group_by(Expense.category).order_by(func.sum(Expense.total_amount).desc()).all()
        report_data = {
            "categories": [{"category": r.category or "Other", "amount": float(r.total)} for r in categories],
            "summary": {"revenue": 0, "expenses": sum(float(r.total) for r in categories)},
        }

    elif report_type_enum == ReportType.MONTHLY_SUMMARY:
        report_data = _build_monthly_data(cid, period_start, period_end, db)

    elif report_type_enum == ReportType.GST_SUMMARY:
        report_data = _build_gst_data(cid, period_start, period_end, db)

    elif report_type_enum == ReportType.TRIAL_BALANCE:
        report_data = _build_trial_balance_data(cid, period_end, db)

    elif report_type_enum == ReportType.AGED_RECEIVABLES:
        report_data = _build_aged_data(cid, period_end, "receivables", db)

    elif report_type_enum == ReportType.AGED_PAYABLES:
        report_data = _build_aged_data(cid, period_end, "payables", db)

    elif report_type_enum == ReportType.CUSTOMER_STATEMENT:
        if not data.party_id:
            raise HTTPException(status_code=422, detail="party_id is required for Customer Statement")
        report_data = _build_statement_data(cid, data.party_id, True, period_start, period_end, db)

    elif report_type_enum == ReportType.VENDOR_STATEMENT:
        if not data.party_id:
            raise HTTPException(status_code=422, detail="party_id is required for Vendor Statement")
        report_data = _build_statement_data(cid, data.party_id, False, period_start, period_end, db)

    else:
        report_data = {"summary": {"revenue": 0, "expenses": 0}}

    # ── AI Insight (summary and/or comparison — graceful degradation on failure)
    ai_insight: Optional[str] = None
    want_ai = data.enable_ai_summary or data.enable_ai_comparison
    if want_ai:
        try:
            comp_obj = db.query(Company).filter(Company.id == cid).first()
            provider = getattr(comp_obj, "ai_provider", None) or settings.AI_PROVIDER
            primary_label = f"{period_start.strftime('%d %b %Y')} – {period_end.strftime('%d %b %Y')}"
            ai_parts: list[str] = []

            if data.enable_ai_summary:
                summary_text = _call_ai_summary(
                    provider, report_data, report_type_enum.value, primary_label
                )
                if summary_text:
                    ai_parts.append(f"Summary ({primary_label}):\n{summary_text}")

            if data.enable_ai_comparison and data.comparison_basis:
                cmp_start, cmp_end, cmp_label = _get_comparison_period(
                    data.comparison_basis, period_start, period_end,
                    data.comparison_period_start, data.comparison_period_end,
                )
                if report_type_enum == ReportType.PROFIT_LOSS:
                    cmp_data = _build_pl_data(cid, cmp_start, cmp_end, db)
                elif report_type_enum == ReportType.MONTHLY_SUMMARY:
                    cmp_data = _build_monthly_data(cid, cmp_start, cmp_end, db)
                else:
                    cmp_data = _build_pl_data(cid, cmp_start, cmp_end, db)

                comparison_text = _call_ai_comparison(
                    provider, report_data, cmp_data,
                    report_type_enum.value, primary_label, cmp_label,
                )
                if comparison_text:
                    ai_parts.append(f"Comparative Analysis (vs {cmp_label}):\n{comparison_text}")

            if ai_parts:
                ai_insight = "\n\n".join(ai_parts)
        except Exception:
            ai_insight = None  # never block report generation on AI failure

    # ── Generate PDF
    title = data.title or f"{report_type_enum.value.replace('_', ' ').title()} Report"
    pdf_path = generate_pdf_report(
        report_type_enum, company, report_data,
        period_start, period_end, title, ai_insight=ai_insight,
    )

    report_record = Report(
        company_id=cid,
        generated_by=current_user.id,
        report_type=report_type_enum,
        title=title,
        period_start=period_start,
        period_end=period_end,
        parameters={
            "type": data.report_type,
            "party_id": data.party_id,
            "ai_summary": data.enable_ai_summary,
            "ai_comparison": data.enable_ai_comparison,
            "comparison_basis": data.comparison_basis,
        },
        file_path=pdf_path,
        ai_insights=ai_insight,
    )
    db.add(report_record)
    db.commit()

    audit_service.log(db, cid, current_user.id, AuditAction.GENERATE_REPORT,
                      entity_type="report", entity_id=report_record.id,
                      description=f"Generated {title}")

    return {
        "report_id": str(report_record.id),
        "title": title,
        "download_url": f"/api/reports/{report_record.id}/download",
        "data": report_data,
        "ai_insight": ai_insight,
    }


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(
        Report.id == uuid.UUID(report_id),
        Report.company_id == current_user.company_id,
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.file_path and os.path.exists(report.file_path):
        try:
            os.remove(report.file_path)
        except OSError:
            pass
    db.delete(report)
    db.commit()
    return {"deleted": True}


class BulkDeleteRequest(BaseModel):
    ids: list[str]


@router.post("/bulk-delete")
def bulk_delete_reports(
    data: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uuids = []
    for rid in data.ids:
        try:
            uuids.append(uuid.UUID(rid))
        except ValueError:
            pass

    reports = db.query(Report).filter(
        Report.id.in_(uuids),
        Report.company_id == current_user.company_id,
    ).all()

    deleted = 0
    for report in reports:
        if report.file_path and os.path.exists(report.file_path):
            try:
                os.remove(report.file_path)
            except OSError:
                pass
        db.delete(report)
        deleted += 1

    db.commit()
    return {"deleted": deleted}


@router.get("/{report_id}/download")
def download_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(
        Report.id == uuid.UUID(report_id),
        Report.company_id == current_user.company_id,
    ).first()
    if not report or not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(
        path=report.file_path,
        media_type="application/pdf",
        filename=f"{report.title}.pdf",
    )


@router.get("")
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Report).filter(
        Report.company_id == current_user.company_id
    ).order_by(Report.created_at.desc())
    total = q.count()
    reports = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": str(r.id), "title": r.title, "report_type": r.report_type.value,
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "created_at": r.created_at.isoformat(),
                "download_url": f"/api/reports/{r.id}/download",
                "ai_insights": r.ai_insights,
            }
            for r in reports
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


# ─── Ledger/Party search for statement reports ───────────────────────────────

@router.get("/parties/search")
def search_parties(
    q: str = Query("", min_length=0),
    party_type: str = Query("customer", regex="^(customer|vendor)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    if party_type == "customer":
        query = db.query(Customer).filter(
            Customer.company_id == cid,
            Customer.is_active == True,
        )
        if q:
            query = query.filter(Customer.name.ilike(f"%{q}%"))
        items = query.order_by(Customer.name).limit(20).all()
        return [{"id": str(i.id), "name": i.name, "gstin": getattr(i, "gst_number", "")} for i in items]
    else:
        query = db.query(Vendor).filter(
            Vendor.company_id == cid,
            Vendor.is_active == True,
        )
        if q:
            query = query.filter(Vendor.name.ilike(f"%{q}%"))
        items = query.order_by(Vendor.name).limit(20).all()
        return [{"id": str(i.id), "name": i.name, "gstin": getattr(i, "gst_number", "")} for i in items]
