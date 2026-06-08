from fastapi import APIRouter, Depends
from server.auth import verify_token
from server.state_reader import read_state

router = APIRouter()


@router.get("/status")
def get_status(user: str = Depends(verify_token)) -> dict:
    return read_state()
