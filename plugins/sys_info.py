# 🧪 How to Use It
# ✅ In Chat Mode
# Start the server and client as usual, then type:

# /plugin sysinfo

# You’ll see output like:
# OS: Linux
# Release: 6.4.0
# Version: #1 SMP Wed Jul 12 10:00:00 UTC 2025
# Machine: x86_64
# Processor: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz

# ✅ In Reverse Shell
# From the server side, type:
# plugin sysinfo
# And the client will execute the plugin and return the result.

import platform

name = "sys_info"

def run(args):
    """
    Returns basic system information.
    Args are ignored in this plugin.
    """
    info = {
        "OS": platform.system(),
        "Release": platform.release(),
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Processor": platform.processor()
    }
    return "\n".join(f"{k}: {v}" for k, v in info.items())
