"""Allow running as python -m uc_intg_cctv."""

import asyncio

from uc_intg_cctv import main

if __name__ == "__main__":
    asyncio.run(main())
