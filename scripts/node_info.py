from typing import Dict


class LoadInfo:
    def __init__(self, p: float):
        self.p = p


class GeneratorInfo:
    def __init__(self, p: float, p_max_pu: float, p_nom_opt: float, p_max: float):
        self.p = p
        self.p_max_pu = p_max_pu
        self.p_nom_opt = p_nom_opt
        self.p_max = p_max


class NodeInfo:
    def __init__(self, load_info: LoadInfo, generator_info: Dict[str, GeneratorInfo]):
        """

        :param load_info: a LoadInfo object for this node
        :param generator_info: A dict of carrier or carrier group names to GeneratorInfo objects
        """
        self.load_info = load_info
        self.generator_info = generator_info
