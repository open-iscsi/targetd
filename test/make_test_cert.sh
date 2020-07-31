#!/bin/bash

# Make a source of random for openssl
dd if=/dev/random of=~/.rnd bs=1024 count=1 || exit 1

# Generate the private key
openssl genrsa -out targetd_key.pem 2048 || exit 1

# Make the public cert. for testing
openssl req -new -x509 -key targetd_key.pem -out targetd_cert.pem -days 30 -subj "/C=US/ST=private/L=province/O=city/CN=localhost" -addext "subjectAltName = DNS:localhost"

# Copy them
cp targetd_key.pem targetd_cert.pem /etc/target/. || exit 1

# Test code expecting cert in same directory as test lib.
cp targetd_cert.pem test/. || exit 1
chmod 400 /etc/target/*.pem || exit 1

exit 0
