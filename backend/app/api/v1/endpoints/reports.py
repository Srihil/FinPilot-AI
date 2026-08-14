from fastapi import APIRouter, Depends, HTTPException
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
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from app.core.config import settings
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import uuid
import os

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    report_type: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    title: Optional[str] = None


def _register_unicode_fonts() -> tuple[str, str]:
    """Register a Unicode-capable TTF font for PDF generation.
    Falls back through available options; returns (regular_name, bold_name).
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        # Windows
        ("C:/Windows/Fonts/arial.ttf",    "C:/Windows/Fonts/arialbd.ttf",    "Arial",    "Arial-Bold"),
        ("C:/Windows/Fonts/calibri.ttf",  "C:/Windows/Fonts/calibrib.ttf",   "Calibri",  "Calibri-Bold"),
        # Linux
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "DejaVu",   "DejaVu-Bold"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "Liberation", "Liberation-Bold"),
        # macOS
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

    # Last resort: Vera (bundled with ReportLab, no ₹ but won't crash)
    return "Helvetica", "Helvetica-Bold"


def generate_pdf_report(
    report_type: str, company: Company, data: dict,
    period_start: datetime, period_end: datetime, title: str
) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.units import cm

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"{settings.UPLOAD_DIR}/report_{uuid.uuid4()}.pdf"

    # Register a font that contains the ₹ glyph
    FONT, FONT_BOLD = _register_unicode_fonts()

    # Custom styles using the Unicode-capable font
    def style(name, size, bold=False, color=None, align="LEFT"):
        s = ParagraphStyle(
            name,
            fontName=FONT_BOLD if bold else FONT,
            fontSize=size,
            leading=size * 1.4,
            textColor=color or colors.HexColor("#1E293B"),
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0),
        )
        return s

    doc = SimpleDocTemplate(filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
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

    # ── Shared helpers ─────────────────────────────────────────────────────────
    def fmt(amount: float) -> str:
        """Format as Indian rupees with ₹ symbol."""
        return f"₹{float(amount):,.0f}"   # U+20B9 = ₹

    def make_table(table_data: list, col_widths: list, bold_last=False) -> Table:
        body_font = FONT
        head_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE",   (0, 0), (-1, 0), 10),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("FONTNAME",   (0, 1), (-1, -1), body_font),
            ("FONTSIZE",   (0, 1), (-1, -1), 10),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F7FF")]),
        ]
        if bold_last:
            head_style += [
                ("FONTNAME",   (0, -1), (-1, -1), FONT_BOLD),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF2FF")),
            ]
        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle(head_style))
        return t

    # ── Report-specific content ────────────────────────────────────────────────
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
        story.append(make_table(table_data, [12*cm, 5*cm]))

    elif report_type == ReportType.REVENUE:
        story.append(Paragraph("Revenue Summary", style("h2", 13, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        items = data.get("items", [])
        if items:
            table_data = [["Invoice #", "Customer", "Date", "Amount", "Status"]] + [
                [
                    i.get("invoice_number", ""),
                    i.get("customer", ""),
                    i.get("date", ""),
                    fmt(i.get("amount", 0)),
                    i.get("status", ""),
                ]
                for i in items[:30]
            ]
            story.append(make_table(table_data, [3*cm, 5*cm, 3*cm, 4*cm, 3*cm]))

    elif report_type == ReportType.EXPENSE:
        story.append(Paragraph("Expense Breakdown", style("h2", 13, bold=True)))
        story.append(Spacer(1, 0.3*cm))
        items = data.get("categories", [])
        if items:
            total = sum(i.get("amount", 0) for i in items)
            table_data = [["Category", "Amount", "% of Total"]] + [
                [
                    i.get("category", "Other"),
                    fmt(i.get("amount", 0)),
                    f"{i.get('amount', 0) / total * 100:.1f}%" if total else "0%",
                ]
                for i in items
            ]
            table_data.append(["TOTAL", fmt(total), "100%"])
            story.append(make_table(table_data, [8*cm, 5*cm, 4*cm], bold_last=True))

    else:
        story.append(Paragraph(f"Report type: {report_type}", style("body", 11)))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(str(data)[:500], style("body2", 10)))

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

    report_data = {}
    report_type_enum = ReportType(data.report_type) if data.report_type in [e.value for e in ReportType] else ReportType.PROFIT_LOSS

    if report_type_enum == ReportType.PROFIT_LOSS:
        revenue = float(db.query(func.sum(Invoice.total_amount)).filter(
            Invoice.company_id == current_user.company_id,
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID]),
            Invoice.invoice_date.between(period_start, period_end),
        ).scalar() or 0)
        expenses = float(db.query(func.sum(Expense.total_amount)).filter(
            Expense.company_id == current_user.company_id,
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.expense_date.between(period_start, period_end),
        ).scalar() or 0)
        report_data = {
            "summary": {
                "revenue": revenue, "expenses": expenses,
                "net_profit": revenue - expenses,
                "profit_margin": round((revenue - expenses) / revenue * 100, 1) if revenue > 0 else 0,
            }
        }

    elif report_type_enum == ReportType.REVENUE:
        invoices = db.query(Invoice).filter(
            Invoice.company_id == current_user.company_id,
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
            ]
        }

    elif report_type_enum == ReportType.EXPENSE:
        categories = db.query(
            Expense.category, func.sum(Expense.total_amount).label("total")
        ).filter(
            Expense.company_id == current_user.company_id,
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.expense_date.between(period_start, period_end),
        ).group_by(Expense.category).order_by(func.sum(Expense.total_amount).desc()).all()
        report_data = {
            "categories": [{"category": r.category or "Other", "amount": float(r.total)} for r in categories]
        }

    title = data.title or f"{report_type_enum.value.replace('_', ' ').title()} Report"
    pdf_path = generate_pdf_report(report_type_enum, company, report_data, period_start, period_end, title)

    report_record = Report(
        company_id=current_user.company_id,
        generated_by=current_user.id,
        report_type=report_type_enum,
        title=title,
        period_start=period_start,
        period_end=period_end,
        parameters={"type": data.report_type},
        file_path=pdf_path,
    )
    db.add(report_record)
    db.commit()

    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.GENERATE_REPORT,
                      entity_type="report", entity_id=report_record.id,
                      description=f"Generated {title}")

    return {
        "report_id": str(report_record.id),
        "title": title,
        "download_url": f"/api/reports/{report_record.id}/download",
        "data": report_data,
    }


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reports = db.query(Report).filter(
        Report.company_id == current_user.company_id
    ).order_by(Report.created_at.desc()).limit(20).all()

    return [
        {
            "id": str(r.id), "title": r.title, "report_type": r.report_type.value,
            "period_start": r.period_start.isoformat() if r.period_start else None,
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "created_at": r.created_at.isoformat(),
            "download_url": f"/api/reports/{r.id}/download",
        }
        for r in reports
    ]
