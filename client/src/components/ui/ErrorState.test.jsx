import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ErrorState from './ErrorState'

describe('ErrorState', () => {
  it('renders default error message', () => {
    render(<ErrorState />)
    expect(screen.getByText('Error')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('renders custom error message and title', () => {
    render(<ErrorState title="Failed to Load" message="Network error occurred" />)
    expect(screen.getByText('Failed to Load')).toBeInTheDocument()
    expect(screen.getByText('Network error occurred')).toBeInTheDocument()
  })

  it('renders error icon', () => {
    const { container } = render(<ErrorState />)
    const icon = container.querySelector('.error-state__icon')
    expect(icon).toBeInTheDocument()
    expect(icon.textContent).toBe('⚠️')
  })

  it('renders retry button when onRetry is provided', () => {
    const handleRetry = vi.fn()
    render(<ErrorState onRetry={handleRetry} />)
    expect(screen.getByText('Try Again')).toBeInTheDocument()
  })

  it('calls onRetry when retry button is clicked', async () => {
    const user = userEvent.setup()
    const handleRetry = vi.fn()
    render(<ErrorState onRetry={handleRetry} />)
    const button = screen.getByText('Try Again')
    await user.click(button)
    expect(handleRetry).toHaveBeenCalledTimes(1)
  })

  it('does not render retry button when onRetry is not provided', () => {
    render(<ErrorState />)
    const button = screen.queryByText('Try Again')
    expect(button).not.toBeInTheDocument()
  })
})

