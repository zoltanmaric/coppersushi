"""Parallel feed requests share pacing and publisher cooldowns."""
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from io import BytesIO
import time
import urllib.error

import pandas as pd
import pytest

from coppersushi import REPO
from coppersushi.data_sources import jao

START = pd.Timestamp('2026-01-01', tz='UTC')
END = pd.Timestamp('2026-01-02', tz='UTC')
PAYLOAD = REPO / 'tests/fixtures/synthetic-jao/active-fb-day.json'


@pytest.mark.parametrize('rate', [40, 90])
def test_parallel_endpoints_share_request_start_pacing(monkeypatch, rate):
    monkeypatch.setattr(jao, '_pacer', jao.RequestPacer(requests_per_minute=rate))
    starts = []
    def open_request(*args, **kwargs):
        starts.append(time.monotonic())
        return BytesIO(PAYLOAD.read_bytes())
    monkeypatch.setattr(jao.urllib.request, 'urlopen', open_request)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda endpoint: jao._get(endpoint, START, END),
                      ['activeFbConstraints', 'finalComputation', 'netPos']))
    assert all(b-a >= 60/rate - 0.01 for a,b in zip(starts, starts[1:]))


@pytest.mark.parametrize('header,seconds', [(None,60), ('invalid',60), ('nan',60), ('-1',60), ('12',12)])
def test_429_blocks_other_feeds_then_allows_recovery(monkeypatch, header, seconds):
    now = [100.]
    monkeypatch.setattr(jao.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(jao, '_pacer', jao.RequestPacer())
    headers = Message()
    if header is not None:
        headers['Retry-After'] = header
    calls = []
    def open_request(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise urllib.error.HTTPError('https://example.invalid',429,'limited',headers,None)
        return BytesIO(PAYLOAD.read_bytes())
    monkeypatch.setattr(jao.urllib.request, 'urlopen', open_request)
    with pytest.raises(urllib.error.HTTPError):
        jao._get('finalComputation',START,END)
    with pytest.raises(RuntimeError,match=f'retry in {seconds} seconds'):
        jao._get('activeFbConstraints',START,END)
    assert len(calls) == 1
    now[0] += seconds
    assert jao._get('activeFbConstraints',START,END)
    assert len(calls) == 2


def test_http_date_cooldown_and_overlapping_429_do_not_shorten_wait(monkeypatch):
    from datetime import datetime, UTC
    from email.utils import format_datetime
    pacer = jao.RequestPacer()
    pacer.throttle(format_datetime(datetime(2099,1,1,tzinfo=UTC)))
    pacer.throttle('1')
    with pytest.raises(RuntimeError,match='JAO rate limit'):
        pacer.wait()


def test_backfill_retries_429_after_shared_cooldown(monkeypatch):
    now = [0.]
    monkeypatch.setattr(jao.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(jao.time, 'sleep', lambda delay: now.__setitem__(0, now[0] + delay))
    pacer = jao.RequestPacer(requests_per_minute=90, retry_attempts=3)
    monkeypatch.setattr(jao, '_pacer', pacer)
    starts = []
    headers = Message()
    headers['Retry-After'] = '12'
    def open_request(*args, **kwargs):
        starts.append(now[0])
        if len(starts) == 1:
            raise urllib.error.HTTPError('https://example.invalid',429,'limited',headers,None)
        return BytesIO(PAYLOAD.read_bytes())
    monkeypatch.setattr(jao.urllib.request, 'urlopen', open_request)
    assert jao._get('alphaFactor', START, END)
    assert starts == [0., 12.]
    assert jao._get('netPos', START, END)
    assert starts[2] - starts[1] == pytest.approx((60 / 90) * 1.25)


def test_backfill_retry_budget_is_finite(monkeypatch):
    now = [0.]
    monkeypatch.setattr(jao.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(jao.time, 'sleep', lambda delay: now.__setitem__(0, now[0] + delay))
    monkeypatch.setattr(jao, '_pacer', jao.RequestPacer(requests_per_minute=90, retry_attempts=3))
    headers = Message()
    headers['Retry-After'] = '1'
    starts = []
    def open_request(*args, **kwargs):
        starts.append(now[0])
        raise urllib.error.HTTPError('https://example.invalid',429,'limited',headers,None)
    monkeypatch.setattr(jao.urllib.request, 'urlopen', open_request)
    with pytest.raises(urllib.error.HTTPError):
        jao._get('alphaFactor', START, END)
    assert len(starts) == 4
    assert all(b - a >= 1 for a, b in zip(starts, starts[1:]))


def test_repeated_429s_do_not_reduce_backfill_below_conservative_rate(monkeypatch):
    now = [0.]
    monkeypatch.setattr(jao.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(jao.time, 'sleep', lambda delay: now.__setitem__(0, now[0] + delay))
    pacer = jao.RequestPacer(requests_per_minute=90, retry_attempts=3)
    for _ in range(40):
        pacer.throttle('1')
    now[0] = 100.
    pacer.wait()
    first = now[0]
    pacer.wait()
    assert now[0] - first == pytest.approx(1.5)
