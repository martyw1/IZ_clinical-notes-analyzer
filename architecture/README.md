# Offline application architecture

Double-click **index.html** to open the guide in a browser. No server, install, account, or internet connection is required. Keep this folder inside the repository for its relative source links to work. Browsers may display or download linked source files depending on file type.

The guide covers active V2 screens and account gates, unrouted page components, frontend composition, API operations and classifications, services, local data relationships, deterministic evaluation, access/privacy boundaries, workflows, and Windows hosting. It is architecture documentation, not a working clinical app or a production qualification report.

The HTML, CSS, and JavaScript are self-contained. Regenerate the HTML and source inventories from the repository root with `node architecture/build.cjs`. Explanatory descriptions are reviewed prose in the generator; update them alongside behavior changes. The generator reads source only and never initializes the backend, database, configuration, or vendor connections.

Source snapshot: October 17, 2026; app 1.0.2 / build 2026.10.16.1.
