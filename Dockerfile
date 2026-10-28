FROM --platform=linux/amd64 ghcr.io/prefix-dev/pixi:0.77.1-noble AS environment
WORKDIR /opt/webapp
COPY . .
RUN pixi install --locked -e runtime && \
    pixi shell-hook --locked -e runtime -s bash > /opt/entrypoint.sh && \
    printf '\nexec "$@"\n' >> /opt/entrypoint.sh

FROM --platform=linux/amd64 ubuntu:24.04 AS lambda
WORKDIR /opt/webapp
COPY --from=environment /opt/webapp /opt/webapp
COPY --from=environment /opt/entrypoint.sh /opt/entrypoint.sh
ENTRYPOINT ["/bin/bash", "/opt/entrypoint.sh"]

# Refuse pointers and missing data before precomputing maps.
RUN if grep -rlq '^version https://git-lfs' networks/; then \
      echo 'networks/ holds Git LFS pointers; run git lfs pull before building' >&2; exit 1; fi
RUN if [ ! -f data/jao/element-ends.csv ] || [ ! -d data/osm-locator ]; then \
      echo 'Prepare the endpoint seed and OSM locator (infra/lambda/README.md)' >&2; exit 1; fi
RUN /bin/bash /opt/entrypoint.sh python -m coppersushi.data_sources.image_data
RUN chmod -R a+rX data

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter
ENV COPPERSUSHI_DATA_DIR=/tmp/coppersushi/data \
    MPLCONFIGDIR=/tmp/matplotlib \
    AWS_LWA_PORT=8080 \
    AWS_LWA_ASYNC_INIT=true \
    AWS_LWA_ENABLE_COMPRESSION=true
USER 1000
CMD ["bash", "infra/lambda/start.sh"]
