import {useEffect, useState} from 'react';

/** Market calendar day in Brussels, independent of the visitor's timezone. */
export function marketDay(now: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Brussels',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
  return ['year','month','day'].map(type => parts.find(part => part.type === type)!.value).join('-');
}

/** Keep an open page's date limits current across market midnight. */
export function useMarketToday(): string {
  const [today, setToday] = useState(() => marketDay(new Date()));
  useEffect(() => {
    const update = () => setToday(marketDay(new Date()));
    const timer = window.setInterval(update, 60_000);
    window.addEventListener('focus', update);
    return () => {window.clearInterval(timer); window.removeEventListener('focus', update);};
  }, []);
  return today;
}
