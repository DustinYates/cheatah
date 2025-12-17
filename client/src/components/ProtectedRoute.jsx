import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LoadingState } from './ui';

export default function ProtectedRoute({ children, requireProfile = false }) {
  const { user, loading, profileComplete, profileLoading } = useAuth();

  if (loading || profileLoading) {
    return <LoadingState message="Authenticating..." fullPage />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requireProfile && !user.is_global_admin && profileComplete === false) {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
}
