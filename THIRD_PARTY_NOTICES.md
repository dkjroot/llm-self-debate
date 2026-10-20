# Third-party dependencies and credits

Reviewed 20 October 2026 against `requirements.txt` and the corresponding locally
installed distribution metadata/license files. Dependencies are installed
separately and are not vendored into the application source. Their copyright and
license notices remain with their distributions.

| Package/version | Upstream authors/source | License |
| --- | --- | --- |
| openai 1.68.2 | [OpenAI and contributors](https://github.com/openai/openai-python/tree/v1.68.2) | Apache-2.0 |
| annotated-types 0.7.0 | [annotated-types contributors](https://github.com/annotated-types/annotated-types) | MIT |
| anyio 4.9.0 | [Alex Gronholm and contributors](https://github.com/agronholm/anyio) | MIT |
| certifi 2025.1.31 | [Certifi contributors / Mozilla CA data](https://github.com/certifi/python-certifi) | MPL-2.0 |
| distro 1.9.0 | [distro contributors](https://github.com/python-distro/distro) | Apache-2.0 |
| exceptiongroup 1.2.2 | [Alex Gronholm and contributors](https://github.com/agronholm/exceptiongroup) | MIT |
| h11 0.14.0 | [Nathaniel J. Smith and contributors](https://github.com/python-hyper/h11) | MIT |
| httpcore 1.0.7 | [Encode and contributors](https://github.com/encode/httpcore) | BSD-3-Clause |
| httpx 0.28.1 | [Encode and contributors](https://github.com/encode/httpx) | BSD-3-Clause |
| idna 3.10 | [Kim Davies and contributors](https://github.com/kjd/idna) | BSD-3-Clause |
| jiter 0.9.0 | [Pydantic contributors](https://github.com/pydantic/jiter) | MIT |
| pydantic 2.10.6 | [Samuel Colvin and contributors](https://github.com/pydantic/pydantic) | MIT |
| pydantic_core 2.27.2 | [Pydantic contributors](https://github.com/pydantic/pydantic-core) | MIT |
| sniffio 1.3.1 | [Nathaniel J. Smith and contributors](https://github.com/python-trio/sniffio) | MIT OR Apache-2.0 |
| tqdm 4.67.1 | [tqdm developers](https://github.com/tqdm/tqdm) | MIT for code; MPL-2.0 for documentation, as detailed in upstream LICENCE |
| typing_extensions 4.12.2 | [Python typing contributors](https://github.com/python/typing_extensions) | PSF-2.0 |

On Windows, the installed environment additionally resolves colorama 0.4.6
([Jonathan Hartley and contributors](https://github.com/tartley/colorama), BSD-3-Clause).
Python and pip have their own PSF/MIT and vendored component notices; they are
development/runtime tools, not application-authored code.

These library licenses permit inclusion with GPLv3 code subject to their terms.
When distributing installed dependencies, keep their full copyright/permission
texts, preserve Apache notices and identify modifications where required. MPL
covered material such as certifi's CA bundle keeps its own license and applicable
source-availability requirements; GPL on this application does not erase those
obligations. The source tree does not bundle model weights or SDK/provider output.
Check exact versions and platform/native dependencies again for any installer.
See [LICENSING.md](LICENSING.md).
