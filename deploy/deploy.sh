#!/usr/bin/env bash
# OneShot deploy driver — runs ON the deployment host (self-hosted runner or
# an operator shell); see docs/deployment.md.
#
#   RSM_IMAGE=ghcr.io/<owner>/oneshot-rsm \
#   WEB_IMAGE=ghcr.io/<owner>/oneshot-web \
#   IMAGE_TAG=sha-abc123   deploy/deploy.sh
#
#   RSM_IMAGE=... WEB_IMAGE=... deploy/deploy.sh --rollback
#
# Contract:
#   * Deploys the registry-pulled stack via deploy/compose.prod.yml (the base
#     docker-compose.yml holds build/local defaults; the override pins the
#     GHCR images and tag).
#   * Records the previously running tag in .deploy-prev-tag BEFORE changing
#     anything and rolls back to it automatically when smoke fails.
#   * Smoke = daemon /healthz on loopback :8787 AND UI / on loopback :3000,
#     polled for up to 60 s. A non-zero exit fails the workflow.
set -euo pipefail

: "${RSM_IMAGE:?RSM_IMAGE must be set (e.g. ghcr.io/<owner>/oneshot-rsm)}"
: "${WEB_IMAGE:?WEB_IMAGE must be set (e.g. ghcr.io/<owner>/oneshot-web)}"
# GHCR requires lowercase repository paths.
RSM_IMAGE="${RSM_IMAGE,,}"
WEB_IMAGE="${WEB_IMAGE,,}"

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.yml -f deploy/compose.prod.yml)
PREV_FILE=.deploy-prev-tag

current_tag() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q rsm 2>/dev/null | head -n 1)"
  [ -n "${cid}" ] || return 0
  docker inspect -f '{{.Config.Image}}' "${cid}" 2>/dev/null | awk -F: '{print $NF}' | head -n 1
}

smoke() {
  local i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 3 http://127.0.0.1:8787/healthz >/dev/null 2>&1 &&
       curl -fsS --max-time 3 http://127.0.0.1:3000/ >/dev/null 2>&1; then
      echo "smoke: OK after $((i * 2))s"
      return 0
    fi
    sleep 2
  done
  echo "smoke: FAILED after 60s (daemon :8787/healthz and/or UI :3000/)" >&2
  return 1
}

bring_up() { # $1 = image tag
  local tag="$1"
  echo "== bring up tag: ${tag}"
  IMAGE_TAG="${tag}" "${COMPOSE[@]}" pull
  IMAGE_TAG="${tag}" "${COMPOSE[@]}" up -d --remove-orphans
}

if [ "${1:-}" = "--rollback" ]; then
  prev="$(cat "${PREV_FILE}" 2>/dev/null || true)"
  [ -n "${prev}" ] || { echo "rollback: no ${PREV_FILE} recorded" >&2; exit 1; }
  bring_up "${prev}"
  smoke
  exit $?
fi

: "${IMAGE_TAG:?IMAGE_TAG must be set (a GHCR tag such as sha-<12>) or pass --rollback}"

previous="$(current_tag || true)"
echo "== previous tag: ${previous:-<none>}"
printf '%s\n' "${previous}" > "${PREV_FILE}"

if bring_up "${IMAGE_TAG}" && smoke; then
  echo "== deploy OK: ${IMAGE_TAG}"
  exit 0
fi

echo "== deploy FAILED; rolling back to: ${previous:-<none>}" >&2
if [ -n "${previous}" ]; then
  if bring_up "${previous}" && smoke; then
    echo "rollback: previous revision (${previous}) is serving" >&2
  else
    echo "rollback: FAILED — manual intervention required" >&2
  fi
else
  "${COMPOSE[@]}" down || true
  echo "rollback: no previous revision — failed stack stopped" >&2
fi
exit 1