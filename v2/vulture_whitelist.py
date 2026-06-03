"""Static-analysis whitelist for dynamic Flask/Jinja entry points.

Keep this file narrow. Add names only when vulture reports a false positive
caused by Flask routing, template usage, CLI entry points, or other dynamic
framework behavior.
"""
