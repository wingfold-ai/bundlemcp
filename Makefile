# Aliases for deploy/stack.sh, which is the actual entrypoint (it needs only
# bash and Docker; `make` is optional).
#
#   make up        start everything, exposed through a tunnel (TUNNEL in deploy/.env)
#   make down      stop and remove the containers; Postgres data stays in its volume
#   make rebuild   drop the volumes, rebuild the images, start fresh
#   make logs      follow the logs
#   make ps        what is running
#   make url       the public URL the stack is currently published at
#   make secrets   generate any secret deploy/.env lacks, without starting

.PHONY: up down rebuild logs ps url secrets

up down rebuild logs ps url secrets:
	@./deploy/stack.sh $@
