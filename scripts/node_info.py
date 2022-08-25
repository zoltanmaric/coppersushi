from typing import Dict
from dataclasses import dataclass
import jsons


@dataclass
class LoadInfo:
    p: float


@dataclass
class GeneratorInfo:
    p: float
    p_max_pu: float
    p_nom_opt: float
    p_max: float


@dataclass
class NodeInfo:
    lon: float
    lat: float
    p: float
    load_info: LoadInfo
    generator_info: Dict[str, GeneratorInfo]
