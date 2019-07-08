FROM alpine:edge

RUN apk update && \
    apk add \
        python3 \
        python3-dev \
        py3-gobject3 \
        libblockdev-dev \
        py3-libblockdev \
        py3-rtslib \
        build-base \
        udev \
        lvm2

RUN sed -i 's/udev_rules = 1/udev_rules = 0/g' /etc/lvm/lvm.conf && \
    sed -i 's/udev_sync = 1/udev_sync = 0/g' /etc/lvm/lvm.conf

RUN pip3 install \
         setproctitle \
         pyyaml \
         six

ADD . /targetd

WORKDIR targetd
RUN python3 setup.py install
CMD ["/usr/bin/targetd"]
