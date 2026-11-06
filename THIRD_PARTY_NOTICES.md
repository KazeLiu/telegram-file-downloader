# Third-party components

The collector retains the upstream MIT license in LICENSE.

The Docker image includes the official 7-Zip 26.05 Linux x64 distribution.
7-Zip is licensed under the GNU LGPL, with BSD 3-clause and unRAR restrictions
for some components. Its original license and readme files are retained in
`/opt/7zip` in the image. Copyright (C) Igor Pavlov.

7-Zip website and source code: https://www.7-zip.org/
Official source releases: https://github.com/ip7z/7zip

The web console uses Vue, Nuxt, Tailwind CSS and Motion for Vue (MIT),
FastAPI (MIT), and Uvicorn (BSD-3-Clause).
Local image decoding and thumbnails use Pillow; pip retains its packaged license
notices in the installed distribution. Project and license: https://github.com/python-pillow/Pillow
The visual reference DESIGN.md was generated from the Apple design analysis at
https://getdesign.md/apple/design-md. No Apple logo, proprietary font file or
product image is redistributed.
