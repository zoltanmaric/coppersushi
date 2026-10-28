FROM --platform=linux/amd64 ubuntu:24.04 AS environment
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
ADD https://github.com/prefix-dev/pixi/releases/download/v0.77.1/pixi-x86_64-unknown-linux-musl.tar.gz /tmp/pixi.tar.gz
RUN tar -xzf /tmp/pixi.tar.gz -C /usr/local/bin && rm /tmp/pixi.tar.gz
WORKDIR /opt/webapp
COPY . .
RUN pixi install --locked -e runtime
RUN pixi shell-hook -e runtime -s bash > /opt/activate.sh && \
    printf '#!/bin/bash\nsource /opt/activate.sh\nexec "$@"\n' > /opt/entrypoint.sh && \
    chmod +x /opt/entrypoint.sh

FROM --platform=linux/amd64 ubuntu:24.04 AS runtime
WORKDIR /opt/webapp
COPY --from=environment /opt/webapp /opt/webapp
COPY --from=environment /opt/activate.sh /opt/entrypoint.sh /opt/
ENTRYPOINT ["/opt/entrypoint.sh"]

# Refuse pointers and missing data before precomputing maps.
RUN if grep -rlq '^version https://git-lfs' networks/; then \
      echo 'networks/ holds Git LFS pointers; run git lfs pull before building' >&2; exit 1; fi
RUN if [ ! -f data/jao/element-ends.csv ] || [ ! -d data/osm-locator ]; then \
      echo 'Prepare the endpoint seed and OSM locator (README: Installation on Heroku)' >&2; exit 1; fi
RUN /opt/entrypoint.sh python -m coppersushi.data_sources.image_data

# Heroku supplies a runtime UID; only disposable data needs to be writable.
RUN chmod -R a+rX data && chmod a+rwx data data/jao
USER 1000
CMD ["bash", "-c", "exec gunicorn --timeout 90 --bind 0.0.0.0:$PORT app:server"]

FROM runtime AS lambda
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter
ENV COPPERSUSHI_DATA_DIR=/tmp/coppersushi/data \
    MPLCONFIGDIR=/tmp/matplotlib \
    AWS_LWA_PORT=8080 \
    AWS_LWA_ASYNC_INIT=true \
    AWS_LWA_ENABLE_COMPRESSION=true
CMD ["bash", "infra/lambda/start.sh"]

FROM runtime AS heroku
