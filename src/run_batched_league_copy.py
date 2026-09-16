from __future__ import annotations

import write_league_copy_batched
from resilient_openai_client import ResilientOpenAI


if __name__ == "__main__":
    write_league_copy_batched.OpenAI = ResilientOpenAI
    write_league_copy_batched.main()
