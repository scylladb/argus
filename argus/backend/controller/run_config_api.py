from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.service.run_config_params import SEARCH_LIMIT, RunConfigParamService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/run_configs")


@router.get("/param_names", name="api.run_config_api.param_names")
def param_names(query: str = Query(""), limit: int = Query(SEARCH_LIMIT, ge=1, le=SEARCH_LIMIT),
                user: User = Depends(api_current_user)):
    res = RunConfigParamService().search_names(query=query, limit=limit)
    return APIResponse({
        "status": "ok",
        "response": res
    })


@router.get("/param_values", name="api.run_config_api.param_values")
def param_values(name: str = Query(...), query: str = Query(""),
                 limit: int = Query(SEARCH_LIMIT, ge=1, le=SEARCH_LIMIT),
                 user: User = Depends(api_current_user)):
    res = RunConfigParamService().search_values(name=name, query=query, limit=limit)
    return APIResponse({
        "status": "ok",
        "response": res
    })
