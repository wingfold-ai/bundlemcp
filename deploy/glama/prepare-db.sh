#!/bin/sh
# Creates the gateway's demo role and database in the cluster the Debian
# postgresql package sets up. Runs once, as root, while the image is built.
set -eu
pg_version=$(ls /usr/lib/postgresql)
pg_ctlcluster "$pg_version" main start
su postgres -c "psql -q -c \"CREATE ROLE bundlemcp LOGIN PASSWORD 'bundlemcp'\" -c 'CREATE DATABASE bundlemcp OWNER bundlemcp'"
pg_ctlcluster "$pg_version" main stop
