# Native package test fixture

This is an independently installable source layout used by compiler tests. It is
not a graphics package: the C code only validates scalar/token lifetimes and
writes fixed test payloads. No JPEG codec is linked by the fixture.

`native/expected.jpg` is an original, generated 2×1 RGB image (red and blue
input pixels), created for this repository using libjpeg-turbo's `cjpeg`:

```sh
cjpeg -quality 90 -sample 1x1 -outfile expected.jpg input.ppm
djpeg -outfile decoded.ppm expected.jpg
```

The PPM input is `P6\n2 1\n255\n` followed by bytes `ff 00 00 00 00 ff`. The
fixture image and its generated C byte array in `jpeg_payload.h` are distributed
under this repository's license. Tests compare the complete output with this
JPEG and separately cover a payload containing NUL/non-UTF-8 bytes. An installed
`djpeg` additionally verifies decoding without making any codec a production
compiler dependency.
