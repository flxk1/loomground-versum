# PDF extraction regression fixtures

- `line-break-regression.pdf` contains `one two`, `HUGE`, and `three four` on separate
  visual lines.
- `single-line-control.pdf` contains the same words on one visual line.

They reproduce the layout case that motivated the original root-level `bug.pdf` and
`ctl.pdf`. The regression test asserts that both remain readable and that the cleaner does
not drop the visually isolated word. The files are intentionally small, synthetic fixtures.
