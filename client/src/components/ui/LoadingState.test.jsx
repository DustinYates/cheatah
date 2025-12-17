import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LoadingState from './LoadingState'

describe('LoadingState', () => {
  it('renders default loading message', () => {
    render(<LoadingState />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders custom loading message', () => {
    render(<LoadingState message="Loading prompts..." />)
    expect(screen.getByText('Loading prompts...')).toBeInTheDocument()
  })

  it('renders spinner element', () => {
    const { container } = render(<LoadingState />)
    const spinner = container.querySelector('.loading-spinner')
    expect(spinner).toBeInTheDocument()
  })

  it('applies fullPage class when fullPage is true', () => {
    const { container } = render(<LoadingState fullPage />)
    const loadingState = container.querySelector('.loading-state')
    expect(loadingState).toHaveClass('loading-state--full')
  })

  it('does not apply fullPage class when fullPage is false', () => {
    const { container } = render(<LoadingState fullPage={false} />)
    const loadingState = container.querySelector('.loading-state')
    expect(loadingState).not.toHaveClass('loading-state--full')
  })
})

