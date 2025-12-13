import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children, requireProfile = false }) {
  const { user, loading, profileComplete, profileLoading } = useAuth();

  if (loading || profileLoading) {
    return <div className="loading">Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requireProfile && !user.is_global_admin && profileComplete === false) {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
}
