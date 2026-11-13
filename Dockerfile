FROM ghcr.io/prefix-dev/pixi:0.77.1-noble AS dependencies
WORKDIR /opt/webapp
COPY pyproject.toml pixi.lock ./

# The publisher receives only prepared catalog inputs, never solved networks or OPF figures.
FROM dependencies AS publisher-source
RUN pixi install --locked -e publisher --skip coppersushi
COPY . .
RUN pixi install --locked -e publisher

FROM publisher-source AS publisher-check
RUN .pixi/envs/publisher/bin/python -c "import sys; import awslambdaric; from coppersushi.pipelines.cnec.handler import handler; assert not {'flask','dash','plotly'} & sys.modules.keys()"

FROM publisher-source AS publisher-environment
RUN .pixi/envs/publisher/bin/python -c "from coppersushi.pipelines.data_sources.runtime_data import check_sources; from coppersushi.pipelines.grid.data_sources.zone_shapes import load; check_sources(); load()"
RUN rm -rf coppersushi/networks assets coppersushi/frontend .pixi/envs/default
RUN .pixi/envs/publisher/bin/python -m compileall -q coppersushi

FROM ubuntu:24.04 AS publisher
WORKDIR /opt/webapp
COPY --from=publisher-environment /opt/webapp /opt/webapp
ENV PATH="/opt/webapp/.pixi/envs/publisher/bin:${PATH}" \
    COPPERSUSHI_DATA_DIR=/tmp/coppersushi/data \
    MPLCONFIGDIR=/tmp/matplotlib
ENTRYPOINT ["/opt/webapp/.pixi/envs/publisher/bin/python", "-m", "awslambdaric"]
CMD ["coppersushi.pipelines.cnec.handler.handler"]
USER 1000
