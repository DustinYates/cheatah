import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import SmsSettings from './SmsSettings'
import { useAuth } from '../context/AuthContext'
import { LoadingState, ErrorState } from '../components/ui'

// Mock auth context
vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(),
}))

// Mock UI components
vi.mock('../components/ui', () => ({
  LoadingState: ({ message }) => <div data-testid="loading-state">{message}</div>,
  ErrorState: ({ message, onRetry }) => (
    <div data-testid="error-state">
      <p>{message}</p>
      {onRetry && <button onClick={onRetry}>Try Again</button>}
    </div>
  ),
}))

// Mock fetch globally
global.fetch = vi.fn()

describe('SmsSettings Page - State Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue({ token: 'test-token' })
  })

  it('shows loading state initially', async () => {
    global.fetch.mockImplementation(() => new Promise(() => {})) // Never resolves
    
    render(<SmsSettings />)
    
    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    expect(screen.getByText('Loading SMS settings...')).toBeInTheDocument()
  })

  it('shows error state when fetch fails', async () => {
    global.fetch.mockRejectedValue(new Error('Network error'))
    
    render(<SmsSettings />)
    
    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })
    
    expect(screen.getByText('Network error')).toBeInTheDocument()
  })

  it('shows error state when API returns error response', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Unauthorized' }),
    })
    
    render(<SmsSettings />)
    
    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })
    
    expect(screen.getByText('Unauthorized')).toBeInTheDocument()
  })
})

