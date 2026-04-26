import './LeadScoreBadge.css';

const BAND_LABEL = {
  hot: 'Hot',
  warm: 'Warm',
  cold: 'Cold',
};

export default function LeadScoreBadge({ score = 0, band = 'cold', breakdown }) {
  const safeBand = BAND_LABEL[band] ? band : 'cold';
  const title = breakdown
    ? Object.entries(breakdown)
        .map(([k, v]) => `${k}: ${v > 0 ? '+' : ''}${v}`)
        .join('\n')
    : `${BAND_LABEL[safeBand]} lead — score ${score}/100`;

  return (
    <span
      className={`lead-score-badge lead-score-badge--${safeBand}`}
      title={title}
      aria-label={`Lead score ${score} out of 100, ${BAND_LABEL[safeBand]}`}
    >
      {safeBand === 'hot' && <span className="lead-score-badge__icon" aria-hidden>🔥</span>}
      <span className="lead-score-badge__num">{score}</span>
    </span>
  );
}
