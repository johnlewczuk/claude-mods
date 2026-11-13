from thermo.alerts import AlertChecker


class FakeSink:
    def __init__(self):
        self.sent = []

    def send(self, alert):
        self.sent.append(alert)


def test_alert_above_threshold():
    sink = FakeSink()
    c = AlertChecker({"alert_threshold_c": 80, "alert_severity_levels": []}, sink)
    assert c.check({"device_id": "d1", "temperature": 85, "ts": 1}) is not None
    assert len(sink.sent) == 1


def test_no_alert_below_threshold():
    c = AlertChecker({"alert_threshold_c": 80, "alert_severity_levels": []}, FakeSink())
    assert c.check({"device_id": "d1", "temperature": 70, "ts": 1}) is None
