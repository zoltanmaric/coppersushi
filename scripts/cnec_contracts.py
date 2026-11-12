"""Export the prepared-publication boundary for frontend validation and type generation."""
import json
import sys
from pathlib import Path
from pydantic import BaseModel

from coppersushi.pipelines.powerflow.dataset import Dataset
from coppersushi.pipelines.cnec.models import DayBundle
from coppersushi.pipelines.cnec.models import DayManifest
from coppersushi.pipelines.cnec.models import DayMetadata
from coppersushi.pipelines.cnec.models import MarketInterval

class CnecContracts(BaseModel):
    bundle: DayBundle
    metadata: DayMetadata
    interval: MarketInterval
    manifest: DayManifest

if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'coppersushi/frontend/data/contracts.json'
    content = json.dumps(CnecContracts.model_json_schema(), indent=2) + '\n'
    if '--check' in sys.argv:
        assert target.read_text() == content, 'Run pixi run frontend-contracts'
    else:
        target.write_text(content)

    opf_target = target.parents[1] / 'pages/powerflow/contracts.json'
    opf_content = json.dumps(Dataset.model_json_schema(), indent=2) + '\n'
    if '--check' in sys.argv:
        assert opf_target.read_text() == opf_content, 'Run pixi run frontend-contracts'
    else:
        opf_target.write_text(opf_content)
