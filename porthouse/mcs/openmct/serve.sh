#!/bin/bash
docker run \
    --interactive --tty \
    --rm \
    --name openmct_build \
    --mount type=bind,readonly,source="$(pwd)",target=/app \
    --workdir /app \
    --publish 8080:8080 \
    node:18.20-alpine3.19 \
    npm start
