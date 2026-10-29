#!/usr/bin/env bash
# deploy/stack.sh replaces every published development secret in deploy/.env,
# rotates the token encryption key instead of dropping the published one, and leaves
# values it generated (or an operator chose) alone. Runs without Docker: only the
# `secrets` subcommand is exercised, against a copy of deploy/.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$root/deploy/stack.sh" "$root/deploy/docker-compose.yml" "$root/deploy/.env.example" "$work/"

fail() { echo "FAIL: $*" >&2; exit 1; }
value() { grep -E "^$1=" "$work/.env" | tail -1 | cut -d= -f2- | sed "s/^'\(.*\)'\$/\1/"; }
published() { sed -n "s/.*\${$1:-\(.*\)}.*/\1/p" "$work/docker-compose.yml" | head -1; }

published_key=$(published BUNDLEMCP_INITIAL_SERVICE_KEY)
published_keys=$(published BUNDLEMCP_TOKEN_ENCRYPTION_KEYS)
[ -n "$published_key" ] && [ -n "$published_keys" ] || fail "published defaults not found"

# a fresh checkout: .env is created and gets three generated values
bash "$work/stack.sh" secrets >/dev/null
key=$(value BUNDLEMCP_INITIAL_SERVICE_KEY)
keys=$(value BUNDLEMCP_TOKEN_ENCRYPTION_KEYS)
password=$(value KEYCLOAK_ADMIN_PASSWORD)
[[ "$key" =~ ^bmcp_sk_[A-Za-z0-9_-]{43}$ ]] || fail "service key has the wrong shape: $key"
[ "$key" != "$published_key" ] || fail "service key is the published one"
[[ "$keys" =~ ^\[\"[A-Za-z0-9_-]{43}=\",\" ]] || fail "encryption keys lack a new first key: $keys"
[ "$keys" = "[\"${keys:2:44}\",${published_keys#[}" ] || fail "published key not kept second: $keys"
[ -n "$password" ] && [ "$password" != admin ] || fail "Keycloak password not generated"
[ "$(stat -c %a "$work/.env")" = 600 ] || fail ".env is not mode 600"

# a second run changes nothing
before=$(cat "$work/.env")
bash "$work/stack.sh" secrets >/dev/null
[ "$before" = "$(cat "$work/.env")" ] || fail "a second run rewrote .env"

# a published service key in an existing .env is replaced, other lines are kept
printf 'TUNNEL=none\nBUNDLEMCP_INITIAL_SERVICE_KEY=%s\n' "$published_key" >"$work/.env"
bash "$work/stack.sh" secrets >/dev/null
[ "$(value BUNDLEMCP_INITIAL_SERVICE_KEY)" != "$published_key" ] || fail "published key kept"
[ "$(value TUNNEL)" = none ] || fail "an unrelated line was lost"

# an operator's own values are left alone
printf "BUNDLEMCP_INITIAL_SERVICE_KEY='bmcp_sk_mine'\nKEYCLOAK_ADMIN_PASSWORD='mine'\n" >"$work/.env"
bash "$work/stack.sh" secrets >/dev/null
[ "$(value BUNDLEMCP_INITIAL_SERVICE_KEY)" = bmcp_sk_mine ] || fail "operator's key replaced"
[ "$(value KEYCLOAK_ADMIN_PASSWORD)" = mine ] || fail "operator's password replaced"

echo "deploy/stack.sh secrets: ok"
