import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Onboarding from './Onboarding'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { LoadingState, ErrorState } from '../components/ui'

vi.mock('../api/client', () => ({
  api: {
    getBusinessProfile: vi.fn(),
  }
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../components/ui', () => ({
  LoadingState: ({ message }) => <div data-testid="loading-state">{message}</div>,
  ErrorState: ({ message, onRetry }) => (
    <div data-testid="error-state">
      <p>{message}</p>
      {onRetry && <button onClick={onRetry}>Try Again</button>}
    </div>
  ),
}))

const renderOnboarding = () => {
  return render(
    <BrowserRouter>
      <Onboarding />
    </BrowserRouter>
  )
}

describe('Onboarding Page - State Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue({ refreshProfile: vi.fn() })
  })

  it('shows loading state initially', async () => {
    api.getBusinessProfile.mockImplementation(() => new Promise(() => {}))
    
    renderOnboarding()
    
    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    expect(screen.getByText('Loading your profile...')).toBeInTheDocument()
  })

  it('shows error state when profile load fails', async () => {
    const errorMessage = 'Failed to load profile'
    api.getBusinessProfile.mockRejectedValue(new Error(errorMessage))
    
    renderOnboarding()
    
    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })
    
    expect(screen.getByText(errorMessage)).toBeInTheDocument()
  })
})

