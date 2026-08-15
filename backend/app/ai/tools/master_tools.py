"""
Master data read tools for LangGraph agents.
These tools access Tally master records (ledgers, stock items, groups, units, godowns)
via deterministic DB queries. The LLM never executes arbitrary SQL.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.models.tally_masters import TallyLedger, TallyStockGroup, TallyUnit, TallyGodown
from app.models.product import Product
from app.models.customer import Customer
from app.models.vendor import Vendor
from typing import Optional
import uuid


class MasterTools:
    def __init__(self, db: Session):
        self.db = db

    def get_ledgers(self, company_id: str, search: Optional[str] = None,
                    group: Optional[str] = None, limit: int = 20) -> dict:
        q = self.db.query(TallyLedger).filter(
            TallyLedger.company_id == uuid.UUID(company_id),
            TallyLedger.is_active == True,
        )
        if search:
            q = q.filter(TallyLedger.name.ilike(f"%{search}%"))
        if group:
            q = q.filter(TallyLedger.parent_group.ilike(f"%{group}%"))
        ledgers = q.order_by(TallyLedger.name).limit(limit).all()
        total = q.count()
        return {
            "ledgers": [
                {
                    "name": l.name,
                    "parent_group": l.parent_group,
                    "opening_balance": float(l.opening_balance or 0),
                    "closing_balance": float(l.closing_balance or 0),
                    "source": l.source,
                    "sync_status": l.tally_sync_status,
                }
                for l in ledgers
            ],
            "total": total,
            "shown": len(ledgers),
        }

    def get_stock_items(self, company_id: str, search: Optional[str] = None,
                        low_stock_only: bool = False, limit: int = 20) -> dict:
        q = self.db.query(Product).filter(
            Product.company_id == uuid.UUID(company_id),
            Product.is_active == True,
        )
        if search:
            q = q.filter(or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%")))
        if low_stock_only:
            q = q.filter(Product.stock_quantity <= Product.reorder_threshold)
        products = q.order_by(Product.name).limit(limit).all()
        total = self.db.query(func.count(Product.id)).filter(
            Product.company_id == uuid.UUID(company_id), Product.is_active == True
        ).scalar() or 0
        return {
            "stock_items": [
                {
                    "name": p.name,
                    "sku": p.sku,
                    "unit": p.unit,
                    "stock_quantity": float(p.stock_quantity or 0),
                    "selling_price": float(p.selling_price or 0),
                    "purchase_price": float(p.purchase_price or 0),
                    "low_stock": float(p.stock_quantity or 0) <= float(p.reorder_threshold or 0),
                    "reorder_threshold": float(p.reorder_threshold or 0),
                }
                for p in products
            ],
            "total": total,
            "shown": len(products),
        }

    def get_stock_groups(self, company_id: str, limit: int = 20) -> dict:
        groups = self.db.query(TallyStockGroup).filter(
            TallyStockGroup.company_id == uuid.UUID(company_id),
            TallyStockGroup.is_active == True,
        ).order_by(TallyStockGroup.name).limit(limit).all()
        return {
            "stock_groups": [
                {"name": g.name, "parent": g.parent, "sync_status": g.tally_sync_status}
                for g in groups
            ],
            "count": len(groups),
        }

    def get_units(self, company_id: str, limit: int = 20) -> dict:
        units = self.db.query(TallyUnit).filter(
            TallyUnit.company_id == uuid.UUID(company_id),
            TallyUnit.is_active == True,
        ).order_by(TallyUnit.name).limit(limit).all()
        return {
            "units": [
                {"name": u.name, "symbol": u.symbol, "decimal_places": u.decimal_places}
                for u in units
            ],
            "count": len(units),
        }

    def get_godowns(self, company_id: str, limit: int = 20) -> dict:
        godowns = self.db.query(TallyGodown).filter(
            TallyGodown.company_id == uuid.UUID(company_id),
            TallyGodown.is_active == True,
        ).order_by(TallyGodown.name).limit(limit).all()
        return {
            "godowns": [
                {"name": g.name, "parent": g.parent, "sync_status": g.tally_sync_status}
                for g in godowns
            ],
            "count": len(godowns),
        }

    def get_customers(self, company_id: str, search: Optional[str] = None,
                      limit: int = 20) -> dict:
        q = self.db.query(Customer).filter(
            Customer.company_id == uuid.UUID(company_id),
            Customer.is_active == True,
        )
        if search:
            q = q.filter(or_(Customer.name.ilike(f"%{search}%"), Customer.email.ilike(f"%{search}%")))
        customers = q.order_by(Customer.name).limit(limit).all()
        total = self.db.query(func.count(Customer.id)).filter(
            Customer.company_id == uuid.UUID(company_id), Customer.is_active == True
        ).scalar() or 0
        return {
            "customers": [
                {
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "city": c.city,
                    "state": c.state,
                    "gstin": c.gst_number,
                }
                for c in customers
            ],
            "total": total,
            "shown": len(customers),
        }

    def get_vendors(self, company_id: str, search: Optional[str] = None,
                    limit: int = 20) -> dict:
        q = self.db.query(Vendor).filter(
            Vendor.company_id == uuid.UUID(company_id),
            Vendor.is_active == True,
        )
        if search:
            q = q.filter(or_(Vendor.name.ilike(f"%{search}%"), Vendor.email.ilike(f"%{search}%")))
        vendors = q.order_by(Vendor.name).limit(limit).all()
        total = self.db.query(func.count(Vendor.id)).filter(
            Vendor.company_id == uuid.UUID(company_id), Vendor.is_active == True
        ).scalar() or 0
        return {
            "vendors": [
                {
                    "name": v.name,
                    "email": v.email,
                    "phone": v.phone,
                    "city": v.city,
                    "state": v.state,
                    "gstin": v.gst_number,
                }
                for v in vendors
            ],
            "total": total,
            "shown": len(vendors),
        }

    def get_tool_definitions(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_ledgers",
                    "description": "Search and list accounting ledgers (accounts)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search": {"type": "string", "description": "Name to search for"},
                            "group": {"type": "string", "description": "Filter by parent group (e.g., 'Sundry Debtors')"},
                            "limit": {"type": "integer", "description": "Max results, default 20"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stock_items",
                    "description": "List stock items / products with their inventory levels",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search": {"type": "string"},
                            "low_stock_only": {"type": "boolean", "description": "Only show items below reorder level"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customers",
                    "description": "List customers / sundry debtors",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vendors",
                    "description": "List vendors / suppliers / sundry creditors",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stock_groups",
                    "description": "List stock groups / product categories",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_units",
                    "description": "List units of measurement (Nos, Kg, Ltr, etc.)",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_godowns",
                    "description": "List godowns / warehouses / storage locations",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def call_tool(self, tool_name: str, args: dict, company_id: str) -> dict:
        args["company_id"] = company_id
        tool_map = {
            "get_ledgers": self.get_ledgers,
            "get_stock_items": self.get_stock_items,
            "get_customers": self.get_customers,
            "get_vendors": self.get_vendors,
            "get_stock_groups": self.get_stock_groups,
            "get_units": self.get_units,
            "get_godowns": self.get_godowns,
        }
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}
        import inspect
        fn = tool_map[tool_name]
        sig = inspect.signature(fn)
        filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
        return fn(**filtered_args)
