# fleetd HTTP API

Errors always use the shared shape `{"error": "<message>"}` with a 4xx/5xx status.

## GET /devices?group=<name>

Response 200:

    {"devices": [{"id": str, "group": str, "firmware": str, "last_seen": str | null}]}

Consumers: the field-ops dashboard and the device provisioning tool both read this
endpoint.
