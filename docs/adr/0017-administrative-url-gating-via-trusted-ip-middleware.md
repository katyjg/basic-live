# Administrative URL Gating via Trusted IP Middleware

Administrative and internal endpoints present high-value targets when exposed on facility networks. We decided to enforce IP-based access control at the application layer using `TrustedAccessMiddleware`, validating client addresses (with configurable proxy depth via `TRUSTED_PROXIES`) against allowed CIDR ranges in `TRUSTED_IPS` and returning silent HTTP 404 responses for untrusted requests to obscure endpoint existence.
