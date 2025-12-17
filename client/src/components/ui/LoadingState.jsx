import './ui.css';

/**
 * Standardized loading state component
 * @param {string} message - Loading message to display
 * @param {boolean} fullPage - If true, centers in full page height
 */
export default function LoadingState({ message = "Loading...", fullPage = false }) {
  return (
    <div className={`loading-state ${fullPage ? 'loading-state--full' : ''}`}>
      <div className="loading-spinner"></div>
      <p>{message}</p>
    </div>
  );
}
