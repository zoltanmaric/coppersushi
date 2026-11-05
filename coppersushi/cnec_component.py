"""Dash mount point for the React-owned CNEC view."""

from dash.development.base_component import Component


class CnecView(Component):
    """Progressive CNEC map; React owns controls, requests and loading state."""

    _namespace = "coppersushi_cnec"
    _type = "CnecView"
    _children_props: list[str] = []

    def __init__(self, *, id: str, day: str, token: str, basemap: dict):
        self._prop_names = ["id", "day", "token", "basemap"]
        self._valid_wildcard_attributes = []
        self.available_properties = self._prop_names
        self.available_wildcard_properties = []
        super().__init__(id=id, day=day, token=token, basemap=basemap)
