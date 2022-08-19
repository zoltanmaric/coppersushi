FROM --platform=linux/x86_64 mambaorg/micromamba

# Add our code
ADD . /opt/webapp/
WORKDIR /opt/webapp

# Reuse the project env file, but install it into the base env
RUN micromamba install -y -n base -f environment.yml
RUN micromamba clean --all --yes

CMD gunicorn --bind 0.0.0.0:$PORT app:server
