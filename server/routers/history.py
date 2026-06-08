from fastapi import APIRouter, Depends, Query
from server.auth import verify_token
from server.state_reader import read_equity_history

router = APIRouter()


@router.get("/equity-history")
def get_equity_history(
    points: int = Query(default=200, ge=1, le=500),
    user: str = Depends(verify_token),
) -> list:
    return read_equity_history(limit=points)
