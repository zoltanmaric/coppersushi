import React, {useEffect} from 'react';

/** Retain one tick per returned interval, including both occurrences of a DST hour. */
export function timelineTicks(labels: string[]) {
  return labels.map((label, index) => {
    const time = label.match(/(\d{2}):(\d{2}) (\S+)$/);
    if (!time) throw new Error(`Invalid market interval label: ${label}`);
    const major = Number(time[1]) % 2 === 0 && time[2] === '00';
    return {index, position: labels.length > 1 ? 100 * index / (labels.length - 1) : 0,
      label, time: major ? `${time[1]}:${time[2]}` : null, zone: time[3]};
  });
}

interface Props {labels: string[]; interval: number; disabled: boolean; onChange: (interval: number) => void;
  onScrubbingChange: (scrubbing: boolean) => void}
const navigationKeys = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown']);

export function Timeline({labels, interval, disabled, onChange, onScrubbingChange}: Props) {
  useEffect(() => {
    const finish = () => onScrubbingChange(false);
    const keyUp = (event: KeyboardEvent) => {if (navigationKeys.has(event.key)) finish();};
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
    window.addEventListener('keyup', keyUp);
    window.addEventListener('blur', finish);
    return () => {
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      window.removeEventListener('keyup', keyUp);
      window.removeEventListener('blur', finish);
    };
  }, [onScrubbingChange]);
  return <div className="cnec-timeline-scroll"><div className="cnec-timeline">
    <input aria-label="Market interval" aria-valuetext={labels[interval]} type="range" min={0}
      max={Math.max(0, labels.length - 1)} step={1} value={interval} disabled={disabled}
      onPointerDown={() => onScrubbingChange(true)} onBlur={() => onScrubbingChange(false)}
      onKeyDown={event => {if (navigationKeys.has(event.key)) onScrubbingChange(event.repeat);}}
      onChange={e => onChange(Number(e.target.value))}/>
    <div className="cnec-timeline-marks" aria-hidden="true">
      {timelineTicks(labels).map(tick => <span key={tick.index} title={tick.label}
        data-hour={tick.time?.slice(0, 2)}
        className={`cnec-tick${tick.time ? ' cnec-tick-major' : ''}${tick.index === 0 ? ' cnec-tick-first' : ''}`}
        style={{left: `${tick.position}%`}}>
        {tick.time && <span className="cnec-tick-label">{tick.time}<small>{tick.zone}</small></span>}
      </span>)}
    </div>
  </div></div>;
}
