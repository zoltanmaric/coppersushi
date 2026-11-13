import React from 'react';
import {useQuery} from '@tanstack/react-query';
import {publicationOptions} from './data/day-data';
import {useMarketToday} from '../../controls/market-day';
import {CalendarDateControls,stepDay} from '../../controls/date-time-controls';

export function DateControls(props:Omit<React.ComponentProps<typeof CalendarDateControls>,'today'|'maxDay'>) {
  const today = useMarketToday();
  const tomorrow = stepDay(today, 1);
  const publication = useQuery(publicationOptions(tomorrow));
  return <CalendarDateControls {...props} today={today} maxDay={publication.data ? tomorrow : today}/>;
}

