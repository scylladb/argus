ARG PYTHON_VERSION=3.10.4-bullseye

FROM python:${PYTHON_VERSION}
ENV ROLLUP_ENV=production
ENV FLASK_ENV=production
ENV CQLENG_ALLOW_SCHEMA_MANAGEMENT=1
ENV ARGUS_USER=argus
# Create daemon user
RUN useradd -s /bin/bash -c "Argus User" -m ${ARGUS_USER}
ENV PATH="$PATH:/home/${ARGUS_USER}/.local/bin"
# Upgrade everything
RUN apt-get update -y \
    && apt-get upgrade -y
# Install npm and python build dependencies
RUN apt-get install -y build-essential apt-utils
# Install nginx
RUN apt-get install -y nginx-full && \
    chown ${ARGUS_USER}:${ARGUS_USER} -R /var/log/nginx /var/lib/nginx
# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm i -g yarn
# Install uv
USER ${ARGUS_USER}
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
# Copy project files
COPY --chown=${ARGUS_USER}:${ARGUS_USER} . /app
WORKDIR /app
# Build project
RUN uv sync --extra web-backend --extra docker-image \
    && yarn \
    && ROLLUP_ENV=${ROLLUP_ENV} yarn rollup -c \
    && mkdir /app/nginx
VOLUME [ "/app/storage", "/app/config" ]
EXPOSE 8000/tcp
ENTRYPOINT [ "./docker-entrypoint.sh" ]
