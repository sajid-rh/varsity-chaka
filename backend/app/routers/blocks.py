"""API endpoints for safety blocks between students."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.schemas.blocks import BlockCreate
from app.services import block_service
from app.tenancy.context import TenantContext, require_role

router = APIRouter(prefix="/api/v1/blocks", tags=["blocks"])
student_only = require_role("student")


@router.post("", status_code=201)
def block_user(
    payload: BlockCreate,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    block = block_service.block_user(db, ctx.user, payload.blocked_user_id)
    return ok({
        "id": block.id,
        "university_id": block.university_id,
        "blocker_id": block.blocker_id,
        "blocked_id": block.blocked_id,
        "created_at": block.created_at,
    })


@router.delete("/{blocked_user_id}")
def unblock_user(
    blocked_user_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    block_service.unblock_user(db, ctx.user, blocked_user_id)
    return ok({"unblocked": True})


@router.get("")
def list_blocks(
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    blocks = block_service.list_blocks(db, ctx.user)
    return ok({
        "count": len(blocks),
        "items": [
            {
                "id": b.id,
                "university_id": b.university_id,
                "blocker_id": b.blocker_id,
                "blocked_id": b.blocked_id,
                "created_at": b.created_at,
            }
            for b in blocks
        ],
    })
