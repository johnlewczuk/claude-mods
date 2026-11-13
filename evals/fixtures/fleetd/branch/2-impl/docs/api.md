# fleetd HTTP API

Errors always use the shared shape `{"error": "<message>"}` with a 4xx/5xx status.

## GET /devices?group=<name>

Response 200:

    {"devices": [{"id": str, "groups": [str], "firmware": str,
                  "target_firmware": str | null, "last_seen": str | null}]}

Consumers: the field-ops dashboard and the device provisioning tool both read this
endpoint.

## POST /rollouts

Body: `{"firmware": str, "groups": [str], "batch_percent": int}`.
Response 202: `{"id": int}`.

## GET /rollouts?status=<status>

Response 200: `{"rollouts": [...]}`.

## GET /rollouts/<id>

Response 200: the rollout, with `failure_rate`.

## POST /rollouts/<id>/results

Body: `{"device_id": str, "result": "success" | "failure"}`. Response 200: `{"recorded": bool}`.
