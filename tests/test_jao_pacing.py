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


def test_parallel_endpoints_share_request_start_pacing(monkeypatch):
    monkeypatch.setattr(jao, '_pacer', jao.RequestPacer())
    starts = []
    def open_request(*args, **kwargs):
        starts.append(time.monotonic())
        return BytesIO(PAYLOAD.read_bytes())
    monkeypatch.setattr(jao.urllib.request, 'urlopen', open_request)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda endpoint: jao._get(endpoint, START, END),
                      ['activeFbConstraints', 'finalComputation', 'netPos']))
    assert all(b-a >= 1.49 for a,b in zip(starts, starts[1:]))


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
