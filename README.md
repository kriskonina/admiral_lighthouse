Admiral Lighthouse
=========

Admiral Lighthouse is (aimed to be) an extremely lightweight alternative to other container monitoring tools.

How it works
-------
Essentialy, by parsing the output of  ```docker stats``` (Docker Engine >=13.0.0). It thus fully relies on the accuracy of docker-provided metrics about its own (running) containers. It can be thought of as an extension to Docker Remote API which, as of time of writing, lacks support for some of the nifty novelities introduced with Docker Engine version 13.0.0. 

Each time ```docker stats``` outputs new data (every second), the stats of all running containers get summed up and put put on the queue. Future version (if any), will provide some additional aggregation tools, i.e. average the results over arbitrary timeframes.

It sports a simple web server listening on port 1988 to handle data extraction.

How to run it
-------

```bash
# build the image
docker build --rm -t admiral_lighthouse:latest .
# run it
docker run -d \
   -v $(which docker):/bin/docker \
   -v /var/run/docker.sock:/var/run/docker.sock \
   -p 1988:1988 \
   --rm \
   superfunnel/admiral_lighthouse
# query it
curl http://0.0.0.0:1988
```
will query the server for the queued usage record, returning a JSON response, specifically a list of the following:
* summed cpu usage from all containers [%]
* memory usage [KB]
* incoming network traffic [KB]
* outcoming network traffic [KB]
* block writes [KB]
* block reads [KB]
* a total number of processes

