/** One external disk — see api.storage. */
export interface StorageVolume {
  name: string
  /** `/dev/sdb1`. The handle for mount/unmount: a row number is not one, since
   *  a disk arriving while the screen is open renumbers the list. */
  device: string
  label: string
  uuid: string
  fstype: string
  size: string
  /** Where udisks put it. Not stable across replugs — do not record it. */
  mountpoint: string
  mounted: boolean
  slug: string
  /** `<DATA>/volumes/<slug>` — what a romsPath should point at. Survives a
   *  replug, which the mount point does not: udisks calls the second mount of
   *  the same disk "ROMS 1". */
  stable_path: string
  /** false for exFAT/NTFS: ROMs are fine, emulator saves are not. */
  keeps_permissions: boolean
  /** The sentence to show when keeps_permissions is false; "" otherwise. */
  saves_warning: string
}
