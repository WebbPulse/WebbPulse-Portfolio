/** Sets html[data-theme] before first paint from the saved choice or the OS preference. */
(function () {
  var theme = null;
  try {
    var saved = window.localStorage.getItem('cp-theme');
    if (saved === 'light' || saved === 'dark') theme = saved;
  } catch (e) {
    theme = null;
  }
  if (!theme) {
    try {
      theme =
        window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light';
    } catch (e) {
      theme = 'light';
    }
  }
  document.documentElement.setAttribute('data-theme', theme);
})();
