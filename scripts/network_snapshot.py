from scripts.node_info import *
import pandas as pd
import pypsa
from typing import Dict


class NetworkSnapshot:
    CARRIER_GROUPING = {
        'coal': 'fossil',
        'CCGT': 'fossil',
        'OCGT': 'fossil',
        'oil': 'fossil',
        'lignite': 'fossil',
        'nuclear': 'nuclear',
        'geothermal': 'geothermal',
        'biomass': 'biomass',
        'hydro': 'hydro',
        'PHS': 'hydro',
        'ror': 'hydro',
        'offwind-ac': 'wind',
        'offwind-dc': 'wind',
        'onwind': 'wind',
        'solar': 'solar',
    }

    def __init__(self, network: pypsa.Network, snapshot: pd.Timestamp):
        self.n = network
        self.snapshot = snapshot

        self.loads = self._loads()
        self.generators = self._generators()
        self.node_infos = self._to_node_info(self.loads, self.generators)
        # self.generators_by_carrier_group = self._generators_by_carrier_group()

    def _loads(self) -> pd.DataFrame:
        power_series = self.n.loads_t.p.loc[self.snapshot].rename('p_load')
        return pd.DataFrame(power_series).rename_axis('Bus', axis='index')

    def _flat_generators(self):
        p = self.n.generators_t.p.loc[self.snapshot].rename('p')
        p_max_pu = self.n.generators_t.p_max_pu.loc[self.snapshot].rename('p_max_pu')
        # Collect time-dependent quantities into a single dataframe
        # Example:
        #                          p  p_max_pu
        # Generator
        # 1004 onwind       0.000000  0.000000
        # 1004 solar       32.479277  0.702325
        # 1005 offwind-ac   0.032157  0.054890
        # 1005 onwind       2.965762  0.087245
        # 1005 solar       13.412731  0.708857
        generators_t = pd.concat([p, p_max_pu], axis='columns')

        # Combine static and time-dependent generator quantities,
        # rename the 'bus' column to 'Bus' to match the node index name,
        # name the columns-axis 'quantities' to distinguish it from the
        # additional 'carrier' columns-level to be added later
        #
        # Example:
        # quantities       p_nom_opt   Bus     carrier         p  p_max_pu
        # Generator
        # 1004 onwind      18.087540  1004      onwind  0.000000  0.000000
        # 1004 solar       46.245459  1004       solar  0.000000  0.000000
        # 1005 offwind-ac   0.586715  1005  offwind-ac  0.023185  0.039598
        # 1005 onwind      33.994279  1005      onwind  1.555266  0.045753
        # 1005 solar       18.921727  1005       solar  0.000000  0.000000
        generators = self.n.generators[['p_nom_opt', 'bus', 'carrier']].join(generators_t)
        generators['p_max'] = generators.p_max_pu * generators.p_nom_opt
        return generators.rename({'bus': 'Bus'}, axis='columns')\
            .rename_axis('quantities', axis='columns')

    def _generators(self) -> pd.DataFrame:
        """
        :return: A `pandas` DataFrame indexed by the bus ID **and** the generator carrier
        """
        flat_generators = self._flat_generators()

        # Replace the current indexing by generator name with a MultiIndex
        # by bus and carrier.
        # Then, unstack the multi-index to move the grouping by carrier into
        # a second columns-level.
        # Then, reorder the columns levels so that columns are grouped first
        # by carrier and then by quantites.
        #
        # Example:
        # TODO
        return flat_generators.set_index(['Bus', 'carrier'])

    def _generators_by_carrier_group(self) -> pd.DataFrame:
        """Groups individual carriers by NodesQuery.CARRIER_GROUPING"""
        raise Exception("I ain't implemented")

    @classmethod
    def _row_to_load_info(cls, row):
        return LoadInfo(row.p_load)

    @classmethod
    def _row_to_generators_info(cls, row):
        _bus, carrier = row.name
        return carrier, GeneratorInfo(row.p, row.p_max_pu, row.p_nom_opt, row.p_max)

    @classmethod
    def _group_to_generators_dict(cls, group):
        generator_infos_series = group.apply(cls._row_to_generators_info, axis='columns')
        return dict(generator_infos_series.to_list())

    @classmethod
    def _to_node_info(cls, loads: pd.DataFrame, generators: pd.DataFrame) -> 'pd.Series[NodeInfo]':
        """

        :param loads: The local loads DataFrame
        :param generators: The local generators DataFrame
        :return: A pandas series of NodeInfo objects
        """
        load_infos: pd.Series[LoadInfo] = loads.apply(cls._row_to_load_info, axis='columns').rename('load_info')
        generator_infos: pd.Series[Dict[str, GeneratorInfo]] =\
            generators.groupby(level='Bus').apply(cls._group_to_generators_dict).rename('generator_info')
        node_infos = pd.DataFrame([load_infos, generator_infos]).\
            apply(lambda row: NodeInfo(row.load_info, row.generator_info))
        return node_infos
