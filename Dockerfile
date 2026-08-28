FROM europe-west1-docker.pkg.dev/speedy-lattice-334/sil-docker-proxy/python:3.11.5-bullseye

ARG CI_COMMIT_REF_NAME
ARG CI_COMMIT_SHORT_SHA
ARG SIL_PYPI_USER
ARG SIL_PYPI_PASSWORD
ARG REQUIREMENTS
ARG GOOGLE_APPLICATION_CREDENTIALS
ARG ENCRYPTION_PUBLIC_KEY_PATH

ENV PORT 8000
ENV GOOGLE_APPLICATION_CREDENTIALS=/opt/advantage/service_account.json
ENV ENCRYPTION_PUBLIC_KEY_PATH=/opt/advantage/encryption_pub_key.gpg
ENV TZ=Africa/Nairobi

RUN pip install --quiet --no-cache-dir pip==23.2.1

WORKDIR /opt/advantage/
COPY . /opt/advantage/

RUN apt-get -qq update && apt-get install -y ca-certificates curl gnupg tzdata gettext 1> /dev/null \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get install -y nodejs npm 1> /dev/null \
    && npm i --quiet \
    && sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt bullseye-pgdg main" > /etc/apt/sources.list.d/postgres.list' \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
    && apt update && apt -y install postgresql-client-16 && rm -rf /var/lib/apt/lists/*

RUN pip install --quiet \
        --extra-index-url https://$SIL_PYPI_USER:$SIL_PYPI_PASSWORD@pip.slade360.co.ke/simple \
        --no-cache-dir -r requirements/$REQUIREMENTS.txt \
    && advantage_manage collectstatic --noinput
# Define the entrypoint for the container
ENTRYPOINT [ "bash", "/opt/advantage/entrypoint.sh" ]
