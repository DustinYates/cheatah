import { useState, useCallback, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, ErrorState, EmojiPicker } from '../components/ui';
import './Forums.css';

export default function NewForumPost() {
  const { forumSlug, categorySlug } = useParams();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const contentTextareaRef = useRef(null);

  const fetchForum = useCallback(async () => {
    return api.getForum(forumSlug);
  }, [forumSlug]);

  const { data: forum, loading, error: forumError } = useFetchData(fetchForum);

  const category = forum?.categories?.find(c => c.slug === categorySlug);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError('Title is required');
      return;
    }

    if (!content.trim()) {
      setError('Content is required');
      return;
    }

    setIsSubmitting(true);
    try {
      const newPost = await api.createForumPost(forumSlug, categorySlug, {
        title: title.trim(),
        content: content.trim(),
      });
      navigate(`/forums/${forumSlug}/${categorySlug}/${newPost.id}`);
    } catch (err) {
      setError(err.message || 'Failed to create post');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEmojiSelect = (emoji) => {
    const textarea = contentTextareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const updated = content.substring(0, start) + emoji + content.substring(end);
      setContent(updated);
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
        textarea.focus();
      }, 0);
    } else {
      setContent(content + emoji);
    }
  };

  if (loading) {
    return <LoadingState message="Loading..." />;
  }

  if (forumError) {
    return <ErrorState message={forumError.message} />;
  }

  if (!forum || !category) {
    return <ErrorState message="Category not found" />;
  }

  return (
    <div className="new-post-page">
      <div className="forum-breadcrumb">
        <Link to="/forums">Forums</Link>
        <span>/</span>
        <Link to={`/forums/${forumSlug}`}>{forum.name}</Link>
        <span>/</span>
        <Link to={`/forums/${forumSlug}/${categorySlug}`}>{category.name}</Link>
        <span>/</span>
        <span>New Post</span>
      </div>

      <div className="forum-detail-header">
        <h1>New Post in {category.name}</h1>
        {category.description && (
          <p className="forum-detail-description">{category.description}</p>
        )}
      </div>

      <form className="new-post-form" onSubmit={handleSubmit}>
        {error && (
          <div style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            padding: '12px',
            marginBottom: '16px',
            color: '#dc2626',
            fontSize: '14px'
          }}>
            {error}
          </div>
        )}

        <div className="form-group">
          <label htmlFor="title">Title</label>
          <input
            type="text"
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Enter a descriptive title..."
            maxLength={500}
            disabled={isSubmitting}
          />
        </div>

        <div className="form-group">
          <label htmlFor="content">Content</label>
          <div className="composer-wrapper">
            <textarea
              ref={contentTextareaRef}
              id="content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Describe your idea, question, or issue in detail..."
              disabled={isSubmitting}
            />
            <div className="composer-toolbar">
              <EmojiPicker onSelect={handleEmojiSelect} position="bottom" />
            </div>
          </div>
        </div>

        <div className="form-actions">
          <Link
            to={`/forums/${forumSlug}/${categorySlug}`}
            className="btn-secondary"
          >
            Cancel
          </Link>
          <button
            type="submit"
            className="btn-primary"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Creating...' : 'Create Post'}
          </button>
        </div>
      </form>
    </div>
  );
}
