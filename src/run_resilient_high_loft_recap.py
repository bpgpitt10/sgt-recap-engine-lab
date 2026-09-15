from __future__ import annotations

import write_recap
import write_high_loft_recap  # noqa: F401 - importing applies High Loft prompt/validator overrides
from resilient_openai_client import ResilientOpenAI


if __name__ == "__main__":
    write_recap.OpenAI = ResilientOpenAI
    write_recap.main()
