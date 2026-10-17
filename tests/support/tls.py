from pathlib import Path
import ssl

from terminal_browser.net.transport import TlsPolicy


class FixtureTlsContextFactory:
    def __init__(self, ca_path: Path) -> None:
        self._ca_path = ca_path

    def create(self, policy: TlsPolicy) -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=str(self._ca_path))
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = policy.min_tls_version
        return context
