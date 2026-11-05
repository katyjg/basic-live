# Automounter Selection State and Polling Synchronization via Config Model

Coordinating sample changer loading between human staff at the beamline and automated robot controllers requires sharing transient deck selection and reload states. We decided to synchronize automounter UI workflows using an ephemeral database model (`Config`) with short-lived selection timeouts and HTTP client polling rather than introducing stateful WebSocket or Redis pub/sub dependencies into the core framework.
