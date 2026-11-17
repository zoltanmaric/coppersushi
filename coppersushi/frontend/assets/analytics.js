// The site identifier is public; local previews must not send production telemetry.
if (window.location.hostname === 'coppersushi.121gigawatts.org') {
  const beacon = document.createElement('script');
  beacon.type = 'module';
  beacon.src = 'https://static.cloudflareinsights.com/beacon.min.js';
  beacon.dataset.cfBeacon = JSON.stringify({token: '4768db0a8e344b71b9e52fee17050402'});
  document.head.appendChild(beacon);
}
