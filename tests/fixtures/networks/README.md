`v1-sample.nc` is a 13-bus subnetwork of v1's solved network `networks/elec_s_all_ec_lv1.01_2H.nc`, cut so the
tests keep asserting on the same entities with unchanged values (line `11274`, link `T22`, buses `5624`, `1004`,
`1005`, plus the first six buses so a negative-load node stays early in trace order). Recipe:

```python
import pypsa
n = pypsa.Network("networks/elec_s_all_ec_lv1.01_2H.nc")
line, link = n.lines.loc["11274"], n.links.loc["T22"]
keep = {"5624", "1004", "1005", line.bus0, line.bus1, link.bus0, link.bus1} | set(n.buses.index[:6])
sub = n[n.buses.index.isin(keep)]
sub.name = "v1 sample"
sub.export_to_netcdf("tests/fixtures/networks/v1-sample.nc")
```
