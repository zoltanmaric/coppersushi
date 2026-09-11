FROM --platform=linux/x86_64 mambaorg/micromamba

# Add our code
ADD . /opt/webapp/
WORKDIR /opt/webapp

# Refuse to ship Git LFS pointers instead of networks (README: Git LFS)
RUN if grep -rlq '^version https://git-lfs' networks/; then \
      echo 'networks/ holds Git LFS pointers; run `git lfs pull` before building' >&2; exit 1; fi

# The CNEC page reads JAO domain days and the OSM locator from `data/`, which is docker-ignored,
# so a deployed image can only show its error banner. Until the image is given
# that data, or fetches it at runtime, refuse to build rather than ship a page that cannot work.
RUN if [ ! -d data/jao ] || [ ! -d data/osm-locator ]; then \
      echo '/cnec needs data/jao and data/osm-locator, which this image does not carry' >&2; exit 1; fi

# Reuse the project env file, but install it into the base env
RUN micromamba install -y -n base -f environment.yml
RUN micromamba clean --all --yes

CMD gunicorn --bind 0.0.0.0:$PORT app:server
