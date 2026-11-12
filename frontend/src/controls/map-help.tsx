import React, {useId} from 'react';
import * as Popover from '@radix-ui/react-popover';
import {QuestionMarkIcon} from '@radix-ui/react-icons';

export function MapHelp() {
  const headingId = useId();
  return <Popover.Root>
    <Popover.Trigger className="cnec-help-trigger" aria-label="What am I looking at?">
      <QuestionMarkIcon width={24} height={24} aria-hidden="true"/>
    </Popover.Trigger>
    <Popover.Content className="cnec-help" side="bottom" align="end" sideOffset={-44}
      avoidCollisions={false} collisionPadding={12} aria-labelledby={headingId}>
      <h2 id={headingId}>What am I looking at?</h2>
      <div className="cnec-help-copy">
        <p>Country colours show day-ahead electricity prices for the selected time.</p>
        <p>Purple highlights mark grid constraints that limit access to cheaper power.</p>
        <p>Click a highlighted element to see how much it contributes to price differences between countries and your selected reference country.</p>
        <a href="https://121gigawatts.org/critical-elements/" target="_blank" rel="noopener noreferrer">Read the full post: Critical Elements ⚡️</a>
      </div>
    </Popover.Content>
  </Popover.Root>;
}
