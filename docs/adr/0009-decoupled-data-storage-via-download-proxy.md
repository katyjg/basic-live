# Decoupled Data Storage via External Download Proxy

High-throughput detector collections generate immense raw data volumes that should not bottleneck the web application tier. We decided that BasicLIVE acts strictly as a metadata and authorization broker without directly serving, streaming, or managing physical files on POSIX storage, delegating all raw data downloads to an external reverse proxy service that validates short-lived download tokens issued by BasicLIVE.
