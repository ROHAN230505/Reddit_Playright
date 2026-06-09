from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Proxy, RedditAccount
from app.db.session import get_db
from app.schemas import (
    ProxyCreate,
    ProxyItem,
    ProxyUpdate,
    ProxyValidationResult,
)
from app.services import crypto
from app.services.proxy_check import validate_proxy

router = APIRouter(prefix="/proxies", tags=["proxies"])


def _serialize(db: Session, proxy: Proxy) -> ProxyItem:
    account_count = db.scalar(
        select(func.count(RedditAccount.id)).where(RedditAccount.proxy_id == proxy.id)
    ) or 0
    return ProxyItem(
        id=proxy.id,
        label=proxy.label,
        scheme=proxy.scheme,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        has_password=bool(proxy.password_enc),
        status=proxy.status,
        notes=proxy.notes,
        account_count=int(account_count),
        last_checked_at=proxy.last_checked_at,
        last_check_error=proxy.last_check_error,
        last_check_ip=proxy.last_check_ip,
        created_at=proxy.created_at,
    )


def _decrypt_password(proxy: Proxy) -> str | None:
    if not proxy.password_enc:
        return None
    return crypto.decrypt(proxy.password_enc)


@router.get("", response_model=list[ProxyItem])
def list_proxies(db: Session = Depends(get_db)):
    proxies = db.scalars(select(Proxy).order_by(Proxy.created_at.desc())).all()
    return [_serialize(db, p) for p in proxies]


@router.post("", response_model=ProxyItem)
def create_proxy(payload: ProxyCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Proxy).where(Proxy.label == payload.label))
    if existing:
        raise HTTPException(status_code=409, detail="A proxy with that label already exists.")

    password_enc = crypto.encrypt(payload.password) if payload.password else None

    status = "ACTIVE"
    last_check_error: str | None = None
    last_check_ip: str | None = None
    last_checked_at: datetime | None = None

    if not payload.skip_validation:
        ok, ip, error = validate_proxy(
            scheme=payload.scheme,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password,
        )
        last_checked_at = datetime.utcnow()
        if ok:
            last_check_ip = ip
            status = "ACTIVE"
        else:
            last_check_error = error
            status = "FAILED"

    proxy = Proxy(
        label=payload.label,
        scheme=payload.scheme,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password_enc=password_enc,
        status=status,
        notes=payload.notes,
        last_checked_at=last_checked_at,
        last_check_error=last_check_error,
        last_check_ip=last_check_ip,
    )
    db.add(proxy)
    db.commit()
    db.refresh(proxy)

    if status == "FAILED" and not payload.skip_validation:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Proxy validation failed",
                "error": last_check_error,
                "proxy_id": proxy.id,
            },
        )
    return _serialize(db, proxy)


@router.post("/{proxy_id}/validate", response_model=ProxyValidationResult)
def revalidate_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    password = _decrypt_password(proxy)
    ok, ip, error = validate_proxy(
        scheme=proxy.scheme,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=password,
    )
    proxy.last_checked_at = datetime.utcnow()
    proxy.last_check_ip = ip
    proxy.last_check_error = error
    proxy.status = "ACTIVE" if ok else "FAILED"
    db.add(proxy)
    db.commit()
    return ProxyValidationResult(ok=ok, ip=ip, error=error)


@router.patch("/{proxy_id}", response_model=ProxyItem)
def update_proxy(proxy_id: int, payload: ProxyUpdate, db: Session = Depends(get_db)):
    proxy = db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")

    if payload.label is not None and payload.label != proxy.label:
        clash = db.scalar(select(Proxy).where(Proxy.label == payload.label, Proxy.id != proxy.id))
        if clash:
            raise HTTPException(status_code=409, detail="Another proxy already uses that label.")
        proxy.label = payload.label
    if payload.scheme is not None:
        proxy.scheme = payload.scheme
    if payload.host is not None:
        proxy.host = payload.host
    if payload.port is not None:
        proxy.port = payload.port
    if payload.username is not None:
        proxy.username = payload.username or None
    if payload.password is not None:
        proxy.password_enc = crypto.encrypt(payload.password) if payload.password else None
    if payload.status is not None:
        proxy.status = payload.status
    if payload.notes is not None:
        proxy.notes = payload.notes

    db.add(proxy)
    db.commit()
    db.refresh(proxy)

    if payload.revalidate:
        password = _decrypt_password(proxy)
        ok, ip, error = validate_proxy(
            scheme=proxy.scheme,
            host=proxy.host,
            port=proxy.port,
            username=proxy.username,
            password=password,
        )
        proxy.last_checked_at = datetime.utcnow()
        proxy.last_check_ip = ip
        proxy.last_check_error = error
        proxy.status = "ACTIVE" if ok else "FAILED"
        db.add(proxy)
        db.commit()
        db.refresh(proxy)

    return _serialize(db, proxy)


@router.delete("/{proxy_id}")
def delete_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    in_use = db.scalar(
        select(func.count(RedditAccount.id)).where(RedditAccount.proxy_id == proxy.id)
    ) or 0
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete proxy — {in_use} account(s) still reference it.",
        )
    db.delete(proxy)
    db.commit()
    return {"ok": True}
