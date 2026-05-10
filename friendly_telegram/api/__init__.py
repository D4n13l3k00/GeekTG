"""Stable, semver-friendly surface for module authors.

Third-party modules should import from ``friendly_telegram.api`` rather than
poking around in internals. Anything re-exported here carries a softer
breakage promise than the rest of the package.

The first thing exposed is :class:`ModuleContext` — a single, typed bundle
of the dependencies a module needs at runtime. Today it is *additive*:
the framework still sets ``self.allmodules``/``self.inline``/etc. as it
always did, but new code should read from ``self.ctx`` instead.
"""

from .context import ModuleContext

__all__ = ["ModuleContext"]
