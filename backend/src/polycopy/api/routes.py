from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from polycopy.api.deps import CurrentUser, SessionDep
from polycopy.api.schemas import (
    CopiedTradeOut,
    FollowOut,
    MeOut,
    PaperPortfolioOut,
    PaperPositionOut,
    PnlOut,
    SettingsIn,
    StatsOut,
    TelegramLoginIn,
    TokenOut,
    TraderOut,
)
from polycopy.core import portfolio as portfolio_svc
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
        paper_trading=user.paper_trading,
        paper_starting_balance=user.paper_starting_balance,
        paper_balance=user.paper_balance,
        linked=cred is not None,
        wallet_origin=cred.origin if cred else None,
        wallet_address=cred.proxy_address if cred else None,
    )


@router.patch("/me/settings", response_model=MeOut)
async def update_settings(
    payload: SettingsIn, user: CurrentUser, session: SessionDep
) -> MeOut:
    data = payload.model_dump(exclude_none=True)
    # Funding the paper account resets baseline, cash, and open positions.
    if "paper_balance" in data:
        amount = data.pop("paper_balance")
        if amount < 0:
            raise HTTPException(status_code=422, detail="paper_balance can't be negative")
        await repo.set_paper_balance(session, user, amount)
    if data.get("sizing_mode") not in (None, "multiplier", "proportional"):
        raise HTTPException(
            status_code=422, detail="sizing_mode must be 'multiplier' or 'proportional'"
        )
    for attr, value in data.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
            raise HTTPException(status_code=422, detail=f"{attr} can't be negative")
        setattr(user, attr, value)
    await session.commit()
    return await get_me(user, session)


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


@router.get("/me/pnl", response_model=PnlOut)
async def my_pnl(user: CurrentUser, session: SessionDep) -> PnlOut:
    status_counts = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(CopiedTrade.status, func.count())
                .where(CopiedTrade.user_id == user.id)
                .group_by(CopiedTrade.status)
            )
        ).all()
    }

    real = await portfolio_svc.real_portfolio(session, user)

    return PnlOut(
        wallet_address=real.wallet_address,
        portfolio_value=real.portfolio_value,
        unrealized_pnl=real.unrealized_pnl,
        realized_pnl=real.realized_pnl,
        win_rate=real.win_rate,
        settled_markets=real.settled_markets,
        open_positions=real.open_positions,
        trades_filled=status_counts.get("filled", 0),
        trades_submitted=status_counts.get("submitted", 0) + status_counts.get("partial", 0),
        trades_skipped=status_counts.get("skipped", 0),
        trades_paper=status_counts.get("paper", 0),
    )


@router.get("/me/paper", response_model=PaperPortfolioOut)
async def my_paper(user: CurrentUser, session: SessionDep) -> PaperPortfolioOut:
    p = await portfolio_svc.paper_portfolio(session, user)
    return PaperPortfolioOut(
        enabled=p.enabled,
        starting_balance=p.starting_balance,
        cash=p.cash,
        market_value=p.market_value,
        portfolio_value=p.portfolio_value,
        unrealized_pnl=p.unrealized_pnl,
        realized_pnl=p.realized_pnl,
        total_pnl=p.total_pnl,
        open_positions=p.open_positions,
        win_rate=p.win_rate,
        settled_markets=p.settled_markets,
        positions=[
            PaperPositionOut(
                market_question=pos.market_question,
                market_slug=pos.market_slug,
                outcome=pos.outcome,
                shares=pos.shares,
                avg_price=pos.avg_price,
                cur_price=pos.cur_price,
                value=pos.value,
                unrealized_pnl=pos.unrealized_pnl,
            )
            for pos in p.positions
        ],
    )


@router.get("/me/trades", response_model=list[CopiedTradeOut])
async def my_trades(
    user: CurrentUser, session: SessionDep, limit: int = 50
) -> list[CopiedTradeOut]:
    trades = await repo.list_copied_trades(session, user, limit=min(limit, 200))
    return [CopiedTradeOut.model_validate(t, from_attributes=True) for t in trades]
