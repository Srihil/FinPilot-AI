from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from typing import Optional
import math
import uuid

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    low_stock: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_active == True,
    )
    if search:
        query = query.filter(
            Product.name.ilike(f"%{search}%") | Product.sku.ilike(f"%{search}%")
        )
    if category:
        query = query.filter(Product.category == category)
    if low_stock is True:
        query = query.filter(Product.stock_quantity <= Product.reorder_threshold)

    total = query.count()
    items = query.order_by(Product.name).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [
            {
                "id": str(p.id), "company_id": str(p.company_id), "sku": p.sku,
                "name": p.name, "description": p.description, "category": p.category,
                "unit": p.unit, "purchase_price": float(p.purchase_price),
                "selling_price": float(p.selling_price), "tax_rate": float(p.tax_rate),
                "stock_quantity": float(p.stock_quantity),
                "reorder_threshold": float(p.reorder_threshold),
                "is_active": p.is_active, "track_inventory": p.track_inventory,
                "created_at": p.created_at.isoformat(),
                "inventory_value": float(p.stock_quantity) * float(p.purchase_price),
                "is_low_stock": float(p.stock_quantity) <= float(p.reorder_threshold),
            }
            for p in items
        ],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.post("")
def create_product(
    data: ProductCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    p = Product(company_id=current_user.company_id, **data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "name": p.name, "message": "Product created successfully"}


@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    from app.services.tally_write_service import queue_tally_write
    p = db.query(Product).filter(
        Product.id == uuid.UUID(product_id),
        Product.company_id == current_user.company_id,
        Product.is_active == True,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    p.is_active = False
    tally_queued = queue_tally_write(
        db, current_user.company_id, "DELETE_STOCK_ITEM", {"name": p.name}
    )
    db.commit()
    msg = "Product deleted from FinPilot and delete queued for TallyPrime." if tally_queued else "Product deleted from FinPilot."
    return {"deleted": True, "tally_queued": tally_queued, "message": msg}


@router.put("/{product_id}")
def update_product(
    product_id: str,
    data: ProductUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    p = db.query(Product).filter(Product.id == uuid.UUID(product_id), Product.company_id == current_user.company_id).first()
    if not p:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "name": p.name, "message": "Product updated successfully"}
