import './ui.css';

/**
 * Standardized empty state component
 * @param {string} icon - Emoji or icon to display
 * @param {string} title - Main heading
 * @param {string} description - Supporting text
 * @param {object} action - Optional CTA { label: string, onClick: function }
 */
export default function EmptyState({ 
  icon = "📭", 
  title = "Nothing here yet",
  description,
  action
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <h3 className="empty-state__title">{title}</h3>
      {description && <p className="empty-state__description">{description}</p>}
      {action && (
        <button className="btn-primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
