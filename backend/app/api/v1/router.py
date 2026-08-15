from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, dashboard, customers, vendors, products,
    invoices, expenses, approvals, assistant,
    analytics, audit_logs, settings, uploads, reports, tally, management,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(customers.router)
api_router.include_router(vendors.router)
api_router.include_router(products.router)
api_router.include_router(invoices.router)
api_router.include_router(expenses.router)
api_router.include_router(approvals.router)
api_router.include_router(assistant.router)
api_router.include_router(analytics.router)
api_router.include_router(audit_logs.router)
api_router.include_router(settings.router)
api_router.include_router(uploads.router)
api_router.include_router(reports.router)
api_router.include_router(tally.router)
api_router.include_router(management.router)
