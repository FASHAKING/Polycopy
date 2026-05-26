from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import repo
from polycopy.core.db import get_session
from polycopy.core.models import User
from polycopy.core.security import read_session_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    telegram_id = read_session_token(token)
    if telegram_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await repo.get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
