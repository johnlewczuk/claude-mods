"""Minimal request/response types shared by the API handlers."""
import json
from dataclasses import dataclass, field


@dataclass
class Request:
    method: str
    path: str
    query: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)


@dataclass
class Response:
    status: int
    body: str
    headers: dict = field(default_factory=lambda: {"Content-Type": "application/json"})


def json_response(data, status=200):
    return Response(status, json.dumps(data, sort_keys=True))


def error_response(status, message):
    return json_response({"error": message}, status)
