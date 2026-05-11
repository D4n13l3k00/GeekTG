"""GeekTG userbot package.

Backward-compat shim: legacy code, third-party modules and cloud-DB keys
reference the historical package name ``friendly-telegram``. We install a
lightweight :class:`importlib.abc.MetaPathFinder` that re-maps any
``friendly-telegram[.X]`` import to the corresponding ``friendly_telegram[.X]`` module,
so:

* ``importlib.import_module("friendly-telegram.utils")`` works
* ``mod.__module__ == "friendly-telegram.modules.X"`` introspection holds
* relative imports inside dynamically-loaded modules registered under
  ``friendly-telegram.modules.<name>`` resolve their parent package
* no submodule is eagerly imported at package-init time (no circular imports)
"""

import importlib as _importlib
import importlib.util as _importlib_util
import sys as _sys

__version__ = (4, 2, 0)

_LEGACY = "friendly-telegram"
_REAL = __name__


class _LegacyAliasFinder:
    """Resolve ``friendly-telegram[.X]`` to the matching ``friendly_telegram[.X]`` module."""

    @classmethod
    def find_module(cls, fullname, path=None):  # legacy API used by some tools
        if fullname == _LEGACY or fullname.startswith(_LEGACY + "."):
            return cls
        return None

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if fullname != _LEGACY and not fullname.startswith(_LEGACY + "."):
            return None
        real_name = _REAL + fullname[len(_LEGACY) :]
        real_mod = _importlib.import_module(real_name)
        _sys.modules[fullname] = real_mod
        return _importlib_util.spec_from_loader(fullname, loader=None, origin=real_name)

    def load_module(self, fullname):  # noqa: D401  (legacy hook)
        return _sys.modules[fullname]


# Top-level alias must exist eagerly so attribute access like
# ``sys.modules["friendly-telegram"].utils`` works without an import.
_sys.modules.setdefault(_LEGACY, _sys.modules[_REAL])

# Install finder once.
if not any(
    isinstance(f, _LegacyAliasFinder) or f is _LegacyAliasFinder for f in _sys.meta_path
):
    _sys.meta_path.append(_LegacyAliasFinder)
