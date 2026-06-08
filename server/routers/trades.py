from fastapi import APIRouter, Depends, Query
from server.auth import verify_token
from server.state_reader import read_history

router = APIRouter()


@router.get("/trades")
def get_trades(
    limit: int = Query(default=100, ge=1, le=500),
    user: str = Depends(verify_token),
) -> list:
    return read_history(limit=limit)
