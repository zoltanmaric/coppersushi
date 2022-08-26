import cProfile
import pypsa
import scripts.plot_power_flow as ppf

n = pypsa.Network('networks/elec_s_all_ec_lv1.01_2H.nc')

with cProfile.Profile() as pr:
    ppf.colored_network_figure(n, 'net_power')

pr.dump_stats('profiling/plot.prof')
