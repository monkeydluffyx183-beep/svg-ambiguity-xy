"""xybench — the SVG reference-resolution study, on real charts exported by the XY
charting library, with the format-matched control from ``fmtcontrol_xy``.

Two corpus variants of the same charts: ``masked`` (marker coordinates replaced by opaque
tokens — upstream's information gap on real markup) and ``real`` (coordinates legible).
Four conditions per variant: ``baseline``, ``permuted``, ``enhanced``, ``named_id``.
"""

__version__ = "0.1.0"
