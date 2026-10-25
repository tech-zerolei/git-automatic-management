# Bundled dependencies

- Python semver 3.0.4, BSD-3-Clause. Vendored from the published PyPI wheel; wheel SHA-256 `9c824d87ba7f7ab4a1890799cec8596f15c1241cb473404ea1cb0c55e4b04746`. License included under vendor/.
- Lucide UMD bundle from the installed workspace runtime; ISC license included at static/vendor/LUCIDE-LICENSE. No CDN or external requests at runtime.

No Python/npm runtime package installation is required. Python standard library, system Git, Bubblewrap, Zenity and a desktop browser are used. These system dependencies must already be installed; unavailable isolation fails closed.
