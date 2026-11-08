import React from 'react';

/** Place clock labels at their actual market intervals, including on DST days. */
export function timelineLabels(labels: string[]) {
  return labels.flatMap((label, index) => {
    const time = label.match(/(\d{2}):(\d{2}) (\S+)$/);
    if (!time) throw new Error(`Invalid market interval label: ${label}`);
    if (Number(time[1]) % 6 !== 0 || time[2] !== '00') {
      if (index !== labels.length - 1) return [];
    }
    return [{index, position: labels.length > 1 ? 100 * index / (labels.length - 1) : 0,
      time: `${time[1]}:${time[2]}`}];
  });
}

interface Props {labels: string[]; interval: number; disabled: boolean; onChange: (interval: number) => void}
export function Timeline({labels, interval, disabled, onChange}: Props) {
  const progress = labels.length > 1 ? 100 * interval / (labels.length - 1) : 0;
  return <div className="cnec-timeline" style={{'--cnec-time-progress': `${progress}%`} as React.CSSProperties}>
    <input aria-label="Market interval" aria-valuetext={labels[interval]} type="range" min={0}
      max={Math.max(0, labels.length - 1)} step={1} value={interval} disabled={disabled}
      onChange={e => onChange(Number(e.target.value))}/>
    <div className="cnec-timeline-labels" aria-hidden="true">
      {timelineLabels(labels).map(label => <span key={label.index} style={{left: `${label.position}%`}}>
        {label.time}
      </span>)}
    </div>
  </div>;
}
