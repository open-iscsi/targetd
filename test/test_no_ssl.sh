#!/bin/bash


# Getting an env variable to work with circle ci is problematic...

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export TARGETD_UT_PROTO=http

"$SCRIPT_DIR"/test.sh "$@" || exit 1
exit 0