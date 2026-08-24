from __future__ import annotations

import os


if os.environ.get("SERVER") != "true" and os.environ.get("REMOTER_CONFIG"):
    from remoter import autoremote

    autoremote.start(False)
