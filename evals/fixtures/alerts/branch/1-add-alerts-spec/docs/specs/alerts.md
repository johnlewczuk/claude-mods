# Temperature alerts

R1. `check(reading)` returns an `Alert` when the temperature exceeds the configured
    threshold (config key `alert_threshold_c`, default 80), otherwise `None`.
R2. An `Alert` carries the device id, the temperature, and the reading's timestamp.
R3. Repeated alerts for the same device are suppressed for `alert_cooldown_s` seconds
    (default 300) after the last delivered alert for that device.
R4. Alerts are delivered by HTTP POST of a JSON body to `alert_webhook_url`.

Out of scope for this change: email delivery (planned for phase 2).
