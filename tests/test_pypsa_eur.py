from pipeline.sources import pypsa_eur


def test_solved_network_is_named_by_its_day():
    assert pypsa_eur.network_filename("2013-07-17") == "opf-2013-07-17.nc"


def test_candidate_filename_carries_day_and_pin():
    assert pypsa_eur.candidate_filename("2013-07-17", "bccf56e8d5e8cf69") == "opf-2013-07-17-bccf56e8.nc"
