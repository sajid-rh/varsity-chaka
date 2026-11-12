"""Block service: manage safety blocking between students."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Block, User


def block_user(db: Session, blocker: User, blocked_user_id: int) -> Block:
    if blocker.id == blocked_user_id:
        raise AppError("cannot_block_self", "You cannot block yourself", 400)

    target = db.get(User, blocked_user_id)
    if target is None or target.university_id != blocker.university_id or not target.is_active:
        raise AppError("user_not_found", "User not found", 404)

    # Check if already blocked
    existing = db.execute(
        select(Block).where(
            Block.university_id == blocker.university_id,
            Block.blocker_id == blocker.id,
            Block.blocked_id == blocked_user_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    block = Block(
        university_id=blocker.university_id,
        blocker_id=blocker.id,
        blocked_id=blocked_user_id,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def unblock_user(db: Session, blocker: User, blocked_user_id: int) -> None:
    block = db.execute(
        select(Block).where(
            Block.university_id == blocker.university_id,
            Block.blocker_id == blocker.id,
            Block.blocked_id == blocked_user_id,
        )
    ).scalar_one_or_none()

    if block is None:
        raise AppError("block_not_found", "Block record not found", 404)

    db.delete(block)
    db.commit()


def get_blocked_pair_user_ids(db: Session, user_id: int, university_id: int) -> set[int]:
    """Return all user IDs that have a block relation with this user (either direction)."""
    rows = db.execute(
        select(Block.blocker_id, Block.blocked_id).where(
            Block.university_id == university_id,
            or_(Block.blocker_id == user_id, Block.blocked_id == user_id),
        )
    ).all()

    blocked_ids = set()
    for b_id, target_id in rows:
        if b_id == user_id:
            blocked_ids.add(target_id)
        else:
            blocked_ids.add(b_id)
    return blocked_ids


def are_users_blocked(db: Session, user_a_id: int, user_b_id: int, university_id: int) -> bool:
    """Check if either user has blocked the other."""
    count = db.execute(
        select(Block.id).where(
            Block.university_id == university_id,
            or_(
                (Block.blocker_id == user_a_id) & (Block.blocked_id == user_b_id),
                (Block.blocker_id == user_b_id) & (Block.blocked_id == user_a_id),
            ),
        )
    ).first()
    return count is not None


def list_blocks(db: Session, blocker: User) -> list[Block]:
    return list(
        db.execute(
            select(Block)
            .where(
                Block.university_id == blocker.university_id,
                Block.blocker_id == blocker.id,
            )
            .order_by(Block.created_at.desc())
        ).scalars().all()
    )
