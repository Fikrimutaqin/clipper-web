from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import time
from pydantic import BaseModel

from _database.db import get_db, Job, User, Withdrawal
from routes.auth import get_current_user
from core import response_success

router = APIRouter()

def _get_ready_to_withdraw(db: Session, user_id: str) -> float:
    total_released = (
        db.query(Job)
        .filter(Job.clipper_id == user_id, Job.payment_status == "RELEASED")
        .all()
    )
    total_released_amount = sum((j.budget or 0) for j in total_released)
    total_withdrawn_amount = (
        db.query(Withdrawal)
        .filter(Withdrawal.user_id == user_id, Withdrawal.status == "COMPLETED")
        .all()
    )
    withdrawn = sum((w.amount or 0) for w in total_withdrawn_amount)
    ready = total_released_amount - withdrawn
    return ready if ready > 0 else 0.0


@router.get("")
@router.get("/")
async def earnings_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang bisa mengakses earnings")

    jobs = db.query(Job).filter(Job.clipper_id == current_user.id).all()

    total_released = sum((j.budget or 0) for j in jobs if (j.payment_status or "PENDING") == "RELEASED")
    pending_escrow = sum((j.budget or 0) for j in jobs if (j.payment_status or "PENDING") == "ESCROW_HOLD")
    completed_jobs = sum(1 for j in jobs if (j.status or "") == "COMPLETED")
    ready_to_withdraw = _get_ready_to_withdraw(db, current_user.id)

    return response_success(
        message="Ringkasan earnings berhasil diambil",
        data={
            "total_released": total_released,
            "pending_escrow": pending_escrow,
            "ready_to_withdraw": ready_to_withdraw,
            "completed_jobs": completed_jobs,
        },
    )


@router.get("/history")
async def earnings_history(
    payment_status: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang bisa mengakses earnings")

    query = db.query(Job).filter(Job.clipper_id == current_user.id)
    if payment_status:
        query = query.filter(Job.payment_status == payment_status)

    jobs = query.order_by(Job.updated_at.desc()).limit(limit).all()

    items = []
    for j in jobs:
        items.append(
            {
                "job_id": j.id,
                "title": j.title,
                "amount": j.budget or 0,
                "status": j.status,
                "payment_status": j.payment_status or "PENDING",
                "created_at": j.created_at,
                "updated_at": j.updated_at,
            }
        )

    return response_success(message="Riwayat earnings berhasil diambil", data=items, meta={"limit": limit})


class WithdrawRequest(BaseModel):
    amount: float


@router.post("/withdraw")
async def withdraw(
    req: WithdrawRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang bisa withdraw")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Jumlah withdraw harus lebih dari 0")

    ready = _get_ready_to_withdraw(db, current_user.id)
    if req.amount > ready:
        raise HTTPException(status_code=400, detail="Saldo tidak cukup untuk withdraw")

    now = int(time.time())
    w = Withdrawal(user_id=current_user.id, amount=req.amount, status="COMPLETED", created_at=now)
    db.add(w)
    db.commit()
    db.refresh(w)

    return response_success(
        message="Withdraw berhasil (simulasi)",
        data={"withdrawal_id": w.id, "amount": w.amount, "status": w.status, "created_at": w.created_at},
        meta={"ready_to_withdraw": _get_ready_to_withdraw(db, current_user.id)},
    )


@router.get("/withdraw/history")
async def withdraw_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang bisa mengakses withdraw history")

    items = (
        db.query(Withdrawal)
        .filter(Withdrawal.user_id == current_user.id)
        .order_by(Withdrawal.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for w in items:
        result.append({"id": w.id, "amount": w.amount, "status": w.status, "created_at": w.created_at})
    return response_success(message="Riwayat withdraw berhasil diambil", data=result, meta={"limit": limit})
