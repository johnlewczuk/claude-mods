from thermo.alerts import AlertChecker, WebhookSink
c = AlertChecker({"alert_threshold_c": 1, "alert_severity_levels": []}, WebhookSink("http://localhost:9999"))
print(c.check({"device_id": "x", "temperature": 5, "ts": 0}))
