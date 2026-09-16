from __future__ import annotations

import write_high_loft_recap  # noqa: F401 - importing applies High Loft prompt/validator overrides
import write_recap_batched
from resilient_openai_client import ResilientOpenAI


if __name__ == "__main__":
    write_recap_batched.OpenAI = ResilientOpenAI
    write_recap_batched.main()
