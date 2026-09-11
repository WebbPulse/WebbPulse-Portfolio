/** The holding page shown when the site is switched off. */
export function UnderConstruction() {
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center px-6 text-center">
      <div className="max-w-md w-full space-y-8">
        <div className="space-y-3">
          <p className="text-gray-500 text-sm font-mono tracking-widest uppercase">
            webbpulse.com
          </p>
          <h1 className="text-4xl font-bold text-white">Under Construction</h1>
          <p className="text-gray-400 text-lg leading-relaxed">
            The site is getting a refresh. Check back soon.
          </p>
        </div>

        <div className="border-t border-gray-800 pt-8">
          <p className="text-gray-600 text-sm">
            In the meantime, reach out at{' '}
            <a
              href="mailto:tyler@webbpulse.com"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              tyler@webbpulse.com
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
