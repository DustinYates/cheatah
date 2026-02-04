import { useState, useCallback } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState } from '../components/ui';
import { formatDistanceToNow } from '../utils/dateFormat';
import './Forums.css';

function ArchiveModal({ isOpen, onClose, onArchive, isSubmitting }) {
  const [status, setStatus] = useState('implemented');
  const [notes, setNotes] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    onArchive(status, notes);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Archive Post</h2>
          <button className="modal-close" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Status</label>
            <div className="status-options">
              <label className={`status-option ${status === 'implemented' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="status"
                  value="implemented"
                  checked={status === 'implemented'}
                  onChange={(e) => setStatus(e.target.value)}
                />
                <div>
                  <strong>Implemented</strong>
                  <div style={{ fontSize: '13px', color: '#6b7280' }}>
                    The feature or idea has been built
                  </div>
                </div>
              </label>
              <label className={`status-option ${status === 'resolved' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="status"
                  value="resolved"
                  checked={status === 'resolved'}
                  onChange={(e) => setStatus(e.target.value)}
                />
                <div>
                  <strong>Resolved</strong>
                  <div style={{ fontSize: '13px', color: '#6b7280' }}>
                    The bug or issue has been fixed
                  </div>
                </div>
              </label>
              <label className={`status-option ${status === 'archived' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="status"
                  value="archived"
                  checked={status === 'archived'}
                  onChange={(e) => setStatus(e.target.value)}
                />
                <div>
                  <strong>Archived</strong>
                  <div style={{ fontSize: '13px', color: '#6b7280' }}>
                    No action taken, just archived
                  </div>
                </div>
              </label>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="notes">Resolution Notes (optional)</label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add any notes about the resolution..."
              rows={3}
            />
          </div>

          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Archiving...' : 'Archive Post'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ForumPost() {
  const { forumSlug, categorySlug, postId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [showArchiveModal, setShowArchiveModal] = useState(false);
  const [isArchiving, setIsArchiving] = useState(false);
  const [voteData, setVoteData] = useState(null);

  const fetchPost = useCallback(async () => {
    const data = await api.getForumPost(forumSlug, categorySlug, postId);
    setVoteData({ user_has_voted: data.user_has_voted, vote_count: data.vote_count });
    return data;
  }, [forumSlug, categorySlug, postId]);

  const { data: post, loading, error, refetch } = useFetchData(fetchPost);

  const handleVote = async () => {
    try {
      const result = await api.togglePostVote(forumSlug, categorySlug, postId);
      setVoteData({ user_has_voted: result.user_has_voted, vote_count: result.vote_count });
    } catch (err) {
      console.error('Failed to vote:', err);
    }
  };

  const handleArchive = async (status, notes) => {
    setIsArchiving(true);
    try {
      await api.archivePost(forumSlug, categorySlug, postId, {
        status,
        resolution_notes: notes || null,
      });
      setShowArchiveModal(false);
      refetch();
    } catch (err) {
      console.error('Failed to archive:', err);
    } finally {
      setIsArchiving(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading post..." />;
  }

  if (error) {
    return <ErrorState message={error.message} />;
  }

  if (!post) {
    return <ErrorState message="Post not found" />;
  }

  // Determine if voting is allowed (based on category - we'd need to fetch this)
  // For now, we'll show vote if vote_count exists
  const allowsVoting = post.vote_count !== undefined;
  const currentVoteData = voteData || { user_has_voted: post.user_has_voted, vote_count: post.vote_count };
  const isArchived = post.status !== 'active';

  return (
    <div className="post-detail-page">
      <div className="forum-breadcrumb">
        <Link to="/forums">Forums</Link>
        <span>/</span>
        <Link to={`/forums/${forumSlug}`}>{post.forum_slug}</Link>
        <span>/</span>
        <Link to={`/forums/${forumSlug}/${categorySlug}`}>{post.category_name}</Link>
        <span>/</span>
        <span>Post</span>
      </div>

      <div className="post-detail-header">
        <h1 className="post-detail-title">
          {post.is_pinned && <span className="post-pinned-badge">Pinned</span>}
          {isArchived && (
            <span className={`post-status-badge ${post.status}`}>
              {post.status === 'implemented' ? 'Implemented' :
               post.status === 'resolved' ? 'Resolved' : 'Archived'}
            </span>
          )}
          {post.title}
        </h1>

        <div className="post-detail-meta">
          <span>
            Posted by <strong>{post.author_email}</strong>
            {post.author_tenant_name && ` (${post.author_tenant_name})`}
          </span>
          <span>{formatDistanceToNow(post.created_at)}</span>
        </div>
      </div>

      {/* Resolution notes for archived posts */}
      {isArchived && post.resolution_notes && (
        <div className="archive-section">
          <h3>Resolution Notes</h3>
          <p>{post.resolution_notes}</p>
        </div>
      )}

      <div className="post-detail-content">
        <p>{post.content}</p>
      </div>

      <div className="post-detail-actions">
        {allowsVoting && (
          <div className="post-detail-vote">
            <button
              className={`vote-btn ${currentVoteData.user_has_voted ? 'voted' : ''}`}
              onClick={handleVote}
              disabled={isArchived}
            >
              <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clipRule="evenodd" />
              </svg>
              <span className="vote-count">{currentVoteData.vote_count}</span>
              <span className="vote-label">votes</span>
            </button>
          </div>
        )}

        {user?.is_global_admin && !isArchived && (
          <button
            className="btn-secondary"
            onClick={() => setShowArchiveModal(true)}
          >
            Archive Post
          </button>
        )}

        <Link
          to={`/forums/${forumSlug}/${categorySlug}`}
          className="btn-secondary"
          style={{ marginLeft: 'auto' }}
        >
          Back to {post.category_name}
        </Link>
      </div>

      <ArchiveModal
        isOpen={showArchiveModal}
        onClose={() => setShowArchiveModal(false)}
        onArchive={handleArchive}
        isSubmitting={isArchiving}
      />
    </div>
  );
}
