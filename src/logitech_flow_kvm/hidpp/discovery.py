"""Device discovery, dispatched to the backend available on this platform.

The backend modules are imported conditionally so that neither platform's
dependencies are loaded on the other: the hidapi backend needs a package that is
only installed on Windows.
"""

import sys

if sys.platform == "win32":
    from .discovery_hidapi import find_direct_devices
    from .discovery_hidapi import find_receivers
else:
    from .discovery_linux import find_direct_devices
    from .discovery_linux import find_receivers

__all__ = ["find_direct_devices", "find_receivers"]
