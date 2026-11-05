"""Export the Python HTTP boundary for frontend validation and type generation."""
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from coppersushi.data_model.cnec_api import DayResponse, LayerResponse, ApiError
from coppersushi.data_model.cnec_attribution import AttributionPayload

class CnecContracts(BaseModel):
    day: DayResponse
    layer: LayerResponse
    attribution: AttributionPayload
    error: ApiError

if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'frontend/src/contracts.json'
    content = json.dumps(CnecContracts.model_json_schema(), indent=2) + '\n'
    if '--check' in sys.argv:
        assert target.read_text() == content, 'Run pixi run frontend-contracts'
    else:
        target.write_text(content)
