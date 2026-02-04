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

  return (
    <Link
      to={`/forums/${forumSlug}/${categorySlug}/${post.id}`}
      className="post-card"
    >
      {allowsVoting && (
        <div className="post-vote-section">
          <button
            className={`vote-btn ${post.user_has_voted ? 'voted' : ''}`}
            onClick={handleVoteClick}
            disabled={post.status !== 'active'}
          >
            <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clipRule="evenodd" />
            </svg>
            <span className="vote-count">{post.vote_count}</span>
            <span className="vote-label">votes</span>
          </button>
        </div>
      )}
      <div className="post-content">
        <h3 className="post-title">
          {post.is_pinned && <span className="post-pinned-badge">Pinned</span>}
          {post.status !== 'active' && (
            <span className={`post-status-badge ${post.status}`}>
              {post.status === 'implemented' ? 'Implemented' :
               post.status === 'resolved' ? 'Resolved' : 'Archived'}
            </span>
          )}
          {post.title}
        </h3>
        <div className="post-meta">
          <span className="post-author">
            by {post.author_email}
            {post.author_tenant_name && (
              <span className="post-tenant"> ({post.author_tenant_name})</span>
            )}
          </span>
          <span>{formatDistanceToNow(post.created_at)}</span>
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

  // Handle voting
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
