from __future__ import annotations

import json
import time

from remoter import autoremote


def main() -> None:
    autoremote.start(False)

    from demo_model import predict

    while True:
        result = predict([1, 2, 3, 4])
        print(json.dumps(result), flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
