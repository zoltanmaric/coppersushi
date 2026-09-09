"""Pins our data_model schemas against PyPSA's own attribute declarations."""

import pypsa

from coppersushi.data_model.network_views import PYPSA_SOURCED


def test_pypsa_sourced_columns_match_pypsas_own_dtypes():
    """PyPSA owns these attributes; our models must not drift from its declarations.

    Both sides are introspected — our model's own declared dtype, PyPSA's own declared
    dtype — so either drifting independently (e.g. `Buses.v_nom` becoming `Series[int]`)
    fails this test.
    """
    n = pypsa.Network()
    for model, model_column, component, pypsa_column in PYPSA_SOURCED:
        model_dtype = str(model.to_schema().columns[model_column].dtype)
        pypsa_dtype = n.components[component].defaults.at[pypsa_column, "dtype"]
        assert model_dtype == pypsa_dtype


def test_bus_country_and_line_v_nom_are_not_pypsa_declared():
    """PyPSA-Eur adds Bus.country; Line.v_nom is derived at runtime by
    `calculate_dependent_values`. Neither is declared by PyPSA itself — pin that so
    nobody later assumes either is guaranteed by PyPSA's own schema.
    """
    n = pypsa.Network()
    assert "country" not in n.components["Bus"].defaults.index
    assert "v_nom" not in n.components["Line"].defaults.index
