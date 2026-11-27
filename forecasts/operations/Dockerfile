FROM ghcr.io/prefix-dev/pixi:0.77.1-noble AS dependencies
WORKDIR /opt/forecast
COPY pyproject.toml pixi.lock ./
RUN pixi install --locked -e runtime --skip coppersushi

FROM dependencies AS installed
COPY forecasts forecasts
COPY coppersushi coppersushi
RUN pixi install --locked -e runtime

FROM ubuntu:24.04
WORKDIR /opt/forecast
COPY --from=installed /opt/forecast /opt/forecast
COPY REVISION REVISION
ENV PATH="/opt/forecast/.pixi/envs/runtime/bin:${PATH}" \
    METAFLOW_SKIP_INSTALL_DEPENDENCIES=1
RUN python -c "import boto3, catboost, metaflow, requests; import forecasts.monthly_fit, forecasts.daily"
WORKDIR /tmp/forecast-task
