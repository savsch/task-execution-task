import re
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """
    Used for gobuster and ffuf task executors, see README.md
    Strictly disallows:
    - Non-HTTP(s) schemes.
    - URLs containing characters like `;`, `\\`
    """

    url_regex = re.compile(r'^(https?)://([a-zA-Z0-9-._~:/?#[\]@!$&\'()*+,;%=]+)$')

    if not url_regex.match(url):
        return False

    parsed_url = urlparse(url)

    if parsed_url.scheme not in ['http', 'https']:
        return False

    disallowed_chars = [';', '\\']
    if any(char in url for char in disallowed_chars):
        return False

    if parsed_url.fragment:
        return False

    if not parsed_url.hostname or not re.match(r'^[a-zA-Z0-9.-]+$', parsed_url.hostname):
        return False

    return True







