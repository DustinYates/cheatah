import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('renders default icon and title', () => {
    render(<EmptyState />)
    expect(screen.getByText('📭')).toBeInTheDocument()
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })

  it('renders custom icon and title', () => {
    render(<EmptyState icon="📝" title="No prompts yet" />)
    expect(screen.getByText('📝')).toBeInTheDocument()
    expect(screen.getByText('No prompts yet')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(
      <EmptyState
        description="Create your first bundle to get started"
      />
    )
    expect(screen.getByText('Create your first bundle to get started')).toBeInTheDocument()
  })

  it('does not render description when not provided', () => {
    const { container } = render(<EmptyState />)
    const description = container.querySelector('.empty-state__description')
    expect(description).not.toBeInTheDocument()
  })

  it('renders action button when action is provided', () => {
    const handleClick = vi.fn()
    render(
      <EmptyState
        action={{
          label: 'Create Bundle',
          onClick: handleClick
        }}
      />
    )
    const button = screen.getByText('Create Bundle')
    expect(button).toBeInTheDocument()
  })

  it('calls onClick when action button is clicked', async () => {
    const user = userEvent.setup()
    const handleClick = vi.fn()
    render(
      <EmptyState
        action={{
          label: 'Create Bundle',
          onClick: handleClick
        }}
      />
    )
    const button = screen.getByText('Create Bundle')
    await user.click(button)
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('does not render action button when action is not provided', () => {
    render(<EmptyState />)
    const button = screen.queryByRole('button')
    expect(button).not.toBeInTheDocument()
  })
})

