from __future__ import annotations

import write_league_copy
from resilient_openai_client import ResilientOpenAI


if __name__ == "__main__":
    write_league_copy.OpenAI = ResilientOpenAI
    write_league_copy.main()
