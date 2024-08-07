#!/bin/bash
docker run \
    --interactive --tty \
    --rm \
    --name openmct_build \
    --mount type=bind,source="$(pwd)",target=/app \
    --workdir /app \
    --user $SUDO_UID:$SUDO_GID \
    node:18.20-alpine3.19 \
	npm install
