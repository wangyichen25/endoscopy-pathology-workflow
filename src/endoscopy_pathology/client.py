"""Explicitly configured HTTPS adapter for a compatible chat-completions service."""
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward evidence or authorization to another endpoint.
        return None


class ProviderError(RuntimeError):
    pass


class HTTPSClient:
    def __init__(self, url, api_key, timeout=300, retries=2):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("An explicit HTTPS endpoint without embedded credentials is required")
        if not api_key:
            raise ValueError("Configure an API key in the environment")
        self.url, self.api_key = url, api_key
        self.timeout, self.retries = timeout, retries
        self.opener = build_opener(NoRedirect())

    @classmethod
    def from_environment(cls):
        return cls(os.getenv("WORKFLOW_API_URL", ""), os.getenv("WORKFLOW_API_KEY", ""))

    def complete(self, payload):
        request = Request(self.url, data=json.dumps(payload).encode(), method="POST",
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key})
        for attempt in range(self.retries + 1):
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    return json.load(response)
            except HTTPError as error:
                status = error.code
                error.close()
                if status not in [429, 500, 502, 503, 504] or attempt == self.retries:
                    raise ProviderError(f"Provider request failed (HTTP {status}); response body omitted") from None
            except (URLError, TimeoutError, OSError):
                raise ProviderError("Provider transport failed; request details omitted") from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ProviderError("Provider returned a non-JSON response; body omitted") from None
            time.sleep(min(2 ** attempt, 8))
        raise ProviderError("Provider request failed")
