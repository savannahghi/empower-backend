#!/bin/bash

if [ "$DEPLOY_TYPE" == "CELERY_BEAT" ]; then
    celery -A sil_advantage.config beat -l info
elif [ "$DEPLOY_TYPE" == "CELERY_WORKER" ]; then
    celery -A sil_advantage.config worker -l info
else
    advantage_manage migrate --noinput \
    && exec gunicorn --bind :$PORT --worker-tmp-dir /dev/shm --workers "${GUNICORN_WORKERS:-3}" \
            sil_advantage.config.wsgi  --access-logfile - --error-logfile - --log-level info
fi
