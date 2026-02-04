import { useState, useCallback, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatDistanceToNow } from '../utils/dateFormat';
import './Forums.css';

function PostCard({ post, forumSlug, categorySlug, allowsVoting, onVote }) {
  const handleVoteClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (allowsVoting && post.status === 'active') {
      await onVote(post.id);
    }
  };

  // Generate preview from content (strip HTML, truncate)
  const getPreview = (content) => {
    if (!content) return '';
    // Remove HTML tags and trim
    const text = content.replace(/<[^>]*>/g, '').trim();
    return text.length > 150 ? text.substring(0, 150) + '...' : text;
  };

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

  const preview = getPreview(post.content);

  return (
    <Link
      to={`/forums/${forumSlug}/${categorySlug}/${post.id}`}
      className="post-card"
    >
      {allowsVoting && (
        <div className="vote-column">
          <button
            className={`vote-arrow vote-up ${post.user_has_voted ? 'active' : ''}`}
            onClick={handleVoteClick}
            disabled={post.status !== 'active'}
            aria-label="Vote"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 4l-8 8h5v8h6v-8h5z" />
            </svg>
          </button>
          <span className="vote-score">{post.vote_count || 0}</span>
        </div>
      )}
      <div className="post-card-main">
        <div className="post-card-badges">
          {post.is_pinned && <span className="badge badge--pinned">Pinned</span>}
          {post.status && post.status !== 'active' && (
            <span className={`badge badge--${post.status.replace('_', '-')}`}>
              {getStatusLabel(post.status)}
            </span>
          )}
        </div>
        <h3 className="post-card-title">{post.title}</h3>
        {preview && <p className="post-card-preview">{preview}</p>}
        <div className="post-card-meta">
          <span className="post-author">
            by {post.author_email?.split('@')[0] || 'Anonymous'}
            {post.author_tenant_name && (
              <span className="post-tenant"> ({post.author_tenant_name})</span>
            )}
          </span>
          <span className="meta-separator">·</span>
          <span>{formatDistanceToNow(post.created_at)}</span>
          <span className="meta-separator">·</span>
          <span className="post-comment-count">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            {post.comment_count || 0}
          </span>
        </div>
      </div>
    </Link>
  );
}

export default function ForumDetail() {
  const { forumSlug, categorySlug } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [postStatus, setPostStatus] = useState('active');
  const [posts, setPosts] = useState([]);
  const [postsLoading, setPostsLoading] = useState(false);

  const fetchForum = useCallback(async () => {
    return api.getForum(forumSlug);
  }, [forumSlug]);

  const { data: forum, loading, error } = useFetchData(fetchForum);

  // Determine the active category
  const activeCategory = forum?.categories?.find(c => c.slug === categorySlug) || forum?.categories?.[0];

  // Fetch posts when category or status changes
  useEffect(() => {
    if (!activeCategory) return;

    const fetchPosts = async () => {
      setPostsLoading(true);
      try {
        const data = await api.getForumPosts(forumSlug, activeCategory.slug, { status: postStatus });
        setPosts(data);
      } catch (err) {
        console.error('Failed to fetch posts:', err);
        setPosts([]);
      } finally {
        setPostsLoading(false);
      }
    };

    fetchPosts();
  }, [forumSlug, activeCategory?.slug, postStatus]);

  // Handle voting (toggle upvote)
  const handleVote = async (postId) => {
    try {
      const result = await api.togglePostVote(forumSlug, activeCategory.slug, postId);
      setPosts(prev => prev.map(p =>
        p.id === postId
          ? { ...p, user_has_voted: result.user_has_voted, vote_count: result.vote_count }
          : p
      ));
    } catch (err) {
      console.error('Failed to vote:', err);
    }
  };

  if (loading) {
    return <LoadingState message="Loading forum..." />;
  }

  if (error) {
    return <ErrorState message={error.message} />;
  }

  if (!forum) {
    return <ErrorState message="Forum not found" />;
  }

  // Navigate to the first category if none selected
  if (!categorySlug && forum.categories?.length > 0) {
    navigate(`/forums/${forumSlug}/${forum.categories[0].slug}`, { replace: true });
    return null;
  }

  return (
    <div className="forum-detail-page">
      <div className="forum-detail-header">
        <div className="forum-breadcrumb">
          <Link to="/forums">Forums</Link>
          <span>/</span>
          <span>{forum.name}</span>
        </div>
        <h1>{forum.name}</h1>
        {forum.description && (
          <p className="forum-detail-description">{forum.description}</p>
        )}
      </div>

      {/* Category Tabs */}
      <div className="category-tabs">
        {forum.categories?.map((category) => (
          <Link
            key={category.id}
            to={`/forums/${forumSlug}/${category.slug}`}
            className={`category-tab ${activeCategory?.id === category.id ? 'active' : ''}`}
          >
            {category.name}
            <span className="category-tab-count">{category.post_count}</span>
          </Link>
        ))}
      </div>

      {/* Posts Section */}
      {activeCategory && (
        <>
          <div className="posts-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <h2>{activeCategory.name}</h2>
              <div className="posts-status-filter">
                <button
                  className={`posts-status-btn ${postStatus === 'active' ? 'active' : ''}`}
                  onClick={() => setPostStatus('active')}
                >
                  Active
                </button>
                <button
                  className={`posts-status-btn ${postStatus !== 'active' ? 'active' : ''}`}
                  onClick={() => setPostStatus('archived,implemented,resolved')}
                >
                  Archive
                </button>
              </div>
            </div>
            {(!activeCategory.admin_only_posting || user?.is_global_admin) && (
              <Link to={`/forums/${forumSlug}/${activeCategory.slug}/new`} className="new-post-btn">
                <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
                </svg>
                New Post
              </Link>
            )}
          </div>

          {postsLoading ? (
            <LoadingState message="Loading posts..." />
          ) : posts.length === 0 ? (
            <EmptyState
              title={postStatus === 'active' ? 'No posts yet' : 'No archived posts'}
              message={postStatus === 'active'
                ? 'Be the first to start a discussion in this category.'
                : 'No posts have been archived yet.'
              }
            />
          ) : (
            <div className="posts-list">
              {posts.map((post) => (
                <PostCard
                  key={post.id}
                  post={post}
                  forumSlug={forumSlug}
                  categorySlug={activeCategory.slug}
                  allowsVoting={activeCategory.allows_voting}
                  onVote={handleVote}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
