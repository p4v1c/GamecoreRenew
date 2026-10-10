import { useEffect, useState } from 'react'
import { coverRect, matrix3dFor, quadFromCorners, quadInRect, type Point } from '../../lib/homography'
import corners from '../../assets/standby/room-screen.json'

/** The plate's size, which the corners are relative to. */
export const PLATE_W = 1920
export const PLATE_H = 1080
/** The glass, laid out flat before the warp: 0.30 x 0.235 m in the scene. */
export const TV_W = 640
export const TV_H = 500

const GLASS = quadFromCorners(corners as Point[])

function transformFor(vw: number, vh: number): string {
  return matrix3dFor(TV_W, TV_H, quadInRect(GLASS, coverRect(vw, vh, PLATE_W, PLATE_H)))
}

/** The TV glass's `transform`, kept on the plate when the window resizes. */
export function useTvPlacement(): string {
  const [transform, setTransform] = useState(() => transformFor(window.innerWidth, window.innerHeight))
  useEffect(() => {
    const onResize = () => setTransform(transformFor(window.innerWidth, window.innerHeight))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return transform
}
