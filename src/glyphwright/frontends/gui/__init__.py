"""The graphical frontend (design 0011).

``scene`` is pure and importable without pygame; only ``paint`` and
``session`` touch the ``gui`` extra, and the CLI imports them lazily so the
core package works with the extra absent.
"""
