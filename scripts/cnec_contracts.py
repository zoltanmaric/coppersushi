"""Export the prepared-publication boundary for frontend validation and type generation."""
import json
import sys
from pathlib import Path
from pydantic import BaseModel

from coppersushi.publication.models import DayBundle, DayManifest, DayMetadata, MarketInterval

class CnecContracts(BaseModel):
    bundle: DayBundle
    metadata: DayMetadata
    interval: MarketInterval
    manifest: DayManifest

if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'frontend/src/data/contracts.json'
    content = json.dumps(CnecContracts.model_json_schema(), indent=2) + '\n'
    if '--check' in sys.argv:
        assert target.read_text() == content, 'Run pixi run frontend-contracts'
    else:
        target.write_text(content)
