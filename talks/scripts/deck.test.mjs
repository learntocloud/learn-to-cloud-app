import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { createStaticServer } from './serve.mjs';

let browser;
let server;
let origin;
let talkUrl;
const basePath = '/learn-to-cloud-app/talks/';

before(async () => {
  process.env.TMPDIR = fileURLToPath(new URL('../.browser-tmp/', import.meta.url));
  await mkdir(process.env.TMPDIR, { recursive: true });
  server = await createStaticServer({ basePath });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  origin = `http://127.0.0.1:${server.address().port}`;
  talkUrl = `${origin}${basePath}building-a-ladder/`;
  browser = await chromium.launch();
});

after(async () => {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
});

async function openDeck(t, { viewport = { width: 1280, height: 720 }, query = '' } = {}) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript(() => {
    window.__talkTestEvents = { ready: false, pdfReady: false };
    document.addEventListener('ready', () => { window.__talkTestEvents.ready = true; }, true);
    document.addEventListener('pdf-ready', () => { window.__talkTestEvents.pdfReady = true; }, true);
  });
  const failures = [];
  context.on('page', (page) => {
    page.on('pageerror', (error) => failures.push(error.message));
    page.on('console', (message) => {
      if (message.type() === 'error') failures.push(message.text());
    });
  });
  context.on('response', (response) => {
    if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
  });
  context.on('requestfailed', (request) => {
    failures.push(`${request.failure()?.errorText} ${request.url()}`);
  });
  t.after(async () => {
    // Closing the notes previews aborts their requests; only check failures before teardown.
    const observed = [...failures];
    await context.close();
    assert.deepEqual(observed, [], 'Browser errors or failed asset requests');
  });
  const page = await context.newPage();
  await page.goto(`${talkUrl}${query}`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__talkTestEvents.ready && window.Reveal?.isReady());
  await page.evaluate(() => document.fonts.ready);
  return page;
}

test('initializes locally at the GitHub Pages project path, with speaker notes on every slide', async (t) => {
  const page = await openDeck(t);
  const deck = await page.evaluate(() => ({
    width: Reveal.getConfig().width,
    height: Reveal.getConfig().height,
    notesPlugin: Reveal.hasPlugin('notes'),
    slides: Reveal.getSlides().map((slide) => ({
      id: slide.id,
      notes: slide.querySelector('aside.notes')?.textContent.trim() ?? slide.dataset.notes?.trim(),
    })),
    assets: [...document.querySelectorAll('script[src], link[rel="stylesheet"]')]
      .map((element) => element.src || element.href),
  }));
  assert.equal(deck.width, 1280);
  assert.equal(deck.height, 720);
  assert.equal(deck.notesPlugin, true);
  assert.ok(deck.slides.length > 1);
  for (const [index, slide] of deck.slides.entries()) {
    assert.ok(slide.notes, `Missing speaker notes on slide ${index + 1} (${slide.id})`);
  }
  for (const asset of deck.assets) assert.ok(asset.startsWith(talkUrl), `Nonlocal asset: ${asset}`);
});

test('supports keyboard navigation and reloadable hash links', async (t) => {
  const page = await openDeck(t);
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => Reveal.getIndices().h === 1);
  await page.waitForFunction(() => location.hash.length > 2);
  const hash = new URL(page.url()).hash;
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.Reveal?.isReady() && Reveal.getIndices().h === 1);
  assert.equal(new URL(page.url()).hash, hash);
  await page.keyboard.press('ArrowLeft');
  await page.waitForFunction(() => Reveal.getIndices().h === 0);
});

test('keeps the original title in a minimal blue deck of short slides', async (t) => {
  const page = await openDeck(t);
  const presentation = await page.evaluate(() => ({
    title: document.querySelector('h1').innerText.replace(/\s+/g, ' ').trim(),
    accent: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),
    slides: Reveal.getSlides().map((slide) => {
      const content = slide.cloneNode(true);
      content.querySelectorAll('aside.notes, footer').forEach((element) => element.remove());
      // Verbatim artifacts (code, commands, quoted incident text) are the point of
      // these slides, so the budget only covers the prose written around them.
      content
        .querySelectorAll('pre, code, blockquote, table, figcaption, .code-label')
        .forEach((element) => element.remove());
      content.querySelectorAll('br').forEach((element) => element.replaceWith(' '));
      return { id: slide.id, words: content.textContent.trim().split(/\s+/).filter(Boolean).length };
    }),
  }));
  assert.equal(presentation.title, 'How GitHub Helps Us Reach 6,000 Learners');
  assert.equal(presentation.accent, '#83bcff');
  assert.equal(presentation.slides.length, 23);
  for (const slide of presentation.slides) {
    assert.ok(slide.words <= 40, `${slide.id} has ${slide.words} words; move detail into notes`);
  }
});

test('grounds the technical slides in verbatim artifacts', async (t) => {
  const page = await openDeck(t);
  const artifacts = await page.evaluate(() =>
    Reveal.getSlides()
      .filter((slide) => slide.querySelector('pre.code, table.checks, .ticket'))
      .map((slide) => slide.id),
  );
  for (const id of [
    'github-oauth',
    'first-real-workflow',
    'first-checkpoint',
    'real-infrastructure',
    'investigate-it',
    'done-when',
    'token-binding',
    'feedback-that-fits',
    'same-bytes',
    'dont-fix-the-assignment',
    'working-isnt-usable',
  ]) {
    assert.ok(artifacts.includes(id), `${id} should show real code, commands, or quoted text`);
  }
});

test('Reveal viewport uses the dark background required by the slide text', async (t) => {
  const page = await openDeck(t);
  const background = await page.evaluate(() =>
    getComputedStyle(document.querySelector('.reveal-viewport')).backgroundColor);
  assert.equal(background, 'rgb(16, 25, 28)', 'Reveal must not override the dark theme with its default white background');
});

test('all images load', async (t) => {
  const page = await openDeck(t);
  const images = await page.evaluate(async () => {
    const pictures = [...document.images];
    await Promise.all(pictures.map((image) => image.decode()));
    return { count: pictures.length, broken: pictures.filter((image) => !image.naturalWidth).length };
  });
  assert.ok(images.count > 0, 'The presentation should include its visual assets');
  assert.equal(images.broken, 0);
});

test('visible slide content fits the canvas and stays above its footer', async (t) => {
  const page = await openDeck(t);
  await page.evaluate(() => Reveal.configure({ transition: 'none' }));
  const slides = await page.evaluate(() => Reveal.getSlides().map((slide) => Reveal.getIndices(slide)));
  for (const indices of slides) {
    await page.evaluate(({ h, v }) => Reveal.slide(h, v, Infinity), indices);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const overflow = await page.evaluate(() => {
      const slide = Reveal.getCurrentSlide();
      const footerSelector = 'footer, .deck-footer, .slide-footer, [data-deck-footer]';
      const footer = slide.querySelector(footerSelector);
      if (!footer) return ['Slide is missing its footer'];
      const footerTop = footer.getBoundingClientRect().top;
      const canvas = document.querySelector('.reveal .slides').getBoundingClientRect();
      const scale = Reveal.getScale();
      const bounds = {
        left: canvas.left - 2,
        top: canvas.top - 2,
        right: canvas.left + 1280 * scale + 2,
        bottom: canvas.top + 720 * scale + 2,
      };
      const overflow = [];
      const elements = new Set([
        ...slide.querySelectorAll('*'),
        ...document.querySelectorAll(footerSelector),
      ]);
      for (const element of elements) {
        if (element.closest('aside.notes') || ['SCRIPT', 'STYLE'].includes(element.tagName)) continue;
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        const rectangles = [element.getBoundingClientRect()];
        for (const child of element.childNodes) {
          if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
            const range = document.createRange();
            range.selectNodeContents(child);
            rectangles.push(...range.getClientRects());
          }
        }
        if (rectangles.some((rect) => rect.width && rect.height &&
          (rect.left < bounds.left || rect.top < bounds.top || rect.right > bounds.right || rect.bottom > bounds.bottom))) {
          overflow.push(`${element.tagName}.${element.className}: ${element.textContent.trim().slice(0, 70)}`);
        }
        if (!element.closest(footerSelector) &&
          rectangles.some((rect) => rect.width && rect.height && rect.bottom > footerTop + 1)) {
          overflow.push(`Overlaps footer: ${element.tagName}.${element.className}: ${element.textContent.trim().slice(0, 70)}`);
        }
      }
      return overflow;
    });
    assert.deepEqual(overflow, [], `Overflow at slide ${indices.h}/${indices.v}`);
  }
});

test('speaker popup connects and synchronizes navigation', async (t) => {
  const page = await openDeck(t);
  const popupPromise = page.waitForEvent('popup');
  await page.keyboard.press('s');
  const popup = await popupPromise;
  await popup.waitForSelector('#current-slide iframe');
  await popup.waitForFunction(() => document.querySelector('#connection-status')?.style.display === 'none');
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => Reveal.getIndices().h === 1);
  await popup.waitForFunction(() => {
    const frame = document.querySelector('#current-slide iframe');
    return frame?.contentWindow.__talkTestEvents?.ready &&
      frame.contentWindow.Reveal?.isReady() && frame.contentWindow.Reveal.getIndices().h === 1;
  });
});

test('narrow viewport keeps the presentation usable', async (t) => {
  const page = await openDeck(t, { viewport: { width: 390, height: 844 } });
  assert.equal(await page.locator('.slides section').first().isVisible(), true);
  // Reveal may use its mobile scroll view; both modes must remain navigable.
  if (await page.evaluate(() => Reveal.isScrollView())) {
    await page.evaluate(() => Reveal.next());
  } else {
    await page.locator('.reveal .controls .navigate-right').click();
  }
  await page.waitForFunction(() => Reveal.getIndices().h === 1);
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
    slide: Reveal.getCurrentSlide().getBoundingClientRect().toJSON(),
  }));
  assert.ok(dimensions.width <= dimensions.viewport + 1, 'Page should not scroll horizontally');
  assert.ok(dimensions.slide.left >= -1 && dimensions.slide.right <= dimensions.viewport + 1);
});

test('print mode creates one page per slide with loaded images', async (t) => {
  const page = await openDeck(t, { query: '?print-pdf' });
  await page.waitForFunction(() => window.__talkTestEvents.pdfReady);
  const slideCount = await page.evaluate(() => Reveal.getSlides().length);
  assert.equal(await page.locator('.pdf-page').count(), slideCount);
  await page.evaluate(() => Promise.all([...document.images].map((image) => image.decode())));
  await page.emulateMedia({ media: 'print' });
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  assert.ok(pdf.length > 1000, 'Print output should contain the presentation');
});

test('server handles missing files, malformed paths, methods, and MIME types', async () => {
  for (const [pathname, status] of [
    [`${basePath}missing.js`, 404],
    ['/package.json', 404],
    [`${basePath}%ZZ`, 400],
    [`${basePath}%00`, 400],
    [`${basePath}..%2fpackage.json`, 400],
  ]) {
    const response = await fetch(`${origin}${pathname}`);
    assert.equal(response.status, status, pathname);
  }
  assert.equal((await fetch(talkUrl, { method: 'POST' })).status, 405);
  const head = await fetch(talkUrl, { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.match(head.headers.get('content-type'), /^text\/html/);
  assert.equal(await head.text(), '');
  const script = await fetch(`${talkUrl}vendor/reveal/notes.js`);
  assert.match(script.headers.get('content-type'), /^text\/javascript/);
  const redirect = await fetch(talkUrl.slice(0, -1), { redirect: 'manual' });
  assert.equal(redirect.status, 301);
});

test('server snapshots assets and refuses symlinks instead of following changed files', async () => {
  const fixture = await mkdtemp(fileURLToPath(new URL('../dist/snapshot-', import.meta.url)));
  const outside = await mkdtemp(fileURLToPath(new URL('../.browser-tmp/outside-', import.meta.url)));
  const asset = path.join(fixture, 'asset.txt');
  let snapshotServer;
  try {
    await writeFile(asset, 'public asset');
    const privateFile = path.join(outside, 'private.txt');
    await writeFile(privateFile, 'must not be served');
    snapshotServer = await createStaticServer();
    await new Promise((resolve, reject) => {
      snapshotServer.once('error', reject);
      snapshotServer.listen(0, '127.0.0.1', resolve);
    });
    await rm(asset);
    await symlink(privateFile, asset);
    const url = `http://127.0.0.1:${snapshotServer.address().port}/${path.basename(fixture)}/asset.txt`;
    const response = await fetch(url);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'public asset');
    await assert.rejects(createStaticServer(), /Unsupported asset type/);
  } finally {
    if (snapshotServer?.listening) await new Promise((resolve) => snapshotServer.close(resolve));
    await rm(fixture, { recursive: true, force: true });
    await rm(outside, { recursive: true, force: true });
  }
});
