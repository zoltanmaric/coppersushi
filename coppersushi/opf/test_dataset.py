"""Exercise publication validation and parity with a solved network."""
import json
from pathlib import Path

import pypsa
import pytest
from pydantic import ValidationError
from coppersushi.opf.dataset import Dataset
from coppersushi.opf.export import extract
from coppersushi.opf import power_flow


@pytest.fixture(scope='module')
def dataset() -> tuple[pypsa.Network, Dataset]:
    network = pypsa.Network(Path(__file__).parents[2] / 'tests/fixtures/networks/v1-sample.nc')
    return network, extract(network)


def test_export_preserves_all_snapshot_values(dataset: tuple[pypsa.Network, Dataset]) -> None:
    network, exported = dataset
    geometry = power_flow.get_branch_info(network)
    assert len(exported.intervals) == len(network.snapshots)
    for time, interval in zip(network.snapshots, exported.intervals, strict=True):
        expected = power_flow.get_branch_info_for_snapshot(network, geometry, time)
        assert [v.net_power_mw for v in interval.nodes] == list(network.buses_t.p.loc[time])
        for value in interval.branches:
            assert value.flow_mw == pytest.approx(expected.loc[(value.component, value.name), 'p0'])
    noon = exported.intervals[6]
    node = next(value for value in noon.nodes if value.node == '5624')
    assert node.load_mw == pytest.approx(204.94, abs=.01)
    coal = next(value for value in node.generators if value.technology == 'Coal')
    assert coal.power_mw == pytest.approx(127.35, abs=.01)
    assert coal.available_mw == pytest.approx(147.0)
    text = exported.model_dump_json()
    assert 'layout' not in json.loads(text)
    assert '<br>' not in text
    assert Dataset.model_validate_json(text) == exported


@pytest.mark.parametrize('damage', ['endpoint', 'duplicate', 'missing', 'time', 'nan'])
def test_rejects_corrupt_publications(dataset: tuple[pypsa.Network, Dataset], damage: str) -> None:
    _, exported = dataset
    raw = exported.model_dump(mode='json')
    if damage == 'endpoint':
        raw['branches'][0]['bus0'] = 'missing-node'
    elif damage == 'duplicate':
        raw['nodes'].append(raw['nodes'][0])
    elif damage == 'missing':
        raw['intervals'][0]['nodes'].pop()
    elif damage == 'time':
        raw['intervals'][1]['timestamp'] = raw['intervals'][0]['timestamp']
    else:
        raw['intervals'][0]['branches'][0]['flow_mw'] = float('nan')
    with pytest.raises(ValidationError):
        Dataset.model_validate(raw)
