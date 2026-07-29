"""Tiny read-only ISO9660 accessor — just enough to pull one file out of a
disc image (PSP ICON0.PNG, PS1/PS2 SYSTEM.CNF).

Supports plain 2048-byte sector images (.iso) and raw 2352-byte dumps
(.bin/.img, MODE1 and MODE2/Form1).
"""
import os
import struct

# (sector_size, offset of the 2048 user-data bytes within a sector)
_LAYOUTS = ((2048, 0), (2352, 16), (2352, 24))


class Iso9660:
    def __init__(self, fh, sector_size: int, data_offset: int):
        self._fh = fh
        self._ss = sector_size
        self._off = data_offset

    @classmethod
    def open(cls, path) -> "Iso9660 | None":
        """Open a disc image, autodetecting the sector layout. None if the
        file is not a readable ISO9660 volume (e.g. compressed .cso)."""
        try:
            fh = open(path, "rb")
        except OSError:
            return None
        for ss, off in _LAYOUTS:
            try:
                fh.seek(16 * ss + off)
                head = fh.read(6)
            except OSError:
                break
            # Volume descriptor: type byte then "CD001"
            if len(head) == 6 and head[1:6] == b"CD001":
                return cls(fh, ss, off)
        fh.close()
        return None

    def close(self):
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _sector(self, lba: int) -> bytes:
        self._fh.seek(lba * self._ss + self._off)
        return self._fh.read(2048)

    def _read_extent(self, lba: int, size: int) -> bytes:
        # `size` is read out of the directory record, i.e. out of the file we
        # are parsing — a corrupt or hostile image can claim any 32-bit length.
        # Cap it at what the image could actually hold, so the loop below stops
        # at end-of-file instead of growing a multi-gigabyte bytearray.
        try:
            file_size = os.fstat(self._fh.fileno()).st_size
        except OSError:
            file_size = 0
        if file_size:
            size = min(size, file_size)
        out = bytearray()
        while len(out) < size:
            chunk = self._sector(lba)
            if not chunk:
                break
            out += chunk
            lba += 1
        return bytes(out[:size])

    def _entries(self, lba: int, size: int):
        """Yield (name, extent_lba, size, flags) for a directory extent."""
        data = self._read_extent(lba, size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # zero-padding at the end of a sector — skip to the next one
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = data[pos : pos + rec_len]
            pos += rec_len
            if len(rec) < 34:
                continue
            name_len = rec[32]
            raw_name = rec[33 : 33 + name_len]
            if raw_name in (b"\x00", b"\x01"):  # "." and ".." entries
                continue
            name = raw_name.decode("ascii", "replace").split(";")[0].rstrip(".")
            extent = struct.unpack_from("<I", rec, 2)[0]
            fsize = struct.unpack_from("<I", rec, 10)[0]
            yield name, extent, fsize, rec[25]

    def read_file(self, path: str) -> bytes | None:
        """Read a file by absolute path ("PSP_GAME/ICON0.PNG"), case-insensitive.
        None if any component is missing."""
        pvd = self._sector(16)
        if len(pvd) < 190:
            return None
        # Root directory record lives at offset 156 of the PVD
        extent = struct.unpack_from("<I", pvd, 156 + 2)[0]
        size = struct.unpack_from("<I", pvd, 156 + 10)[0]
        components = [c for c in path.upper().split("/") if c]
        for i, comp in enumerate(components):
            found = None
            for name, e, s, flags in self._entries(extent, size):
                if name.upper() == comp:
                    found = (e, s, flags)
                    break
            if not found:
                return None
            extent, size, flags = found
            if i < len(components) - 1 and not flags & 0x02:
                return None  # intermediate component is not a directory
        return self._read_extent(extent, size)
