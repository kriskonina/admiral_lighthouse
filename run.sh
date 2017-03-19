#!/bin/bash

docker build --rm -t admiral_lighthouse:latest .
docker run \
   -v /Applications/Docker.app/Contents/Resources/bin/docker:/bin/docker \
   -v /var/run/docker.sock:/var/run/docker.sock \
   -p 1988:1988 \
   --rm \
   admiral_lighthouse
