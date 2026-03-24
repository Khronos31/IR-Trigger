ARG BUILD_FROM=ghcr.io/hassio-addons/base:14.3.2
FROM $BUILD_FROM

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    libusb

# Install pyusb & requests
RUN pip3 install --no-cache-dir pyusb requests

# Copy python script and run script
COPY run.sh /app/run.sh
COPY ir_daemon.py /app/ir_daemon.py

WORKDIR /app
RUN chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
