FROM --platform=linux/x86_64 mambaorg/micromamba

# Add our code
ADD . /opt/webapp/
WORKDIR /opt/webapp

# Refuse to ship Git LFS pointers instead of networks (README: Git LFS)
RUN if grep -rlq '^version https://git-lfs' networks/; then \
      echo 'networks/ holds Git LFS pointers; run `git lfs pull` before building' >&2; exit 1; fi

# Bundled data survives dyno cycling; later cache additions may be fetched again.
RUN if [ ! -f data/jao/element-ends.csv ] || [ ! -d data/osm-locator ]; then \
      echo 'Prepare the endpoint seed and OSM locator before building (README: Installation on Heroku)' >&2; exit 1; fi

# Reuse the project env file, but install it into the base env
RUN micromamba install -y -n base -f environment.yml
RUN micromamba clean --all --yes

# Heroku assigns a runtime UID instead of using the image's USER. Only the disposable
# data directories need to be writable; code and bundled locator files stay read-only.
USER root
RUN chmod -R a+rX data && chmod a+rwx data data/jao
USER $MAMBA_USER

RUN micromamba run -n base python -m coppersushi.data_sources.jao check-seed && \
    micromamba run -n base python -c "from coppersushi.data_sources.osm_locator import read_csvs; read_csvs()"

# Let a slow fetch finish caching even if Heroku's router has already timed out.
CMD gunicorn --timeout 90 --bind 0.0.0.0:$PORT app:server
