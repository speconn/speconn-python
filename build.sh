#!/bin/sh
set -e
cd "$(dirname "$0")"
podman build -t speconn-python:build -f Containerfile.build .
echo "speconn-python: build OK"
