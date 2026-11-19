import React, {useId, useRef, useState} from 'react';

type Range = {min?: number; max?: number};

export function FilterButton({id, label, active}: {id: string; label: string; active: boolean}) {
  return <button type="button" className="study-filter-button" {...{popovertarget: id}}
    aria-controls={id} aria-haspopup="dialog" aria-label={`Filter ${label}${active ? ' (active)' : ''}`}
    data-active={active} title={`Filter ${label}`}>
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 3h12L9.5 8v4l-3 1V8Z" stroke="currentColor" fill={active ? 'currentColor' : 'none'}/>
    </svg>
  </button>;
}

export function NumericFilter({label, column, range, onChange}: {
  label: string; column: string; range?: Range; onChange: (range?: Range) => void;
}) {
  const id = useId();
  const dialog = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);

  function apply(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const min = fields.get('min') ? Number(fields.get('min')) : undefined;
    const max = fields.get('max') ? Number(fields.get('max')) : undefined;
    if (min !== undefined && max !== undefined && min > max) {
      setError(true);
      return;
    }
    setError(false);
    dialog.current?.hidePopover?.();
    onChange(min === undefined && max === undefined ? undefined : {min, max});
  }

  return <>
    <FilterButton id={id} label={label} active={Boolean(range)}/>
    <div id={id} ref={dialog} {...{popover: 'auto'}} className="cnec-calendar study-calendar study-numeric-filter"
      role="dialog" aria-label={`Filter ${label}`}>
      <form key={JSON.stringify(range)} onSubmit={apply}>
        <strong>{label}</strong>
        <div className="study-filter-fields">
          {(['min', 'max'] as const).map(bound => <label key={bound}>
            {bound === 'min' ? 'Min' : 'Max'}
            <input type="number" step="any" name={bound} data-column={column}
              aria-label={`${label} ${bound === 'min' ? 'minimum' : 'maximum'}`} defaultValue={range?.[bound]}/>
          </label>)}
        </div>
        {error && <p role="alert">Minimum must be at most maximum.</p>}
        <div className="study-calendar-actions">
          <button type="button" onClick={() => {
            setError(false);
            dialog.current?.hidePopover?.();
            onChange();
          }}>Clear</button>
          <button type="submit">Apply</button>
        </div>
      </form>
    </div>
  </>;
}
