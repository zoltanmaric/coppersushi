// The site identifier is public; local previews must not send production telemetry.
if (window.location.hostname === 'coppersushi.121gigawatts.org') {
  const beacon = document.createElement('script');
  beacon.type = 'module';
  beacon.src = 'https://static.cloudflareinsights.com/beacon.min.js';
  beacon.dataset.cfBeacon = JSON.stringify({token: 'e604c99bb7db4443b4da0bdf3adfd80f'});
  document.head.appendChild(beacon);
}
