from __future__ import annotations

import write_recap_batched
from resilient_openai_client import ResilientOpenAI


if __name__ == "__main__":
    write_recap_batched.OpenAI = ResilientOpenAI
    write_recap_batched.main()
