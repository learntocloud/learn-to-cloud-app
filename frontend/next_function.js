const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");

const port = parseInt(process.env.FUNCTIONS_CUSTOMHANDLER_PORT || "3000", 10);
const hostname = process.env.WEBSITE_HOSTNAME
// when using middleware `hostname` and `port` must be provided below
const app = next({ dev: false, hostname, port });
const handle = app.getRequestHandler();
const serverOptions = {
  maxHeaderSize: 81920
};

app.prepare().then(() => {
  const server = createServer(serverOptions, async (req, res) => {
    try {
      const userAgent = req.headers['user-agent'];
      if (userAgent && userAgent.includes("BlueRidgeAlwaysOn")) {
        return res.end();
      }

      let parsedUrl = parse(req.url, true);
      const msOriginalUrl = req.headers["x-ms-original-url"];
      if (msOriginalUrl) { // always use msOriginalUrl if it is defined, as the req.url can have trimmed paths from MSHA etc.
        parsedUrl = parse(msOriginalUrl, true);
        req.url = parsedUrl.pathname + (parsedUrl.search || "");
      }
      console.log("serving start: " + req.url);
      res.setHeader("x-ms-nextjs-render", "server");
      await handle(req, res, parsedUrl);
      console.log("serving end: " + req.url + " with status: " + res.statusCode);
    } catch (err) {
        console.error('Error occurred handling', req.url, err);
        res.statusCode = 500;
        res.end('internal server error');
    }
  });

  server.listen(port, (err) => {
    if (err) {
      console.error("Failed to start server", err)
      process.exit(1)
    }
    console.log(`> Ready on http://${hostname}:${port}`)
  })
});
