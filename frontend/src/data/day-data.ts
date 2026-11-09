import {useEffect, useRef} from 'react';
import type {MarketInterval} from './contracts';
import {queryOptions, useQueries, useQuery} from '@tanstack/react-query';
import {fetchDayPart, fetchManifest} from './api';

const intervalOptions = (day:string,generation:string,index:number) => ({
  queryKey:['interval',day,generation,index],
  queryFn:({signal}:{signal:AbortSignal})=>fetchDayPart('interval',day,generation,index,signal),
});

/** Native observers keep prefetch alive when selection leaves an interval. */
export function IntervalPrefetch({day,generation,count,enabled}:{day:string;generation:string;count:number;enabled:boolean}) {
  useQueries({queries:Array.from({length:count},(_,index)=>({
    ...intervalOptions(day,generation,index),enabled,notifyOnChangeProps:[] as const,
  }))});
  return null;
}

/** Share availability checks with selection without downloading day parts. */
export function publicationOptions(day: string) {
  return queryOptions({
    queryKey:['publication',day], queryFn:({signal})=>fetchManifest(day,signal),
    // Unavailable publications poll; immutable day parts keep their existing cache policy.
    refetchInterval: query => query.state.data == null ? 60_000 : false,
    refetchOnWindowFocus: query => query.state.data == null,
    refetchOnReconnect: query => query.state.data == null,
    refetchOnMount: query => query.state.data == null,
  });
}

/** Selection and prefetch subscribe to the same interval query keys. */
export function useDayData(day: string, interval: number) {
  const publication = useQuery(publicationOptions(day));
  const generation = publication.data?.generation ?? '';
  const metadata = useQuery({queryKey:['metadata',day,generation],enabled:!!generation,
    queryFn:({signal})=>fetchDayPart('metadata',day,generation,0,signal)});
  const labels = metadata.data?.labels ?? [];
  const inRange = (i:number)=>i>=0 && i<labels.length;
  const current = useQuery({...intervalOptions(day,generation,interval),enabled:!!generation && (!metadata.data || inRange(interval)),
    placeholderData:(previous,previousQuery)=>previousQuery?.queryKey[1]===day && previousQuery.queryKey[2]===generation ? previous : undefined});
  // Query placeholderData disappears on error; retain the last displayed interval
  // for this generation so a failed navigation does not blank the map.
  const settled = useRef<{day:string;generation:string;data:MarketInterval} | null>(null);
  useEffect(() => {
    if (current.data && !current.isPlaceholderData) settled.current = {day,generation,data:current.data};
  }, [day,generation,current.data,current.isPlaceholderData]);
  const data = current.data ?? (settled.current?.day === day && settled.current.generation === generation ? settled.current.data : undefined);
  return {publication,metadata,current,data,labels,generation};
}
