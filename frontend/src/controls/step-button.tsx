import React from 'react';
export function StepButton({direction, ...props}: React.ComponentProps<'button'> & {direction: 'previous' | 'next'}) {
  return <button {...props}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d={direction === 'previous' ? 'm14 6-6 6 6 6' : 'm10 6 6 6-6 6'}
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg></button>;
}

