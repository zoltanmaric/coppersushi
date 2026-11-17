"""The publication boundary rejects missing evidence and calendar/count drift."""
from datetime import date, datetime, UTC
import pytest
from pydantic import ValidationError
from coppersushi.pipelines.cnec.investigation import BindingInterval, Coverage, Investigation
from coppersushi.pipelines.cnec.reserves import AvailableReserve


def interval(**changes):
    reserve=AvailableReserve(status='available',mw=1000,products=[100,200,300,400],published_at=datetime(2026,10,24,6,tzinfo=UTC))
    values=dict(utc=datetime(2026,10,25,1,15,tzinfo=UTC),date=date(2026,10,25),index=13,shadow=10,required=reserve,procured=reserve,cap=0,price=-5)
    return BindingInterval(**(values|changes))


def study(**changes):
    values=dict(start=date(2026,10,25),end=date(2026,10,25),rows=[interval()],generations={'2026-10-25':'a'*24},sources=[],overlap_verified=0,
                coverage=Coverage(expected=100,observed=100,unknown=0,binding=1,nonbinding=99,shortfall_binding=0,no_shortfall_binding=1))
    return Investigation(**(values|changes))


def test_autumn_day_has_100_distinct_quarters():
    assert study().coverage.expected==100
    with pytest.raises(ValidationError,match='identity'):
        interval(index=9)  # Same local 02:15 label, but the other UTC occurrence.


def test_publication_at_cutoff_is_not_eligible():
    reserve=AvailableReserve(status='available',mw=1000,products=[100,200,300,400],published_at=datetime(2026,10,24,8,30,tzinfo=UTC))
    with pytest.raises(ValidationError,match='pre-submission'):
        interval(required=reserve)


@pytest.mark.parametrize('change',[{'unknown':1},{'observed':99},{'expected':96},{'shortfall_binding':1}])
def test_missing_population_or_inconsistent_counts_cannot_publish(change):
    c=study().coverage.model_dump()|change
    with pytest.raises(ValidationError):study(coverage=Coverage(**c))


def test_duplicate_binding_rows_and_missing_map_days_cannot_publish():
    with pytest.raises(ValidationError):study(rows=[interval(),interval()])
    with pytest.raises(ValidationError):study(generations={})


def test_invalid_reserve_sum_is_rejected():
    reserve=AvailableReserve(status='available',mw=999,products=[100,200,300,400],published_at=datetime(2026,10,24,6,tzinfo=UTC))
    with pytest.raises(ValidationError):interval(procured=reserve)
