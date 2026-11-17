fetch('/data/cnec/v3/2099-01-01/manifest.json'); // Calendar availability may start first.
const scenario = new URL(location.href).searchParams.get('case');
if (scenario === 'exception') throw new Error('fixture application exception');
if (scenario === 'console') console.error('optional diagnostic');
if (scenario !== 'never' && scenario !== 'exception') {
  Promise.resolve(scenario === 'recovery' ? fetch('/retry-data') : undefined).then(()=>fetch('/data/cnec/v3/manifest.json')).then(response => {
    if (!response.ok) throw new Error('required data missing');
    return fetch('/data/cnec/v3/0.json').then(response=>{if(!response.ok) throw new Error('interval missing');return response.json();});
  }).then(() => {
    document.querySelector('section').dataset.loadState = 'ready';
    fetch('/data/cnec/v3/1.json'); // Optional prefetch after the required interval.
  }).catch(() => {document.querySelector('section').dataset.loadState = 'error';});
}
addEventListener('pagehide', () => navigator.sendBeacon('/cdn-cgi/rum', 'test'));
