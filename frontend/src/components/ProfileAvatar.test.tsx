/** The top bar's profile picture: nothing without profiles, the picture or the
 *  initial on the profile's colour, and a press opens Settings → Profiles. */
import { render, fireEvent, cleanup } from '@testing-library/react'
import { it, expect, vi, afterEach } from 'vitest'
import ProfileAvatar from './ProfileAvatar'
import { useStore } from '../store'

afterEach(() => { cleanup(); useStore.getState().setActiveProfile('', '') })

it('shows nothing on a box without profiles', () => {
  const { container } = render(<ProfileAvatar />)
  expect(container.innerHTML).toBe('')
})

it('draws the initial, then the picture, on the profile colour', () => {
  useStore.getState().setActiveProfile('Max', '', { color: '#127a6d', avatar: null })
  const onClick = vi.fn()
  const { getByRole, rerender } = render(<ProfileAvatar onClick={onClick} />)
  const button = getByRole('button', { name: 'Profile: Max' })
  expect(button.textContent).toBe('M')
  expect(button.style.background).toContain('rgb(18, 122, 109)')
  fireEvent.click(button)
  expect(onClick).toHaveBeenCalled()
  useStore.getState().setActiveProfile('Max', '', { color: '#127a6d', avatar: 'fox' })
  rerender(<ProfileAvatar onClick={onClick} />)
  expect(getByRole('button').querySelector('svg path')).toBeTruthy()
})

it('draws the initial for a picture an older version offered', () => {
  useStore.getState().setActiveProfile('Max', '', { color: '#127a6d', avatar: 'rocket' })
  const { getByRole } = render(<ProfileAvatar />)
  expect(getByRole('button').textContent).toBe('M')
})
