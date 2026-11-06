FROM --platform=linux/amd64 node:22-bookworm-slim AS frontend-builder
WORKDIR /opt/webapp/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=linux/amd64 ghcr.io/prefix-dev/pixi:0.77.1-noble AS dependencies
WORKDIR /opt/webapp
COPY pyproject.toml pixi.lock ./

FROM dependencies AS runtime-dependencies
# Keep third-party installation and bytecode independent of application edits.
RUN pixi install --locked -e runtime --skip coppersushi
# Lambda cannot retain bytecode compiled into its read-only image on first use.
RUN .pixi/envs/runtime/bin/python -m compileall -q .pixi/envs/runtime/lib/python3.14

FROM runtime-dependencies AS environment
COPY . .
# Install the editable package only after its source is available.
RUN pixi install --locked -e runtime && \
    pixi shell-hook --locked -e runtime -s bash > /opt/entrypoint.sh && \
    printf '\nexec "$@"\n' >> /opt/entrypoint.sh
RUN /bin/bash /opt/entrypoint.sh python -m compileall -q app.py cnec_server.py coppersushi
COPY --from=frontend-builder /opt/webapp/assets/ /opt/webapp/assets/

# CI supplies fixtures separately so they never enter the serving image.
FROM environment AS runtime-check
RUN --mount=type=bind,from=fixtures,target=/fixtures \
    /bin/bash /opt/entrypoint.sh python infra/lambda/check-runtime.py /fixtures

FROM dependencies AS bundle-builder
RUN pixi install --locked -e build --skip coppersushi
COPY . .

# Refuse pointers and missing data before precomputing maps.
RUN if grep -rlq '^version https://git-lfs' networks/; then \
      echo 'networks/ holds Git LFS pointers; run git lfs pull before building' >&2; exit 1; fi
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
