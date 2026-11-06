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

The photo walls use TanStack Virtual (`@tanstack/vue-virtual` and
`@tanstack/virtual-core`): https://github.com/TanStack/virtual

MIT License

Copyright (c) 2021-present Tanner Linsley

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
