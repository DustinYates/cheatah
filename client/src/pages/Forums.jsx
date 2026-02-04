import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './Forums.css';

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
