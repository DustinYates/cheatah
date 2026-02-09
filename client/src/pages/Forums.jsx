import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './Forums.css';

function formatTimeAgo(isoString) {
  if (!isoString) return null;
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths}mo ago`;
}

export default function Forums() {
  const fetchForums = useCallback(async () => {
    return api.getMyForums();
  }, []);

  const { data: forums, loading, error } = useFetchData(fetchForums);

  if (loading) {
    return <LoadingState message="Loading forums..." />;
  }

  if (error) {
    return <ErrorState message={error.message} />;
  }

  if (!forums || forums.length === 0) {
    return (
      <div className="forums-page">
        <div className="forums-header">
          <h1>Forums</h1>
        </div>
        <EmptyState
          title="No Forums Available"
          message="You don't have access to any forums yet. Contact your administrator to request access."
        />
      </div>
    );
  }

  return (
    <div className="forums-page">
      <div className="forums-header">
        <h1>Forums</h1>
        <p className="forums-subtitle">
          Join discussions with other members in your groups
        </p>
      </div>

      <div className="forums-grid">
        {forums.map((forum) => (
          <Link
            key={forum.id}
            to={`/forums/${forum.slug}`}
            className="forum-card"
          >
            <div className="forum-card-content">
              <h2 className="forum-card-title">{forum.name}</h2>
              <p className="forum-card-group">{forum.group_name}</p>
              {forum.description && (
                <p className="forum-card-description">{forum.description}</p>
              )}
              <div className="forum-card-stats">
                <span className="forum-stat">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                  {forum.total_post_count} {forum.total_post_count === 1 ? 'post' : 'posts'}
                </span>
                <span className="forum-stat">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                  {forum.member_count} {forum.member_count === 1 ? 'member' : 'members'}
                </span>
                {forum.last_activity && (
                  <span className="forum-stat">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    {formatTimeAgo(forum.last_activity)}
                  </span>
                )}
              </div>
            </div>
            <div className="forum-card-arrow">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
              </svg>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
