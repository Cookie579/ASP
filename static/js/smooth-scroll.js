window.addEventListener('DOMContentLoaded', function () {
  const path = window.location.pathname;

  // Only run Lenis if the route is NOT '/stock-viewer'
  if (path !== '/stock-viewer') {
    const lenis = new Lenis({
      smooth: true,
      lerp: 0.1,
      direction: 'vertical',
      smoothWheel: true,
    });

    function raf(time) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }

    requestAnimationFrame(raf);
  }
});