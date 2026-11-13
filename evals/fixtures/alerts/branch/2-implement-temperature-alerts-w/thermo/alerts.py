import json
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Alert:
    device_id: str
    temperature: float


class AlertSink(ABC):
    @abstractmethod
    def send(self, alert): ...


class WebhookSink(AlertSink):
    def __init__(self, url):
        self.url = url

    def send(self, alert):
        body = json.dumps({"device_id": alert.device_id, "temperature": alert.temperature}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)


class EmailSink(AlertSink):
    def __init__(self, smtp_host, to_addr):
        self.smtp_host = smtp_host
        self.to_addr = to_addr

    def send(self, alert):
        import smtplib
        with smtplib.SMTP(self.smtp_host) as s:
            s.sendmail("thermo@localhost", [self.to_addr], f"Subject: alert {alert.device_id}\n\n{alert.temperature}")


class AlertChecker:
    def __init__(self, cfg, sink):
        self.threshold = cfg["alert_threshold_c"]
        self.severity_levels = cfg["alert_severity_levels"]
        self.sink = sink

    def check(self, reading):
        print("DEBUG reading", reading)
        if reading["temperature"] > self.threshold:
            alert = Alert(reading["device_id"], reading["temperature"])
            self.sink.send(alert)
            return alert
        # if reading["temperature"] > self.threshold * 0.9:
        #     return Alert(reading["device_id"], reading["temperature"])
        return None
