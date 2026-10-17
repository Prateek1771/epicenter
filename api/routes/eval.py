"""GET /eval: the newest stored RCAEval result (phase 10). The suite runs from the CLI, never on a request."""

from fastapi import APIRouter

from api import eval as suite
from api.models import EvalSummary
from api.routes.deps import ApiError

router = APIRouter()


@router.get("/eval", response_model=EvalSummary)
def get_eval() -> EvalSummary:
    s = suite.latest()
    if s is None:
        raise ApiError(404, "EVAL_NOT_FOUND", "No eval result yet: run python -m api.eval --suite re2 --system tt")
    return EvalSummary(**s)
