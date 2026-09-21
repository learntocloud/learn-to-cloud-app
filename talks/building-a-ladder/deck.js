const slides = [...document.querySelectorAll(".slides > section")];

for (const [index, slide] of slides.entries()) {
  const footer = document.createElement("footer");
  footer.className = "slide-footer";

  for (const [className, text] of [
    ["footer-brand", "LEARN TO CLOUD"],
    ["footer-chapter", slide.dataset.chapter],
    ["footer-pillar", slide.dataset.pillar],
    ["footer-number", `${String(index + 1).padStart(2, "0")} / ${slides.length}`],
  ]) {
    const label = document.createElement("span");
    label.className = className;
    label.textContent = text;
    footer.append(label);
  }

  slide.append(footer);
}

Reveal.initialize({
  width: 1280,
  height: 720,
  margin: 0.03,
  minScale: 0.2,
  maxScale: 1.5,
  hash: true,
  history: true,
  center: false,
  controls: true,
  controlsTutorial: false,
  progress: true,
  transition: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "none" : "fade",
  transitionSpeed: "fast",
  backgroundTransition: "none",
  pdfSeparateFragments: false,
  pdfMaxPagesPerSlide: 1,
  plugins: [RevealNotes],
});
