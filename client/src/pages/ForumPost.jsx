import { useState, useCallback, useEffect, useRef } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmojiPicker } from '../components/ui';
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

function VoteButtons({ score, userVote, onVote, disabled, vertical = false }) {
  return (
    <div className={`vote-buttons ${vertical ? 'vertical' : ''}`}>
      <button
        className={`vote-arrow up ${userVote === 1 ? 'active' : ''}`}
        onClick={() => onVote(userVote === 1 ? 0 : 1)}
        disabled={disabled}
        title="Upvote"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 4l-8 8h5v8h6v-8h5z" />
        </svg>
      </button>
      <span className={`vote-score ${userVote === 1 ? 'upvoted' : userVote === -1 ? 'downvoted' : ''}`}>
        {score}
      </span>
      <button
        className={`vote-arrow down ${userVote === -1 ? 'active' : ''}`}
        onClick={() => onVote(userVote === -1 ? 0 : -1)}
        disabled={disabled}
        title="Downvote"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 20l8-8h-5V4H9v8H4z" />
        </svg>
      </button>
    </div>
  );
}

function Comment({ comment, onVote, onReply, onDelete, currentUserId, depth = 0, allComments, isArchived, votingComments }) {
  const [showReplyForm, setShowReplyForm] = useState(false);
  const [replyContent, setReplyContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const replyTextareaRef = useRef(null);

  const replies = allComments
    .filter(c => c.parent_comment_id === comment.id)
    .sort((a, b) => b.score - a.score);
  const maxDepth = 4;

  const handleSubmitReply = async (e) => {
    e.preventDefault();
    if (!replyContent.trim()) return;

    setIsSubmitting(true);
    try {
      await onReply(replyContent, comment.id);
      setReplyContent('');
      setShowReplyForm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEmojiSelect = (emoji) => {
    const textarea = replyTextareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const newContent = replyContent.substring(0, start) + emoji + replyContent.substring(end);
      setReplyContent(newContent);
      // Set cursor position after emoji
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
        textarea.focus();
      }, 0);
    } else {
      setReplyContent(replyContent + emoji);
    }
  };

  const canDelete = comment.author_email && currentUserId && !comment.is_deleted;

  return (
    <div className={`comment ${depth > 0 ? 'nested' : ''}`} style={{ marginLeft: Math.min(depth, maxDepth) * 24 }}>
      <div className="comment-left">
        <VoteButtons
          score={comment.score}
          userVote={comment.user_vote}
          onVote={(value) => onVote(comment.id, value)}
          disabled={isArchived || comment.is_deleted || votingComments?.has(comment.id)}
          vertical
        />
        {depth < maxDepth && replies.length > 0 && (
          <div className="comment-thread-line" />
        )}
      </div>
      <div className="comment-body">
        <div className="comment-header">
          <span className="comment-author">
            {comment.author_email?.split('@')[0] || 'Anonymous'}
            {comment.author_tenant_name && <span className="comment-tenant">({comment.author_tenant_name})</span>}
          </span>
          <span className="comment-time">{formatDistanceToNow(comment.created_at)}</span>
        </div>
        <div className={`comment-content ${comment.is_deleted ? 'deleted' : ''}`}>
          {comment.content}
        </div>
        {!isArchived && !comment.is_deleted && (
          <div className="comment-actions">
            <button className="comment-action-btn" onClick={() => setShowReplyForm(!showReplyForm)}>
              Reply
            </button>
            {canDelete && (
              <button className="comment-action-btn delete" onClick={() => onDelete(comment.id)}>
                Delete
              </button>
            )}
          </div>
        )}
        {showReplyForm && (
          <form className="reply-form" onSubmit={handleSubmitReply}>
            <div className="composer-wrapper">
              <textarea
                ref={replyTextareaRef}
                value={replyContent}
                onChange={(e) => setReplyContent(e.target.value)}
                placeholder="Write a reply..."
                rows={2}
              />
              <div className="composer-toolbar">
                <EmojiPicker onSelect={handleEmojiSelect} position="top" />
              </div>
            </div>
            <div className="reply-form-actions">
              <button type="button" className="btn-secondary btn-sm" onClick={() => setShowReplyForm(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary btn-sm" disabled={isSubmitting || !replyContent.trim()}>
                {isSubmitting ? 'Posting...' : 'Reply'}
              </button>
            </div>
          </form>
        )}
        {replies.map(reply => (
          <Comment
            key={reply.id}
            comment={reply}
            onVote={onVote}
            onReply={onReply}
            onDelete={onDelete}
            currentUserId={currentUserId}
            depth={depth + 1}
            allComments={allComments}
            isArchived={isArchived}
            votingComments={votingComments}
          />
        ))}
      </div>
    </div>
  );
}

function CommentsSection({ forumSlug, categorySlug, postId, isArchived }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newComment, setNewComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [votingComments, setVotingComments] = useState(new Set()); // Track comments with pending votes
  const commentTextareaRef = useRef(null);
  const { user } = useAuth();

  const fetchComments = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getPostComments(forumSlug, categorySlug, postId);
      setComments(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [forumSlug, categorySlug, postId]);

  useEffect(() => {
    fetchComments();
  }, [fetchComments]);

  const handleVote = async (commentId, voteValue) => {
    // Prevent double voting - ignore if already voting on this comment
    if (votingComments.has(commentId)) return;

    // Mark comment as voting in progress
    setVotingComments(prev => new Set(prev).add(commentId));

    try {
      const result = await api.voteOnComment(forumSlug, categorySlug, postId, commentId, voteValue);
      setComments(prev => prev.map(c =>
        c.id === commentId
          ? { ...c, score: result.score, user_vote: result.user_vote }
          : c
      ));
    } catch (err) {
      console.error('Failed to vote:', err);
    } finally {
      // Remove from voting set
      setVotingComments(prev => {
        const next = new Set(prev);
        next.delete(commentId);
        return next;
      });
    }
  };

  const handleReply = async (content, parentCommentId = null) => {
    try {
      const result = await api.createComment(forumSlug, categorySlug, postId, {
        content,
        parent_comment_id: parentCommentId,
      });
      setComments(prev => [...prev, result]);
    } catch (err) {
      console.error('Failed to create reply:', err);
      throw err;
    }
  };

  const handleDelete = async (commentId) => {
    if (!window.confirm('Are you sure you want to delete this comment?')) return;
    try {
      await api.deleteComment(forumSlug, categorySlug, postId, commentId);
      setComments(prev => prev.map(c =>
        c.id === commentId
          ? { ...c, is_deleted: true, content: '[deleted]' }
          : c
      ));
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const handleSubmitComment = async (e) => {
    e.preventDefault();
    if (!newComment.trim()) return;

    setIsSubmitting(true);
    try {
      await handleReply(newComment);
      setNewComment('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEmojiSelect = (emoji) => {
    const textarea = commentTextareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const updated = newComment.substring(0, start) + emoji + newComment.substring(end);
      setNewComment(updated);
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
        textarea.focus();
      }, 0);
    } else {
      setNewComment(newComment + emoji);
    }
  };

  const topLevelComments = comments
    .filter(c => !c.parent_comment_id)
    .sort((a, b) => b.score - a.score);

  if (loading) {
    return <div className="comments-loading">Loading comments...</div>;
  }

  if (error) {
    return <div className="comments-error">Failed to load comments: {error}</div>;
  }

  return (
    <div className="comments-section">
      <div className="comments-divider">
        <span>{comments.length} Comment{comments.length !== 1 ? 's' : ''}</span>
      </div>

      {!isArchived && (
        <form className="comment-form" onSubmit={handleSubmitComment}>
          <div className="composer-wrapper">
            <textarea
              ref={commentTextareaRef}
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              placeholder="Share your thoughts..."
              rows={3}
            />
            <div className="composer-toolbar">
              <EmojiPicker onSelect={handleEmojiSelect} position="top" />
              <button type="submit" className="btn-primary" disabled={isSubmitting || !newComment.trim()}>
                {isSubmitting ? 'Posting...' : 'Comment'}
              </button>
            </div>
          </div>
        </form>
      )}

      <div className="comments-list">
        {topLevelComments.length === 0 ? (
          <div className="no-comments">No comments yet. Be the first to share your thoughts!</div>
        ) : (
          topLevelComments.map(comment => (
            <Comment
              key={comment.id}
              comment={comment}
              onVote={handleVote}
              onReply={handleReply}
              onDelete={handleDelete}
              currentUserId={user?.id}
              depth={0}
              allComments={comments}
              isArchived={isArchived}
              votingComments={votingComments}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default function ForumPost() {
  const { forumSlug, categorySlug, postId } = useParams();
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

  const allowsVoting = post.vote_count !== undefined;
  const currentVoteData = voteData || { user_has_voted: post.user_has_voted, vote_count: post.vote_count };
  const isArchived = post.status !== 'active';

  // Map status to display label
  const getStatusLabel = (status) => {
    switch (status) {
      case 'planned': return 'Planned';
      case 'in_progress': return 'In Progress';
      case 'implemented':
      case 'shipped': return 'Shipped';
      case 'resolved': return 'Resolved';
      case 'archived': return 'Archived';
      default: return status;
    }
  };

  return (
    <div className="post-detail-page">
      <div className="forum-breadcrumb">
        <Link to="/forums">Forums</Link>
        <span>/</span>
        <Link to={`/forums/${forumSlug}`}>{post.forum_slug}</Link>
        <span>/</span>
        <Link to={`/forums/${forumSlug}/${categorySlug}`}>{post.category_name}</Link>
      </div>

      {/* Post Article Card */}
      <article className="post-article">
        {/* Header with badges, title, meta */}
        <header className="post-article-header">
          <div className="post-badges">
            {post.is_pinned && <span className="badge badge--pinned">Pinned</span>}
            {isArchived && (
              <span className={`badge badge--${post.status.replace('_', '-')}`}>
                {getStatusLabel(post.status)}
              </span>
            )}
          </div>
          <h1 className="post-article-title">{post.title}</h1>
          <div className="post-article-meta">
            <span className="post-author">
              by {post.author_email?.split('@')[0] || 'Anonymous'}
              {post.author_tenant_name && (
                <span className="post-tenant"> ({post.author_tenant_name})</span>
              )}
            </span>
            <span className="meta-separator">·</span>
            <span>{formatDistanceToNow(post.created_at)}</span>
          </div>
        </header>

        {/* Resolution notes for archived posts */}
        {isArchived && post.resolution_notes && (
          <div className="post-resolution-notes">
            <h3>Resolution Notes</h3>
            <p>{post.resolution_notes}</p>
          </div>
        )}

        {/* Post Content */}
        <div className="post-article-content">
          <p>{post.content}</p>
        </div>

        {/* Action Bar */}
        <footer className="post-action-bar">
          <div className="action-bar-left">
            {allowsVoting && (
              <div className="vote-buttons-inline">
                <button
                  className={`vote-arrow vote-up ${currentVoteData.user_has_voted ? 'active' : ''}`}
                  onClick={handleVote}
                  disabled={isArchived}
                  aria-label={currentVoteData.user_has_voted ? 'Remove vote' : 'Upvote'}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 4l-8 8h5v8h6v-8h5z" />
                  </svg>
                </button>
                <span className={`vote-score ${currentVoteData.user_has_voted ? 'upvoted' : ''}`}>
                  {currentVoteData.vote_count}
                </span>
              </div>
            )}
          </div>
          <div className="action-bar-right">
            <button className="action-btn" title="Share">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="18" cy="5" r="3" />
                <circle cx="6" cy="12" r="3" />
                <circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
              Share
            </button>
            {user?.is_global_admin && !isArchived && (
              <button
                className="action-btn"
                onClick={() => setShowArchiveModal(true)}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" />
                </svg>
                Archive
              </button>
            )}
          </div>
        </footer>
      </article>

      {/* Comments Section */}
      <CommentsSection
        forumSlug={forumSlug}
        categorySlug={categorySlug}
        postId={postId}
        isArchived={isArchived}
      />

      <ArchiveModal
        isOpen={showArchiveModal}
        onClose={() => setShowArchiveModal(false)}
        onArchive={handleArchive}
        isSubmitting={isArchiving}
      />
    </div>
  );
}
