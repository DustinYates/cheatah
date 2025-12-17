import './ui.css';

/**
 * Standardized error state component
 * @param {string} message - Error message to display
 * @param {function} onRetry - Optional retry callback
 * @param {string} title - Optional error title
 */
export default function ErrorState({ 
  message = "Something went wrong", 
  onRetry,
  title = "Error"
}) {
  return (
    <div className="error-state">
      <div className="error-state__icon">⚠️</div>
      <h3 className="error-state__title">{title}</h3>
      <p className="error-state__message">{message}</p>
      {onRetry && (
        <button className="btn-secondary" onClick={onRetry}>
          Try Again
        </button>
      )}
    </div>
  );
}
