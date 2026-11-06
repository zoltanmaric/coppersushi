import {useQueries, useQuery} from '@tanstack/react-query';
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

/** Selection and prefetch subscribe to the same interval query keys. */
export function useDayData(day: string, interval: number, firstInterval: number) {
  const publication = useQuery({
    queryKey:['publication',day], queryFn:({signal})=>fetchManifest(day,signal),
    // Only absent publications poll; immutable day parts keep their existing cache policy.
    refetchInterval: query => query.state.data === null ? 60_000 : false,
    refetchOnWindowFocus: query => query.state.data === null,
    refetchOnReconnect: query => query.state.data === null,
    refetchOnMount: query => query.state.data === null,
  });
  const generation = publication.data?.generation ?? '';
  const metadata = useQuery({queryKey:['metadata',day,generation],enabled:!!generation,
    queryFn:({signal})=>fetchDayPart('metadata',day,generation,0,signal)});
  const labels = metadata.data?.labels ?? [];
  const inRange = (i:number)=>i>=0 && i<labels.length;
  const first = useQuery({...intervalOptions(day,generation,firstInterval),enabled:!!generation && (!metadata.data || inRange(firstInterval))});
  const current = useQuery({...intervalOptions(day,generation,interval),enabled:metadata.isSuccess && inRange(interval) && first.isSuccess,
    placeholderData:(previous,previousQuery)=>previousQuery?.queryKey[1]===day && previousQuery.queryKey[2]===generation ? previous : undefined});
  return {publication,metadata,first,current,labels,generation};
}
