"""Lambda Web Adapter entry point for scheduled publication, independent of Dash."""
import os

from flask import Flask, Response, request

from coppersushi.data_sources.publication import PublicationJob, attempt

server = Flask(__name__)


@server.get('/')
def health() -> str:
    return 'Copper Sushi publisher'


@server.post('/events')
def publish() -> Response:
    job = PublicationJob.model_validate(request.get_json())
    result = attempt(job, os.environ['COPPERSUSHI_CACHE_BUCKET'])
    return Response(result.model_dump_json(), mimetype='application/json')
