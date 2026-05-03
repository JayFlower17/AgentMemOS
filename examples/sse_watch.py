import os
from urllib.request import Request, urlopen


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014").rstrip("/")
    request = Request(f"{base_url}/events/stream?replay=10", headers={"Accept": "text/event-stream"})
    with urlopen(request, timeout=None) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").rstrip()
            if line:
                print(line)


if __name__ == "__main__":
    main()
