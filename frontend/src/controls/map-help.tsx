import React, {useId} from 'react';
import {autoUpdate, offset, size, useFloating} from '@floating-ui/react-dom';

export function MapHelp({page='cnec'}:{page?:'cnec'|'powerflow'}) {
  const popoverId = useId();
  const headingId = useId();
  const {refs, floatingStyles} = useFloating({
    placement: 'bottom-end', strategy: 'fixed', whileElementsMounted: autoUpdate,
    middleware: [offset(({rects}) => -rects.reference.height), size({padding: 12,
      apply: ({availableHeight, elements}) => {
        elements.floating.style.maxHeight = `${Math.max(0, availableHeight)}px`;
      },
    })],
  });
  return <>
    <button ref={refs.setReference} type="button" {...{popovertarget: popoverId}}
      className="cnec-help-trigger" aria-label="What am I looking at?" aria-haspopup="dialog" aria-controls={popoverId}>
      <span aria-hidden="true">?</span>
    </button>
    {/* Floating UI supplies runtime coordinates; visual styling stays in CSS. */}
    <div ref={refs.setFloating} {...{popover: 'auto'}} id={popoverId}
      style={floatingStyles} className="cnec-help" role="dialog" aria-labelledby={headingId}>
      <button type="button" {...{popovertarget: popoverId, popovertargetaction: 'hide'}}
        className="cnec-help-close" aria-label="Close map help"
        ref={node => {if (node) node.autofocus = true;}}><span aria-hidden="true">?</span></button>
      <h2 id={headingId}>What am I looking at?</h2>
      <div className="cnec-help-copy">
        {page === 'powerflow' ? <>
        <p>This map shows a modelled optimal power flow for 29 August 2024, using the European network model.</p>
        <p>Node colours show net power feed-in: generation minus demand. Larger nodes have larger absolute net power.</p>
        <p>Purple branches are loaded above 99% of their modelled capacity. Arrows show the direction of power flow; hover for values.</p>
        <p>Use the hourly controls to explore the fixed study day. These are model results, not live measurements.</p>
        </> : <>
        <p>Country colours show day-ahead electricity prices for the selected time.</p>
        <p>Purple highlights mark grid constraints that limit access to cheaper power.</p>
        <p>Click a highlighted element to see how much it contributes to price differences between countries and your selected reference country.</p>
        <p>Click a country’s name on the map to compare prices against that country.</p>
        <a href="https://121gigawatts.org/critical-elements/" target="_blank" rel="noopener noreferrer">Read the full post: Critical Elements ⚡️</a>
        </>}
      </div>
    </div>
  </>;
}
