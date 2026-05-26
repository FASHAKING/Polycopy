from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from polycopy.api.deps import CurrentUser, SessionDep
from polycopy.api.schemas import (
    CopiedTradeOut,
    FollowOut,
    MeOut,
    StatsOut,
    TelegramLoginIn,
    TokenOut,
    TraderOut,
)
from polycopy.core import repo
from polycopy.core.config import get_settings
from polycopy.core.models import CopiedTrade, Follow, Trader, User
from polycopy.core.security import make_session_token, verify_telegram_login

router = APIRouter(prefix="/api")


@router.get("/stats", response_model=StatsOut)
async def get_stats(session: SessionDep) -> StatsOut:
    async def count(stmt) -> int:
        return (await session.execute(stmt)).scalar_one()

    by_status = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(CopiedTrade.status, func.count()).group_by(CopiedTrade.status)
            )
        ).all()
    }
    return StatsOut(
        users=await count(select(func.count()).select_from(User)),
        traders_tracked=await count(select(func.count()).select_from(Trader)),
        active_follows=await count(
            select(func.count()).select_from(Follow).where(Follow.active.is_(True))
        ),
        copied_trades=await count(select(func.count()).select_from(CopiedTrade)),
        submitted=by_status.get("submitted", 0),
        filled=by_status.get("filled", 0),
        skipped=by_status.get("skipped", 0),
    )


@router.get("/traders/top", response_model=list[TraderOut])
async def top_traders(session: SessionDep, limit: int = 20) -> list[TraderOut]:
    res = await session.execute(
        select(Trader)
        .where(Trader.win_rate.is_not(None))
        .order_by(Trader.win_rate.desc())
        .limit(min(limit, 100))
    )
    return [TraderOut.model_validate(t, from_attributes=True) for t in res.scalars().all()]


@router.post("/auth/telegram", response_model=TokenOut)
async def auth_telegram(payload: TelegramLoginIn, session: SessionDep) -> TokenOut:
    settings = get_settings()
    data = {k: str(v) for k, v in payload.model_dump(exclude_none=True).items()}
    if not verify_telegram_login(data, settings.telegram_bot_token):
        raise HTTPException(status_code=401, detail="Telegram authentication failed")

    await repo.get_or_create_user(session, telegram_id=payload.id, username=payload.username)
    await session.commit()
    return TokenOut(token=make_session_token(payload.id), telegram_id=payload.id)


@router.get("/me", response_model=MeOut)
async def get_me(user: CurrentUser, session: SessionDep) -> MeOut:
    cred = await repo.get_credential_meta(session, user)
    return MeOut(
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        email=user.email,
        auto_scout_enabled=user.auto_scout_enabled,
        linked=cred is not None,
        wallet_origin=cred.origin if cred else None,
        wallet_address=cred.proxy_address if cred else None,
    )


@router.get("/me/follows", response_model=list[FollowOut])
async def my_follows(user: CurrentUser, session: SessionDep) -> list[FollowOut]:
    follows = await repo.list_active_follows(session, user)
    return [
        FollowOut(
            wallet=trader.wallet,
            display_name=trader.display_name,
            source=follow.source,
            win_rate=trader.win_rate,
            created_at=follow.created_at,
        )
        for follow, trader in follows
    ]


@router.get("/me/trades", response_model=list[CopiedTradeOut])
async def my_trades(
    user: CurrentUser, session: SessionDep, limit: int = 50
) -> list[CopiedTradeOut]:
    trades = await repo.list_copied_trades(session, user, limit=min(limit, 200))
    return [CopiedTradeOut.model_validate(t, from_attributes=True) for t in trades]
