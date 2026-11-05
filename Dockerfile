FROM --platform=linux/amd64 node:22-bookworm-slim AS frontend-builder
WORKDIR /opt/webapp/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=linux/amd64 ghcr.io/prefix-dev/pixi:0.77.1-noble AS source
WORKDIR /opt/webapp
COPY . .

FROM source AS environment
COPY --from=frontend-builder /opt/webapp/assets/ /opt/webapp/assets/
RUN pixi install --locked -e runtime && \
    pixi shell-hook --locked -e runtime -s bash > /opt/entrypoint.sh && \
    printf '\nexec "$@"\n' >> /opt/entrypoint.sh
# Lambda cannot retain bytecode compiled into its read-only image on first use.
RUN /bin/bash /opt/entrypoint.sh python -m compileall -q \
    .pixi/envs/runtime/lib/python3.14 app.py cnec_http.py coppersushi

FROM source AS bundle-builder
RUN pixi install --locked -e build

# Refuse pointers and missing data before precomputing maps.
RUN if grep -rlq '^version https://git-lfs' networks/; then \
      echo 'networks/ holds Git LFS pointers; run git lfs pull before building' >&2; exit 1; fi
RUN if [ ! -f data/jao/element-ends.csv ] || [ ! -d data/osm-locator ]; then \
      echo 'Prepare the endpoint seed and OSM locator (infra/lambda/README.md)' >&2; exit 1; fi
RUN pixi run --locked -e build python -m coppersushi.data_sources.image_data
RUN chmod -R a+rX data

FROM --platform=linux/amd64 ubuntu:24.04 AS lambda
WORKDIR /opt/webapp
COPY --from=environment /opt/webapp /opt/webapp
COPY --from=environment /opt/entrypoint.sh /opt/entrypoint.sh
COPY --from=bundle-builder /opt/webapp/data /opt/webapp/data
ENTRYPOINT ["/bin/bash", "/opt/entrypoint.sh"]

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter
ENV COPPERSUSHI_DATA_DIR=/tmp/coppersushi/data \
    MPLCONFIGDIR=/tmp/matplotlib \
    AWS_LWA_PORT=8080 \
    AWS_LWA_ASYNC_INIT=true \
    AWS_LWA_ENABLE_COMPRESSION=true
USER 1000
CMD ["bash", "infra/lambda/start.sh"]
